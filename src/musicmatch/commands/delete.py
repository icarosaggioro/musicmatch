"""Delete Command (/delete).

Follows ADR 0013:
- Moves physical audio files to the host Operating System Recycle Bin via send2trash.
- Cascades record removal across SQLite and FTS5 search indices.
- Enforces two-tier safety: External Storage Warning and Count-Verification Gate.
- Direct unrecoverable file unlinking (os.remove) is strictly prohibited.
"""

from pathlib import Path
from typing import List
from musicmatch.commands.base import Command, CommandContext
from musicmatch.services.location import library_location_manager
from musicmatch.services.maintenance import library_maintenance_service


class DeleteCommand(Command):
    """Move arquivos de áudio para a Lixeira do SO e remove registros do banco."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/delete"
        self._description = "Exclui faixas para a Lixeira e remove do catálogo: /delete <id | --missing | --query <q>>"
        self._aliases = ["/deletar", "/apagar"]
        self._default_error_messages = {
            "usage": "Uso: /delete <id>  ou  /delete --missing  ou  /delete --query <termo>",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args:
            errors = self.get_default_error_messages()
            ctx.ui.render_error(errors["usage"])
            return True

        target_arg = args[0]
        managed_root = library_location_manager.resolve_library_path()

        # Mode 1: --missing
        if target_arg == "--missing":
            tracks = [t for t in ctx.db.get_all_tracks() if t.status == "MISSING"]
            return self._handle_batch_delete(tracks, managed_root, ctx)

        # Mode 2: --query
        if target_arg == "--query":
            if len(args) < 2:
                ctx.ui.render_error("Especifique o termo de busca: /delete --query <termo>")
                return True
            q = " ".join(args[1:])
            tracks = ctx.db.search_fulltext(q) if hasattr(ctx.db, "search_fulltext") else []
            return self._handle_batch_delete(tracks, managed_root, ctx)

        # Mode 3: Single track by ID
        track_id = target_arg
        track = ctx.db.get_track(track_id)
        if not track:
            ctx.ui.render_error(f"Faixa com ID '{track_id}' não encontrada no catálogo.")
            return True

        # External Storage Warning
        is_external = self._is_external_file(track.file_path, managed_root)
        if is_external:
            ctx.ui.render_warning("⚠️ AVISO DE ARMAZENAMENTO EXTERNO: Este arquivo reside fora da Biblioteca Gerenciada!")

        ctx.ui.render_info(f"Faixa: {track.artist} - {track.title}")
        ctx.ui.render_info(f"Arquivo a ser enviado para a Lixeira: {track.file_path}")

        try:
            confirm = input("Confirmar exclusão física para a Lixeira do sistema? [s/N]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            ctx.ui.render_info("Operação cancelada pelo usuário.")
            return True

        if confirm not in ("s", "sim", "y", "yes"):
            ctx.ui.render_info("Operação cancelada pelo usuário.")
            return True

        deleted_count, errors = library_maintenance_service.delete_tracks_to_trash([track.id])
        if errors:
            for err in errors:
                ctx.ui.render_error(err)

        if deleted_count > 0:
            ctx.ui.render_success(f"Faixa '{track.id}' movida para a Lixeira e desindexada.")
        return True

    def _handle_batch_delete(self, tracks: List, managed_root: Path, ctx: CommandContext) -> bool:
        if not tracks:
            ctx.ui.render_info("Nenhuma faixa encontrada para exclusão.")
            return True

        count = len(tracks)
        has_external = any(self._is_external_file(t.file_path, managed_root) for t in tracks)
        if has_external:
            ctx.ui.render_warning("⚠️ AVISO: Parte dos arquivos reside fora da pasta da Biblioteca Gerenciada!")

        ctx.ui.render_warning(f"⚠️ ATENÇÃO: Esta operação moverá {count} arquivo(s) para a Lixeira e removerá do catálogo.")
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
        deleted_count, errors = library_maintenance_service.delete_tracks_to_trash(ids)
        if errors:
            for err in errors:
                ctx.ui.render_error(err)
        ctx.ui.render_success(f"{deleted_count} faixa(s) movida(s) para a Lixeira e removida(s) do catálogo.")
        return True

    def _is_external_file(self, file_path_str: str, managed_root: Path) -> bool:
        try:
            file_path = Path(file_path_str).resolve()
            return managed_root.resolve() not in file_path.parents
        except Exception:
            return True

