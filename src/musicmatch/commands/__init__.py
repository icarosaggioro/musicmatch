"""Structured Command Pattern subsystem for the MusicMatch REPL Harness."""

from musicmatch.commands.analyze import AnalyzeCommand
from musicmatch.commands.base import Command, CommandContext
from musicmatch.commands.clear import ClearCommand
from musicmatch.commands.download import DownloadCommand
from musicmatch.commands.exit import ExitCommand
from musicmatch.commands.help import HelpCommand
from musicmatch.commands.issue import IssueCommand, IssueDeleteCommand, IssueDismissCommand
from musicmatch.commands.library import LibraryCommand
from musicmatch.commands.list import ListCommand
from musicmatch.commands.model import ModelCommand
from musicmatch.commands.player import (
    NextCommand,
    PauseCommand,
    PlayCommand,
    QueueAddCommand,
    QueueAddLastCommand,
    QueueClearCommand,
    QueueCommand,
    QueueConsumeCommand,
    QueuePlayCommand,
    QueueRemoveCommand,
    QueueRepeatCommand,
    QueueShuffleCommand,
    QueueSortCommand,
    StopCommand,
    VolumeCommand,
)
from musicmatch.commands.playlist import (
    PlaylistCommand,
    PlaylistDeleteCommand,
    PlaylistDeleteWithTracksCommand,
    PlaylistExportCommand,
    PlaylistImportCommand,
    PlaylistLoadCommand,
    PlaylistRemoveCommand,
    PlaylistRenameCommand,
    PlaylistSaveCommand,
)
from musicmatch.commands.promote import PromoteCommand
from musicmatch.commands.registry import CommandRegistry
from musicmatch.commands.scan import ScanCommand
from musicmatch.commands.search import SearchCommand
from musicmatch.commands.staging import StagingCommand
from musicmatch.commands.status import StatusCommand

__all__ = [
    "AnalyzeCommand",
    "Command",
    "CommandContext",
    "CommandRegistry",
    "ClearCommand",
    "DownloadCommand",
    "ExitCommand",
    "HelpCommand",
    "IssueCommand",
    "IssueDeleteCommand",
    "IssueDismissCommand",
    "LibraryCommand",
    "ListCommand",
    "ModelCommand",
    "NextCommand",
    "PauseCommand",
    "PlayCommand",
    "PlaylistCommand",
    "PlaylistDeleteCommand",
    "PlaylistDeleteWithTracksCommand",
    "PlaylistExportCommand",
    "PlaylistImportCommand",
    "PlaylistLoadCommand",
    "PlaylistRemoveCommand",
    "PlaylistRenameCommand",
    "PlaylistSaveCommand",
    "PromoteCommand",
    "QueueAddCommand",
    "QueueAddLastCommand",
    "QueueClearCommand",
    "QueueCommand",
    "QueueConsumeCommand",
    "QueuePlayCommand",
    "QueueRemoveCommand",
    "QueueRepeatCommand",
    "QueueShuffleCommand",
    "QueueSortCommand",
    "ScanCommand",
    "SearchCommand",
    "StagingCommand",
    "StatusCommand",
    "StopCommand",
    "VolumeCommand",
]
