"""Unit tests for Fast Relocation Match and Missing Track visualization (ADR 0009)."""

import pytest
from musicmatch.domain.models import Track
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from musicmatch.services.scanner import AudioScanner


def test_find_relocation_candidate_and_relocate(tmp_path):
    db_file = tmp_path / "relocation_test.db"
    repo = SQLiteTrackRepository(db_path=str(db_file))

    # Ingest a track that later becomes missing
    old_track = Track(
        id="trk_old",
        title="Bohemian Rhapsody",
        artist="Queen",
        album="A Night at the Opera",
        genre="Rock",
        duration_seconds=354.0,
        bitrate_kbps=320,
        bpm=72.0,
        file_path="C:/OldMusic/bohemian.mp3",
        file_mtime=1000.0,
        file_size=8500000,
        status="MISSING",
    )
    repo.insert_track(old_track)
    assert repo.count() == 1

    # Candidate search: matches exact size, close duration, same title and artist
    candidate = repo.find_relocation_candidate(
        file_size=8500000,
        duration_seconds=354.1,
        title="Bohemian Rhapsody",
        artist="Queen",
    )
    assert candidate is not None
    assert candidate.id == "trk_old"

    # Candidate search with mismatching size should return None
    assert repo.find_relocation_candidate(
        file_size=9999999,
        duration_seconds=354.1,
        title="Bohemian Rhapsody",
        artist="Queen",
    ) is None

    # Relocate track to new path
    new_id = Track.generate_id("C:/NewMusic/bohemian.mp3")
    new_track = Track(
        id=new_id,
        title="Bohemian Rhapsody",
        artist="Queen",
        album="A Night at the Opera",
        genre="Rock",
        duration_seconds=354.0,
        bitrate_kbps=320,
        bpm=72.0,
        file_path="C:/NewMusic/bohemian.mp3",
        file_mtime=2000.0,
        file_size=8500000,
        status="AVAILABLE",
    )
    relocated = repo.relocate_track(old_id="trk_old", new_track=new_track)
    assert relocated is True

    # Confirm old record migrated
    assert repo.get_track("trk_old") is None
    migrated = repo.get_track(new_id)
    assert migrated is not None
    assert migrated.file_path == "C:/NewMusic/bohemian.mp3"
    assert migrated.status == "AVAILABLE"
    assert repo.count() == 1

    repo.close()


def test_search_and_list_render_missing_status(tmp_path):
    from unittest.mock import MagicMock
    from musicmatch.commands.search import SearchCommand
    from musicmatch.commands.base import CommandContext

    repo = MagicMock()
    missing_track = Track(
        id="trk_miss",
        title="Disappeared Song",
        artist="Ghost Artist",
        album="Ghost Album",
        genre="Ambient",
        duration_seconds=180.0,
        bitrate_kbps=128,
        bpm=100.0,
        file_path="C:/Ghost/song.mp3",
        status="MISSING",
    )
    repo.search_fulltext.return_value = [missing_track]

    ui = MagicMock()
    ctx = CommandContext(ui=ui, agent=None, db=repo, registry=None)
    cmd = SearchCommand()

    cmd.execute(["Ghost"], ctx)

    # UI render_search_results or formatted output should be called displaying missing status
    ui.render_search_results.assert_called_once()
    results_arg = ui.render_search_results.call_args[0][0]
    assert len(results_arg) == 1
    assert results_arg[0].status == "MISSING"

