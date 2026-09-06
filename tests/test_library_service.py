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

def seed_test_tracks(service):
    """Insere faixas de teste padronizadas para validar busca, paginação e estatísticas."""
    tracks = [
        Track(
            id="trk_001",
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            genre="Rock",
            duration_seconds=354.0,
            bitrate_kbps=320,
            bpm=72.0,
            file_path="C:/Music/Queen/Bohemian_Rhapsody.mp3",
            mood="Epic",
            lufs=-12.4
        ),
        Track(
            id="trk_002",
            title="Midnight City",
            artist="M83",
            album="Hurry Up, We're Dreaming",
            genre="Synthwave",
            duration_seconds=243.0,
            bitrate_kbps=320,
            bpm=105.0,
            file_path="C:/Music/M83/Midnight_City.mp3",
            mood="Nostalgic / Energetic",
            lufs=-9.8
        ),
        Track(
            id="trk_003",
            title="Take Five",
            artist="Dave Brubeck Quartet",
            album="Time Out",
            genre="Jazz",
            duration_seconds=324.0,
            bitrate_kbps=256,
            bpm=174.0,
            file_path="C:/Music/Dave_Brubeck/Take_Five.mp3",
            mood="Relaxed / Sophisticated",
            lufs=-16.1
        ),
        Track(
            id="trk_004",
            title="Master of Puppets",
            artist="Metallica",
            album="Master of Puppets",
            genre="Metal",
            duration_seconds=515.0,
            bitrate_kbps=320,
            bpm=212.0,
            file_path="C:/Music/Metallica/Master_of_Puppets.mp3",
            mood="Aggressive / Intense",
            lufs=-8.5
        ),
        Track(
            id="trk_005",
            title="Weightless",
            artist="Marconi Union",
            album="Ambient Transmissions Vol. 2",
            genre="Ambient",
            duration_seconds=485.0,
            bitrate_kbps=320,
            bpm=60.0,
            file_path="C:/Music/Marconi_Union/Weightless.mp3",
            mood="Calm / Meditative",
            lufs=-21.3
        ),
    ]
    service.add_tracks_batch(tracks)

def test_service_scan_and_ingest(tmp_path, service):
    assert service.count_tracks() == 0

    # Cria arquivo de áudio real com tags
    import wave
    import struct
    import mediafile

    test_wav = tmp_path / "song.wav"
    with wave.open(str(test_wav), "w") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(struct.pack("<h", 0) * 88200)

    mf = mediafile.MediaFile(str(test_wav))
    mf.title = "Real Song"
    mf.artist = "Real Artist"
    mf.album = "Real Album"
    mf.genre = "Rock"
    mf.save()

    scan_result = service.scan_and_ingest(str(tmp_path), recursive=True)
    assert scan_result.status == "success"
    assert scan_result.tracks_indexed == 1
    assert scan_result.tracks_added == 1
    assert service.count_tracks() == 1

    tracks = service.get_all_tracks()
    assert tracks[0].title == "Real Song"
    assert tracks[0].artist == "Real Artist"

def test_service_search_tracks(service):
    seed_test_tracks(service)

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
    seed_test_tracks(service)
    stats = service.get_stats()
    assert stats["total_tracks"] == 5
    assert stats["avg_bpm"] > 0

    service.clear_library()
    assert service.count_tracks() == 0
    assert len(service.get_all_tracks()) == 0

def test_service_get_all_tracks_pagination(service):
    seed_test_tracks(service)
    all_tracks = service.get_all_tracks()
    assert len(all_tracks) == 5

    paginated = service.get_all_tracks(limit=2, offset=0)
    assert len(paginated) == 2

    paginated_offset = service.get_all_tracks(limit=2, offset=2)
    assert len(paginated_offset) == 2
    assert paginated[0].id != paginated_offset[0].id


