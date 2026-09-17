"""Clear Command (/clear).

Clears terminal screen and re-renders application welcome banner.
"""

from typing import List

from musicmatch.commands.base import Command, CommandContext


class ClearCommand(Command):
    """Limpa a tela do console."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/clear"
        self._description = "Limpa a tela do terminal."
        self._aliases = ["/cls", "/limpar"]
        self._default_error_messages = {
            "usage": "Uso: /clear (não requer argumentos adicionais).",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        ctx.ui.clear_screen()
        ctx.ui.render_banner(ctx.agent.model_name)
        return True
