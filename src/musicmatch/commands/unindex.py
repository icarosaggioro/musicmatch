"""Unindex Command (/unindex).

Follows ADR 0013:
- Purges track metadata and FTS5 search index records from the SQLite database.
- Physical audio files on disk remain 100% untouched.
- Enforces two-tier safety: single-item interactive confirmation and multi-item Count-Verification Gate.
"""

from typing import List
from musicmatch.commands.base import Command, CommandContext
from musicmatch.services.maintenance import library_maintenance_service


class UnindexCommand(Command):
    """Desindexa faixas do catálogo sem tocar nos arquivos físicos no disco."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/unindex"
        self._description = "Desindexa faixas do banco preservando arquivos: /unindex <id | --missing | --all | --query <q>>"
        self._aliases = ["/desindexar"]
        self._default_error_messages = {
            "usage": "Uso: /unindex <id>  ou  /unindex --missing  ou  /unindex --all  ou  /unindex --query <termo>",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            errors = self.get_default_error_messages()
            ctx.ui.render_error(errors["usage"])
            return True

        target_arg = args[0]

        # Mode 1: --missing
        if target_arg == "--missing":
            tracks = [t for t in ctx.db.get_all_tracks() if t.status == "MISSING"]
            return self._handle_batch_unindex(tracks, ctx)

        # Mode 2: --all
        if target_arg == "--all":
            tracks = ctx.db.get_all_tracks()
            return self._handle_batch_unindex(tracks, ctx)

        # Mode 3: --query
        if target_arg == "--query":
            if len(args) < 2:
                ctx.ui.render_error("Especifique o termo de busca: /unindex --query <termo>")
                return True
            q = " ".join(args[1:])
            tracks = ctx.db.search_fulltext(q) if hasattr(ctx.db, "search_fulltext") else []
            return self._handle_batch_unindex(tracks, ctx)

        # Mode 4: Single track by ID
        track_id = target_arg
        track = ctx.db.get_track(track_id)
        if not track:
            ctx.ui.render_error(f"Faixa com ID '{track_id}' não encontrada no catálogo.")
            return True

        ctx.ui.render_info(f"Faixa selecionada: {track.artist} - {track.title}")
        ctx.ui.render_info(f"Arquivo físico: {track.file_path}")
        try:
            confirm = input("Confirmar desindexação desta faixa do catálogo? [s/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            ctx.ui.render_info("Operação cancelada pelo usuário.")
            return True

        if confirm not in ("s", "sim", "y", "yes"):
            ctx.ui.render_info("Operação cancelada pelo usuário.")
            return True

        library_maintenance_service.unindex_tracks([track.id])
        ctx.ui.render_success(f"Faixa '{track.id}' desindexada com sucesso (arquivo físico preservado).")
        return True

    def _handle_batch_unindex(self, tracks: List, ctx: CommandContext) -> bool:
        if not tracks:
            ctx.ui.render_info("Nenhuma faixa encontrada para desindexação.")
            return True

        count = len(tracks)
        ctx.ui.render_warning(f"⚠️ ATENÇÃO: Esta operação irá desindexar {count} faixa(s) do catálogo.")
        ctx.ui.render_info(f"Para confirmar, digite exatamente o número de faixas afetadas ({count}):")

        try:
            val = input("Confirmação de contagem: ").strip()
        except (KeyboardInterrupt, EOFError):
            ctx.ui.render_info("Operação cancelada pelo usuário.")
            return True

        if val != str(count):
            ctx.ui.render_error("Contagem incorreta. Operação cancelada.")
            return True

        ids = [t.id for t in tracks]
        library_maintenance_service.unindex_tracks(ids)
        ctx.ui.render_success(f"{count} faixa(s) desindexada(s) com sucesso.")
        return True

