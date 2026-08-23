"""Repositório em Memória (Mock DB) para o Laboratório Didático."""

from typing import Dict, List, Optional
from musicmatch.domain.models import Track

class MockDatabase:
    """Simula o banco de dados local SQLite mantendo os dados em memória."""
    
    def __init__(self) -> None:
        self._tracks: Dict[str, Track] = {}

    def insert_track(self, track: Track) -> None:
        """Insere ou atualiza uma faixa no repositório."""
        self._tracks[track.id] = track

    def insert_batch(self, tracks: List[Track]) -> int:
        """Insere uma lista de faixas em lote."""
        for track in tracks:
            self._tracks[track.id] = track
        return len(tracks)

    def get_track(self, track_id: str) -> Optional[Track]:
        """Recupera uma faixa pelo seu ID único."""
        return self._tracks.get(track_id)

    def get_all_tracks(self) -> List[Track]:
        """Retorna todas as faixas atualmente indexadas."""
        return list(self._tracks.values())

    def count(self) -> int:
        """Retorna a quantidade total de faixas registradas."""
        return len(self._tracks)

    def clear(self) -> None:
        """Limpa todo o repositório em memória."""
        self._tracks.clear()

# Instância global singleton do banco em memória
db = MockDatabase()
