"""Unit tests for AudioDownloaderService."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from yt_dlp.utils import DownloadError, MaxDownloadsReached

from musicmatch.config import settings
from musicmatch.services.downloader import AudioDownloaderService


def test_get_safe_ydl_options_native(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)
    opts = service.get_safe_ydl_options(session_dir=tmp_path, format_preference="native")

    assert opts["quiet"] is True
    assert opts["no_warnings"] is True
    assert opts["enable_file_urls"] is False
    assert opts["noplaylist"] is True
    assert "max_downloads" not in opts
    assert "bestaudio[ext=m4a]" in opts["format"]
    assert "postprocessors" not in opts
    assert opts["windowsfilenames"] is True


def test_get_safe_ydl_options_mp3_and_playlist(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)
    hook = MagicMock()
    opts = service.get_safe_ydl_options(
        session_dir=tmp_path,
        format_preference="mp3",
        progress_hook=hook,
        is_playlist=True,
    )

    assert opts["noplaylist"] is False
    assert opts["playlist_items"] == f"1-{settings.DOWNLOAD_PLAYLIST_MAX_TRACKS}"
    assert "max_downloads" not in opts
    assert opts["format"] == "bestaudio/best"
    assert len(opts["postprocessors"]) == 1
    assert opts["postprocessors"][0]["key"] == "FFmpegExtractAudio"
    assert opts["postprocessors"][0]["preferredcodec"] == "mp3"
    assert opts["postprocessors"][0]["preferredquality"] == "320"
    assert opts["progress_hooks"] == [hook]


def test_search_candidates_success(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)

    mock_entries = [
        {
            "id": "vid123",
            "title": "Pink Floyd - Comfortably Numb (Official Video)",
            "channel": "Pink Floyd",
            "duration": 384.0,
            "view_count": 150000000,
        },
        {
            "id": "vid456",
            "title": "Pink Floyd - Time (Audio)",
            "uploader": "Pink Floyd Official",
            "duration": 425.0,
            "view_count": 80000000,
        },
    ]

    with patch("musicmatch.services.downloader.YoutubeDL") as MockYDL:
        mock_instance = MagicMock()
        mock_instance.extract_info.return_value = {"entries": mock_entries}
        MockYDL.return_value.__enter__.return_value = mock_instance

        candidates = service.search_candidates("pink floyd", max_results=2)

        assert len(candidates) == 2
        assert candidates[0]["id"] == "vid123"
        assert candidates[0]["title"] == "Pink Floyd - Comfortably Numb (Official Video)"
        assert candidates[0]["channel"] == "Pink Floyd"
        assert candidates[0]["duration"] == 384.0
        assert candidates[0]["view_count"] == 150000000
        assert candidates[0]["url"] == "https://www.youtube.com/watch?v=vid123"

        assert candidates[1]["id"] == "vid456"
        assert candidates[1]["channel"] == "Pink Floyd Official"


def test_search_candidates_handles_error(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)

    with patch("musicmatch.services.downloader.YoutubeDL") as MockYDL:
        mock_instance = MagicMock()
        mock_instance.extract_info.side_effect = Exception("Network unreachable")
        MockYDL.return_value.__enter__.return_value = mock_instance

        candidates = service.search_candidates("offline query")
        assert candidates == []


def test_download_track_success(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)
    session = service.create_session("queen bohemian rhapsody")
    session_dir = tmp_path / session.session_id

    # Simulated downloaded file
    target_file = session_dir / "vid789.m4a"
    target_file.write_bytes(b"dummy m4a content")

    mock_info = {
        "id": "vid789",
        "title": "Queen - Bohemian Rhapsody (Official Video Remastered)",
        "uploader": "Queen Official",
        "duration": 355.0,
        "album": "A Night at the Opera",
    }

    with patch("musicmatch.services.downloader.YoutubeDL") as MockYDL, \
         patch("musicmatch.services.downloader.mediafile.MediaFile") as MockMediaFile:
        
        mock_ydl_inst = MagicMock()
        mock_ydl_inst.extract_info.return_value = mock_info
        mock_ydl_inst.prepare_filename.return_value = str(target_file)
        MockYDL.return_value.__enter__.return_value = mock_ydl_inst

        mock_mf_inst = MagicMock()
        MockMediaFile.return_value = mock_mf_inst

        staged_track = service.download_track(
            url="https://www.youtube.com/watch?v=vid789",
            session_id=session.session_id,
            format_preference="native",
        )

        assert staged_track.id == "stg_vid789"
        assert staged_track.title == "Bohemian Rhapsody"
        assert staged_track.artist == "Queen"
        assert staged_track.album == "A Night at the Opera"
        assert staged_track.duration_seconds == 355.0
        assert staged_track.format == "m4a"
        assert staged_track.file_size > 0
        assert staged_track.extended_metadata.get("remastered") == "Remastered"

        # Check mediafile tagger was called
        assert mock_mf_inst.title == "Bohemian Rhapsody"
        assert mock_mf_inst.artist == "Queen"
        mock_mf_inst.save.assert_called_once()

        # Check session manifest was updated
        updated_session = service.get_session(session.session_id)
        assert updated_session is not None
        assert len(updated_session.tracks) == 1
        assert updated_session.tracks[0].id == "stg_vid789"


def test_download_track_failure_triggers_atomic_cleanup(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)
    session = service.create_session("bad track")
    session_dir = tmp_path / session.session_id

    # Create partial file
    partial = session_dir / "bad.m4a.part"
    partial.write_bytes(b"corrupt partial bytes")

    with patch("musicmatch.services.downloader.YoutubeDL") as MockYDL:
        mock_ydl_inst = MagicMock()
        mock_ydl_inst.extract_info.side_effect = DownloadError("Download interrupted")
        MockYDL.return_value.__enter__.return_value = mock_ydl_inst

        with pytest.raises(DownloadError):
            service.download_track(
                url="https://www.youtube.com/watch?v=bad123",
                session_id=session.session_id,
            )

        # Ensure partial was cleaned up atomically
        assert not partial.exists()


def test_download_track_recovers_when_max_downloads_reached_is_raised(tmp_path: Path) -> None:
    """Regression test for Issue #4:
    yt-dlp raises MaxDownloadsReached after saving the track to disk.
    The service must not trigger atomic cleanup or fail, but rather recover the track
    metadata, keep the downloaded file, and successfully stage the track.
    """
    service = AudioDownloaderService(staging_dir=tmp_path)
    session = service.create_session("queen bohemian rhapsody")
    session_dir = tmp_path / session.session_id

    # Simulated downloaded file saved to disk prior to MaxDownloadsReached being raised
    target_file = session_dir / "vid789.m4a"
    target_file.write_bytes(b"dummy m4a content")

    mock_info = {
        "id": "vid789",
        "title": "Queen - Bohemian Rhapsody",
        "uploader": "Queen Official",
        "duration": 355.0,
        "album": "A Night at the Opera",
    }

    with patch("musicmatch.services.downloader.YoutubeDL") as MockYDL, \
         patch("musicmatch.services.downloader.mediafile.MediaFile") as MockMediaFile:
        
        mock_ydl_inst = MagicMock()
        # First call with download=True raises MaxDownloadsReached (as yt-dlp does when max_downloads limit is hit)
        # Second call with download=False returns the extracted metadata dictionary
        mock_ydl_inst.extract_info.side_effect = [
            MaxDownloadsReached("Maximum number of downloads reached"),
            mock_info,
        ]
        mock_ydl_inst.prepare_filename.return_value = str(target_file)
        MockYDL.return_value.__enter__.return_value = mock_ydl_inst

        mock_mf_inst = MagicMock()
        MockMediaFile.return_value = mock_mf_inst

        staged_track = service.download_track(
            url="https://www.youtube.com/watch?v=vid789",
            session_id=session.session_id,
            format_preference="native",
        )

        assert staged_track.id == "stg_vid789"
        assert staged_track.title == "Bohemian Rhapsody"
        assert staged_track.artist == "Queen"
        assert target_file.exists()

        # Check session manifest was updated
        updated_session = service.get_session(session.session_id)
        assert updated_session is not None
        assert len(updated_session.tracks) == 1
        assert updated_session.tracks[0].id == "stg_vid789"
