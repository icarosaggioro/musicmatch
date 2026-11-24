"""Playlist Domain Models (ADR 0018).

A playlist is a named, ordered list of library tracks (duplicates allowed), kept in the
catalog database. Names are unique regardless of case and accents ('Café' == 'cafe'), and
commands find a playlist by its name or by a unique prefix of it.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from musicmatch.domain.models import Track
from musicmatch.domain.text import fold_text

MAX_PLAYLIST_NAME_LENGTH = 100
PLAYLIST_FILE_EXTENSIONS = (".m3u8", ".m3u")


class InvalidPlaylistName(ValueError):
    """The name cannot be used for a playlist (empty, too long, control characters, '--')."""


def normalize_playlist_name(name: str) -> str:
    """Trims and validates a playlist name; raises InvalidPlaylistName."""
    cleaned = " ".join((name or "").split())  # collapse runs of whitespace, strip ends
    if not cleaned:
        raise InvalidPlaylistName("O nome da playlist não pode ser vazio.")
    if len(cleaned) > MAX_PLAYLIST_NAME_LENGTH:
        raise InvalidPlaylistName(f"O nome da playlist pode ter no máximo {MAX_PLAYLIST_NAME_LENGTH} caracteres.")
    if cleaned.startswith("--"):
        raise InvalidPlaylistName("O nome da playlist não pode começar com '--' (reservado para opções).")
    if any(ord(c) < 32 for c in cleaned):
        raise InvalidPlaylistName("O nome da playlist não pode conter caracteres de controle.")
    return cleaned


def playlist_name_key(name: str) -> str:
    """Identity of a playlist name: case- and accent-insensitive."""
    return fold_text(" ".join((name or "").split()))


class PlaylistSummary(BaseModel):
    """A playlist as listed by /playlist (without its tracks)."""

    id: int
    name: str
    track_count: int = Field(default=0, ge=0, description="Entries (a track queued twice counts twice)")
    duration_seconds: float = Field(default=0.0, ge=0)
    created_at: str = ""
    updated_at: str = ""


class Playlist(PlaylistSummary):
    """A playlist with its entries in order."""

    tracks: List[Track] = Field(default_factory=list)


class PlaylistImportResult(BaseModel):
    """Outcome of /playlist-import: how each entry of the M3U file was resolved."""

    source_path: str
    playlist: Optional[PlaylistSummary] = None
    total_entries: int = 0
    matched_by_path: int = 0
    matched_by_tags: int = Field(default=0, description="Path not in the catalog; matched by '#EXTINF' artist/title/duration")
    not_in_catalog: List[str] = Field(default_factory=list, description="Files that exist on disk but were never scanned")
    missing_files: List[str] = Field(default_factory=list, description="Files not found on disk nor in the catalog")
    remote_entries: List[str] = Field(default_factory=list, description="URLs (streams), not supported")

    @property
    def matched(self) -> int:
        return self.matched_by_path + self.matched_by_tags

    @property
    def unmatched(self) -> int:
        return len(self.not_in_catalog) + len(self.missing_files) + len(self.remote_entries)


class PlaylistExportResult(BaseModel):
    """Outcome of /playlist-export."""

    path: str
    entries: int
    relative_paths: bool
    absolute_fallbacks: int = Field(default=0, description="--relative entries on another drive, written as absolute")
