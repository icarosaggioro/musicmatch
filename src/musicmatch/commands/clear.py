"""Clear Command (/clear).

Clears terminal screen and re-renders application welcome banner.
"""

from typing import Dict, List

from musicmatch.commands.base import Command, CommandContext


class ClearCommand(Command):
    """Limpa a tela do console."""

    def __init__(self) -> None:
        super().__init__(
            name="/clear",
            description="Limpa a tela do terminal.",
            aliases=["/cls", "/limpar"],
        )

    def get_name(self) -> str:
        return "/clear"

    def get_aliases(self) -> List[str]:
        return ["/cls", "/limpar"]

    def get_description(self) -> str:
        return "Limpa a tela do terminal."

    def get_default_error_messages(self) -> Dict[str, str]:
        return {
            "usage": "Uso: /clear (não requer argumentos adicionais).",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        ctx.ui.clear_screen()
        ctx.ui.render_banner(ctx.agent.model_name)
        return True
