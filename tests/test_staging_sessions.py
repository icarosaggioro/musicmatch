"""Unit tests for staging sessions and lifecycle management."""

import json
from pathlib import Path
import pytest

from musicmatch.domain.staging import DownloadSessionManifest, StagedTrack
from musicmatch.services.downloader import AudioDownloaderService


def test_create_session(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)
    manifest = service.create_session("https://www.youtube.com/watch?v=abcdefghijk")

    assert manifest.session_id.startswith("session_")
    assert manifest.query_or_url == "https://www.youtube.com/watch?v=abcdefghijk"
    assert manifest.status == "ACTIVE"
    assert manifest.tracks == []

    manifest_file = tmp_path / manifest.session_id / "session.json"
    assert manifest_file.exists()

    loaded = service.get_session(manifest.session_id)
    assert loaded is not None
    assert loaded.session_id == manifest.session_id
    assert loaded.query_or_url == manifest.query_or_url


def test_get_nonexistent_or_corrupt_session(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)
    assert service.get_session("nonexistent_session") is None

    # Corrupt session.json
    corrupt_dir = tmp_path / "session_corrupt"
    corrupt_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_dir / "session.json").write_text("invalid json content", encoding="utf-8")

    assert service.get_session("session_corrupt") is None


def test_list_active_sessions(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)

    # Empty staging
    assert service.list_active_sessions() == []

    # Active session
    sess1 = service.create_session("queen bohemian rhapsody")

    # Inactive/discarded session
    sess2 = service.create_session("pink floyd time")
    sess2.status = "DISCARDED"
    service._save_manifest(sess2)

    # Random directory without session.json
    (tmp_path / "some_random_folder").mkdir()

    active = service.list_active_sessions()
    assert len(active) == 1
    assert active[0].session_id == sess1.session_id


def test_discard_session(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)
    sess = service.create_session("led zeppelin kashmir")
    sess_dir = tmp_path / sess.session_id
    assert sess_dir.exists()

    # Create dummy file inside
    dummy_audio = sess_dir / "kashmir.m4a"
    dummy_audio.write_bytes(b"dummy audio data")

    res = service.discard_session(sess.session_id)
    assert res is True
    assert not sess_dir.exists()

    # Discard non-existent
    assert service.discard_session("nonexistent") is False


def test_atomic_cleanup_purges_only_partials(tmp_path: Path) -> None:
    service = AudioDownloaderService(staging_dir=tmp_path)
    sess = service.create_session("daft punk get lucky")
    sess_dir = tmp_path / sess.session_id

    # Create permanent audio and partials
    audio_file = sess_dir / "track.m4a"
    audio_file.write_bytes(b"valid audio")

    manifest_file = sess_dir / "session.json"
    assert manifest_file.exists()

    part_file = sess_dir / "track.m4a.part"
    part_file.write_bytes(b"partial content")

    ytdl_file = sess_dir / "track.m4a.ytdl"
    ytdl_file.write_bytes(b"ytdl resume data")

    temp_file = sess_dir / "track.temp"
    temp_file.write_bytes(b"temp file")

    service.atomic_cleanup(sess.session_id)

    assert audio_file.exists()
    assert manifest_file.exists()
    assert not part_file.exists()
    assert not ytdl_file.exists()
    assert not temp_file.exists()
