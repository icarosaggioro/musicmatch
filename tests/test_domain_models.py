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
