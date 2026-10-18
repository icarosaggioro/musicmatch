"""Unit tests for the unified /library command incorporating /status (ADR 0012/0013)."""

from unittest.mock import MagicMock, call
import pytest

from musicmatch.commands.base import CommandContext
from musicmatch.commands.library import LibraryCommand
from musicmatch.commands.registry import CommandRegistry


@pytest.fixture
def mock_ctx():
    ctx = CommandContext(
        ui=MagicMock(),
        agent=MagicMock(),
        db=MagicMock(),
        registry=None,
    )
    ctx.agent.model_name = "gemini-3.6-flash"
    ctx.db.count.return_value = 10
    ctx.db.get_stats.return_value = {
        "total_duration_hours": 2.5,
        "avg_bpm": 128.0,
        "db_size_kb": 64.0,
    }
    return ctx


def test_library_aliases_include_lib():
    cmd = LibraryCommand()
    aliases = cmd.get_aliases()
    assert "/lib" in aliases
    assert "/biblioteca" in aliases


def test_library_combined_output_status_first_then_library_info(mock_ctx):
    cmd = LibraryCommand()
    should_continue = cmd.execute([], mock_ctx)
    assert should_continue is True

    # 1. System/Database status must be rendered first
    mock_ctx.ui.render_status.assert_called_once()
    status_dict = mock_ctx.ui.render_status.call_args[0][0]
    assert status_dict["Modelo Gemini Ativo"] == "gemini-3.6-flash"
    assert "10 faixa(s)" in status_dict["Total de Faixas no Banco"]
    assert "2.5 horas" in status_dict["Duração Total"]
    assert "128.0" in status_dict["BPM Médio"]
    assert "64.0 KB" in status_dict["Tamanho do Arquivo .db"]

    # 2. Managed Library status must be rendered second
    mock_ctx.ui.render_library_status.assert_called_once()
    lib_dict = mock_ctx.ui.render_library_status.call_args[0][0]
    assert "Caminho Base" in lib_dict
    assert "Acesso de Escrita" in lib_dict
    assert "Estrutura Padrão" in lib_dict

    # 3. Verify ordering: render_status must be called before render_library_status
    status_call_idx = None
    library_call_idx = None
    for idx, mock_call in enumerate(mock_ctx.ui.method_calls):
        if mock_call[0] == "render_status":
            status_call_idx = idx
        elif mock_call[0] == "render_library_status":
            library_call_idx = idx

    assert status_call_idx is not None
    assert library_call_idx is not None
    assert status_call_idx < library_call_idx


def test_library_status_subcommand_shows_combined_output(mock_ctx):
    cmd = LibraryCommand()
    should_continue = cmd.execute(["status"], mock_ctx)
    assert should_continue is True

    mock_ctx.ui.render_status.assert_called_once()
    mock_ctx.ui.render_library_status.assert_called_once()


def test_library_dispatched_via_lib_and_library(mock_ctx):
    registry = CommandRegistry()
    mock_ctx.registry = registry

    # /lib
    assert registry.is_command("/lib") is True
    res_lib = registry.dispatch("/lib", mock_ctx)
    assert res_lib is True
    assert mock_ctx.ui.render_status.call_count == 1
    assert mock_ctx.ui.render_library_status.call_count == 1

    # /library
    assert registry.is_command("/library") is True
    res_lib2 = registry.dispatch("/library", mock_ctx)
    assert res_lib2 is True
    assert mock_ctx.ui.render_status.call_count == 2
    assert mock_ctx.ui.render_library_status.call_count == 2


def test_status_command_delegates_to_library_combined_view(mock_ctx):
    registry = CommandRegistry()
    mock_ctx.registry = registry

    # /status
    assert registry.is_command("/status") is True
    res_status = registry.dispatch("/status", mock_ctx)
    assert res_status is True
    assert mock_ctx.ui.render_status.call_count == 1
    assert mock_ctx.ui.render_library_status.call_count == 1


def test_list_command_remains_independent_and_paginated(mock_ctx):
    registry = CommandRegistry()
    mock_ctx.registry = registry
    mock_ctx.db.count.return_value = 2
    t1 = MagicMock(title="T1", file_path="C:/1.mp3")
    t2 = MagicMock(title="T2", file_path="C:/2.mp3")
    mock_ctx.db.get_all_tracks.return_value = [t1, t2]

    # /list must NOT touch render_status or render_library_status
    should_continue = registry.dispatch("/list", mock_ctx)
    assert should_continue is True
    mock_ctx.ui.render_track_page.assert_called_once_with([t1, t2], 1, 1, 2, start_idx=1)
    mock_ctx.ui.render_info.assert_called_with("Fim da listagem.")
    assert mock_ctx.ui.render_status.call_count == 0
    assert mock_ctx.ui.render_library_status.call_count == 0
