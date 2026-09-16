"""Command Registry and Dispatcher.

Follows the Command Pattern:
- Central registry mapping input keywords and aliases to Command instances via unified O(1) hashmap.
- Bootstraps all default commands deterministically upon initialization.
- Guarantees alphabetical ordering of commands in help catalog output.
"""

import shlex
from typing import Dict, List, Optional

from musicmatch.commands.base import Command, CommandContext
from musicmatch.commands.clear import ClearCommand
from musicmatch.commands.download import DownloadCommand
from musicmatch.commands.exit import ExitCommand
from musicmatch.commands.help import HelpCommand
from musicmatch.commands.library import LibraryCommand
from musicmatch.commands.list import ListCommand
from musicmatch.commands.promote import PromoteCommand
from musicmatch.commands.scan import ScanCommand
from musicmatch.commands.search import SearchCommand
from musicmatch.commands.staging import StagingCommand
from musicmatch.commands.status import StatusCommand


class CommandRegistry:
    """Catálogo central onde comandos são registrados, consultados e despachados."""

    def __init__(self) -> None:
        self._commands: Dict[str, Command] = {}
        self._alias_map: Dict[str, Command] = {}
        # Unified O(1) hashmap indexing canonical trigger names and all aliases directly to Command instances
        self._lookup_map: Dict[str, Command] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Registra os comandos padrão do sistema no início dos tempos."""
        defaults: List[Command] = [
            ClearCommand(),
            DownloadCommand(),
            ExitCommand(),
            HelpCommand(),
            LibraryCommand(),
            ListCommand(),
            PromoteCommand(),
            ScanCommand(),
            SearchCommand(),
            StagingCommand(),
            StatusCommand(),
        ]
        for cmd in defaults:
            self.register(cmd)

    def register(self, command: Command) -> None:
        """Registra um novo comando no catálogo e indexa no hashmap unificado."""
        canonical_key = command.get_name().lower()
        self._commands[canonical_key] = command
        self._lookup_map[canonical_key] = command

        for alias in command.get_aliases():
            alias_key = alias.lower()
            self._alias_map[alias_key] = command
            self._lookup_map[alias_key] = command

    @property
    def lookup_map(self) -> Dict[str, Command]:
        """Retorna o hashmap unificado de palavras-chave/aliases para instâncias de comandos."""
        return self._lookup_map

    def get_all_commands(self) -> List[Command]:
        """Retorna a lista de todos os comandos registrados em ordem alfabética estrita."""
        unique_commands = list(self._commands.values())
        return sorted(unique_commands, key=lambda c: c.get_name().lower())

    def is_command(self, raw_input: str) -> bool:
        """Verifica se a entrada do usuário deve ser tratada como um comando do sistema.

        Critério:
        - O primeiro token coincide com uma chave do hashmap unificado (nome ou alias).
        - Ou inicia com '/' (qualquer slash command cadastrado ou desconhecido).
        """
        cleaned = raw_input.strip()
        if not cleaned:
            return False

        first_token = cleaned.split()[0].lower()
        if first_token in self._lookup_map:
            return True

        return cleaned.startswith("/")

    def dispatch(self, raw_input: str, ctx: CommandContext) -> bool:
        """Processa e executa um comando a partir da linha digitada pelo usuário via hashmap O(1).

        Returns:
            bool: True para manter o loop rodando; False para encerrar o REPL.
        """
        try:
            tokens = shlex.split(raw_input)
        except ValueError:
            tokens = raw_input.split()

        if not tokens:
            return True

        trigger = tokens[0].lower()
        args = tokens[1:]

        # O(1) direct lookup from the unified keyword/alias hashmap
        command = self._lookup_map.get(trigger)

        if not command:
            ctx.ui.render_error(f"Comando '{trigger}' não reconhecido.")
            ctx.ui.render_info("Digite '/help' para visualizar a lista de comandos disponíveis.")
            return True

        return command.execute(args, ctx)
