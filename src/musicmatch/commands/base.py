"""Command Design Pattern for the MusicMatch REPL Harness.

Follows the Command Pattern:
- Encapsulates each user action in an isolated object.
- Defines and implements standard getters for name, aliases, description, and default error messages.
- Subclasses assign values to internal members (_name, _description, _aliases, _default_error_messages).
- Supports explicit dependency injection via CommandContext.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CommandContext:
    """Shared execution context provided to all commands.

    Attributes:
        ui: Console UI renderer instance for displaying messages and prompts.
        agent: AI Agent instance for intelligent queries or verification.
        db: SQLite or mock database repository instance.
        registry: Reference to the CommandRegistry catalog (e.g. consumed by /help).
    """

    ui: Any
    agent: Any
    db: Any
    registry: Any


class Command(ABC):
    """Abstract base class for all system control commands."""

    def __init__(
        self,
        name: str = "",
        description: str = "",
        aliases: Optional[List[str]] = None,
        default_error_messages: Optional[Dict[str, str]] = None,
    ) -> None:
        self._name: str = name
        self._description: str = description
        self._aliases: List[str] = aliases or []
        self._default_error_messages: Dict[str, str] = default_error_messages or {}

    def get_name(self) -> str:
        """Returns the canonical command identifier (e.g. '/help')."""
        return self._name

    def get_aliases(self) -> List[str]:
        """Returns alternate keywords or shortcut aliases (e.g. ['sair', 'exit', 'quit', 'q'])."""
        return list(self._aliases)

    def get_description(self) -> str:
        """Returns human-readable description displayed in the help menu."""
        return self._description

    def get_default_error_messages(self) -> Dict[str, str]:
        """Returns a mapping of standard error messages and usage guidance for this command."""
        if self._default_error_messages:
            return dict(self._default_error_messages)
        name = self.get_name()
        return {
            "usage": f"Uso incorreto do comando '{name}'. Digite '/help' para visualizar instruções.",
            "invalid_args": f"Argumentos inválidos para '{name}'.",
        }

    @property
    def name(self) -> str:
        """Property for backward compatibility and clean attribute access."""
        return self.get_name()

    @property
    def aliases(self) -> List[str]:
        """Property for backward compatibility and clean attribute access."""
        return self.get_aliases()

    @property
    def description(self) -> str:
        """Property for backward compatibility and clean attribute access."""
        return self.get_description()

    @property
    def default_error_messages(self) -> Dict[str, str]:
        """Property for backward compatibility and clean attribute access."""
        return self.get_default_error_messages()

    @abstractmethod
    def execute(self, args: List[str], ctx: CommandContext) -> bool:
        """Executes the command logic.

        Args:
            args: Positional argument tokens passed after the command name.
            ctx: Execution context providing UI, Database, Agent, and Registry access.

        Returns:
            bool: True to keep REPL event loop running; False to request application exit.
        """
        pass
