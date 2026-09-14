"""Staging Area Management Command (/staging).

Follows ADR 0011:
- Inspects isolated download sessions awaiting user review.
- Lists active sessions and displays full metadata details.
- Discards unwanted sessions and cleans up disk space safely.
"""

from typing import List

from musicmatch.commands.base import Command, CommandContext
from musicmatch.services.downloader import audio_downloader_service


class StagingCommand(Command):
    """Gerencia e inspeciona sessões de áudio pendentes na Staging Area."""

    def __init__(self) -> None:
        super().__init__(
            name="/staging",
            description="Gerencia sessões da Staging Area: /staging [list | show <id> | promote <id> | discard <id>]",
        )

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        if not args or args[0].lower() == "list":
            active_sessions = audio_downloader_service.list_active_sessions()
            ctx.ui.render_staging_sessions(active_sessions)
            return True

        subcommand = args[0].lower()
        if subcommand in ("show", "view", "inspect"):
            if len(args) < 2:
                ctx.ui.render_error("Uso incorreto. Especifique o ID da sessão: /staging show <session_id>")
                ctx.ui.render_info("Exemplo: /staging show session_20260913_200000_a1b2c3")
                return True

            session_id = args[1].strip()
            manifest = audio_downloader_service.get_session(session_id)
            if not manifest:
                ctx.ui.render_error(f"Sessão '{session_id}' não encontrada na Staging Area.")
                return True

            ctx.ui.render_staging_detail(manifest)
            return True

        if subcommand in ("discard", "delete", "remove"):
            if len(args) < 2:
                ctx.ui.render_error("Uso incorreto. Especifique o ID da sessão a descartar: /staging discard <session_id>")
                return True

            session_id = args[1].strip()
            success = audio_downloader_service.discard_session(session_id)
            if success:
                ctx.ui.render_success(f"Sessão '{session_id}' e seus arquivos de áudio foram excluídos com sucesso.")
            else:
                ctx.ui.render_error(f"Sessão '{session_id}' não encontrada ou já descartada.")
            return True

        if subcommand in ("promote", "promover"):
            from musicmatch.commands.promote import PromoteCommand
            return PromoteCommand().execute(args[1:], ctx)

        ctx.ui.render_error(f"Subcomando '{subcommand}' não reconhecido para /staging.")
        ctx.ui.render_info("Uso: /staging list | /staging show <id> | /staging promote <id> | /staging discard <id>")
        return True

