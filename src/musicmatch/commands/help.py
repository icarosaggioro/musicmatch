"""Help Command (/help).

Displays the formatted catalog of all registered commands and their descriptions.
"""

from typing import Dict, List

from musicmatch.commands.base import Command, CommandContext


class HelpCommand(Command):
    """Exibe a documentação de todos os comandos registrados no sistema."""

    def __init__(self) -> None:
        super().__init__(
            name="/help",
            description="Exibe esta lista de comandos disponíveis e instruções de uso.",
            aliases=["/ajuda", "/h", "/?"],
        )

    def get_name(self) -> str:
        return "/help"

    def get_aliases(self) -> List[str]:
        return ["/ajuda", "/h", "/?"]

    def get_description(self) -> str:
        return "Exibe esta lista de comandos disponíveis e instruções de uso."

    def get_default_error_messages(self) -> Dict[str, str]:
        return {
            "usage": "Uso: /help (não requer argumentos adicionais).",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        commands = ctx.registry.get_all_commands()
        ctx.ui.render_help(commands)
        return True
