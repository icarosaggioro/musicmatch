"""Unit tests for Library Maintenance Commands (ADR 0013 and ADR 0009)."""

from unittest.mock import MagicMock, patch
import pytest

from musicmatch.commands.base import CommandContext
from musicmatch.commands.registry import CommandRegistry
from musicmatch.domain.models import Track


@pytest.fixture
def mock_maintenance_context():
    ctx = CommandContext(
        ui=MagicMock(),
        agent=MagicMock(),
        db=MagicMock(),
        registry=None,
    )
    ctx.agent.model_name = "gemini-3.6-flash"
    ctx.db.count.return_value = 10
    return ctx


def test_registry_registers_maintenance_commands():
    registry = CommandRegistry()
    names = [c.name for c in registry.get_all_commands()]
    assert "/audit" in names
    assert "/delete" in names
    assert "/prune" in names
    assert "/retag" in names
    assert "/unindex" in names


def test_prune_command_requires_passphrase(mock_maintenance_context, monkeypatch):
    from musicmatch.commands.prune import PruneCommand

    cmd = PruneCommand()

    # Wrong passphrase aborts
    monkeypatch.setattr("builtins.input", lambda prompt="": "WRONG_PASSPHRASE")
    cmd.execute([], mock_maintenance_context)
    mock_maintenance_context.ui.render_error.assert_called_with("Frase de segurança incorreta. Operação cancelada.")

    # Correct passphrase PLEASEPRETTYPLEASE succeeds
    mock_maintenance_context.ui.reset_mock()
    monkeypatch.setattr("builtins.input", lambda prompt="": "PLEASEPRETTYPLEASE")
    with patch("musicmatch.services.maintenance.library_maintenance_service.purge_missing_tracks", return_value=5):
        cmd.execute([], mock_maintenance_context)
        mock_maintenance_context.ui.render_success.assert_called_with("5 faixa(s) 'MISSING' expurgada(s) do catálogo.")


def test_unindex_single_track_confirmation(mock_maintenance_context, monkeypatch):
    from musicmatch.commands.unindex import UnindexCommand

    t = Track(
        id="trk_u1",
        title="Unindex Me",
        artist="Artist",
        album="Album",
        genre="Rock",
        duration_seconds=100.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path="C:/Music/u1.mp3",
    )
    mock_maintenance_context.db.get_track.return_value = t

    cmd = UnindexCommand()

    # Decline confirmation
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    cmd.execute(["trk_u1"], mock_maintenance_context)
    mock_maintenance_context.ui.render_info.assert_called_with("Operação cancelada pelo usuário.")

    # Accept confirmation
    mock_maintenance_context.ui.reset_mock()
    monkeypatch.setattr("builtins.input", lambda prompt="": "s")
    with patch("musicmatch.services.maintenance.library_maintenance_service.unindex_tracks", return_value=1):
        cmd.execute(["trk_u1"], mock_maintenance_context)
        mock_maintenance_context.ui.render_success.assert_called_with("Faixa 'trk_u1' desindexada com sucesso (arquivo físico preservado).")


def test_unindex_batch_count_verification_gate(mock_maintenance_context, monkeypatch):
    from musicmatch.commands.unindex import UnindexCommand

    cmd = UnindexCommand()

    t1 = Track(
        id="trk_m1",
        title="M1",
        artist="Artist",
        album="Album",
        genre="Rock",
        duration_seconds=100.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path="C:/Music/m1.mp3",
        status="MISSING",
    )
    t2 = Track(
        id="trk_m2",
        title="M2",
        artist="Artist",
        album="Album",
        genre="Rock",
        duration_seconds=100.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path="C:/Music/m2.mp3",
        status="MISSING",
    )
    mock_maintenance_context.db.get_all_tracks.return_value = [t1, t2]

    # Typing wrong number fails count verification gate
    monkeypatch.setattr("builtins.input", lambda prompt="": "99")
    cmd.execute(["--missing"], mock_maintenance_context)
    mock_maintenance_context.ui.render_error.assert_called_with("Contagem incorreta. Operação cancelada.")

    # Typing exact count '2' passes gate
    mock_maintenance_context.ui.reset_mock()
    monkeypatch.setattr("builtins.input", lambda prompt="": "2")
    with patch("musicmatch.services.maintenance.library_maintenance_service.unindex_tracks", return_value=2):
        cmd.execute(["--missing"], mock_maintenance_context)
        mock_maintenance_context.ui.render_success.assert_called_with("2 faixa(s) desindexada(s) com sucesso.")


def test_delete_command_external_storage_warning_and_gate(mock_maintenance_context, monkeypatch):
    from musicmatch.commands.delete import DeleteCommand

    cmd = DeleteCommand()

    # Track located outside Managed Library
    t = Track(
        id="trk_ext",
        title="External Track",
        artist="Artist",
        album="Album",
        genre="Rock",
        duration_seconds=100.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path="D:/External/track.mp3",
    )
    mock_maintenance_context.db.get_track.return_value = t

    # Accept confirmation
    monkeypatch.setattr("builtins.input", lambda prompt="": "s")
    with patch("musicmatch.services.maintenance.library_maintenance_service.delete_tracks_to_trash", return_value=(1, [])):
        cmd.execute(["trk_ext"], mock_maintenance_context)
        # Warning for external storage must be rendered
        assert mock_maintenance_context.ui.render_warning.called
        mock_maintenance_context.ui.render_success.assert_called_with("Faixa 'trk_ext' movida para a Lixeira e desindexada.")


def test_retag_command(mock_maintenance_context):
    from musicmatch.commands.retag import RetagCommand

    cmd = RetagCommand()
    t = Track(
        id="trk_r1",
        title="Old Title",
        artist="Old Artist",
        album="Old Album",
        genre="Old Genre",
        duration_seconds=100.0,
        bitrate_kbps=320,
        bpm=120.0,
        file_path="C:/Music/r1.mp3",
    )
    mock_maintenance_context.db.get_track.return_value = t

    with patch("musicmatch.services.maintenance.library_maintenance_service.retag_track", return_value=t):
        cmd.execute(["trk_r1", "--title", "New Title", "--artist", "New Artist"], mock_maintenance_context)
        mock_maintenance_context.ui.render_success.assert_called_with("Tags da faixa 'trk_r1' atualizadas com sucesso.")


def test_library_clear_subcommand(mock_maintenance_context, monkeypatch):
    from musicmatch.commands.library import LibraryCommand

    cmd = LibraryCommand()

    # User confirms clear
    monkeypatch.setattr("builtins.input", lambda prompt="": "s")
    cmd.execute(["clear"], mock_maintenance_context)
    mock_maintenance_context.db.clear.assert_called_once()
    mock_maintenance_context.ui.render_success.assert_called_with("Biblioteca limpa com sucesso! O catálogo agora está vazio.")

