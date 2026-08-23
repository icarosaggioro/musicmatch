"""Testes unitários para a ferramenta de scan (scanner stub)."""

import pytest
from musicmatch.storage.mock_db import db
from musicmatch.tools.scanner import scan_library

def test_scan_library_execution():
    db.clear()
    
    result = scan_library("C:/Music/Collection", recursive=True)
    
    assert result["status"] == "success"
    assert result["path"] == "C:/Music/Collection"
    assert result["tracks_indexed"] == 5
    assert db.count() == 5
    
    track_bohemian = db.get_track("trk_001")
    assert track_bohemian is not None
    assert track_bohemian.title == "Bohemian Rhapsody"
    assert track_bohemian.artist == "Queen"
    assert track_bohemian.genre == "Rock"
    assert track_bohemian.bpm == 72.0
