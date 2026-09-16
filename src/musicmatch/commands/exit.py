"""Exit Command (/exit).

Gracefully terminates the MusicMatch interactive REPL session.
"""

from typing import Dict, List

from musicmatch.commands.base import Command, CommandContext


class ExitCommand(Command):
    """Encerra a sessão interativa do MusicMatch."""

    def __init__(self) -> None:
        super().__init__(
            name="/exit",
            description="Encerra a aplicação MusicMatch.",
            aliases=["sair", "exit", "quit", "q", "/sair", "/quit", "/q"],
        )

    def get_name(self) -> str:
        return "/exit"

    def get_aliases(self) -> List[str]:
        return ["sair", "exit", "quit", "q", "/sair", "/quit", "/q"]

    def get_description(self) -> str:
        return "Encerra a aplicação MusicMatch."

    def get_default_error_messages(self) -> Dict[str, str]:
        return {
            "usage": "Uso: /exit ou palavras de encerramento ('sair', 'quit', 'q').",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        ctx.ui.render_goodbye()
        return False
