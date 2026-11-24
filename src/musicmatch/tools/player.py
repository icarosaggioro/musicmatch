"""Playback tool of the agent (ADR 0015)."""

from typing import Any, Callable, Dict, Optional

from musicmatch.services.library import LibraryService, library_service

# Set by the harness so notices of playback started by the agent (next track, errors) reach the screen.
_event_listener: Optional[Callable[[Any], None]] = None


def set_event_listener(listener: Optional[Callable[[Any], None]]) -> None:
    global _event_listener
    _event_listener = listener


def _summary(track: Any) -> Dict[str, Any]:
    return {
        "id": track.id,
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "duration_seconds": track.duration_seconds,
        "status": track.status,
    }


def play_track(
    query_or_id: str,
    service: Optional[LibraryService] = None,
    player: Optional[Any] = None,
) -> Dict[str, Any]:
    """Toca uma faixa da biblioteca local agora, pelo ID ou por um texto de busca (título, artista).

    Esta ferramenta deve ser chamada quando o usuário pedir para tocar, ouvir ou reproduzir uma música.
    Se o resultado for 'ambiguous', apresente as opções ao usuário ou chame de novo com o ID escolhido.

    Args:
        query_or_id: ID da faixa (ou prefixo, ex: 'trk_3fa2b9') ou texto de busca (ex: 'Queen Bohemian Rhapsody').
        service: Instância opcional da camada de serviços (LibraryService) para injeção de dependência.
        player: Instância opcional do player para injeção de dependência.

    Returns:
        Um dicionário com 'status' ('playing', 'ambiguous', 'not_found' ou 'error') e a faixa ou as opções.
    """
    from musicmatch.services.player import get_player_service, is_track_available
    from musicmatch.services.track_lookup import find_track

    repo = (service or library_service).repo
    found = find_track(repo, query_or_id)
    if found.track is None:
        if not found.candidates:
            return {"status": "not_found", "message": f"Nenhuma faixa encontrada para '{query_or_id}'."}
        return {
            "status": "ambiguous",
            "message": "Mais de uma faixa corresponde; escolha pelo ID.",
            "candidates": [_summary(t) for t in found.candidates],
        }
    track = found.track
    if not is_track_available(track):
        return {"status": "error", "message": "Arquivo indisponível no disco.", "track": _summary(track)}
    if player is None:
        player = get_player_service(repo.db_path if isinstance(getattr(repo, "db_path", None), str) else None)
    if _event_listener is not None:
        player.add_listener(_event_listener)
    if not player.play_track(track):
        return {"status": "error", "message": "Não foi possível iniciar a reprodução.", "track": _summary(track)}
    return {"status": "playing", "track": _summary(track)}
