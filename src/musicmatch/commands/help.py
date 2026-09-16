"""Help Command (/help).

Displays the formatted catalog of all registered commands and their descriptions.
"""

from typing import List

from musicmatch.commands.base import Command, CommandContext


class HelpCommand(Command):
    """Exibe a documentação de todos os comandos registrados no sistema."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/help"
        self._description = "Exibe esta lista de comandos disponíveis e instruções de uso."
        self._aliases = ["/ajuda", "/h", "/?"]
        self._default_error_messages = {
            "usage": "Uso: /help (não requer argumentos adicionais).",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        commands = ctx.registry.get_all_commands()
        ctx.ui.render_help(commands)
        return True
