"""Ferramentas de Ingestão e Varredura de Áudio (Stubs)."""

import time
from typing import Any, Dict
from musicmatch.domain.models import Track
from musicmatch.storage.mock_db import db

def scan_library(path: str, recursive: bool = True) -> Dict[str, Any]:
    """Varre um diretório local em busca de arquivos de áudio (MP3/FLAC/WAV), extrai metadados e popula a biblioteca.

    Esta ferramenta deve ser chamada sempre que o usuário solicitar indexar, escanear,
    adicionar ou atualizar arquivos de música a partir de uma pasta ou disco local.

    Args:
        path: Caminho absoluto ou relativo do diretório a ser varrido (ex: 'C:/Musicas' ou 'D:/Audio/Albuns').
        recursive: Se True, percorre todas as subpastas recursivamente. Padrão é True.

    Returns:
        Um dicionário contendo o status da operação, total de faixas indexadas e uma amostra dos títulos adicionados.
    """
    start_time = time.perf_counter()
    
    # Gera dados sintéticos representativos simulando a varredura de arquivos MP3
    synthetic_tracks = [
        Track(
            id="trk_001",
            title="Bohemian Rhapsody",
            artist="Queen",
            album="A Night at the Opera",
            genre="Rock",
            duration_seconds=354.0,
            bitrate_kbps=320,
            bpm=72.0,
            file_path=f"{path}/Queen/Bohemian_Rhapsody.mp3",
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
            file_path=f"{path}/M83/Midnight_City.mp3",
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
            file_path=f"{path}/Dave_Brubeck/Take_Five.mp3",
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
            file_path=f"{path}/Metallica/Master_of_Puppets.mp3",
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
            file_path=f"{path}/Marconi_Union/Weightless.mp3",
            mood="Calm / Meditative",
            lufs=-21.3
        ),
    ]

    # Popula o banco de dados em memória
    db.insert_batch(synthetic_tracks)
    
    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
    
    return {
        "status": "success",
        "message": f"Varredura concluída com sucesso no diretório '{path}'.",
        "path": path,
        "recursive": recursive,
        "total_files_scanned": len(synthetic_tracks),
        "tracks_indexed": len(synthetic_tracks),
        "sample_tracks": [f"{t.artist} - {t.title} ({t.genre})" for t in synthetic_tracks],
        "duration_ms": elapsed_ms,
        "database_total_tracks": db.count()
    }
