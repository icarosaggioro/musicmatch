"""Tests for the playback commands, short track IDs and player rendering (ADR 0015)."""

from unittest.mock import MagicMock, patch

import pytest

from musicmatch.commands.base import CommandContext
from musicmatch.commands.player import (
    NextCommand,
    PauseCommand,
    PlayCommand,
    QueueAddCommand,
    QueueAddLastCommand,
    QueueClearCommand,
    QueueCommand,
    QueueRemoveCommand,
    StopCommand,
    VolumeCommand,
    resolve_track,
)
from musicmatch.commands.registry import CommandRegistry
from musicmatch.domain.models import Track
from musicmatch.domain.player import PlayerEvent, PlayerState, PlayerStatus
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from musicmatch.ui.renderer import ConsoleUI

ID_A = "trk_3fa2b9c1" + "0" * 56
ID_B = "trk_3fa2ffff" + "0" * 56
ID_C = "trk_77aa0000" + "1" * 56


def _track(track_id=ID_A, title="Song", path="/music/song.mp3", status="AVAILABLE"):
    return Track(id=track_id, title=title, artist="Artist", album="Album", genre="Pop", duration_seconds=215.0,
                 bitrate_kbps=320, bpm=120.0, file_path=path, status=status)


@pytest.fixture
def repo():
    r = SQLiteTrackRepository(db_path=":memory:")
    for tid, title in ((ID_A, "Alpha"), (ID_B, "Beta"), (ID_C, "Gamma")):
        r.insert_track(_track(tid, title, path=f"/music/{title}.mp3"))
    yield r
    r.close()


@pytest.fixture
def player():
    mock = MagicMock()
    mock.state = PlayerState.STOPPED
    mock.volume = 80
    mock.status.return_value = PlayerStatus(state=PlayerState.STOPPED, volume=80)
    with patch("musicmatch.services.player.get_player_service", return_value=mock):
        yield mock


@pytest.fixture
def ctx(repo):
    return CommandContext(ui=MagicMock(), agent=MagicMock(), db=repo, registry=None)


def test_track_references_accept_full_ids_and_unique_prefixes(repo, ctx):
    assert repo.find_tracks_by_id_prefix("trk_3fa2", limit=5) == [repo.get_track(ID_A), repo.get_track(ID_B)]
    assert resolve_track(ID_A, ctx).title == "Alpha"
    assert resolve_track("trk_77aa", ctx).title == "Gamma"
    assert resolve_track("77AA", ctx).title == "Gamma"  # 'trk_' optional, case-insensitive
    assert resolve_track("3fa2b9", ctx).title == "Alpha"

    assert resolve_track("3fa2", ctx) is None
    assert "ambíguo" in ctx.ui.render_error.call_args.args[0]
    assert resolve_track("abc", ctx) is None  # too short to be a prefix
    assert resolve_track("deadbeef", ctx) is None
    assert "não encontrada" in ctx.ui.render_error.call_args.args[0]


def test_play_track_queue_and_resume(ctx, player):
    PlayCommand().execute(["3fa2b9"], ctx)
    assert player.play_track.call_args.args[0].title == "Alpha"
    player.add_listener.assert_called_with(ctx.ui.render_player_event)

    PlayCommand().execute(["queue"], ctx)  # nothing queued, nothing to resume
    assert "vazia" in ctx.ui.render_warning.call_args.args[0]
    PlayCommand().execute([], ctx)
    player.play_queue.assert_not_called()
    player.play.assert_not_called()

    player.status.return_value = PlayerStatus(state=PlayerState.STOPPED, volume=80, queue=[_track()])
    PlayCommand().execute(["fila"], ctx)
    player.play_queue.assert_called_once()
    PlayCommand().execute([], ctx)  # stopped + queue -> play() starts it
    player.play.assert_called_once()

    # Paused (now or in the previous session): /play continues it, /play queue too.
    player.state = PlayerState.PAUSED
    player.status.return_value = PlayerStatus(state=PlayerState.PAUSED, volume=80, current=_track(),
                                              position_seconds=83.0, resume_available=True, current_index=0,
                                              queue=[_track()])
    PlayCommand().execute([], ctx)
    PlayCommand().execute(["queue"], ctx)
    assert player.play.call_count == 2 and player.play_queue.call_count == 2

    player.state = PlayerState.PLAYING
    PlayCommand().execute([], ctx)
    assert "Já existe" in ctx.ui.render_info.call_args.args[0]

    PlayCommand().execute(["nonexistent"], ctx)
    assert player.play_track.call_count == 1


def test_queue_remove_by_position_through_the_dispatcher(ctx, player):
    registry = CommandRegistry()
    ctx.registry = registry
    player.queue_remove_at.return_value = _track(title="Second copy")
    registry.dispatch("/queue-remove #2", ctx)  # '#' must not be parsed as a shell comment
    player.queue_remove_at.assert_called_once_with(2)
    assert "posição 2" in ctx.ui.render_success.call_args.args[0]

    player.queue_remove_at.return_value = None
    registry.dispatch("/queue-remove #9", ctx)
    assert "posição 9" in ctx.ui.render_error.call_args.args[0]
    registry.dispatch("/queue-remove #x", ctx)
    assert "Uso" in ctx.ui.render_error.call_args.args[0]


def test_transport_commands(ctx, player):
    player.toggle_pause.return_value = False
    PauseCommand().execute([], ctx)
    assert "Nada está tocando" in ctx.ui.render_info.call_args.args[0]
    player.stop.return_value = False
    StopCommand().execute([], ctx)
    assert "primeira faixa" in ctx.ui.render_info.call_args.args[0]
    player.stop.return_value = True
    StopCommand().execute([], ctx)
    assert player.stop.call_count == 2

    NextCommand().execute([], ctx)
    player.next.assert_not_called()  # nothing playing, empty queue
    player.status.return_value = PlayerStatus(state=PlayerState.PLAYING, volume=80, current=_track())
    NextCommand().execute([], ctx)
    player.next.assert_called_once()


def test_volume_command(ctx, player):
    VolumeCommand().execute([], ctx)
    assert "80%" in ctx.ui.render_info.call_args.args[0]
    VolumeCommand().execute(["35"], ctx)
    player.set_volume.assert_called_once_with(35)
    VolumeCommand().execute(["100%"], ctx)
    player.set_volume.assert_called_with(100)
    for bad in (["101"], ["-1"], ["loud"]):
        VolumeCommand().execute(bad, ctx)
    assert player.set_volume.call_count == 2
    assert ctx.ui.render_error.call_count == 3


def test_queue_commands(ctx, player):
    QueueAddCommand().execute(["77aa"], ctx)
    assert player.queue_add_next.call_args.args[0].title == "Gamma"
    QueueAddLastCommand().execute([ID_A], ctx)
    assert player.queue_add_last.call_args.args[0].title == "Alpha"
    QueueAddCommand().execute([], ctx)
    assert ctx.ui.render_error.called

    player.status.return_value = PlayerStatus(
        state=PlayerState.STOPPED, volume=80, queue=[_track(ID_A), _track(ID_B), _track(ID_A)]
    )
    QueueRemoveCommand().execute(["3fa2"], ctx)
    assert "ambíguo" in ctx.ui.render_error.call_args.args[0]
    player.queue_remove.return_value = 2
    QueueRemoveCommand().execute(["3fa2b9"], ctx)
    player.queue_remove.assert_called_once_with(ID_A)
    assert "2 ocorrência(s)" in ctx.ui.render_success.call_args.args[0]
    QueueRemoveCommand().execute(["77aa"], ctx)
    assert "não está na fila" in ctx.ui.render_warning.call_args.args[0]

    player.queue_clear.return_value = 3
    QueueClearCommand().execute([], ctx)
    assert "3 faixa(s)" in ctx.ui.render_success.call_args.args[0]

    QueueCommand().execute([], ctx)
    ctx.ui.render_player_status.assert_called_once_with(player.status.return_value)


def test_commands_are_registered_with_aliases():
    registry = CommandRegistry()
    for name in ("/play", "/pause", "/stop", "/next", "/volume", "/queue", "/queue-add", "/queue-add-last",
                 "/queue-remove", "/queue-clear", "/tocar", "/skip", "/vol", "/fila"):
        assert name in registry.lookup_map


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------


def _event(kind, track=None, message=None, background=False):
    return PlayerEvent(kind=kind, state=PlayerState.PLAYING, track=track, message=message, background=background)


def test_player_events_rendering(capsys):
    ui = ConsoleUI()
    missing = _track(title="Lost", path="/mnt/usb/lost.flac", status="MISSING")
    ui.render_player_event(_event("TRACK_STARTED", _track()))
    ui.render_player_event(_event("TRACK_MISSING", missing))
    ui.render_player_event(_event("TRACK_ERROR", _track(), "Invalid data"))
    ui.render_player_event(_event("DEVICE_ERROR", _track(), "no device"))
    ui.render_player_event(_event("PAUSED", _track()))
    ui.render_player_event(_event("VOLUME_CHANGED", message="Volume: 35%"))
    out = capsys.readouterr().out
    assert "Tocando agora: Artist - Song [03:35]" in out
    # One line each (ADR 0019): the path, the decoder message and the advice live in the issue.
    missing = next(line for line in out.splitlines() if "Faixa indisponível" in line)
    assert "Artist - Lost" in missing and "veja /issue" in missing and "/mnt/usb/lost.flac" not in out
    assert "Não foi possível reproduzir Artist - Song [03:35] (veja /issue)" in out and "Invalid data" not in out
    assert "no device" in out and "Pausado" in out and "Volume: 35%" in out
    ui.render_player_event(_event("TRACK_FINISHED", _track()))
    assert capsys.readouterr().out == ""  # the next TRACK_STARTED / QUEUE_ENDED tells the story

    ui.render_player_event(_event("QUEUE_ENDED", message="Fim", background=True))
    out = capsys.readouterr().out
    assert out.startswith("\n") and out.endswith("MusicMatch > ")  # prompt redrawn after async output


def test_player_status_rendering_flags_unavailable_tracks(capsys, tmp_path):
    present = tmp_path / "present.mp3"
    present.write_bytes(b"x")
    status = PlayerStatus(
        state=PlayerState.PAUSED, volume=35, output_backend="WASAPI", position_seconds=60.0,
        current=_track(title="Now", path=str(present)),
        queue=[_track(ID_B, "Next", path=str(present)), _track(ID_C, "Gone", path=str(tmp_path / "gone.mp3"))],
    )
    ConsoleUI().render_player_status(status)
    out = capsys.readouterr().out
    assert "PAUSED" in out and "Volume 35%" in out and "WASAPI" in out
    assert "[01:00 / 03:35]" in out
    lines = out.splitlines()
    assert "ARQUIVO INDISPONÍVEL" not in next(line for line in lines if "Next" in line)
    assert "ARQUIVO INDISPONÍVEL" in next(line for line in lines if "Gone" in line)
    assert "(trk_77aa0000)" in out

    ConsoleUI().render_player_status(PlayerStatus(state=PlayerState.STOPPED, volume=80))
    assert "Nada tocando" in capsys.readouterr().out


def test_queue_view_marks_the_current_and_already_played_entries(capsys, tmp_path):
    present = tmp_path / "present.mp3"
    present.write_bytes(b"x")
    entries = [_track(tid, title, path=str(present)) for tid, title in ((ID_A, "One"), (ID_B, "Two"), (ID_C, "Three"))]
    status = PlayerStatus(state=PlayerState.PAUSED, volume=80, current=entries[1], position_seconds=30.0,
                          queue=entries, current_index=1, next_index=2, resume_available=True, total_plays=7)
    ConsoleUI().render_player_status(status)
    out = capsys.readouterr().out
    line = {title: next(l for l in out.splitlines() if f"- {title} [" in l) for title in ("One", "Two", "Three")}
    assert line["One"].lstrip().startswith("✓") and line["Two"].lstrip().startswith("⏸")
    assert not line["Three"].lstrip().startswith(("✓", "▶", "⏸"))
    assert "Pausado: Artist - Two" in out and "/pause ou /play" in out and "Reproduções totais: 7" in out


def test_startup_notice_is_a_single_clean_line(capsys):
    ui = ConsoleUI()
    ui.render_saved_playback(12, _track(title="Long Road"), 83.0)
    assert capsys.readouterr().out == "🎧 Fila: 12 faixa(s) · Última tocada: Artist - Long Road · Tempo: 01:23\n\n"
    ui.render_saved_playback(3, None, 0.0)
    assert capsys.readouterr().out == "🎧 Fila: 3 faixa(s)\n\n"
    ui.render_saved_playback(0, None, 0.0)
    assert capsys.readouterr().out == ""


def test_track_listings_show_short_ids(capsys):
    ui = ConsoleUI()
    ui.render_track_page([_track()], page=1, total_pages=1, total_count=1)
    ui.render_search_results([_track()])
    out = capsys.readouterr().out
    assert out.count("ID: trk_3fa2b9c1 · Caminho: /music/song.mp3") == 2


def test_harness_releases_the_player_on_exit(monkeypatch):
    import musicmatch.services.player as player_module
    from musicmatch.harness.loop import Harness

    shutdown = MagicMock()
    monkeypatch.setattr(player_module, "shutdown_player_service", shutdown)
    agent = MagicMock()
    agent.model_name = "test"
    harness = Harness(agent=agent, ui=MagicMock(), registry=CommandRegistry(), database=MagicMock())

    def raise_eof(_prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    harness.start()
    shutdown.assert_called_once()
