"""Library Maintenance Service.

Implements ADR 0009 and ADR 0013:
- Diagnostic library health audit (missing files, untagged tracks, degraded bitrates, duplicates).
- Quality-first duplicate detection recommending preservation of highest-fidelity bitstreams.
- Non-destructive unindexing (/unindex) removing catalog metadata while keeping files intact.
- Safe physical file deletion (/delete) routing audio files to the host OS Recycle Bin via send2trash.
- Permanent purging of missing records (/prune).
- Physical tag updating via mediafile (/retag).
- External directory consolidation into Managed Library taxonomy (/library import).
- In-library file reorganization matching updated metadata (/library reorganize).
"""

import os
from pathlib import Path
import shutil
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

import mediafile
import send2trash

from musicmatch.domain.maintenance import (
    DuplicateGroup,
    ImportResult,
    LibraryAuditReport,
    ReorganizeResult,
)
from musicmatch.domain.models import Track
from musicmatch.services.location import LibraryLocationManager, library_location_manager
from musicmatch.services.promotion import sanitize_filename_component
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository


class LibraryMaintenanceService:
    """Orchestrates library health diagnostics, safe deletion, and catalog maintenance."""

    def __init__(
        self,
        repository: Optional[SQLiteTrackRepository] = None,
        location_manager: Optional[LibraryLocationManager] = None,
    ) -> None:
        self.repo = repository or SQLiteTrackRepository()
        self.location_manager = location_manager or library_location_manager

    def audit_library(self) -> LibraryAuditReport:
        """Calculates comprehensive health and integrity metrics across all registered tracks."""
        tracks = self.repo.get_all_tracks()
        total_tracks = len(tracks)

        missing_tracks: List[Track] = []
        untagged_count = 0
        low_bitrate_count = 0

        for t in tracks:
            # Check physical file existence or soft-deleted flag
            if t.status == "MISSING" or not os.path.exists(t.file_path):
                missing_tracks.append(t)

            # Untagged identification (missing or placeholder artist/album)
            artist_clean = (t.artist or "").strip().lower()
            album_clean = (t.album or "").strip().lower()
            if not artist_clean or artist_clean in ("unknown artist", "unknown", "desconhecido"):
                untagged_count += 1
            elif not album_clean or album_clean in ("unknown album", "unknown", "<desconhecido>"):
                untagged_count += 1

            # Degraded bitrate detection (< 128 kbps)
            if t.bitrate_kbps and t.bitrate_kbps < 128:
                low_bitrate_count += 1

        duplicates = self.find_duplicates()
        missing_count = len(missing_tracks)
        available_count = total_tracks - missing_count

        return LibraryAuditReport(
            total_tracks=total_tracks,
            available_tracks=max(0, available_count),
            missing_tracks=missing_count,
            untagged_tracks=untagged_count,
            low_bitrate_tracks=low_bitrate_count,
            duplicate_groups_count=len(duplicates),
            missing_sample=missing_tracks[:5],
        )

    def find_duplicates(self) -> List[DuplicateGroup]:
        """Identifies groups of duplicate tracks using normalized semantic keys and quality heuristics."""
        tracks = self.repo.get_all_tracks()
        grouped: Dict[str, List[Track]] = {}

        for t in tracks:
            norm_artist = re_normalize(t.artist)
            norm_title = re_normalize(t.title)
            if not norm_artist or not norm_title:
                continue
            key = f"{norm_artist}:{norm_title}"
            grouped.setdefault(key, []).append(t)

        duplicate_groups: List[DuplicateGroup] = []
        for key, group_tracks in grouped.items():
            if len(group_tracks) < 2:
                continue

            # Quality heuristic: prefer AVAILABLE tracks, then highest bitrate, then longer duration
            def sort_key(t: Track) -> Tuple[int, int, float]:
                avail = 1 if t.status == "AVAILABLE" and os.path.exists(t.file_path) else 0
                bitrate = t.bitrate_kbps or 0
                dur = t.duration_seconds or 0.0
                return (avail, bitrate, dur)

            sorted_candidates = sorted(group_tracks, key=sort_key, reverse=True)
            recommended = sorted_candidates[0]
            other = sorted_candidates[1]

            reason = (
                f"Highest fidelity bitstream ({recommended.bitrate_kbps} kbps vs {other.bitrate_kbps} kbps)"
                if recommended.bitrate_kbps != other.bitrate_kbps
                else f"Accessible file on disk with {recommended.bitrate_kbps} kbps"
            )

            duplicate_groups.append(
                DuplicateGroup(
                    signature=key,
                    tracks=group_tracks,
                    recommended_track_id=recommended.id,
                    recommendation_reason=reason,
                )
            )

        return duplicate_groups

    def unindex_tracks(self, track_ids: List[str]) -> int:
        """Purges track metadata from SQLite and FTS5 without touching physical files on disk."""
        unindexed = 0
        for tid in track_ids:
            if self.repo.delete_track(tid):
                unindexed += 1
        return unindexed

    def delete_tracks_to_trash(self, track_ids: List[str]) -> Tuple[int, List[str]]:
        """Safely moves audio files to the host OS Recycle Bin via send2trash and cascades database removal."""
        deleted_count = 0
        errors: List[str] = []

        for tid in track_ids:
            track = self.repo.get_track(tid)
            if not track:
                continue

            file_path = track.file_path
            # If the physical file exists on disk, move to OS Recycle Bin
            if os.path.exists(file_path):
                try:
                    send2trash.send2trash(file_path)
                except Exception as e:
                    errors.append(f"Failed to move '{file_path}' to Recycle Bin: {e}")
                    continue

            # Cascade database removal
            self.repo.delete_track(tid)
            deleted_count += 1

        return deleted_count, errors

    def purge_missing_tracks(self) -> int:
        """Permanently purges all tracks currently marked as 'MISSING' from the catalog."""
        tracks = self.repo.get_all_tracks()
        missing_ids = [t.id for t in tracks if t.status == "MISSING"]
        return self.unindex_tracks(missing_ids)

    def retag_track(self, track_id: str, updates: Dict[str, Any]) -> Track:
        """Rewrites ID3/Vorbis tags directly inside audio files via mediafile and synchronizes SQLite."""
        track = self.repo.get_track(track_id)
        if not track:
            raise ValueError(f"Track with ID '{track_id}' not found.")

        if not os.path.exists(track.file_path):
            raise FileNotFoundError(f"Audio file at '{track.file_path}' is missing from local disk.")

        mf = mediafile.MediaFile(track.file_path)
        if "artist" in updates and updates["artist"]:
            mf.artist = updates["artist"]
            track.artist = updates["artist"]
        if "title" in updates and updates["title"]:
            mf.title = updates["title"]
            track.title = updates["title"]
        if "album" in updates and updates["album"]:
            mf.album = updates["album"]
            track.album = updates["album"]
        if "genre" in updates and updates["genre"]:
            mf.genre = updates["genre"]
            track.genre = updates["genre"]

        mf.save()

        # Update stat cache values
        stat = os.stat(track.file_path)
        track.file_mtime = stat.st_mtime
        track.file_size = stat.st_size

        self.repo.update_track(track)
        return track

    def import_external_library(
        self,
        source_path: Path,
        mode: Literal["copy", "move"] = "copy",
        managed_root: Optional[Path] = None,
    ) -> ImportResult:
        """Consolidates an external music directory into the Managed Library taxonomy (ADR 0013)."""
        library_root = managed_root or self.location_manager.resolve_library_path()
        source = Path(source_path).resolve()

        if not source.exists() or not source.is_dir():
            return ImportResult(
                status="error",
                source_path=str(source),
                target_root=str(library_root),
                mode=mode,
                total_files=0,
                imported_count=0,
                skipped_count=0,
                locked_files=[],
                errors=[f"Source directory '{source}' does not exist."],
            )

        supported_exts = {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".wav", ".wma", ".aiff", ".opus"}
        audio_files: List[Path] = []
        for root, _, files in os.walk(source):
            for f in files:
                if os.path.splitext(f)[1].lower() in supported_exts:
                    audio_files.append(Path(root) / f)

        imported_count = 0
        skipped_count = 0
        locked_files: List[str] = []
        errors: List[str] = []

        for p in audio_files:
            try:
                # Per-Item Pre-Flight Isolation in move mode: check read, write, source deletion
                if mode == "move":
                    if not (os.access(p, os.R_OK) and os.access(p, os.W_OK)):
                        locked_files.append(str(p))
                        continue

                mf = mediafile.MediaFile(str(p.resolve()))
                artist = sanitize_filename_component((mf.artist or "").strip() or "Unknown Artist")
                album = sanitize_filename_component((mf.album or "").strip() or "Unknown Album")
                title = sanitize_filename_component((mf.title or "").strip() or p.stem)
                ext = p.suffix.lower()

                dest_dir = library_root / "Artists" / artist / album
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_file = dest_dir / f"{artist} - {title}{ext}"

                # Collision check
                if dest_file.exists():
                    skipped_count += 1
                    continue

                if mode == "move":
                    shutil.move(str(p), str(dest_file))
                else:
                    shutil.copy2(str(p), str(dest_file))

                # Index in catalog
                stat = dest_file.stat()
                track = Track(
                    id=Track.generate_id(str(dest_file)),
                    title=(mf.title or "").strip() or p.stem,
                    artist=(mf.artist or "").strip() or "Unknown Artist",
                    album=(mf.album or "").strip() or "Unknown Album",
                    genre=(mf.genre or "").strip() or "Unknown Genre",
                    duration_seconds=float(mf.length or 0.0),
                    bitrate_kbps=int(mf.bitrate / 1000) if (mf.bitrate and mf.bitrate > 0) else 320,
                    bpm=float(mf.bpm) if (mf.bpm and float(mf.bpm) > 0) else 120.0,
                    file_path=str(dest_file.resolve()).replace("\\", "/"),
                    file_mtime=stat.st_mtime,
                    file_size=stat.st_size,
                    status="AVAILABLE",
                    year=int(mf.year) if (mf.year and str(mf.year).isdigit()) else None,
                    track_number=int(mf.track) if (mf.track and str(mf.track).isdigit()) else None,
                )
                self.repo.insert_track(track)
                imported_count += 1

            except Exception as e:
                errors.append(f"Failed to process '{p}': {e}")

        status = "success" if not errors and not locked_files else "partial"
        return ImportResult(
            status=status,
            source_path=str(source),
            target_root=str(library_root),
            mode=mode,
            total_files=len(audio_files),
            imported_count=imported_count,
            skipped_count=skipped_count,
            locked_files=locked_files,
            errors=errors,
        )

    def reorganize_library(self, managed_root: Optional[Path] = None) -> ReorganizeResult:
        """Realigns files inside Managed Library to canonical folder taxonomy matching updated tags."""
        library_root = managed_root or self.location_manager.resolve_library_path()
        tracks = self.repo.get_tracks_under_path(str(library_root))

        total_evaluated = len(tracks)
        realigned_count = 0
        skipped_count = 0
        errors: List[str] = []

        for track in tracks:
            p = Path(track.file_path)
            if not p.exists():
                skipped_count += 1
                continue

            artist = sanitize_filename_component(track.artist or "Unknown Artist")
            album = sanitize_filename_component(track.album or "Unknown Album")
            title = sanitize_filename_component(track.title or p.stem)
            ext = p.suffix.lower()

            canonical_dir = library_root / "Artists" / artist / album
            canonical_path = canonical_dir / f"{artist} - {title}{ext}"

            if p.resolve() == canonical_path.resolve():
                skipped_count += 1
                continue

            try:
                canonical_dir.mkdir(parents=True, exist_ok=True)
                if canonical_path.exists():
                    skipped_count += 1
                    continue

                shutil.move(str(p), str(canonical_path))
                old_id = track.id
                track.file_path = str(canonical_path.resolve()).replace("\\", "/"),
                track.id = Track.generate_id(str(canonical_path))
                stat = canonical_path.stat()
                track.file_mtime = stat.st_mtime
                track.file_size = stat.st_size

                # Re-index
                self.repo.delete_track(old_id)
                self.repo.insert_track(track)
                realigned_count += 1
            except Exception as e:
                errors.append(f"Error relocating '{p}': {e}")

        status = "success" if not errors else "partial"
        return ReorganizeResult(
            status=status,
            total_evaluated=total_evaluated,
            realigned_count=realigned_count,
            skipped_count=skipped_count,
            errors=errors,
        )


def re_normalize(s: Optional[str]) -> str:
    """Normalizes a string for fuzzy identity comparison."""
    if not s:
        return ""
    import unicodedata
    import re
    nfkd = unicodedata.normalize("NFKD", s)
    no_diacritics = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r"[^a-zA-Z0-9]+", "", no_diacritics).lower()


# Default singleton instance
library_maintenance_service = LibraryMaintenanceService()
