"""Testes unitários para o Mock Database."""

import pytest
from musicmatch.domain.models import Track
from musicmatch.storage.mock_db import MockDatabase

def test_mock_database_operations():
    db = MockDatabase()
    assert db.count() == 0
    
    track = Track(
        id="t1",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        genre="Rock",
        duration_seconds=180.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path="C:/Music/test.mp3"
    )
    
    db.insert_track(track)
    assert db.count() == 1
    assert db.get_track("t1") == track
    assert db.get_track("non_existent") is None
    
    all_tracks = db.get_all_tracks()
    assert len(all_tracks) == 1
    assert all_tracks[0].title == "Test Song"
    
    db.clear()
    assert db.count() == 0
