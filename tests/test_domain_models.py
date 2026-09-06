"""Testes unitários para os Modelos de Domínio Pydantic (Validação e Coerção).

CONCEITO DIDÁTICO:
------------------
Estes testes comprovam as vantagens de migrar de '@dataclass' para 'pydantic.BaseModel':
1. Coerção automática de tipos compatíveis (ex: strings que viram números).
2. Detecção imediata de dados inválidos com 'ValidationError' (ex: BPM negativo ou string alfabética).
3. Capacidade de gerar JSON Schema sem esforço para a LLM.
"""

import pytest
from pydantic import ValidationError
from musicmatch.domain.models import ScanResult, Track

def test_track_valid_creation():
    """Valida a instanciação padrão de uma Track com dados válidos."""
    track = Track(
        id="trk_100",
        title="Clair de Lune",
        artist="Claude Debussy",
        album="Suite Bergamasque",
        genre="Classical",
        duration_seconds=302.5,
        bitrate_kbps=320,
        bpm=65.0,
        file_path="C:/Music/Debussy/Clair_de_Lune.mp3",
        mood="Peaceful",
        lufs=-22.1
    )
    assert track.id == "trk_100"
    assert track.bpm == 65.0
    assert track.bitrate_kbps == 320
    assert track.mood == "Peaceful"

def test_track_type_coercion():
    """Comprova que o Pydantic faz coerção automática de tipos compatíveis."""
    track = Track(
        id="trk_101",
        title="Song with string numbers",
        artist="Test Artist",
        album="Test Album",
        genre="Pop",
        duration_seconds="180.5",  # Passando string no lugar de float
        bitrate_kbps="256",        # Passando string no lugar de int
        bpm="128.0",               # Passando string no lugar de float
        file_path="C:/Music/test.mp3"
    )
    # O Pydantic deve ter convertido as strings para os tipos nativos esperados
    assert isinstance(track.duration_seconds, float)
    assert track.duration_seconds == 180.5
    assert isinstance(track.bitrate_kbps, int)
    assert track.bitrate_kbps == 256
    assert isinstance(track.bpm, float)
    assert track.bpm == 128.0

def test_track_validation_errors():
    """Garante que dados fora da regra de negócio disparam ValidationError imediato."""
    base_data = {
        "id": "trk_err",
        "title": "Invalid Track",
        "artist": "Artist",
        "album": "Album",
        "genre": "Rock",
        "duration_seconds": 180.0,
        "bitrate_kbps": 320,
        "bpm": 120.0,
        "file_path": "C:/Music/test.mp3"
    }

    # Caso 1: BPM negativo ou zero (regra: bpm > 0)
    invalid_bpm = base_data.copy()
    invalid_bpm["bpm"] = -10.0
    with pytest.raises(ValidationError) as exc_info:
        Track(**invalid_bpm)
    assert "bpm" in str(exc_info.value)

    # Caso 2: Duração negativa (regra: duration_seconds >= 0)
    invalid_duration = base_data.copy()
    invalid_duration["duration_seconds"] = -1.0
    with pytest.raises(ValidationError) as exc_info:
        Track(**invalid_duration)
    assert "duration_seconds" in str(exc_info.value)

    # Caso 3: Tipo completamente incompatível (string não numérica no BPM)
    invalid_type = base_data.copy()
    invalid_type["bpm"] = "bpm_muito_rapido"
    with pytest.raises(ValidationError) as exc_info:
        Track(**invalid_type)
    assert "bpm" in str(exc_info.value)

    # Caso 4: Campo obrigatório ausente
    incomplete_data = base_data.copy()
    del incomplete_data["file_path"]
    with pytest.raises(ValidationError) as exc_info:
        Track(**incomplete_data)
    assert "file_path" in str(exc_info.value)

def test_scan_result_model_dump():
    """Testa a criação e serialização do ScanResult."""
    result = ScanResult(
        message="Scan finalizado com sucesso.",
        path="C:/Music",
        total_files_scanned=10,
        tracks_indexed=10,
        duration_ms=45.2,
        database_total_tracks=10
    )
    dumped = result.model_dump()
    assert dumped["status"] == "success"
    assert dumped["total_files_scanned"] == 10
    assert dumped["tracks_indexed"] == 10
    assert dumped["recursive"] is True

def test_pydantic_json_schema_generation():
    """Comprova a geração automática de JSON Schema para integração com LLMs."""
    schema = Track.model_json_schema()
    assert "properties" in schema
    assert "bpm" in schema["properties"]
    assert schema["properties"]["bpm"]["description"] == "Batidas por minuto detectadas (BPM)"
    assert "required" in schema
    assert "file_path" in schema["required"]

def test_track_deterministic_id_generation():
    """Valida a geração determinística de ID via hash SHA-256 do caminho canônico (ADR 0009)."""
    path_win = "C:\\Music\\Rock\\Queen - Bohemian Rhapsody.mp3"
    path_norm = "c:/music/rock/queen - bohemian rhapsody.mp3"
    
    id_1 = Track.generate_id(path_win)
    id_2 = Track.generate_id(path_norm)
    
    assert id_1 == id_2
    assert id_1.startswith("trk_")
    assert len(id_1) == 68  # 'trk_' (4) + 64 hex characters

def test_track_adr0009_stat_cache_and_status_fields():
    """Valida os campos de stat-cache, status ('AVAILABLE' / 'MISSING') e metadados adicionais."""
    track = Track(
        id=Track.generate_id("C:/Music/song.mp3"),
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        genre="Rock",
        duration_seconds=120.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path="C:/Music/song.mp3",
        file_mtime=1725600000.5,
        file_size=4194304,
        status="AVAILABLE",
        year=2024,
        track_number=1,
    )
    assert track.file_mtime == 1725600000.5
    assert track.file_size == 4194304
    assert track.status == "AVAILABLE"
    assert track.year == 2024
    assert track.track_number == 1

    # Status deve aceitar 'MISSING'
    track_missing = track.model_copy(update={"status": "MISSING"})
    assert track_missing.status == "MISSING"

def test_scan_result_adr0009_metrics():
    """Valida as métricas detalhadas de idempotência do ScanResult conforme ADR 0009."""
    result = ScanResult(
        message="Scan completo com stat-cache.",
        path="C:/Music",
        total_files_scanned=50,
        tracks_indexed=10,
        tracks_added=10,
        tracks_updated=2,
        tracks_unchanged=38,
        tracks_missing=1,
        errors_count=0,
        duration_ms=25.0,
        database_total_tracks=49
    )
    assert result.tracks_added == 10
    assert result.tracks_updated == 2
    assert result.tracks_unchanged == 38
    assert result.tracks_missing == 1
    assert result.errors_count == 0

