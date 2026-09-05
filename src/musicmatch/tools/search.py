"""Ferramentas de Consulta e Busca Semântica/Acústica na Biblioteca."""

from typing import Any, Dict, Optional
from musicmatch.services.library import LibraryService, library_service

def search_tracks(
    query: Optional[str] = None,
    genre: Optional[str] = None,
    min_bpm: Optional[float] = None,
    max_bpm: Optional[float] = None,
    limit: int = 10,
    service: Optional[LibraryService] = None,
) -> Dict[str, Any]:
    """Busca faixas musicais na biblioteca local utilizando busca textual em FTS5 e/ou filtros acústicos.

    Esta ferramenta deve ser chamada sempre que o usuário perguntar quais músicas existem na biblioteca,
    pedir recomendações por gênero (Rock, Jazz, etc.), por faixa de BPM (ex: 'músicas para correr entre 120 e 140 BPM')
    ou pesquisar por artista, álbum ou humor (mood).

    Args:
        query: Termo de busca textual para pesquisar em título, artista, álbum ou mood (ex: 'Queen', 'Bohemian', 'energetic').
        genre: Gênero musical exato a filtrar (ex: 'Rock', 'Jazz', 'Synthwave', 'Metal').
        min_bpm: Batimentos por minuto mínimos desejados (ex: 120.0).
        max_bpm: Batimentos por minuto máximos desejados (ex: 140.0).
        limit: Número máximo de faixas a retornar. Padrão é 10.
        service: Instância opcional da camada de serviços (LibraryService).

    Returns:
        Um dicionário contendo o total de faixas encontradas e a lista com os metadados de cada faixa.
    """
    svc = service or library_service
    results = svc.search_tracks(
        query=query,
        genre=genre,
        min_bpm=min_bpm,
        max_bpm=max_bpm,
        limit=limit,
    )
    return {
        "status": "success",
        "total_matches": len(results),
        "tracks": [t.model_dump() for t in results],
    }
