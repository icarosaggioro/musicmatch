"""Exit Command (/exit).

Gracefully terminates the MusicMatch interactive REPL session.
"""

from typing import List

from musicmatch.commands.base import Command, CommandContext


class ExitCommand(Command):
    """Encerra a sessão interativa do MusicMatch."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/exit"
        self._description = "Encerra a aplicação MusicMatch."
        self._aliases = ["sair", "exit", "quit", "q", "/sair", "/quit", "/q"]
        self._default_error_messages = {
            "usage": "Uso: /exit ou palavras de encerramento ('sair', 'quit', 'q').",
        }

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        ctx.ui.render_goodbye()
        return False
