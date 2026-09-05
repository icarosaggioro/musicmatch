"""Módulo de Comandos Estruturados (Command Pattern) do Harness."""

from musicmatch.commands.base import Command, CommandContext
from musicmatch.commands.registry import CommandRegistry

__all__ = ["Command", "CommandContext", "CommandRegistry"]
