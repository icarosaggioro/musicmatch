"""Status Command (/status).

Displays system operational status, active Gemini model, storage backend,
and library statistics, delegating to the unified status view in LibraryCommand.
"""

from typing import List

from musicmatch.commands.base import Command, CommandContext
from musicmatch.commands.library import LibraryCommand


class StatusCommand(Command):
    """Exibe o status operacional do sistema, modelo conectado e biblioteca."""

    def __init__(self) -> None:
        super().__init__()
        self._name = "/status"
        self._description = "Exibe o status operacional do sistema e da biblioteca."
        self._aliases = ["/info"]
        self._default_error_messages = {
            "usage": "Uso: /status (não requer argumentos adicionais).",
        }
        self._library_command = LibraryCommand()

    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        return self._library_command.execute(["status"], ctx)


__all__ = ["StatusCommand"]
