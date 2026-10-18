"""Unit tests for LibraryMaintenanceService (ADR 0013 and ADR 0009)."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from musicmatch.domain.models import Track
from musicmatch.domain.maintenance import LibraryAuditReport, DuplicateGroup
from musicmatch.services.maintenance import LibraryMaintenanceService
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository


@pytest.fixture
def temp_repo(tmp_path):
    db_path = tmp_path / "maintenance_test.db"
    repo = SQLiteTrackRepository(db_path=str(db_path))
    yield repo
    repo.close()


def test_audit_library_metrics(temp_repo, tmp_path):
    # Track 1: Normal available high quality
    f1 = tmp_path / "t1.mp3"
    f1.write_bytes(b"dummy audio 1")
    t1 = Track(
        id="trk_1",
        title="Song 1",
        artist="Artist A",
        album="Album A",
        genre="Rock",
        duration_seconds=200.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path=str(f1).replace("\\", "/"),
        status="AVAILABLE",
    )

    # Track 2: Low bitrate (< 128 kbps)
    f2 = tmp_path / "t2.mp3"
    f2.write_bytes(b"dummy audio 2")
    t2 = Track(
        id="trk_2",
        title="Song 2",
        artist="Artist B",
        album="Album B",
        genre="Pop",
        duration_seconds=180.0,
        bitrate_kbps=96,
        bpm=110.0,
        file_path=str(f2).replace("\\", "/"),
        status="AVAILABLE",
    )

    # Track 3: Missing file on disk
    t3 = Track(
        id="trk_3",
        title="Ghost Song",
        artist="Ghost Artist",
        album="Ghost Album",
        genre="Ambient",
        duration_seconds=150.0,
        bitrate_kbps=256,
        bpm=90.0,
        file_path="C:/Ghost/missing.mp3",
        status="MISSING",
    )

    # Track 4: Untagged track
    f4 = tmp_path / "t4.mp3"
    f4.write_bytes(b"dummy audio 4")
    t4 = Track(
        id="trk_4",
        title="t4",
        artist="Unknown Artist",
        album="Unknown Album",
        genre="Unknown Genre",
        duration_seconds=100.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path=str(f4).replace("\\", "/"),
        status="AVAILABLE",
    )

    temp_repo.insert_batch([t1, t2, t3, t4])

    service = LibraryMaintenanceService(repository=temp_repo)
    report = service.audit_library()

    assert report.total_tracks == 4
    assert report.available_tracks == 3
    assert report.missing_tracks == 1
    assert report.low_bitrate_tracks == 1
    assert report.untagged_tracks == 1
    assert len(report.missing_sample) == 1
    assert report.missing_sample[0].id == "trk_3"


def test_find_duplicates_quality_heuristic(temp_repo, tmp_path):
    f_low = tmp_path / "dup_low.mp3"
    f_low.write_bytes(b"dummy low")
    t_low = Track(
        id="trk_d1",
        title="Take On Me",
        artist="A-Ha",
        album="Hunting High and Low",
        genre="Pop",
        duration_seconds=225.0,
        bitrate_kbps=128,
        bpm=84.0,
        file_path=str(f_low).replace("\\", "/"),
        status="AVAILABLE",
    )

    f_high = tmp_path / "dup_high.mp3"
    f_high.write_bytes(b"dummy high")
    t_high = Track(
        id="trk_d2",
        title="Take on me",
        artist="a-ha",
        album="Hunting High and Low",
        genre="Pop",
        duration_seconds=225.0,
        bitrate_kbps=320,
        bpm=84.0,
        file_path=str(f_high).replace("\\", "/"),
        status="AVAILABLE",
    )

    temp_repo.insert_batch([t_low, t_high])

    service = LibraryMaintenanceService(repository=temp_repo)
    duplicates = service.find_duplicates()

    assert len(duplicates) == 1
    group = duplicates[0]
    assert len(group.tracks) == 2
    assert group.recommended_track_id == "trk_d2"
    assert "320 kbps" in group.recommendation_reason


def test_unindex_tracks_leaves_files_untouched(temp_repo, tmp_path):
    audio_file = tmp_path / "keep_file.mp3"
    audio_file.write_bytes(b"dummy content")
    t = Track(
        id="trk_unindex",
        title="Song to Unindex",
        artist="Artist",
        album="Album",
        genre="Rock",
        duration_seconds=120.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path=str(audio_file).replace("\\", "/"),
        status="AVAILABLE",
    )
    temp_repo.insert_track(t)
    assert temp_repo.count() == 1

    service = LibraryMaintenanceService(repository=temp_repo)
    unindexed_count = service.unindex_tracks(["trk_unindex"])

    assert unindexed_count == 1
    assert temp_repo.count() == 0
    # Physical file on disk must be completely untouched
    assert audio_file.exists()


def test_delete_tracks_routes_to_trash(temp_repo, tmp_path):
    audio_file = tmp_path / "trash_file.mp3"
    audio_file.write_bytes(b"dummy trash")
    t = Track(
        id="trk_trash",
        title="Song to Trash",
        artist="Artist",
        album="Album",
        genre="Rock",
        duration_seconds=120.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path=str(audio_file).replace("\\", "/"),
        status="AVAILABLE",
    )
    temp_repo.insert_track(t)

    service = LibraryMaintenanceService(repository=temp_repo)

    with patch("send2trash.send2trash") as mock_trash:
        deleted_count, errors = service.delete_tracks_to_trash(["trk_trash"])
        assert deleted_count == 1
        assert len(errors) == 0
        mock_trash.assert_called_once_with(str(audio_file).replace("\\", "/"))

    # Database record must be cascaded
    assert temp_repo.get_track("trk_trash") is None


def test_purge_missing_tracks(temp_repo):
    t_miss1 = Track(
        id="trk_m1",
        title="M1",
        artist="A",
        album="Al",
        genre="G",
        duration_seconds=10.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path="C:/Ghost1.mp3",
        status="MISSING",
    )
    t_miss2 = Track(
        id="trk_m2",
        title="M2",
        artist="A",
        album="Al",
        genre="G",
        duration_seconds=10.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path="C:/Ghost2.mp3",
        status="MISSING",
    )
    t_ok = Track(
        id="trk_ok",
        title="OK",
        artist="A",
        album="Al",
        genre="G",
        duration_seconds=10.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path="C:/OK.mp3",
        status="AVAILABLE",
    )
    temp_repo.insert_batch([t_miss1, t_miss2, t_ok])

    service = LibraryMaintenanceService(repository=temp_repo)
    purged = service.purge_missing_tracks()
    assert purged == 2
    assert temp_repo.count() == 1
    assert temp_repo.get_track("trk_ok") is not None


def test_import_external_library(temp_repo, tmp_path):
    source_dir = tmp_path / "external_source"
    source_dir.mkdir()
    managed_dir = tmp_path / "managed_library"
    managed_dir.mkdir()

    # Use real test media file from tests/_MEDIA/Artists/A-HA
    src_media = Path(__file__).parent / "_MEDIA" / "Artists" / "A-HA" / "Hunting High and Low" / "01 Take on me.mp3"
    if not src_media.exists():
        pytest.skip("Test media not found")

    import shutil
    shutil.copy2(src_media, source_dir / "external_take_on_me.mp3")

    service = LibraryMaintenanceService(repository=temp_repo)
    result = service.import_external_library(source_path=source_dir, mode="copy", managed_root=managed_dir)

    assert result.status == "success"
    assert result.total_files == 1
    assert result.imported_count == 1
    assert result.skipped_count == 0
    assert temp_repo.count() == 1


def test_retag_track(temp_repo, tmp_path):
    src_media = Path(__file__).parent / "_MEDIA" / "Artists" / "A-HA" / "Hunting High and Low" / "01 Take on me.mp3"
    if not src_media.exists():
        pytest.skip("Test media not found")

    import shutil
    test_media = tmp_path / "retag_sample.mp3"
    shutil.copy2(src_media, test_media)

    t = Track(
        id="trk_retag",
        title="Take on me",
        artist="A-Ha",
        album="Hunting High and Low",
        genre="Alternative",
        duration_seconds=225.0,
        bitrate_kbps=128,
        bpm=84.0,
        file_path=str(test_media).replace("\\", "/"),
        status="AVAILABLE",
    )
    temp_repo.insert_track(t)

    service = LibraryMaintenanceService(repository=temp_repo)
    updated = service.retag_track("trk_retag", {"title": "Take On Me (Remastered)", "genre": "Synthpop"})

    assert updated.title == "Take On Me (Remastered)"
    assert updated.genre == "Synthpop"

    db_track = temp_repo.get_track("trk_retag")
    assert db_track.title == "Take On Me (Remastered)"
    assert db_track.genre == "Synthpop"
