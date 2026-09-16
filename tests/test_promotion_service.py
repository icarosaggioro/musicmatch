"""Unit and integration tests for TrackPromotionService."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from musicmatch.domain.staging import DownloadSessionManifest, StagedTrack
from musicmatch.services.downloader import AudioDownloaderService
from musicmatch.services.location import LibraryLocationManager
from musicmatch.services.promotion import TrackPromotionService, sanitize_filename_component
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository


# ==============================================================================
# 1. Sanitization & Taxonomy Routing Tests
# ==============================================================================

def test_sanitize_filename_component() -> None:
    assert sanitize_filename_component('Queen: "Live at Wembley"') == "Queen_ _Live at Wembley_"
    assert sanitize_filename_component("AC/DC & Guns N' Roses") == "AC_DC & Guns N' Roses"
    assert sanitize_filename_component("  ...Some Track...  ") == "Some Track"
    assert sanitize_filename_component("   ") == "Unknown"
    assert sanitize_filename_component("???") == "Unknown"


def test_compute_target_path_artist_single(tmp_path: Path) -> None:
    service = TrackPromotionService()
    track = StagedTrack(
        id="stg_1",
        title="Bohemian Rhapsody",
        artist="Queen",
        source_url="https://youtube.com/1",
        file_path=str(tmp_path / "1.m4a"),
        format="m4a",
    )
    dest = service.compute_target_path(track, library_root=tmp_path)
    expected = tmp_path / "Artists" / "Queen" / "Singles" / "Queen - Bohemian Rhapsody.m4a"
    assert dest == expected


def test_compute_target_path_artist_album(tmp_path: Path) -> None:
    service = TrackPromotionService()
    track = StagedTrack(
        id="stg_1",
        title="Time",
        artist="Pink Floyd",
        album="The Dark Side of the Moon",
        source_url="https://youtube.com/1",
        file_path=str(tmp_path / "1.opus"),
        format="opus",
    )
    dest = service.compute_target_path(track, library_root=tmp_path, track_number=4)
    expected = tmp_path / "Artists" / "Pink Floyd" / "The Dark Side of the Moon" / "04 - Pink Floyd - Time.opus"
    assert dest == expected


def test_compute_target_path_various_artists(tmp_path: Path) -> None:
    service = TrackPromotionService()
    track = StagedTrack(
        id="stg_1",
        title="Stayin' Alive",
        artist="Bee Gees",
        album="Saturday Night Fever",
        source_url="https://youtube.com/1",
        file_path=str(tmp_path / "1.mp3"),
        format="mp3",
        extended_metadata={"albumartist": "Various Artists"},
    )
    dest = service.compute_target_path(track, library_root=tmp_path, is_compilation=True, track_number=1)
    expected = tmp_path / "Various Artists" / "Saturday Night Fever" / "01 - Bee Gees - Stayin' Alive.mp3"
    assert dest == expected


def test_compute_target_path_collection(tmp_path: Path) -> None:
    service = TrackPromotionService()
    track = StagedTrack(
        id="stg_1",
        title="Hotel California",
        artist="Eagles",
        album="Hotel California",
        source_url="https://youtube.com/1",
        file_path=str(tmp_path / "1.m4a"),
        format="m4a",
    )
    dest = service.compute_target_path(
        track,
        library_root=tmp_path,
        collection_name="Classic Rock Mixtape",
    )
    expected = tmp_path / "Collections" / "Classic Rock Mixtape" / "Eagles - Hotel California.m4a"
    assert dest == expected


# ==============================================================================
# 2. Promotion Execution & Collision Invariant Tests
# ==============================================================================

@pytest.fixture
def promotion_env(tmp_path: Path):
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    library_dir = tmp_path / "library"
    library_dir.mkdir(parents=True, exist_ok=True)

    downloader = AudioDownloaderService(staging_dir=staging_dir)
    location_mgr = LibraryLocationManager(config_path=tmp_path / "lib_cfg.json")
    location_mgr.set_library_path(library_dir)
    repo = SQLiteTrackRepository(db_path=":memory:")

    service = TrackPromotionService(
        downloader_service=downloader,
        location_manager=location_mgr,
        repo=repo,
    )
    return {
        "service": service,
        "downloader": downloader,
        "location_mgr": location_mgr,
        "repo": repo,
        "staging_dir": staging_dir,
        "library_dir": library_dir,
    }


def test_promote_track_session_not_found(promotion_env) -> None:
    service = promotion_env["service"]
    res = service.promote_track(session_id="nonexistent", track_id_or_idx="stg_1")
    assert res.status == "NOT_FOUND"
    assert "not found" in res.error_message


def test_promote_track_track_not_found(promotion_env) -> None:
    service = promotion_env["service"]
    downloader = promotion_env["downloader"]
    session = downloader.create_session("query")

    res = service.promote_track(session_id=session.session_id, track_id_or_idx="stg_unknown")
    assert res.status == "NOT_FOUND"

    res_idx = service.promote_track(session_id=session.session_id, track_id_or_idx=99)
    assert res_idx.status == "NOT_FOUND"


def test_promote_track_source_file_missing(promotion_env) -> None:
    service = promotion_env["service"]
    downloader = promotion_env["downloader"]
    staging_dir = promotion_env["staging_dir"]

    session = downloader.create_session("query")
    session_dir = staging_dir / session.session_id
    missing_file = session_dir / "missing.m4a"

    track = StagedTrack(
        id="stg_missing",
        title="Ghost Track",
        artist="Ghost",
        source_url="https://youtube.com/ghost",
        file_path=str(missing_file),
        format="m4a",
    )
    session.tracks.append(track)
    downloader._save_manifest(session)

    res = service.promote_track(session_id=session.session_id, track_id_or_idx="stg_missing")
    assert res.status == "ERROR"
    assert "does not exist" in res.error_message


def test_promote_track_collision_invariant(promotion_env) -> None:
    """Strict Collision Invariant: If destination file exists, promotion stops and staged file remains."""
    service = promotion_env["service"]
    downloader = promotion_env["downloader"]
    staging_dir = promotion_env["staging_dir"]
    library_dir = promotion_env["library_dir"]

    session = downloader.create_session("led zeppelin kashmir")
    session_dir = staging_dir / session.session_id
    staged_audio = session_dir / "kashmir.m4a"
    staged_audio.write_bytes(b"staged audio content")

    track = StagedTrack(
        id="stg_kashmir",
        title="Kashmir",
        artist="Led Zeppelin",
        album="Physical Graffiti",
        source_url="https://youtube.com/kashmir",
        file_path=str(staged_audio),
        format="m4a",
    )
    session.tracks.append(track)
    downloader._save_manifest(session)

    # Pre-create the collision destination in library
    dest_path = library_dir / "Artists" / "Led Zeppelin" / "Physical Graffiti" / "Led Zeppelin - Kashmir.m4a"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(b"existing library audio content")

    # Attempt promotion
    res = service.promote_track(session_id=session.session_id, track_id_or_idx="stg_kashmir")

    assert res.status == "COLLISION"
    assert "already exists" in res.error_message

    # Staged audio was NOT deleted or moved
    assert staged_audio.exists()
    assert staged_audio.read_bytes() == b"staged audio content"

    # Destination was NOT overwritten
    assert dest_path.exists()
    assert dest_path.read_bytes() == b"existing library audio content"

    # Manifest track was NOT marked as promoted
    loaded_session = downloader.get_session(session.session_id)
    assert loaded_session.tracks[0].promoted is False


def test_promote_track_success_and_cataloging(promotion_env) -> None:
    service = promotion_env["service"]
    downloader = promotion_env["downloader"]
    staging_dir = promotion_env["staging_dir"]
    library_dir = promotion_env["library_dir"]
    repo = promotion_env["repo"]

    session = downloader.create_session("queen bohemian rhapsody")
    session_dir = staging_dir / session.session_id
    staged_file = session_dir / "bohemian.m4a"
    staged_file.write_bytes(b"simulated m4a bitstream")

    track = StagedTrack(
        id="stg_bohemian",
        title="Bohemian Rhapsody",
        artist="Queen",
        album="A Night at the Opera",
        duration_seconds=355.0,
        source_url="https://youtube.com/bohemian",
        file_path=str(staged_file),
        format="m4a",
    )
    session.tracks.append(track)
    downloader._save_manifest(session)

    with patch("musicmatch.services.promotion.mediafile.MediaFile") as MockMediaFile:
        mock_mf = MagicMock()
        MockMediaFile.return_value = mock_mf

        res = service.promote_track(
            session_id=session.session_id,
            track_id_or_idx=1,  # promote by 1-based index
            track_number=11,
        )

        assert res.status == "PROMOTED"
        expected_dest = library_dir / "Artists" / "Queen" / "A Night at the Opera" / "11 - Queen - Bohemian Rhapsody.m4a"
        assert res.destination_path == str(expected_dest.resolve()).replace("\\", "/")

        # Original file moved
        assert not staged_file.exists()
        assert expected_dest.exists()

        # Tags written
        assert mock_mf.artist == "Queen"
        assert mock_mf.title == "Bohemian Rhapsody"
        assert mock_mf.album == "A Night at the Opera"
        assert mock_mf.track == 11
        mock_mf.save.assert_called_once()

        # Cataloged into SQLite
        cataloged = repo.get_all_tracks()
        assert len(cataloged) == 1
        assert cataloged[0].artist == "Queen"
        assert cataloged[0].title == "Bohemian Rhapsody"
        assert cataloged[0].track_number == 11

        # Searchable via FTS5
        search_res = repo.search_fulltext("Bohemian")
        assert len(search_res) == 1
        assert search_res[0].id == cataloged[0].id

        # Session manifest updated to RESOLVED because the only track was promoted
        updated_sess = downloader.get_session(session.session_id)
        assert updated_sess.status == "RESOLVED"
        assert updated_sess.tracks[0].promoted is True
        assert updated_sess.tracks[0].promoted_to == str(expected_dest.resolve()).replace("\\", "/")


def test_promote_session_batch(promotion_env) -> None:
    service = promotion_env["service"]
    downloader = promotion_env["downloader"]
    staging_dir = promotion_env["staging_dir"]
    library_dir = promotion_env["library_dir"]
    repo = promotion_env["repo"]

    session = downloader.create_session("pink floyd album")
    session_dir = staging_dir / session.session_id

    file1 = session_dir / "track1.m4a"
    file1.write_bytes(b"track 1 data")
    file2 = session_dir / "track2.m4a"
    file2.write_bytes(b"track 2 data")

    t1 = StagedTrack(
        id="stg_t1",
        title="Speak to Me",
        artist="Pink Floyd",
        album="The Dark Side of the Moon",
        source_url="https://youtube.com/1",
        file_path=str(file1),
        format="m4a",
    )
    t2 = StagedTrack(
        id="stg_t2",
        title="Breathe",
        artist="Pink Floyd",
        album="The Dark Side of the Moon",
        source_url="https://youtube.com/2",
        file_path=str(file2),
        format="m4a",
    )
    session.tracks.extend([t1, t2])
    downloader._save_manifest(session)

    with patch("musicmatch.services.promotion.mediafile.MediaFile"):
        results = service.promote_session(session_id=session.session_id)

        assert len(results) == 2
        assert all(r.status == "PROMOTED" for r in results)

        # Database contains both tracks
        assert repo.count() == 2

        # Session manifest is resolved
        manifest = downloader.get_session(session.session_id)
        assert manifest.status == "RESOLVED"
        assert all(t.promoted for t in manifest.tracks)

