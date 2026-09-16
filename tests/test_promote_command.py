"""Unit and integration tests for /promote and /staging promote commands."""

from unittest.mock import MagicMock, patch
import pytest

from musicmatch.commands.base import CommandContext
from musicmatch.commands.promote import PromoteCommand
from musicmatch.commands.staging import StagingCommand
from musicmatch.domain.staging import DownloadSessionManifest, PromotionResult, StagedTrack


@pytest.fixture
def mock_context():
    return CommandContext(
        ui=MagicMock(),
        agent=MagicMock(),
        db=MagicMock(),
        registry=MagicMock(),
    )


def test_promote_no_args(mock_context):
    cmd = PromoteCommand()
    assert cmd.execute([], mock_context) is True
    mock_context.ui.render_error.assert_called_once()
    assert "Uso incorreto" in mock_context.ui.render_error.call_args[0][0]


def test_promote_session_not_found(mock_context):
    cmd = PromoteCommand()
    with patch("musicmatch.commands.promote.audio_downloader_service") as mock_downloader:
        mock_downloader.get_session.return_value = None

        assert cmd.execute(["session_nonexistent"], mock_context) is True
        mock_context.ui.render_error.assert_called_once()
        assert "não encontrada" in mock_context.ui.render_error.call_args[0][0]


def test_promote_session_already_promoted(mock_context):
    cmd = PromoteCommand()
    track = StagedTrack(
        id="stg_1",
        title="Song",
        artist="Artist",
        source_url="https://youtube.com/1",
        file_path="C:/1.m4a",
        promoted=True,
    )
    manifest = DownloadSessionManifest(
        session_id="session_done",
        created_at="2026-09-14T00:00:00Z",
        query_or_url="query",
        status="RESOLVED",
        tracks=[track],
    )

    with patch("musicmatch.commands.promote.audio_downloader_service") as mock_downloader:
        mock_downloader.get_session.return_value = manifest

        assert cmd.execute(["session_done"], mock_context) is True
        mock_context.ui.render_info.assert_called_once()
        assert "já foram promovidas" in mock_context.ui.render_info.call_args[0][0]


def test_promote_single_track_in_session_auto_promotion(mock_context):
    cmd = PromoteCommand()
    track = StagedTrack(
        id="stg_single",
        title="Bohemian Rhapsody",
        artist="Queen",
        source_url="https://youtube.com/1",
        file_path="C:/1.m4a",
        promoted=False,
    )
    manifest = DownloadSessionManifest(
        session_id="session_1track",
        created_at="2026-09-14T00:00:00Z",
        query_or_url="query",
        status="ACTIVE",
        tracks=[track],
    )
    promo_result = PromotionResult(
        track_id="stg_single",
        source_path="C:/1.m4a",
        destination_path="C:/Music/Queen/Singles/Queen - Bohemian Rhapsody.m4a",
        status="PROMOTED",
    )

    with patch("musicmatch.commands.promote.audio_downloader_service") as mock_downloader, \
         patch("musicmatch.commands.promote.track_promotion_service") as mock_promo_svc:

        mock_downloader.get_session.return_value = manifest
        mock_promo_svc.promote_track.return_value = promo_result

        assert cmd.execute(["session_1track"], mock_context) is True

        mock_promo_svc.promote_track.assert_called_once_with(
            session_id="session_1track",
            track_id_or_idx="stg_single",
            album=None,
            artist=None,
            track_number=None,
            is_compilation=False,
            collection_name=None,
        )
        mock_context.ui.render_promotion_results.assert_called_once_with([promo_result])


def test_promote_multiple_tracks_without_flags_warns_user(mock_context):
    cmd = PromoteCommand()
    t1 = StagedTrack(id="stg_1", title="S1", artist="A1", source_url="u", file_path="p", promoted=False)
    t2 = StagedTrack(id="stg_2", title="S2", artist="A2", source_url="u", file_path="p", promoted=False)
    manifest = DownloadSessionManifest(
        session_id="session_multi",
        created_at="2026-09-14T00:00:00Z",
        query_or_url="query",
        status="ACTIVE",
        tracks=[t1, t2],
    )

    with patch("musicmatch.commands.promote.audio_downloader_service") as mock_downloader:
        mock_downloader.get_session.return_value = manifest

        assert cmd.execute(["session_multi"], mock_context) is True
        mock_context.ui.render_warning.assert_called_once()
        assert "--all" in mock_context.ui.render_warning.call_args[0][0]


def test_promote_all_with_flags(mock_context):
    cmd = PromoteCommand()
    t1 = StagedTrack(id="stg_1", title="S1", artist="A1", source_url="u", file_path="p", promoted=False)
    manifest = DownloadSessionManifest(
        session_id="session_batch",
        created_at="2026-09-14T00:00:00Z",
        query_or_url="query",
        status="ACTIVE",
        tracks=[t1],
    )
    res = PromotionResult(track_id="stg_1", source_path="p", destination_path="dest", status="PROMOTED")

    with patch("musicmatch.commands.promote.audio_downloader_service") as mock_downloader, \
         patch("musicmatch.commands.promote.track_promotion_service") as mock_promo_svc:

        mock_downloader.get_session.return_value = manifest
        mock_promo_svc.promote_session.return_value = [res]

        args = ["session_batch", "--all", "--album", "My Album", "--collection", "Favs", "--va"]
        assert cmd.execute(args, mock_context) is True

        mock_promo_svc.promote_session.assert_called_once_with(
            session_id="session_batch",
            album="My Album",
            artist=None,
            is_compilation=True,
            collection_name="Favs",
        )
        mock_context.ui.render_promotion_results.assert_called_once_with([res])


def test_promote_specific_track_by_index(mock_context):
    cmd = PromoteCommand()
    t1 = StagedTrack(id="stg_1", title="S1", artist="A1", source_url="u", file_path="p", promoted=False)
    manifest = DownloadSessionManifest(
        session_id="session_track",
        created_at="2026-09-14T00:00:00Z",
        query_or_url="query",
        status="ACTIVE",
        tracks=[t1],
    )
    res = PromotionResult(track_id="stg_1", source_path="p", destination_path="dest", status="PROMOTED")

    with patch("musicmatch.commands.promote.audio_downloader_service") as mock_downloader, \
         patch("musicmatch.commands.promote.track_promotion_service") as mock_promo_svc:

        mock_downloader.get_session.return_value = manifest
        mock_promo_svc.promote_track.return_value = res

        args = ["session_track", "--track", "1", "--track-number", "5"]
        assert cmd.execute(args, mock_context) is True

        mock_promo_svc.promote_track.assert_called_once_with(
            session_id="session_track",
            track_id_or_idx=1,
            album=None,
            artist=None,
            track_number=5,
            is_compilation=False,
            collection_name=None,
        )


def test_staging_promote_delegation(mock_context):
    staging_cmd = StagingCommand()
    with patch("musicmatch.commands.promote.PromoteCommand.execute") as mock_execute:
        mock_execute.return_value = True
        res = staging_cmd.execute(["promote", "session_test", "--all"], mock_context)
        assert res is True
        mock_execute.assert_called_once_with(["session_test", "--all"], mock_context)

