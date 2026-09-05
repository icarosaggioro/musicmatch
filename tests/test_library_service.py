"""Testes unitários para a camada de serviços de negócio (LibraryService)."""

import pytest
from musicmatch.domain.models import Track
from musicmatch.services.library import LibraryService
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository

@pytest.fixture
def service():
    """Cria uma instância do LibraryService conectada a um repositório isolado em memória."""
    repo = SQLiteTrackRepository(db_path=":memory:")
    svc = LibraryService(repository=repo)
    yield svc
    repo.close()

def test_service_add_and_get_track(service):
    track = Track(
        id="trk_svc",
        title="Service Song",
        artist="Service Artist",
        album="Service Album",
        genre="Jazz",
        duration_seconds=200.0,
        bitrate_kbps=320,
        bpm=100.0,
        file_path="C:/Music/svc.mp3"
    )
    added = service.add_track(track)
    assert added.id == "trk_svc"

    retrieved = service.get_track("trk_svc")
    assert retrieved is not None
    assert retrieved.title == "Service Song"

    by_path = service.get_track_by_path("C:/Music/svc.mp3")
    assert by_path is not None
    assert by_path.id == "trk_svc"

def test_service_update_and_delete(service):
    track = Track(
        id="trk_up",
        title="Initial Title",
        artist="Artist",
        album="Album",
        genre="Pop",
        duration_seconds=150.0,
        bitrate_kbps=256,
        bpm=90.0,
        file_path="C:/Music/initial.mp3"
    )
    service.add_track(track)

    # Update
    track.title = "Updated Title"
    assert service.update_track(track) is True
    assert service.get_track("trk_up").title == "Updated Title"

    # Delete
    assert service.delete_track("trk_up") is True
    assert service.get_track("trk_up") is None
    assert service.delete_track("trk_up") is False

def test_service_scan_and_ingest(service):
    assert service.count_tracks() == 0

    scan_result = service.scan_and_ingest("C:/MyMusic", recursive=True)
    assert scan_result.status == "success"
    assert scan_result.tracks_indexed == 5
    assert service.count_tracks() == 5

    # Comprova que faixas escaneadas foram persistidas no SQLite
    bohemian = service.get_track("trk_001")
    assert bohemian is not None
    assert bohemian.title == "Bohemian Rhapsody"

def test_service_search_tracks(service):
    service.scan_and_ingest("C:/MyMusic")

    # Busca textual simples via FTS5
    results = service.search_tracks(query="Queen")
    assert len(results) == 1
    assert results[0].artist == "Queen"

    # Busca com filtro de gênero
    rock_tracks = service.search_tracks(genre="Rock")
    assert len(rock_tracks) == 1
    assert rock_tracks[0].title == "Bohemian Rhapsody"

    # Busca com faixa de BPM
    fast_tracks = service.search_tracks(min_bpm=150.0)
    assert len(fast_tracks) >= 1  # Dave Brubeck (174) e Metallica (212)

def test_service_stats_and_clear(service):
    service.scan_and_ingest("C:/MyMusic")
    stats = service.get_stats()
    assert stats["total_tracks"] == 5
    assert stats["avg_bpm"] > 0

    service.clear_library()
    assert service.count_tracks() == 0
    assert len(service.get_all_tracks()) == 0

def test_service_get_all_tracks_pagination(service):
    service.scan_and_ingest("C:/MyMusic")
    all_tracks = service.get_all_tracks()
    assert len(all_tracks) == 5

    paginated = service.get_all_tracks(limit=2, offset=0)
    assert len(paginated) == 2

    paginated_offset = service.get_all_tracks(limit=2, offset=2)
    assert len(paginated_offset) == 2
    assert paginated[0].id != paginated_offset[0].id

