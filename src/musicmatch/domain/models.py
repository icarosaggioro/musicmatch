"""Modelos de Domínio do MusicMatch."""

from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Track:
    """Representa uma faixa musical indexada com seus metadados essenciais."""
    
    id: str
    title: str
    artist: str
    album: str
    genre: str
    duration_seconds: float
    bitrate_kbps: int
    bpm: float
    file_path: str
    mood: Optional[str] = None
    lufs: Optional[float] = None

@dataclass
class ScanResult:
    """Resultado consolidado de uma operação de varredura/escaneamento de diretório."""
    
    path: str
    total_files_scanned: int
    tracks_added: int
    duration_ms: float
    tracks: List[Track] = field(default_factory=list)
