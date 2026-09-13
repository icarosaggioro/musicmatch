"""Audio Downloader Service using yt-dlp.

Follows ADR 0010, ADR 0011, and ADR 0012:
- Safe options (blocks SSRF, live streams, duration limits, DoS).
- Two-stage staging isolation with session.json manifests.
- Native bitstream preservation (or optional MP3 conversion).
- Atomic cleanup of partial artifacts on cancellation or error.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

import mediafile
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, match_filter_func

from musicmatch.config import settings
from musicmatch.domain.staging import DownloadSessionManifest, StagedTrack
from musicmatch.services.sanitizer import metadata_sanitizer


class AudioDownloaderService:
    """Orchestrates web audio search, safe downloading, and staging sessions."""

    def __init__(self, staging_dir: Optional[Path] = None) -> None:
        self.staging_dir = (staging_dir or Path(settings.STAGING_DIR)).resolve()
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def _generate_session_id(self) -> str:
        """Generates a timestamped unique session ID."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        short_id = uuid.uuid4().hex[:6]
        return f"session_{ts}_{short_id}"

    def create_session(self, query_or_url: str) -> DownloadSessionManifest:
        """Creates a new staging session directory with an initial manifest."""
        session_id = self._generate_session_id()
        session_dir = self.staging_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        manifest = DownloadSessionManifest(
            session_id=session_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            query_or_url=query_or_url,
            status="ACTIVE",
            tracks=[],
        )
        self._save_manifest(manifest)
        return manifest

    def _get_manifest_path(self, session_id: str) -> Path:
        return self.staging_dir / session_id / "session.json"

    def _save_manifest(self, manifest: DownloadSessionManifest) -> None:
        path = self._get_manifest_path(manifest.session_id)
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    def get_session(self, session_id: str) -> Optional[DownloadSessionManifest]:
        """Loads session manifest from disk."""
        path = self._get_manifest_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return DownloadSessionManifest.model_validate(data)
        except Exception:
            return None

    def list_active_sessions(self) -> List[DownloadSessionManifest]:
        """Scans staging directory and returns all manifests with status 'ACTIVE'."""
        active: List[DownloadSessionManifest] = []
        if not self.staging_dir.exists():
            return active

        for item in self.staging_dir.iterdir():
            if item.is_dir() and (item / "session.json").exists():
                manifest = self.get_session(item.name)
                if manifest and manifest.status == "ACTIVE":
                    active.append(manifest)
        return active

    def discard_session(self, session_id: str) -> bool:
        """Purges a session folder and all unpromoted audio files."""
        session_dir = self.staging_dir / session_id
        if session_dir.exists() and session_dir.is_dir():
            shutil.rmtree(session_dir, ignore_errors=True)
            return True
        return False

    def atomic_cleanup(self, session_id: str) -> None:
        """Purges any incomplete partial artifacts (.part, .ytdl) in the session folder."""
        session_dir = self.staging_dir / session_id
        if not session_dir.exists():
            return
        for file in session_dir.iterdir():
            if file.is_file() and file.suffix.lower() in (".part", ".ytdl", ".temp"):
                try:
                    file.unlink()
                except OSError:
                    pass

    def get_safe_ydl_options(
        self,
        session_dir: Path,
        format_preference: str = "native",
        progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
        is_playlist: bool = False,
    ) -> Dict[str, Any]:
        """Builds hardened YoutubeDL options (ADR 0010 & ADR 0011)."""
        max_duration = settings.DOWNLOAD_MAX_DURATION_SECONDS
        max_playlist = settings.DOWNLOAD_PLAYLIST_MAX_TRACKS

        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "enable_file_urls": False,
            "socket_timeout": 15,
            "noplaylist": not is_playlist,
            "max_downloads": max_playlist if is_playlist else 1,
            "max_filesize": 250 * 1024 * 1024,  # 250 MB
            "match_filter": match_filter_func(f"!is_live & duration <= {max_duration}"),
            "outtmpl": str(session_dir / "%(id)s.%(ext)s"),
            "windowsfilenames": True,
        }

        if progress_hook:
            opts["progress_hooks"] = [progress_hook]

        if format_preference == "mp3":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }
            ]
        else:
            # Native bitstream preservation: best m4a/opus container without lossy transcoding
            opts["format"] = "bestaudio[ext=m4a]/bestaudio[ext=opus]/bestaudio/best"

        return opts

    def search_candidates(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Queries YouTube without downloading, returning clean candidate metadata."""
        search_query = f"ytsearch{max_results}:{query}"
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
            "enable_file_urls": False,
            "socket_timeout": 10,
        }

        candidates: List[Dict[str, Any]] = []
        with YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(search_query, download=False)
                entries = info.get("entries", []) if info else []
                for entry in entries:
                    if not entry:
                        continue
                    video_id = entry.get("id") or ""
                    candidates.append(
                        {
                            "id": video_id,
                            "title": entry.get("title", "Unknown Title"),
                            "channel": entry.get("channel") or entry.get("uploader") or "Unknown Channel",
                            "duration": float(entry.get("duration") or 0.0),
                            "view_count": int(entry.get("view_count") or 0),
                            "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else entry.get("url", ""),
                        }
                    )
            except Exception as e:
                # Return empty list if search fails or network is offline
                return []

        return candidates

    def download_track(
        self,
        url: str,
        session_id: str,
        format_preference: str = "native",
        progress_hook: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> StagedTrack:
        """Downloads audio track to session staging directory, sanitizes metadata, and tags file."""
        session_dir = self.staging_dir / session_id
        if not session_dir.exists():
            session_dir.mkdir(parents=True, exist_ok=True)

        opts = self.get_safe_ydl_options(
            session_dir=session_dir,
            format_preference=format_preference,
            progress_hook=progress_hook,
            is_playlist=False,
        )

        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise DownloadError(f"Could not extract information from '{url}'.")

                # If the result was a playlist with single item or flattened list
                if "entries" in info:
                    entries = list(info["entries"])
                    if not entries:
                        raise DownloadError(f"No downloadable media found in '{url}'.")
                    info = entries[0]

                downloaded_file = Path(ydl.prepare_filename(info))
                
                # If postprocessed (e.g. mp3 conversion changed extension)
                if format_preference == "mp3" and downloaded_file.suffix.lower() != ".mp3":
                    possible_mp3 = downloaded_file.with_suffix(".mp3")
                    if possible_mp3.exists():
                        downloaded_file = possible_mp3

                # Ensure file exists on disk
                if not downloaded_file.exists():
                    # Check if another audio file exists in session directory
                    candidates = [f for f in session_dir.iterdir() if f.is_file() and f.suffix.lower() in (".m4a", ".opus", ".mp3", ".webm", ".ogg")]
                    if candidates:
                        downloaded_file = candidates[0]
                    else:
                        raise FileNotFoundError(f"Downloaded audio file '{downloaded_file}' not found on disk.")

                # Sanitize Title & Artist and extract extended metadata
                raw_title = info.get("title") or downloaded_file.stem
                uploader = info.get("uploader") or info.get("channel")
                sanitized = metadata_sanitizer.sanitize(raw_title, uploader=uploader)

                # Write tags directly to file via mediafile
                try:
                    mf = mediafile.MediaFile(str(downloaded_file))
                    mf.title = sanitized.title
                    mf.artist = sanitized.artist
                    mf.album = info.get("album") or None
                    mf.save()
                except Exception:
                    # Tagging failure should not crash download completion
                    pass

                # Build StagedTrack
                track_id = f"stg_{info.get('id', downloaded_file.stem)}"
                duration = float(info.get("duration") or 0.0)
                file_size = downloaded_file.stat().st_size
                ext = downloaded_file.suffix.lstrip(".").lower()

                staged_track = StagedTrack(
                    id=track_id,
                    title=sanitized.title,
                    artist=sanitized.artist,
                    album=info.get("album") or None,
                    duration_seconds=duration,
                    source_url=url,
                    file_path=str(downloaded_file.resolve()).replace("\\", "/"),
                    file_size=file_size,
                    format=ext,
                    extended_metadata=sanitized.extended_metadata,
                )

                # Atomically append to session manifest
                manifest = self.get_session(session_id)
                if manifest:
                    manifest.tracks.append(staged_track)
                    self._save_manifest(manifest)

                return staged_track

        except Exception as e:
            self.atomic_cleanup(session_id)
            raise e


# Global default instance
audio_downloader_service = AudioDownloaderService()
