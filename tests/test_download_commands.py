"""Integration and unit tests for /download, /staging, and /library CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from musicmatch.commands.base import CommandContext
from musicmatch.commands.download import DownloadCommand
from musicmatch.commands.library import LibraryCommand
from musicmatch.commands.staging import StagingCommand
from musicmatch.domain.staging import DownloadSessionManifest, StagedTrack


@pytest.fixture
def mock_context():
    ctx = CommandContext(
        ui=MagicMock(),
        agent=MagicMock(),
        db=MagicMock(),
        registry=MagicMock(),
    )
    return ctx


# ==============================================================================
# /download Command Tests
# ==============================================================================

def test_download_no_args(mock_context):
    cmd = DownloadCommand()
    assert cmd.execute([], mock_context) is True
    mock_context.ui.render_error.assert_called_once()
    assert "Uso incorreto" in mock_context.ui.render_error.call_args[0][0]


def test_download_direct_url_success(mock_context):
    cmd = DownloadCommand()
    mock_manifest = DownloadSessionManifest(
        session_id="session_test_123",
        created_at="2026-09-13T20:00:00Z",
        query_or_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        status="ACTIVE",
        tracks=[],
    )
    mock_track = StagedTrack(
        id="stg_dQw4w9WgXcQ",
        title="Never Gonna Give You Up",
        artist="Rick Astley",
        duration_seconds=213.0,
        source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        file_path="C:/staging/test.m4a",
        file_size=5000000,
        format="m4a",
    )

    with patch("musicmatch.commands.download.audio_downloader_service") as mock_service:
        mock_service.create_session.return_value = mock_manifest
        mock_service.download_track.return_value = mock_track

        res = cmd.execute(["https://www.youtube.com/watch?v=dQw4w9WgXcQ"], mock_context)
        assert res is True

        mock_service.create_session.assert_called_once_with("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        mock_service.download_track.assert_called_once_with(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            session_id="session_test_123",
            format_preference="native",
        )
        mock_context.ui.render_success.assert_called_once()
        assert "Rick Astley" in mock_context.ui.render_success.call_args[0][0]


def test_download_direct_url_with_mp3_format(mock_context):
    cmd = DownloadCommand()
    mock_manifest = DownloadSessionManifest(
        session_id="session_mp3",
        created_at="2026-09-13T20:00:00Z",
        query_or_url="https://www.youtube.com/watch?v=123",
        status="ACTIVE",
    )
    mock_track = StagedTrack(
        id="stg_123",
        title="Song",
        artist="Artist",
        source_url="https://www.youtube.com/watch?v=123",
        file_path="C:/staging/123.mp3",
        format="mp3",
    )

    with patch("musicmatch.commands.download.audio_downloader_service") as mock_service:
        mock_service.create_session.return_value = mock_manifest
        mock_service.download_track.return_value = mock_track

        cmd.execute(["https://www.youtube.com/watch?v=123", "--format", "mp3"], mock_context)
        mock_service.download_track.assert_called_once_with(
            url="https://www.youtube.com/watch?v=123",
            session_id="session_mp3",
            format_preference="mp3",
        )


def test_download_direct_url_failure(mock_context):
    cmd = DownloadCommand()
    mock_manifest = DownloadSessionManifest(
        session_id="session_fail",
        created_at="2026-09-13T20:00:00Z",
        query_or_url="https://www.youtube.com/watch?v=fail",
        status="ACTIVE",
    )

    with patch("musicmatch.commands.download.audio_downloader_service") as mock_service:
        mock_service.create_session.return_value = mock_manifest
        mock_service.download_track.side_effect = RuntimeError("Network error")

        res = cmd.execute(["https://www.youtube.com/watch?v=fail"], mock_context)
        assert res is True
        mock_context.ui.render_error.assert_called_once()
        assert "Network error" in mock_context.ui.render_error.call_args[0][0]


def test_download_search_query_no_results(mock_context):
    cmd = DownloadCommand()
    with patch("musicmatch.commands.download.audio_downloader_service") as mock_service:
        mock_service.search_candidates.return_value = []

        res = cmd.execute(["some", "obscure", "song"], mock_context)
        assert res is True
        mock_context.ui.render_warning.assert_called_once()
        assert "Nenhum resultado" in mock_context.ui.render_warning.call_args[0][0]


def test_download_search_query_user_cancels(mock_context, monkeypatch):
    cmd = DownloadCommand()
    candidates = [
        {"title": "Track 1", "channel": "Artist", "duration": 180, "url": "https://yt.com/1"},
    ]

    with patch("musicmatch.commands.download.audio_downloader_service") as mock_service:
        mock_service.search_candidates.return_value = candidates
        monkeypatch.setattr("builtins.input", lambda _: "0")

        res = cmd.execute(["Queen"], mock_context)
        assert res is True
        mock_context.ui.render_search_candidates.assert_called_once_with(candidates)
        mock_context.ui.render_info.assert_any_call("Download cancelado.")
        mock_service.download_track.assert_not_called()


def test_download_search_query_valid_selection(mock_context, monkeypatch):
    cmd = DownloadCommand()
    candidates = [
        {"title": "Track 1", "channel": "Artist", "duration": 180, "url": "https://yt.com/1"},
        {"title": "Track 2", "channel": "Artist", "duration": 200, "url": "https://yt.com/2"},
    ]
    mock_manifest = DownloadSessionManifest(
        session_id="session_chosen",
        created_at="2026-09-13T20:00:00Z",
        query_or_url="https://yt.com/2",
        status="ACTIVE",
    )
    mock_track = StagedTrack(
        id="stg_2",
        title="Track 2 Clean",
        artist="Artist",
        source_url="https://yt.com/2",
        file_path="C:/staging/2.m4a",
        format="m4a",
    )

    with patch("musicmatch.commands.download.audio_downloader_service") as mock_service:
        mock_service.search_candidates.return_value = candidates
        mock_service.create_session.return_value = mock_manifest
        mock_service.download_track.return_value = mock_track
        monkeypatch.setattr("builtins.input", lambda _: "2")

        res = cmd.execute(["Queen"], mock_context)
        assert res is True
        mock_service.create_session.assert_called_once_with("https://yt.com/2")
        mock_service.download_track.assert_called_once_with(
            url="https://yt.com/2",
            session_id="session_chosen",
            format_preference="native",
        )
        mock_context.ui.render_success.assert_called_once()


def test_download_search_query_invalid_selection(mock_context, monkeypatch):
    cmd = DownloadCommand()
    candidates = [{"title": "Track 1", "url": "https://yt.com/1"}]

    with patch("musicmatch.commands.download.audio_downloader_service") as mock_service:
        mock_service.search_candidates.return_value = candidates
        monkeypatch.setattr("builtins.input", lambda _: "abc")

        cmd.execute(["Queen"], mock_context)
        mock_context.ui.render_error.assert_called_once()
        assert "Entrada inválida" in mock_context.ui.render_error.call_args[0][0]


# ==============================================================================
# /staging Command Tests
# ==============================================================================

def test_staging_list(mock_context):
    cmd = StagingCommand()
    with patch("musicmatch.commands.staging.audio_downloader_service") as mock_service:
        mock_service.list_active_sessions.return_value = []
        res = cmd.execute([], mock_context)
        assert res is True
        mock_service.list_active_sessions.assert_called_once()
        mock_context.ui.render_staging_sessions.assert_called_once_with([])


def test_staging_show_missing_arg(mock_context):
    cmd = StagingCommand()
    cmd.execute(["show"], mock_context)
    mock_context.ui.render_error.assert_called_once()
    assert "Especifique o ID da sessão" in mock_context.ui.render_error.call_args[0][0]


def test_staging_show_not_found(mock_context):
    cmd = StagingCommand()
    with patch("musicmatch.commands.staging.audio_downloader_service") as mock_service:
        mock_service.get_session.return_value = None
        cmd.execute(["show", "nonexistent"], mock_context)
        mock_context.ui.render_error.assert_called_once()
        assert "não encontrada" in mock_context.ui.render_error.call_args[0][0]


def test_staging_show_success(mock_context):
    cmd = StagingCommand()
    manifest = DownloadSessionManifest(
        session_id="session_valid",
        created_at="2026-09-13T20:00:00Z",
        query_or_url="query",
        status="ACTIVE",
    )
    with patch("musicmatch.commands.staging.audio_downloader_service") as mock_service:
        mock_service.get_session.return_value = manifest
        cmd.execute(["show", "session_valid"], mock_context)
        mock_context.ui.render_staging_detail.assert_called_once_with(manifest)


def test_staging_discard_success(mock_context):
    cmd = StagingCommand()
    with patch("musicmatch.commands.staging.audio_downloader_service") as mock_service:
        mock_service.discard_session.return_value = True
        cmd.execute(["discard", "session_del"], mock_context)
        mock_service.discard_session.assert_called_once_with("session_del")
        mock_context.ui.render_success.assert_called_once()


def test_staging_discard_not_found(mock_context):
    cmd = StagingCommand()
    with patch("musicmatch.commands.staging.audio_downloader_service") as mock_service:
        mock_service.discard_session.return_value = False
        cmd.execute(["discard", "session_del"], mock_context)
        mock_context.ui.render_error.assert_called_once()


def test_staging_unknown_subcommand(mock_context):
    cmd = StagingCommand()
    cmd.execute(["foobar"], mock_context)
    mock_context.ui.render_error.assert_called_once()
    assert "não reconhecido" in mock_context.ui.render_error.call_args[0][0]


# ==============================================================================
# /library Command Tests
# ==============================================================================

def test_library_path_display(mock_context):
    cmd = LibraryCommand()
    with patch("musicmatch.commands.library.library_location_manager") as mock_mgr:
        mock_mgr.resolve_library_path.return_value = Path("C:/Music/MusicMatch")
        mock_mgr.validate_and_probe_path.return_value = Path("C:/Music/MusicMatch")

        res = cmd.execute([], mock_context)
        assert res is True
        mock_context.ui.render_library_status.assert_called_once()
        status = mock_context.ui.render_library_status.call_args[0][0]
        assert "C:/Music/MusicMatch" in status["Caminho Base"]
        assert "Permitido (OK)" in status["Acesso de Escrita"]


def test_library_set_path_missing_arg(mock_context):
    cmd = LibraryCommand()
    cmd.execute(["set-path"], mock_context)
    mock_context.ui.render_error.assert_called_once()
    assert "Especifique o novo caminho" in mock_context.ui.render_error.call_args[0][0]


def test_library_set_path_success(mock_context, tmp_path):
    cmd = LibraryCommand()
    target_dir = tmp_path / "MyLibrary"
    with patch("musicmatch.commands.library.library_location_manager") as mock_mgr:
        mock_mgr.set_library_path.return_value = target_dir

        res = cmd.execute(["set-path", str(target_dir)], mock_context)
        assert res is True
        mock_mgr.set_library_path.assert_called_once_with(target_dir)
        mock_context.ui.render_success.assert_called_once()


def test_library_set_path_validation_error(mock_context):
    cmd = LibraryCommand()
    with patch("musicmatch.commands.library.library_location_manager") as mock_mgr:
        mock_mgr.set_library_path.side_effect = ValueError("Root drive disallowed")

        res = cmd.execute(["set-path", "C:\\"], mock_context)
        assert res is True
        mock_context.ui.render_error.assert_called_once()
        assert "Root drive disallowed" in mock_context.ui.render_error.call_args[0][0]


def test_library_unknown_subcommand(mock_context):
    cmd = LibraryCommand()
    cmd.execute(["foobar"], mock_context)
    mock_context.ui.render_error.assert_called_once()
    assert "não reconhecido" in mock_context.ui.render_error.call_args[0][0]
