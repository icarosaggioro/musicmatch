"""Testes unitários para a ferramenta de scan."""

import pytest
from musicmatch.services.library import LibraryService
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from musicmatch.tools.scanner import scan_library

def test_scan_library_execution():
    repo = SQLiteTrackRepository(db_path=":memory:")
    svc = LibraryService(repository=repo)
    
    result = scan_library("C:/Music/Collection", recursive=True, service=svc)
    
    assert result["status"] == "success"
    assert result["path"] == "C:/Music/Collection"
    assert result["tracks_indexed"] == 5
    assert svc.count_tracks() == 5
    
    track_bohemian = svc.get_track("trk_001")
    assert track_bohemian is not None
    assert track_bohemian.title == "Bohemian Rhapsody"
    assert track_bohemian.artist == "Queen"
    assert track_bohemian.genre == "Rock"
    assert track_bohemian.bpm == 72.0
    repo.close()
