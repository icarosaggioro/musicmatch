"""Retag Command (/retag).

Follows ADR 0013:
- Rewrites ID3/Vorbis tags directly inside audio files via mediafile.
- Synchronizes SQLite database and FTS5 search index atomically.
"""

from typing import Any, Dict, List
from musicmatch.commands.base import Command, CommandContext
from musicmatch.services.maintenance import library_maintenance_service


class RetagCommand(Command):
    """Atualiza as tags físicas do arquivo de áudio e sincroniza o catálogo."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/retag"
        self._description = "Atualiza tags físicas e banco: /retag <id> [--artist <v>] [--title <v>] [--album <v>] [--genre <v>]"
        self._aliases = ["/etiquetar"]
        self._default_error_messages = {
            "usage": "Uso: /retag <track_id> [--artist <v>] [--title <v>] [--album <v>] [--genre <v>]",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if len(args) < 3:
            errors = self.get_default_error_messages()
            ctx.ui.render_error(errors["usage"])
            return True

        track_id = args[0]
        updates: Dict[str, Any] = {}

        idx = 1
        while idx < len(args):
            flag = args[idx].lower()
            if flag in ("--artist", "-a") and idx + 1 < len(args):
                updates["artist"] = args[idx + 1]
                idx += 2
            elif flag in ("--title", "-t") and idx + 1 < len(args):
                updates["title"] = args[idx + 1]
                idx += 2
            elif flag in ("--album", "-l") and idx + 1 < len(args):
                updates["album"] = args[idx + 1]
                idx += 2
            elif flag in ("--genre", "-g") and idx + 1 < len(args):
                updates["genre"] = args[idx + 1]
                idx += 2
            else:
                idx += 1

        if not updates:
            ctx.ui.render_error("Nenhum metadado informado para atualização. Use --title, --artist, --album ou --genre.")
            return True

        try:
            updated_track = library_maintenance_service.retag_track(track_id, updates)
            ctx.ui.render_success(f"Tags da faixa '{track_id}' atualizadas com sucesso.")
            ctx.ui.render_info(f"Metadados: {updated_track.artist} - {updated_track.title} [{updated_track.album}]")
        except Exception as e:
            ctx.ui.render_error(f"Erro ao atualizar tags da faixa '{track_id}': {e}")

        return True

