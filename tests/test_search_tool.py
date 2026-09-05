"""Testes unitários para as ferramentas de busca e scanner."""

from unittest.mock import MagicMock
from musicmatch.domain.models import ScanResult, Track
from musicmatch.tools.scanner import scan_library
from musicmatch.tools.search import search_tracks

def test_search_tracks_tool():
    mock_service = MagicMock()
    mock_track = Track(
        id="t1",
        title="Bohemian Rhapsody",
        artist="Queen",
        album="A Night at the Opera",
        genre="Rock",
        duration_seconds=354.0,
        bitrate_kbps=320,
        bpm=72.0,
        file_path="C:/Music/bohemian.mp3"
    )
    mock_service.search_tracks.return_value = [mock_track]

    result = search_tracks(query="Queen", genre="Rock", service=mock_service)

    assert result["status"] == "success"
    assert result["total_matches"] == 1
    assert result["tracks"][0]["title"] == "Bohemian Rhapsody"
    mock_service.search_tracks.assert_called_once_with(
        query="Queen",
        genre="Rock",
        min_bpm=None,
        max_bpm=None,
        limit=10
    )

def test_search_tracks_tool_empty():
    mock_service = MagicMock()
    mock_service.search_tracks.return_value = []

    result = search_tracks(query="desconhecido", service=mock_service)
    assert result["status"] == "success"
    assert result["total_matches"] == 0
    assert result["tracks"] == []

def test_scan_library_tool_delegation():
    mock_service = MagicMock()
    mock_scan_result = ScanResult(
        message="Scan completo",
        path="C:/Music",
        total_files_scanned=5,
        tracks_indexed=5,
        duration_ms=10.0,
        database_total_tracks=5
    )
    mock_service.scan_and_ingest.return_value = mock_scan_result

    result = scan_library("C:/Music", recursive=True, service=mock_service)
    assert result["status"] == "success"
    assert result["tracks_indexed"] == 5
    mock_service.scan_and_ingest.assert_called_once_with(path="C:/Music", recursive=True)
