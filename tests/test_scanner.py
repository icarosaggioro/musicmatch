"""Testes unitários rigorosos (TDD) para o motor de varredura real com mediafile e ADR 0009."""

import struct
import time
import wave
from pathlib import Path
import pytest
import mediafile
from musicmatch.services.library import LibraryService
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from musicmatch.tools.scanner import scan_library

def create_tagged_wav(
    file_path: Path,
    title: str = "Test Title",
    artist: str = "Test Artist",
    album: str = "Test Album",
    genre: str = "Rock",
    year: int = 2024,
    track: int = 1,
    duration_seconds: float = 1.0,
) -> Path:
    """Cria um arquivo WAV válido com metadados reais gravados pelo mediafile."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(file_path), "w") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        frames = int(44100 * duration_seconds)
        data = struct.pack("<h", 0) * (frames * 2)
        wav.writeframes(data)

    mf = mediafile.MediaFile(str(file_path))
    mf.title = title
    mf.artist = artist
    mf.album = album
    mf.genre = genre
    mf.year = year
    mf.track = track
    mf.save()
    return file_path

@pytest.fixture
def repo():
    r = SQLiteTrackRepository(db_path=":memory:")
    yield r
    r.close()

@pytest.fixture
def svc(repo):
    return LibraryService(repository=repo)

def test_scan_nonexistent_directory(svc):
    result = scan_library("C:/Path/That/Does/Not/Exist_XYZ123", service=svc)
    assert result["status"] == "error"
    assert "não encontrado" in result["message"].lower() or "não existe" in result["message"].lower()

def test_scan_empty_directory(tmp_path, svc):
    empty_dir = tmp_path / "empty_music"
    empty_dir.mkdir()
    result = scan_library(str(empty_dir), service=svc)
    assert result["status"] == "success"
    assert result["total_files_scanned"] == 0
    assert result["tracks_indexed"] == 0
    assert result["tracks_added"] == 0
    assert svc.count_tracks() == 0

def test_scan_real_audio_files(tmp_path, svc):
    music_dir = tmp_path / "audio_library"
    f1 = create_tagged_wav(music_dir / "01_queen.wav", title="Bohemian Rhapsody", artist="Queen", album="A Night at the Opera", genre="Rock", year=1975, track=1)
    f2 = create_tagged_wav(music_dir / "02_daftpunk.wav", title="Get Lucky", artist="Daft Punk", album="Random Access Memories", genre="Disco", year=2013, track=2)

    result = scan_library(str(music_dir), recursive=True, service=svc)
    assert result["status"] == "success"
    assert result["total_files_scanned"] == 2
    assert result["tracks_indexed"] == 2
    assert result["tracks_added"] == 2
    assert result["tracks_unchanged"] == 0
    assert svc.count_tracks() == 2

    # Verifica os dados persistidos no banco
    tracks = svc.get_all_tracks()
    titles = {t.title for t in tracks}
    assert "Bohemian Rhapsody" in titles
    assert "Get Lucky" in titles

    queen_track = [t for t in tracks if t.title == "Bohemian Rhapsody"][0]
    assert queen_track.artist == "Queen"
    assert queen_track.album == "A Night at the Opera"
    assert queen_track.genre == "Rock"
    assert queen_track.year == 1975
    assert queen_track.track_number == 1
    assert queen_track.file_size > 0
    assert queen_track.file_mtime is not None
    assert queen_track.status == "AVAILABLE"
    assert queen_track.duration_seconds >= 0.9

def test_stat_cache_idempotency(tmp_path, svc):
    music_dir = tmp_path / "idempotent_library"
    create_tagged_wav(music_dir / "song1.wav", title="Song 1", artist="Artist 1")
    create_tagged_wav(music_dir / "song2.wav", title="Song 2", artist="Artist 2")

    # Primeiro scan: insere 2 faixas
    res1 = scan_library(str(music_dir), service=svc)
    assert res1["tracks_added"] == 2
    assert res1["tracks_unchanged"] == 0

    # Segundo scan imediato: nada mudou no disco
    res2 = scan_library(str(music_dir), service=svc)
    assert res2["total_files_scanned"] == 2
    assert res2["tracks_indexed"] == 0
    assert res2["tracks_added"] == 0
    assert res2["tracks_updated"] == 0
    assert res2["tracks_unchanged"] == 2
    assert svc.count_tracks() == 2

def test_file_modification_detection(tmp_path, svc):
    music_dir = tmp_path / "mod_library"
    f1 = create_tagged_wav(music_dir / "song1.wav", title="Original Title", artist="Artist 1")
    
    # Primeiro scan
    res1 = scan_library(str(music_dir), service=svc)
    assert res1["tracks_added"] == 1

    # Modifica a tag do arquivo
    time.sleep(0.05)  # Garante mtime diferente
    mf = mediafile.MediaFile(str(f1))
    mf.title = "Updated Title"
    mf.save()

    # Segundo scan: deve detectar a alteração
    res2 = scan_library(str(music_dir), service=svc)
    assert res2["tracks_updated"] == 1
    assert res2["tracks_added"] == 0
    assert res2["tracks_unchanged"] == 0
    assert svc.count_tracks() == 1

    track = svc.get_all_tracks()[0]
    assert track.title == "Updated Title"

def test_soft_delete_missing_files(tmp_path, svc):
    music_dir = tmp_path / "delete_library"
    f1 = create_tagged_wav(music_dir / "keep.wav", title="Keep Me")
    f2 = create_tagged_wav(music_dir / "delete.wav", title="Delete Me")

    res1 = scan_library(str(music_dir), service=svc)
    assert res1["tracks_added"] == 2

    # Remove fisicamente o arquivo delete.wav do disco
    f2.unlink()

    # Segundo scan: f2 deve ser marcado como MISSING (soft-delete, sem apagar do banco)
    res2 = scan_library(str(music_dir), service=svc)
    assert res2["tracks_missing"] == 1
    assert res2["tracks_unchanged"] == 1
    assert svc.count_tracks() == 2  # Total de registros preservado!

    tracks = svc.get_all_tracks()
    keep_trk = [t for t in tracks if t.title == "Keep Me"][0]
    del_trk = [t for t in tracks if t.title == "Delete Me"][0]
    assert keep_trk.status == "AVAILABLE"
    assert del_trk.status == "MISSING"

def test_corrupted_audio_file_resilience(tmp_path, svc):
    music_dir = tmp_path / "corrupt_library"
    create_tagged_wav(music_dir / "good.wav", title="Good Song")

    # Cria um arquivo com extensão .mp3 contendo lixo binário corrompido
    corrupt_file = music_dir / "bad.mp3"
    corrupt_file.write_bytes(b"CORRUPT_NOT_AUDIO_DATA_1234567890")

    res = scan_library(str(music_dir), service=svc)
    assert res["status"] == "success"
    assert res["total_files_scanned"] == 2
    assert res["tracks_added"] == 1
    assert res["errors_count"] == 1
    assert svc.count_tracks() == 1

def test_recursive_vs_non_recursive_scanning(tmp_path, svc):
    root_dir = tmp_path / "root_audio"
    sub_dir = root_dir / "subdir"
    create_tagged_wav(root_dir / "root.wav", title="Root Track")
    create_tagged_wav(sub_dir / "sub.wav", title="Sub Track")

    # Scan não recursivo: apenas root.wav
    res_non_rec = scan_library(str(root_dir), recursive=False, service=svc)
    assert res_non_rec["total_files_scanned"] == 1
    assert res_non_rec["tracks_added"] == 1
    assert svc.count_tracks() == 1
