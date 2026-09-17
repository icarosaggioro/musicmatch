"""Structured Command Pattern subsystem for the MusicMatch REPL Harness."""

from musicmatch.commands.base import Command, CommandContext
from musicmatch.commands.clear import ClearCommand
from musicmatch.commands.download import DownloadCommand
from musicmatch.commands.exit import ExitCommand
from musicmatch.commands.help import HelpCommand
from musicmatch.commands.library import LibraryCommand
from musicmatch.commands.list import ListCommand
from musicmatch.commands.promote import PromoteCommand
from musicmatch.commands.registry import CommandRegistry
from musicmatch.commands.scan import ScanCommand
from musicmatch.commands.search import SearchCommand
from musicmatch.commands.staging import StagingCommand
from musicmatch.commands.status import StatusCommand

__all__ = [
    "Command",
    "CommandContext",
    "CommandRegistry",
    "ClearCommand",
    "DownloadCommand",
    "ExitCommand",
    "HelpCommand",
    "LibraryCommand",
    "ListCommand",
    "PromoteCommand",
    "ScanCommand",
    "SearchCommand",
    "StagingCommand",
    "StatusCommand",
]
