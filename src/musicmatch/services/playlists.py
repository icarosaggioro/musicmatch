"""Playlist Service (ADR 0018): saved playlists and M3U/M3U8 import and export.

- Playlists are named, ordered lists of library tracks (duplicates allowed). They are filled
  from the play queue (/playlist-save) and loaded back into it (/playlist-load).
- Import reads M3U and extended M3U (#EXTINF) files written by other players. Each entry is
  resolved to a catalog track by its file path (the canonical path hash, ADR 0009), or, when
  the file is not in the catalog under that path (another machine, another drive letter), by the
  '#EXTINF' artist, title and duration. Files that exist but were never scanned are reported
  (with the folders to /scan) instead of being indexed behind the user's back.
- Export writes extended M3U (UTF-8), with absolute paths or paths relative to the playlist file.
"""

import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from musicmatch.domain.issues import IssueKind
from musicmatch.domain.models import Track
from musicmatch.domain.playlist import (
    PLAYLIST_FILE_EXTENSIONS,
    Playlist,
    PlaylistExportResult,
    PlaylistImportResult,
    PlaylistSummary,
    playlist_name_key,
)
from musicmatch.services.issues import report_issue
from musicmatch.services.promotion import sanitize_filename_component
from musicmatch.storage.playlist_repo import SQLitePlaylistRepository
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository

EXPORT_FOLDER_NAME = "Playlists"
_TAG_MATCH_DURATION_TOLERANCE = 3.0  # seconds between '#EXTINF' and catalog durations
_URL_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


class PlaylistFileError(ValueError):
    """The playlist file cannot be read or written (missing, unsupported format, I/O error)."""


@dataclass(frozen=True)
class M3UEntry:
    location: str  # absolute local path, or the URL of a remote entry
    remote: bool = False
    duration: Optional[float] = None  # from '#EXTINF', when present and positive
    artist: Optional[str] = None
    title: Optional[str] = None


# ----------------------------------------------------------------------
# M3U format
# ----------------------------------------------------------------------


def _decode(data: bytes, suffix: str) -> str:
    """.m3u8 is UTF-8 by definition; classic .m3u is often the Windows ANSI code page."""
    if data.startswith(b"\xef\xbb\xbf") or suffix == ".m3u8":
        return data.decode("utf-8-sig", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _local_path(raw: str, base_dir: Path) -> str:
    if raw.lower().startswith("file:"):
        parsed = urllib.parse.urlparse(raw)
        path = urllib.request.url2pathname(parsed.path)
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            path = f"//{parsed.netloc}{path}"  # UNC share
    else:
        path = raw
    if os.sep == "/":
        path = path.replace("\\", "/")  # playlists written on Windows
    if not os.path.isabs(path):
        path = os.path.join(str(base_dir), path)
    return os.path.normpath(path)


def _parse_extinf(line: str) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """'#EXTINF:215,Artist - Title' -> (215.0, 'Artist', 'Title'); attributes before the comma are ignored."""
    head, _, display = line[len("#EXTINF:"):].partition(",")
    duration: Optional[float] = None
    number = re.match(r"\s*(-?\d+(?:\.\d+)?)", head)
    if number and float(number.group(1)) > 0:
        duration = float(number.group(1))
    artist, sep, title = display.strip().partition(" - ")
    if not sep or not artist.strip() or not title.strip():
        return duration, None, None
    return duration, artist.strip(), title.strip()


def parse_m3u(path: Path) -> List[M3UEntry]:
    """Entries of an M3U/M3U8 file in order (relative paths resolved against the file's folder)."""
    try:
        text = _decode(path.read_bytes(), path.suffix.lower())
    except OSError as exc:
        raise PlaylistFileError(f"Não foi possível ler '{path}': {exc}") from exc
    entries: List[M3UEntry] = []
    info: Tuple[Optional[float], Optional[str], Optional[str]] = (None, None, None)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.upper().startswith("#EXTINF:"):
                info = _parse_extinf(line)
            continue
        duration, artist, title = info
        info = (None, None, None)
        if _URL_SCHEME.match(line) and not line.lower().startswith("file:"):
            entries.append(M3UEntry(location=line, remote=True))
        else:
            entries.append(M3UEntry(_local_path(line, path.parent), duration=duration, artist=artist, title=title))
    return entries


def format_m3u(name: str, tracks: Sequence[Track], path_for: Callable[[Track], str]) -> str:
    lines = ["#EXTM3U", f"#PLAYLIST:{name}"]
    for track in tracks:
        # Whole seconds as in classic EXTM3U; -1 = unknown (a positive length never rounds down to 0).
        seconds = max(1, int(round(track.duration_seconds))) if track.duration_seconds and track.duration_seconds > 0 else -1
        lines.append(f"#EXTINF:{seconds},{track.artist} - {track.title}")
        lines.append(path_for(track))
    return "\n".join(lines) + "\n"


def playlist_file_stem(name: str) -> str:
    """File name for a playlist: characters illegal on Windows/POSIX replaced, reserved device names avoided."""
    stem = sanitize_filename_component(name)
    return f"_{stem}" if stem.split(".")[0].upper() in _WINDOWS_RESERVED else stem


# ----------------------------------------------------------------------
# Service
# ----------------------------------------------------------------------


class PlaylistService:
    def __init__(self, tracks: SQLiteTrackRepository, library_root: Optional[Callable[[], Path]] = None) -> None:
        self.tracks = tracks
        self.repo = SQLitePlaylistRepository(tracks.conn)
        self._library_root = library_root

    # -- lookup ----------------------------------------------------------------
    def list(self) -> List[PlaylistSummary]:
        return self.repo.list_summaries()

    def get(self, playlist_id: int) -> Optional[Playlist]:
        return self.repo.get(playlist_id)

    def find_exact(self, name: str) -> Optional[PlaylistSummary]:
        return self.repo.find_by_name(name)

    def resolve(self, ref: str) -> Tuple[Optional[PlaylistSummary], List[PlaylistSummary]]:
        """The playlist named `ref` (case/accent-insensitive), else the only one starting with it.
        Returns (match, candidates): no match with several candidates means the prefix is ambiguous."""
        exact = self.repo.find_by_name(ref)
        if exact is not None:
            return exact, [exact]
        candidates = self.repo.find_by_name_prefix(ref, limit=6)
        return (candidates[0] if len(candidates) == 1 else None), candidates

    # -- changes ---------------------------------------------------------------
    def save(self, name: str, tracks: Sequence[Track], existing: Optional[PlaylistSummary] = None) -> PlaylistSummary:
        """Creates `name` with the tracks, or replaces the entries of `existing` (its name is kept)."""
        ids = [t.id for t in tracks]
        if existing is not None:
            return self.repo.replace_entries(existing.id, ids)
        return self.repo.create(name, ids)

    def rename(self, playlist: PlaylistSummary, new_name: str) -> PlaylistSummary:
        return self.repo.rename(playlist.id, new_name)

    def delete(self, playlist: PlaylistSummary) -> bool:
        return self.repo.delete(playlist.id)

    def remove_track(self, playlist: PlaylistSummary, track_id: str) -> int:
        """Removes every occurrence of a track from the playlist ('/playlist-remove <name> <id>')."""
        return self.repo.remove_track(playlist.id, track_id)

    def remove_at(self, playlist: PlaylistSummary, position: int) -> Optional[Track]:
        """Removes the single entry at a 1-based position ('/playlist-remove <name> #<pos>');
        returns the removed track, or None when there is no such position."""
        current = self.repo.get(playlist.id)
        if current is None or not 1 <= position <= len(current.tracks):
            return None
        return current.tracks[position - 1] if self.repo.remove_at(playlist.id, position - 1) else None

    def other_playlists_with(self, track_ids: Sequence[str], playlist: PlaylistSummary) -> List[str]:
        return self.repo.playlists_containing(track_ids, exclude_id=playlist.id)

    def delete_with_tracks(self, playlist: Playlist, maintenance) -> Tuple[int, List[str], bool]:
        """Moves the playlist's track files to the Recycle Bin and unindexes them (ADR 0013), then
        deletes the playlist. If some files could not be moved, the playlist is kept holding
        exactly those tracks, so the operation can be retried. Returns (deleted, errors, playlist_deleted)."""
        ids = list(dict.fromkeys(t.id for t in playlist.tracks))
        deleted, errors = maintenance.delete_tracks_to_trash(ids) if ids else (0, [])
        remaining = self.repo.get_summary(playlist.id)
        if remaining is not None and remaining.track_count == 0:
            self.repo.delete(playlist.id)
            return deleted, errors, True
        return deleted, errors, False

    # -- import ----------------------------------------------------------------
    def import_m3u(self, source: Path, name: str, existing: Optional[PlaylistSummary] = None) -> PlaylistImportResult:
        """Resolves every entry of an M3U file and saves the matched tracks as playlist `name`
        (replacing `existing`). Nothing is saved when no entry matches."""
        source = Path(source)
        if source.suffix.lower() not in PLAYLIST_FILE_EXTENSIONS:
            raise PlaylistFileError(f"Formato não suportado: '{source.suffix or source.name}'. Use .m3u ou .m3u8.")
        if not source.is_file():
            raise PlaylistFileError(f"Arquivo de playlist não encontrado: '{source}'.")
        entries = parse_m3u(source)
        result = PlaylistImportResult(source_path=str(source), total_entries=len(entries))
        matched: List[Track] = []
        for entry in entries:
            if entry.remote:
                result.remote_entries.append(entry.location)
                continue
            track = self.tracks.get_track(Track.generate_id(entry.location))
            if track is not None:
                result.matched_by_path += 1
                matched.append(track)
                continue
            track = self._match_by_tags(entry)
            if track is not None:
                result.matched_by_tags += 1
                matched.append(track)
            elif os.path.isfile(entry.location):
                result.not_in_catalog.append(entry.location)
            else:
                result.missing_files.append(entry.location)
        if matched:
            result.playlist = self.save(name, matched, existing)
        if result.unmatched:
            self._report_incomplete_import(result, name)
        return result

    @staticmethod
    def _report_incomplete_import(result: PlaylistImportResult, name: str) -> None:
        """One issue per imported file (not per entry), listing what could not be resolved."""
        created = (f"playlist '{result.playlist.name}' criada com {result.matched}"
                   if result.playlist else "nenhuma playlist criada")
        details = {}
        if result.not_in_catalog:
            details["fora do catálogo (rode /scan nas pastas)"] = result.not_in_catalog
        if result.missing_files:
            details["não encontrados"] = result.missing_files
        if result.remote_entries:
            details["URLs ignoradas"] = result.remote_entries
        report_issue(
            IssueKind.PLAYLIST_IMPORT_INCOMPLETE, result.source_path,
            f"{result.unmatched} de {result.total_entries} entrada(s) não resolvida(s); {created}.",
            subject_type="playlist_file", subject_label=f"{Path(result.source_path).name} → '{name}'",
            source="playlist", details=details,
        )

    # -- checks ------------------------------------------------------------------
    def report_empty(self, playlist: PlaylistSummary) -> None:
        report_issue(
            IssueKind.PLAYLIST_EMPTY, f"playlist:{playlist.id}", "A playlist não tem faixas.",
            subject_type="playlist", subject_label=playlist.name, source="playlist",
            details={"sugestão": f"Preencha a fila e use /playlist-save {playlist.name}, ou /playlist-delete {playlist.name}."},
        )

    def report_empty_playlists(self) -> int:
        """Startup check: playlists can become empty silently when their tracks leave the Library."""
        empty = [p for p in self.repo.list_summaries() if p.track_count == 0]
        for playlist in empty:
            self.report_empty(playlist)
        return len(empty)

    def _match_by_tags(self, entry: M3UEntry) -> Optional[Track]:
        """Same artist and title (case-insensitive) and, when '#EXTINF' has one, a duration within 3 s.
        Among several copies, the available one with the highest bitrate wins."""
        if not entry.artist or not entry.title:
            return None
        candidates = self.tracks.find_tracks_by_artist_title(entry.artist, entry.title)
        if entry.duration:
            candidates = [t for t in candidates
                          if abs((t.duration_seconds or 0.0) - entry.duration) <= _TAG_MATCH_DURATION_TOLERANCE]
        if not candidates:
            return None
        return max(candidates, key=lambda t: (t.status == "AVAILABLE" and os.path.isfile(t.file_path), t.bitrate_kbps))

    # -- export ----------------------------------------------------------------
    def export_target(self, playlist: PlaylistSummary, destination: Optional[str] = None) -> Path:
        """Where /playlist-export writes: a .m3u8/.m3u file, or '<name>.m3u8' inside a folder
        (default: the 'Playlists' folder of the Managed Library Directory)."""
        file_name = f"{playlist_file_stem(playlist.name)}.m3u8"
        if not destination:
            root = self._library_root() if self._library_root else _managed_library_root()
            return Path(root) / EXPORT_FOLDER_NAME / file_name
        target = Path(os.path.expanduser(destination))
        suffix = target.suffix.lower()
        if suffix in PLAYLIST_FILE_EXTENSIONS:
            return target.resolve()
        if target.is_dir() or not suffix or destination.endswith(("/", "\\")):
            return (target / file_name).resolve()
        raise PlaylistFileError(f"Extensão não suportada: '{target.suffix}'. Use .m3u8 ou .m3u, ou informe uma pasta.")

    def export_m3u(self, playlist: Playlist, target: Path, relative: bool = False) -> PlaylistExportResult:
        """Writes the playlist as extended M3U, UTF-8 (atomically: a temp file then a rename)."""
        target = Path(target)
        fallbacks = 0

        def path_for(track: Track) -> str:
            nonlocal fallbacks
            if relative:
                try:
                    return os.path.relpath(track.file_path, start=str(target.parent))
                except ValueError:  # another drive (Windows): no relative path exists
                    fallbacks += 1
            return track.file_path

        content = format_m3u(playlist.name, playlist.tracks, path_for)
        temp = target.with_name(target.name + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(content, encoding="utf-8")
            os.replace(temp, target)
        except OSError as exc:
            try:
                temp.unlink()
            except OSError:
                pass
            raise PlaylistFileError(f"Não foi possível gravar '{target}': {exc}") from exc
        return PlaylistExportResult(path=str(target), entries=len(playlist.tracks), relative_paths=relative,
                                    absolute_fallbacks=fallbacks)


def _managed_library_root() -> Path:
    from musicmatch.services.location import library_location_manager

    return library_location_manager.resolve_library_path()
