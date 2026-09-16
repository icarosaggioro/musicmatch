"""Track Promotion Service.

Follows ADR 0011 and ADR 0012:
- Transfers staged tracks from isolated sessions into the Managed Library.
- Implements 4-namespace canonical taxonomy (Artist Albums, Artist Singles, Various Artists, Collections).
- Enforces strict Collision Invariant (blocks overwrite, retains staged audio).
- Updates physical file tags via mediafile.
- Catalogs promoted tracks into SQLiteTrackRepository with immediate FTS5 searchability.
- Updates session manifest, transitioning to 'RESOLVED' upon full session promotion.
"""

from pathlib import Path
import re
import shutil
from typing import List, Optional, Union

import mediafile

from musicmatch.domain.models import Track
from musicmatch.domain.staging import DownloadSessionManifest, PromotionResult, StagedTrack
from musicmatch.services.downloader import AudioDownloaderService, audio_downloader_service
from musicmatch.services.location import LibraryLocationManager, library_location_manager
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository


def sanitize_filename_component(text: str) -> str:
    """Sanitizes filename/directory string by stripping characters illegal on Windows and POSIX."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00]', "_", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned or not cleaned.strip("_"):
        return "Unknown"
    return cleaned


class TrackPromotionService:
    """Handles promotion of tracks from Staging sessions to the Managed Library."""

    def __init__(
        self,
        downloader_service: Optional[AudioDownloaderService] = None,
        location_manager: Optional[LibraryLocationManager] = None,
        repo: Optional[SQLiteTrackRepository] = None,
    ) -> None:
        self.downloader_service = downloader_service or audio_downloader_service
        self.location_manager = location_manager or library_location_manager
        self._repo = repo

    @property
    def repo(self) -> SQLiteTrackRepository:
        if self._repo is None:
            self._repo = SQLiteTrackRepository()
        return self._repo

    def compute_target_path(
        self,
        track: StagedTrack,
        library_root: Path,
        album: Optional[str] = None,
        artist: Optional[str] = None,
        track_number: Optional[int] = None,
        is_compilation: bool = False,
        collection_name: Optional[str] = None,
    ) -> Path:
        """Computes canonical filesystem destination path based on ADR 0011 taxonomy."""
        artist_name = sanitize_filename_component(artist or track.artist)
        title_name = sanitize_filename_component(track.title)
        ext = track.format.lstrip(".").lower()

        # 1. Custom User Collection: Collections/<Collection>/<Artist> - <Title>.<ext>
        if collection_name:
            col_sanitized = sanitize_filename_component(collection_name)
            dest_dir = library_root / "Collections" / col_sanitized
            filename = f"{artist_name} - {title_name}.{ext}"
            return dest_dir / filename

        # 2. Compilation / Soundtracks: Various Artists/<Album>/<Num:02d> - <Artist> - <Title>.<ext>
        albumartist = track.extended_metadata.get("albumartist") or ""
        if is_compilation or albumartist.lower() in ("various artists", "various"):
            album_name = sanitize_filename_component(album or track.album or "Unknown Compilation")
            dest_dir = library_root / "Various Artists" / album_name
            num_prefix = f"{track_number:02d} - " if track_number else ""
            filename = f"{num_prefix}{artist_name} - {title_name}.{ext}"
            return dest_dir / filename

        # 3. Artist Album: Artists/<Artist>/<Album>/<Artist> - <Title>.<ext>
        effective_album = album or track.album
        if effective_album:
            album_name = sanitize_filename_component(effective_album)
            dest_dir = library_root / "Artists" / artist_name / album_name
            num_prefix = f"{track_number:02d} - " if track_number else ""
            filename = f"{num_prefix}{artist_name} - {title_name}.{ext}"
            return dest_dir / filename

        # 4. Artist Single: Artists/<Artist>/Singles/<Artist> - <Title>.<ext>
        dest_dir = library_root / "Artists" / artist_name / "Singles"
        filename = f"{artist_name} - {title_name}.{ext}"
        return dest_dir / filename

    def promote_track(
        self,
        session_id: str,
        track_id_or_idx: Union[str, int],
        library_root: Optional[Path] = None,
        album: Optional[str] = None,
        artist: Optional[str] = None,
        track_number: Optional[int] = None,
        is_compilation: bool = False,
        collection_name: Optional[str] = None,
    ) -> PromotionResult:
        """Promotes a single staged track to the Managed Library."""
        manifest = self.downloader_service.get_session(session_id)
        if not manifest:
            return PromotionResult(
                track_id=str(track_id_or_idx),
                source_path="",
                status="NOT_FOUND",
                error_message=f"Session '{session_id}' not found.",
            )

        # Locate track in session manifest
        target_track: Optional[StagedTrack] = None
        if isinstance(track_id_or_idx, int):
            idx = track_id_or_idx - 1
            if 0 <= idx < len(manifest.tracks):
                target_track = manifest.tracks[idx]
            else:
                return PromotionResult(
                    track_id=str(track_id_or_idx),
                    source_path="",
                    status="NOT_FOUND",
                    error_message=f"Track index {track_id_or_idx} out of range (total: {len(manifest.tracks)}).",
                )
        else:
            for t in manifest.tracks:
                if t.id == track_id_or_idx:
                    target_track = t
                    break
            if not target_track:
                return PromotionResult(
                    track_id=str(track_id_or_idx),
                    source_path="",
                    status="NOT_FOUND",
                    error_message=f"Track ID '{track_id_or_idx}' not found in session '{session_id}'.",
                )

        if target_track.promoted:
            return PromotionResult(
                track_id=target_track.id,
                source_path=target_track.file_path,
                destination_path=target_track.promoted_to,
                status="ERROR",
                error_message=f"Track '{target_track.title}' has already been promoted.",
            )

        source_file = Path(target_track.file_path)
        if not source_file.exists():
            return PromotionResult(
                track_id=target_track.id,
                source_path=target_track.file_path,
                status="ERROR",
                error_message=f"Source audio file '{source_file}' does not exist on disk.",
            )

        root = library_root or self.location_manager.resolve_library_path()
        target_path = self.compute_target_path(
            track=target_track,
            library_root=root,
            album=album,
            artist=artist,
            track_number=track_number,
            is_compilation=is_compilation,
            collection_name=collection_name,
        )

        # Strict Collision Invariant: do NOT overwrite existing files!
        if target_path.exists():
            return PromotionResult(
                track_id=target_track.id,
                source_path=target_track.file_path,
                destination_path=str(target_path).replace("\\", "/"),
                status="COLLISION",
                error_message=(
                    f"Destination file '{target_path.name}' already exists in library at '{target_path.parent}'. "
                    "Promotion halted without modifying the staged audio file."
                ),
            )

        # Create destination directories and move file
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(source_file), str(target_path))
        except OSError as exc:
            return PromotionResult(
                track_id=target_track.id,
                source_path=target_track.file_path,
                destination_path=str(target_path).replace("\\", "/"),
                status="ERROR",
                error_message=f"Failed to move file to destination: {exc}",
            )

        # Update physical audio tags
        final_artist = artist or target_track.artist
        final_title = target_track.title
        final_album = album or target_track.album or ("Singles" if not collection_name and not is_compilation else "")
        try:
            mf = mediafile.MediaFile(str(target_path))
            mf.artist = final_artist
            mf.title = final_title
            if final_album:
                mf.album = final_album
            if track_number is not None:
                mf.track = track_number
            mf.save()
        except Exception:
            pass

        # Index into SQLite catalog
        stat = target_path.stat()
        track_entity = Track(
            id=Track.generate_id(str(target_path)),
            title=final_title,
            artist=final_artist,
            album=final_album,
            genre="Unknown",
            duration_seconds=target_track.duration_seconds,
            bitrate_kbps=320,
            bpm=120.0,
            file_path=str(target_path.resolve()).replace("\\", "/"),
            file_mtime=stat.st_mtime,
            file_size=stat.st_size,
            status="AVAILABLE",
            track_number=track_number,
        )
        self.repo.insert_batch([track_entity])

        # Update session manifest
        dest_str = str(target_path.resolve()).replace("\\", "/")
        target_track.promoted = True
        target_track.promoted_to = dest_str

        # If all tracks are promoted, resolve session
        if all(t.promoted for t in manifest.tracks):
            manifest.status = "RESOLVED"

        self.downloader_service._save_manifest(manifest)

        return PromotionResult(
            track_id=target_track.id,
            source_path=target_track.file_path,
            destination_path=dest_str,
            status="PROMOTED",
        )

    def promote_session(
        self,
        session_id: str,
        library_root: Optional[Path] = None,
        album: Optional[str] = None,
        artist: Optional[str] = None,
        is_compilation: bool = False,
        collection_name: Optional[str] = None,
    ) -> List[PromotionResult]:
        """Promotes all unpromoted tracks in a given session."""
        manifest = self.downloader_service.get_session(session_id)
        if not manifest:
            return [
                PromotionResult(
                    track_id="",
                    source_path="",
                    status="NOT_FOUND",
                    error_message=f"Session '{session_id}' not found.",
                )
            ]

        results: List[PromotionResult] = []
        for track in manifest.tracks:
            if not track.promoted:
                res = self.promote_track(
                    session_id=session_id,
                    track_id_or_idx=track.id,
                    library_root=library_root,
                    album=album,
                    artist=artist,
                    is_compilation=is_compilation,
                    collection_name=collection_name,
                )
                results.append(res)
        return results


# Global singleton instance
track_promotion_service = TrackPromotionService()
