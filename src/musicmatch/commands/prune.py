"""Prune Command (/prune).

Follows ADR 0009 Two-Stage Purge Protocol:
- Permanently purges all tracks currently marked as 'MISSING' from the database catalog.
- Protected by a strict two-stage confirmation requiring the passphrase: PLEASEPRETTYPLEASE.
"""

from typing import List
from musicmatch.commands.base import Command, CommandContext
from musicmatch.services.maintenance import library_maintenance_service


class PruneCommand(Command):
    """Remove permanentemente do catálogo todas as faixas com status 'MISSING'."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/prune"
        self._description = "Expurgo permanente de faixas ausentes do catálogo: /prune"
        self._aliases = ["/expurgar"]
        self._default_error_messages = {
            "usage": "Uso: /prune (requer confirmação com frase de segurança).",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        ctx.ui.render_warning("⚠️ ATENÇÃO: Esta operação removerá permanentemente todos os registros 'MISSING' do catálogo.")
        ctx.ui.render_info("Para confirmar a operação, digite a frase de segurança: PLEASEPRETTYPLEASE")

        try:
            user_input = input("Frase de segurança: ").strip()
        except (KeyboardInterrupt, EOFError):
            ctx.ui.render_info("Operação cancelada pelo usuário.")
            return True

        if user_input != "PLEASEPRETTYPLEASE":
            ctx.ui.render_error("Frase de segurança incorreta. Operação cancelada.")
            return True

        purged_count = library_maintenance_service.purge_missing_tracks()
        if purged_count > 0:
            ctx.ui.render_success(f"{purged_count} faixa(s) 'MISSING' expurgada(s) do catálogo.")
        else:
            ctx.ui.render_info("Nenhuma faixa com status 'MISSING' encontrada para expurgo.")
        return True

