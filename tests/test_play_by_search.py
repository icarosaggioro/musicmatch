"""'/play <search>', '/resume', playback in '/status' and the agent's play_track tool (issue #9)."""

from unittest.mock import MagicMock, patch

import pytest

from musicmatch.agent.core import SingleTurnAgent
from musicmatch.commands.base import CommandContext
from musicmatch.commands.player import PlayCommand, ResumeCommand, playback_summary
from musicmatch.commands.registry import CommandRegistry
from musicmatch.domain.models import Track
from musicmatch.domain.player import PlayerState, PlayerStatus
from musicmatch.harness.loop import Harness
from musicmatch.services.track_lookup import MAX_CANDIDATES, find_track
from musicmatch.storage.playback_store import SQLitePlaybackStore
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from musicmatch.tools import player as player_tool
from musicmatch.tools import play_track


def _track(key, title, artist="Queen", album="Album", path=None, status="AVAILABLE"):
    return Track(id=f"trk_{key:0<64}", title=title, artist=artist, album=album, genre="Rock", duration_seconds=355.0,
                 bitrate_kbps=320, bpm=120.0, file_path=path or f"/music/{key}.mp3", status=status)


@pytest.fixture
def repo():
    r = SQLiteTrackRepository(db_path=":memory:")
    r.insert_batch([
        _track("aaaa1", "Bohemian Rhapsody"),
        _track("aaaa2", "Bohemian Rhapsody (Live)"),
        _track("bbbb1", "Radio Ga Ga"),
        _track("cccc1", "Back in Black", artist="AC/DC"),
        _track("dddd1", "To Be or Not to Be", artist="Mel Brooks"),
        _track("1985f", "Summer Song", artist="Band"),
        _track("eeee1", "1985", artist="Bowling for Soup"),
        _track("eeee2", "Érase una vez", artist="Ana"),
    ])
    yield r
    r.close()


@pytest.fixture
def player():
    mock = MagicMock()
    mock.state = PlayerState.STOPPED
    mock.status.return_value = PlayerStatus(state=PlayerState.STOPPED, volume=80)
    with patch("musicmatch.services.player.get_player_service", return_value=mock):
        yield mock


@pytest.fixture
def ctx(repo):
    return CommandContext(ui=MagicMock(), agent=MagicMock(), db=repo, registry=None)


@pytest.mark.parametrize("ref,title", [
    ("radio", "Radio Ga Ga"),                       # a single match
    ("queen - radio ga ga", "Radio Ga Ga"),         # punctuation is not FTS5 syntax
    ("AC/DC", "Back in Black"),
    ("be or not", "To Be or Not to Be"),            # neither are words like OR and NOT
    ("bohemian rhapsody", "Bohemian Rhapsody"),     # the exact title wins over "(Live)"
    ("Queen Bohemian Rhapsody", "Bohemian Rhapsody"),
    ("erase una vez", "Érase una vez"),             # accents do not matter
    ("trk_aaaa2", "Bohemian Rhapsody (Live)"),      # short IDs still work
    ("bbbb1", "Radio Ga Ga"),
])
def test_a_reference_that_identifies_one_track(repo, ref, title):
    found = find_track(repo, ref)
    assert found.track is not None and found.track.title == title


def test_ambiguous_references_give_candidates_instead_of_a_guess(repo):
    assert {t.title for t in find_track(repo, "bohemian").candidates} == {
        "Bohemian Rhapsody", "Bohemian Rhapsody (Live)"}
    # A year that is also the start of an ID: both readings are offered.
    assert {t.title for t in find_track(repo, "1985").candidates} == {"Summer Song", "1985"}
    assert len(find_track(repo, "trk_aaaa").candidates) == 2

    repo.insert_batch([_track(f"f{i:04d}", f"Take {i}", artist="Many") for i in range(MAX_CANDIDATES + 5)])
    many = find_track(repo, "many take")
    assert len(many.candidates) == MAX_CANDIDATES and many.more


@pytest.mark.parametrize("ref", ["", "  ", "nothing like this", "!!!", '"', "trk_ffffffff", "zzz OR", "* NEAR("])
def test_references_that_match_nothing_never_raise(repo, ref):
    found = find_track(repo, ref)
    assert found.track is None and found.candidates == []


def test_play_by_search_plays_the_single_match(ctx, player):
    CommandRegistry().dispatch("/play radio ga", ctx)
    assert player.play_track.call_args.args[0].title == "Radio Ga Ga"


def test_play_by_search_lists_the_options_or_says_nothing_was_found(ctx, player):
    PlayCommand().execute(["bohemian"], ctx)
    assert "/play <id>" in ctx.ui.render_warning.call_args.args[0]
    assert len(ctx.ui.render_search_results.call_args.args[0]) == 2

    PlayCommand().execute(["nothing", "like", "this"], ctx)
    assert "nothing like this" in ctx.ui.render_error.call_args.args[0]
    player.play_track.assert_not_called()


def test_resume_continues_only_a_paused_track(ctx, player):
    ResumeCommand().execute([], ctx)
    assert "Não há faixa pausada" in ctx.ui.render_info.call_args.args[0]
    player.state = PlayerState.PLAYING
    ResumeCommand().execute([], ctx)
    assert "já está tocando" in ctx.ui.render_info.call_args.args[0]
    player.resume.assert_not_called()
    player.state = PlayerState.PAUSED
    CommandRegistry().dispatch("/resume", ctx)
    player.resume.assert_called_once_with()


def test_status_shows_the_running_player(ctx, repo, monkeypatch):
    running = MagicMock()
    running.status.return_value = PlayerStatus(
        state=PlayerState.PLAYING, volume=70, current=repo.get_track("trk_" + "bbbb1".ljust(64, "0")),
        position_seconds=134.0, queue=[_track("aaaa1", "Bohemian Rhapsody")])
    monkeypatch.setattr("musicmatch.services.player._player", running)
    assert playback_summary(ctx) == "▶ Tocando: Queen - Radio Ga Ga [02:14 / 05:55] · volume 70% · fila: 1 faixa(s)"


def test_status_shows_the_saved_session_without_starting_the_player(tmp_path, monkeypatch):
    monkeypatch.setattr("musicmatch.services.player._player", None)
    db = SQLiteTrackRepository(db_path=tmp_path / "catalog.db")
    try:
        track = _track("bbbb1", "Radio Ga Ga")
        db.insert_track(track)
        store = SQLitePlaybackStore(db.db_path)
        store.save_queue([track.id])
        store.save_session(track.id, 61.0, 61.0, False, volume=50, state="PAUSED")
        store.close()
        ctx = CommandContext(ui=MagicMock(), agent=MagicMock(), db=db, registry=None)
        with patch("musicmatch.services.player.get_player_service") as start:
            CommandRegistry().dispatch("/status", ctx)
            start.assert_not_called()
        shown = ctx.ui.render_status.call_args.args[0]["Reprodução"]
        assert shown == "⏸ Pausado: Queen - Radio Ga Ga [01:01 / 05:55] · volume 50% · fila: 1 faixa(s)"
    finally:
        db.close()


# ----------------------------------------------------------------------
# Agent tool
# ----------------------------------------------------------------------


@pytest.fixture
def service(repo):
    return MagicMock(repo=repo)


def test_agent_tool_plays_one_track_and_reports_the_rest(service, repo, player, tmp_path):
    audio = tmp_path / "x.mp3"
    audio.write_bytes(b"x")
    repo.insert_track(_track("9999a", "Unique Tune", artist="Solo", path=str(audio)))
    result = play_track("unique tune", service=service, player=player)
    assert result["status"] == "playing" and result["track"]["title"] == "Unique Tune"
    assert player.play_track.call_args.args[0].file_path == str(audio)

    options = play_track("bohemian", service=service, player=player)
    assert options["status"] == "ambiguous" and len(options["candidates"]) == 2
    assert all(option["id"].startswith("trk_") for option in options["candidates"])
    assert play_track("nothing like this", service=service, player=player)["status"] == "not_found"

    missing = play_track("radio", service=service, player=player)  # its file does not exist
    assert missing["status"] == "error" and "indisponível" in missing["message"]
    player.play_track.return_value = False
    assert play_track("unique tune", service=service, player=player)["status"] == "error"
    assert player.play_track.call_count == 2


def test_agent_playback_reports_to_the_screen(service, repo, player, tmp_path):
    audio = tmp_path / "x.mp3"
    audio.write_bytes(b"x")
    repo.insert_track(_track("9999a", "Unique Tune", artist="Solo", path=str(audio)))
    ui = MagicMock()
    try:
        Harness(agent=MagicMock(), ui=ui, database=repo)
        play_track("unique tune", service=service, player=player)
        player.add_listener.assert_called_once_with(ui.render_player_event)
    finally:
        player_tool.set_event_listener(None)


def test_agent_exposes_the_tool():
    agent = SingleTurnAgent(api_key="test-key")  # its request is built in test_agent_structure.py
    assert "play_track" in agent.tool_map
