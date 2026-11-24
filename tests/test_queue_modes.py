"""Queue playback modes (ADR 0017): repeat, consume, shuffle and sort, and the '/queue-<action>' naming rule."""

import random
from unittest.mock import MagicMock, patch

import pytest

from audio_synth import sine, write_wav
from musicmatch.commands.base import CommandContext
from musicmatch.commands.player import (
    PLAYER_COMMANDS,
    PlayCommand,
    QueueConsumeCommand,
    QueuePlayCommand,
    QueueRepeatCommand,
    QueueShuffleCommand,
    QueueSortCommand,
)
from musicmatch.commands.registry import CommandRegistry
from musicmatch.domain.models import Track
from musicmatch.domain.player import (
    PlayerEvent,
    PlayerState,
    PlayerStatus,
    QueueOrder,
    parse_queue_order,
    queue_sort_key,
)
from musicmatch.services.audio_decoder import AudioDecoder
from musicmatch.services.player import PlayerService
from musicmatch.storage.playback_store import SQLitePlaybackStore
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from musicmatch.ui.renderer import ConsoleUI
from test_player_service import FakeOutput, dominant_hz, kinds, player_factory, tones, wait_for  # noqa: F401


def meta(track_id, title="T", artist="A", album="Al", genre="G", number=None, path=None):
    """A catalog track (no file needed: sort keys are pure functions of the metadata)."""
    return Track(id=track_id, title=title, artist=artist, album=album, genre=genre, duration_seconds=1.0,
                 bitrate_kbps=1411, bpm=120, file_path=path or f"/music/{track_id}.wav", track_number=number)


@pytest.fixture
def tagged(tmp_path):
    """Factory: a short playable WAV with the given tags (sorting tests need real, available files)."""

    def make(name, title=None, artist="Artist", album="Album", genre="Genre", number=None, folder="lib",
             seconds=0.3, freq=440.0):
        directory = tmp_path / folder
        directory.mkdir(parents=True, exist_ok=True)
        path = write_wav(directory / f"{name}.wav", sine(freq, seconds, -6.0))
        return Track(id=f"trk_{name}", title=title or name, artist=artist, album=album, genre=genre,
                     duration_seconds=seconds, bitrate_kbps=1411, bpm=120, file_path=str(path), track_number=number)

    return make


def ids(player):
    return [t.id.removeprefix("trk_") for t in player.status().queue]


# ----------------------------------------------------------------------
# Sort keys (domain)
# ----------------------------------------------------------------------


def test_sort_keys_are_case_and_accent_insensitive_and_missing_tags_go_last():
    tracks = [meta("1", title="zebra"), meta("2", title="Élan"), meta("3", title="apple"), meta("4", title="Banana")]
    assert [t.id for t in sorted(tracks, key=lambda t: queue_sort_key(t, QueueOrder.TITLE))] == ["3", "4", "2", "1"]

    artists = [meta("u", artist="Unknown Artist"), meta("z", artist="Zappa"), meta("a", artist="ABBA")]
    assert [t.id for t in sorted(artists, key=lambda t: queue_sort_key(t, QueueOrder.ARTIST))] == ["a", "z", "u"]
    genres = [meta("u", genre="Unknown Genre"), meta("r", genre="Rock"), meta("e", genre="")]
    assert [t.id for t in sorted(genres, key=lambda t: queue_sort_key(t, QueueOrder.GENRE))][0] == "r"


def test_secondary_keys_genre_and_artist_then_title_album_then_track_number():
    pool = [
        meta("rock-b", title="b", genre="Rock", artist="Y"), meta("jazz-z", title="z", genre="Jazz", artist="X"),
        meta("rock-a", title="a", genre="rock", artist="X"), meta("jazz-a", title="a", genre="Jazz", artist="Y"),
    ]
    by = lambda order: [t.id for t in sorted(pool, key=lambda t: queue_sort_key(t, order))]  # noqa: E731
    assert by(QueueOrder.GENRE) == ["jazz-a", "jazz-z", "rock-a", "rock-b"]
    assert by(QueueOrder.ARTIST) == ["rock-a", "jazz-z", "jazz-a", "rock-b"]

    album = [meta("t10", title="a", album="Blue", number=10), meta("none", title="a", album="Blue"),
             meta("t2", title="z", album="Blue", number=2), meta("red", album="Red", number=1)]
    assert [t.id for t in sorted(album, key=lambda t: queue_sort_key(t, QueueOrder.ALBUM))] == ["t2", "t10", "none", "red"]


def test_same_named_albums_in_different_folders_do_not_interleave():
    pool = [
        meta("queen1", album="Greatest Hits", number=1, path="/m/Queen/Greatest Hits/01.mp3"),
        meta("abba2", album="Greatest Hits", number=2, path="/m/ABBA/Greatest Hits/02.mp3"),
        meta("queen2", album="Greatest Hits", number=2, path="/m/Queen/Greatest Hits/02.mp3"),
        meta("abba1", album="Greatest Hits", number=1, path="C:\\m\\ABBA\\Greatest Hits\\01.mp3".replace("C:", "")),
    ]
    ordered = [t.id for t in sorted(pool, key=lambda t: queue_sort_key(t, QueueOrder.ALBUM))]
    assert ordered == ["abba1", "abba2", "queen1", "queen2"]


def test_sort_key_names_accept_english_portuguese_and_accents():
    assert parse_queue_order("title") == parse_queue_order("Título") == QueueOrder.TITLE
    assert parse_queue_order("GENRE") == parse_queue_order("gênero") == QueueOrder.GENRE
    assert parse_queue_order("artista") == QueueOrder.ARTIST
    assert parse_queue_order("álbum") == QueueOrder.ALBUM
    assert parse_queue_order("bpm") is None


# ----------------------------------------------------------------------
# Repeat (service, real playback)
# ----------------------------------------------------------------------


def test_repeat_plays_the_whole_queue_again_until_turned_off(tones, player_factory):
    output = FakeOutput()
    player, events = player_factory(output)
    a, b = tones("a", 330.0, 0.3), tones("b", 660.0, 0.3)
    player.queue_add_last(a)
    player.queue_add_last(b)
    player.set_repeat(True)
    assert player.repeat and player.status().repeat and events[-1].kind == "REPEAT_CHANGED"

    player.play_queue()
    assert wait_for(lambda: [e.kind for e in events].count("TRACK_STARTED") >= 5)
    started = [e.track.id for e in events if e.kind == "TRACK_STARTED"][:5]
    assert started == ["trk_a", "trk_b", "trk_a", "trk_b", "trk_a"]
    assert "QUEUE_ENDED" not in kinds(events)
    wraps = [e for e in events if e.kind == "QUEUE_REPEATED"]
    assert len(wraps) >= 2 and all(e.background for e in wraps)
    # Each pass really played the audio of each entry, in order.
    heard = [dominant_hz(h.audio) for h in output.handles[:4]]
    assert heard == [pytest.approx(330.0, abs=3), pytest.approx(660.0, abs=3)] * 2

    player.set_repeat(False)  # the current pass finishes, then the queue stops as usual
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))
    assert player.state == PlayerState.STOPPED and player.status().next_index == 0


def test_next_on_the_last_entry_wraps_only_in_repeat_mode(tones, player_factory):
    player, events = player_factory(FakeOutput(speed=1.0))
    for name, freq in (("a", 330.0), ("b", 550.0)):
        player.queue_add_last(tones(name, freq, 5.0))
    player.set_repeat(True)
    player.play_queue()
    player.next()
    assert player.next() is True and player.status().current.id == "trk_a"
    assert player.status().current_index == 0 and player.status().next_index == 1
    assert kinds(events)[-2:] == ["QUEUE_REPEATED", "TRACK_STARTED"]

    player.set_repeat(False)
    player.next()
    assert player.next() is False and kinds(events)[-1] == "QUEUE_ENDED"


def test_repeat_never_loops_forever_over_unplayable_entries(tones, player_factory, tmp_path):
    player, events = player_factory()
    for name in ("x", "y"):
        player.queue_add_last(tones(name, 440.0))
    for track in player.status().queue:
        tmp_path.joinpath(f"{track.title}.wav").unlink()  # the drive went away
    player.set_repeat(True)
    events.clear()

    assert player.play_queue() is False
    assert kinds(events) == ["TRACK_MISSING", "TRACK_MISSING", "QUEUE_ENDED"]
    assert "Nenhuma faixa" in events[-1].message
    assert player.state == PlayerState.STOPPED and len(player.status().queue) == 2  # entries are kept

    player.queue_add_last(tones("z", 550.0, 0.3))  # one playable entry after the missing ones
    events.clear()
    assert player.play_queue() is True
    assert kinds(events)[:3] == ["TRACK_MISSING", "TRACK_MISSING", "TRACK_STARTED"]


def test_repeat_does_not_apply_to_a_track_played_by_id_from_an_idle_player(tones, player_factory):
    player, events = player_factory()
    player.queue_add_last(tones("queued", 330.0, 0.3))
    player.set_repeat(True)
    player.play_track(tones("single", 660.0, 0.3))
    assert wait_for(lambda: player.state == PlayerState.STOPPED)
    assert [e.track.id for e in events if e.kind == "TRACK_STARTED"] == ["trk_single"]


# ----------------------------------------------------------------------
# Shuffle and sort (service)
# ----------------------------------------------------------------------


def test_sorting_an_idle_queue_reorders_every_entry_and_keeps_duplicates(tagged, player_factory):
    player, events = player_factory()
    tracks = [
        tagged("c", title="Cello", artist="Zed", genre="Jazz", album="One", number=2),
        tagged("a", title="Alto", artist="Moby", genre="Rock", album="Two", number=1),
        tagged("b", title="Bass", artist="Abba", genre="Jazz", album="One", number=1),
    ]
    for track in tracks + [tracks[1]]:
        player.queue_add_last(track)
    events.clear()

    assert player.queue_sort(QueueOrder.TITLE) == 4
    assert ids(player) == ["a", "a", "b", "c"]
    assert kinds(events) == ["QUEUE_REORDERED"] and "Fila ordenada por nome da faixa (4 faixas)" in events[0].message
    player.queue_sort(QueueOrder.ARTIST)
    assert ids(player) == ["b", "a", "a", "c"]
    player.queue_sort(QueueOrder.GENRE)
    assert ids(player) == ["b", "c", "a", "a"]  # Jazz (Bass, Cello), then Rock
    player.queue_sort(QueueOrder.ALBUM)
    assert ids(player) == ["b", "c", "a", "a"]
    assert "A ordem já era essa" in events[-1].message
    assert player.status().next_index == 0 and player.status().current_index is None


def test_sorting_mid_pass_sorts_everything_and_playback_continues_from_the_current_track(tagged, player_factory):
    player, events = player_factory(FakeOutput(speed=1.0))
    for name in ["e", "a", "now", "d", "c", "b"]:
        player.queue_add_last(tagged(name, seconds=5.0))
    player.play_queue()
    player.next()
    player.next()  # 'e' and 'a' played, 'now' is playing
    assert player.status().current.id == "trk_now"

    assert player.queue_sort(QueueOrder.TITLE) == 6
    status = player.status()
    assert ids(player) == ["a", "b", "c", "d", "e", "now"]  # the whole queue, played entries included
    assert status.current_index == 5 and status.next_index == 6  # the current track followed its entry
    assert player.state == PlayerState.PLAYING and status.current.id == "trk_now"
    assert "Fila ordenada por nome da faixa (6 faixas)" in events[-1].message
    assert "continua a partir da posição 6 (a faixa atual)" in events[-1].message

    player.queue_sort(QueueOrder.TITLE)
    assert "A ordem já era essa" in events[-1].message and player.status().current_index == 5


def test_shuffling_mid_pass_moves_the_current_track_to_the_top_and_everything_else_follows(tagged, player_factory):
    player, events = player_factory(FakeOutput(speed=1.0))
    for name in "abcdef":
        player.queue_add_last(tagged(name, seconds=5.0))
    player.play_queue()
    for _ in range(3):
        player.next()  # 'd' is playing
    assert player.status().current.id == "trk_d"

    assert player.queue_shuffle() == 6
    status = player.status()
    assert ids(player)[0] == "d" and sorted(ids(player)) == list("abcdef")
    assert status.current_index == 0 and status.next_index == 1
    assert "posição 1 (a faixa atual)" in events[-1].message
    second = ids(player)[1]
    player.next()
    assert player.status().current.id == f"trk_{second}"  # playback follows the new order


def test_reordering_while_paused_or_between_tracks_anchors_the_right_entry(tagged, player_factory):
    player, events = player_factory(FakeOutput(speed=1.0))
    for name in "dcba":
        player.queue_add_last(tagged(name, seconds=5.0))
    player.play_queue()
    player.next()
    player.pause()  # paused on 'c' (entry 2)
    player.queue_sort(QueueOrder.TITLE)
    status = player.status()
    assert ids(player) == list("abcd") and status.current_index == 2 and status.next_index == 3
    assert player.resume() and player.status().current.id == "trk_c"

    # A track played by ID mid-queue: the queue entry due next ('d') is the anchor.
    player.play_track(tagged("outside", seconds=5.0))
    player.queue_sort(QueueOrder.TITLE)  # already sorted: nothing moves
    player.queue_shuffle()
    status = player.status()
    assert ids(player)[0] == "d" and status.current_index is None and status.next_index == 0
    assert "(a próxima faixa)" in events[-1].message
    player.next()
    assert player.status().current.id == "trk_d"


def test_shuffle_is_random_but_always_changes_the_order_when_it_can(tagged):
    player = PlayerService(output=FakeOutput(), rng=random.Random(7))
    try:
        for name in "abcdef":
            player.queue_add_last(tagged(name))
        seen = set()
        for _ in range(10):
            before = ids(player)
            assert player.queue_shuffle() == 6
            after = ids(player)
            assert after != before and sorted(after) == list("abcdef")
            seen.add(tuple(after))
        assert len(seen) > 5

        two = PlayerService(output=FakeOutput(), rng=random.Random(0))
        for name in "ab":
            two.queue_add_last(tagged(name))
        for _ in range(5):  # with two entries a plain shuffle keeps the order half of the time
            before = ids(two)
            two.queue_shuffle()
            assert ids(two) == before[::-1]
        two.shutdown()
    finally:
        player.shutdown()


def test_nothing_to_reorder_leaves_the_queue_untouched(tagged, player_factory):
    player, events = player_factory()
    assert player.queue_shuffle() == 0 and player.queue_sort(QueueOrder.TITLE) == 0
    player.queue_add_last(tagged("solo"))
    assert player.queue_shuffle() == 1
    assert events[-1].kind == "QUEUE_CHANGED"  # no QUEUE_REORDERED for a no-op


# ----------------------------------------------------------------------
# Consume mode (service, real playback)
# ----------------------------------------------------------------------


@pytest.fixture
def counting_player():
    """A player whose play-count threshold is 0.2 s, so 'counted as played' happens quickly."""
    players = []

    def make(speed=1.0, store=None):
        player = PlayerService(decoder=AudioDecoder(ffmpeg_path=None, use_miniaudio=False, timeout_seconds=None),
                               output=FakeOutput(speed=speed), volume=100, store=store,
                               play_count_seconds=0.2, tick_seconds=0.02)
        events = []
        player.add_listener(events.append)
        players.append(player)
        return player, events

    yield make
    for player in players:
        player.shutdown()


def test_consume_removes_each_track_as_it_finishes_and_keeps_unplayable_ones(tones, player_factory, tmp_path):
    player, events = player_factory()
    for name, freq in (("a", 330.0), ("gone", 440.0), ("b", 550.0)):
        player.queue_add_last(tones(name, freq, 0.3))
    tmp_path.joinpath("gone.wav").unlink()
    player.set_consume(True)
    assert player.consume and player.status().consume and events[-1].kind == "CONSUME_CHANGED"

    player.play_queue()
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))
    consumed = [e.track.id for e in events if e.kind == "QUEUE_ENTRY_CONSUMED"]
    assert consumed == ["trk_a", "trk_b"] and all(e.background for e in events if e.kind == "QUEUE_ENTRY_CONSUMED")
    assert ids(player) == ["gone"]  # never heard: it stays for when the drive is back
    assert player.status().next_index == 0


def test_consume_only_removes_tracks_that_counted_as_played(tones, counting_player):
    player, events = counting_player()
    for name in ("a", "b", "c", "d"):
        player.queue_add_last(tones(name, 440.0, 5.0))
    player.set_consume(True)
    player.play_queue()

    player.next()  # 'a' skipped before the threshold: it stays
    assert ids(player) == ["a", "b", "c", "d"] and player.status().current_index == 1

    assert wait_for(lambda: "PLAY_COUNTED" in kinds(events))
    player.next()  # 'b' was heard: it leaves, and 'c' plays
    assert ids(player) == ["a", "c", "d"]
    status = player.status()
    assert status.current.id == "trk_c" and status.current_index == 1 and status.next_index == 2

    assert wait_for(lambda: kinds(events).count("PLAY_COUNTED") == 2)
    player.pause()
    player.next()  # paused after being heard, then skipped: it leaves too
    assert ids(player) == ["a", "d"] and player.status().current.id == "trk_d"

    assert wait_for(lambda: kinds(events).count("PLAY_COUNTED") == 3)
    player.stop()  # stopping is not moving on: the track stays
    assert ids(player) == ["a", "d"] and player.status().next_index == 0


def test_consume_removes_a_heard_entry_replaced_by_play_id_and_only_that_copy(tones, counting_player):
    player, events = counting_player()
    a, b = tones("a", 330.0, 5.0), tones("b", 550.0, 5.0)
    for track in (a, b, a):
        player.queue_add_last(track)
    player.set_consume(True)
    player.play_queue()
    assert wait_for(lambda: "PLAY_COUNTED" in kinds(events))

    player.play_track(tones("other", 660.0, 5.0))
    assert ids(player) == ["b", "a"]  # the first copy of 'a' left, the duplicate stays
    assert player.status().next_index == 0
    player.next()
    assert player.status().current.id == "trk_b"  # the queue carries on after the track played by ID


def test_repeat_and_consume_exclude_each_other(tones, player_factory):
    player, events = player_factory()
    player.set_repeat(True)
    player.set_consume(True)
    assert player.consume and not player.repeat
    assert "Repetir fila foi desligado" in events[-1].message
    player.set_repeat(True)
    assert player.repeat and not player.consume
    assert "Remover faixas tocadas foi desligado" in events[-1].message
    player.set_consume(False)
    assert player.repeat and not player.consume and "desligado" in events[-1].message


def test_turning_consume_on_leaves_the_tracks_already_played_in_the_queue(tones, player_factory):
    player, events = player_factory()
    for name in ("a", "b"):
        player.queue_add_last(tones(name, 440.0, 0.3))
    player.play_queue()
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))
    player.set_consume(True)
    assert ids(player) == ["a", "b"]


# ----------------------------------------------------------------------
# Persistence (restart = new PlayerService on the same database)
# ----------------------------------------------------------------------


def test_queue_modes_and_reordered_queue_survive_a_restart(tmp_path, tagged):
    db_path = str(tmp_path / "musicmatch.db")
    repo = SQLiteTrackRepository(db_path=db_path)
    store = SQLitePlaybackStore(db_path)
    tracks = [tagged("b", title="Beta"), tagged("a", title="Alpha"), tagged("c", title="Gamma")]
    for track in tracks:
        repo.insert_track(track)

    def new_player():
        return PlayerService(decoder=AudioDecoder(ffmpeg_path=None, use_miniaudio=False, timeout_seconds=None),
                             output=FakeOutput(), store=store)

    try:
        player = new_player()
        assert player.repeat is False and player.consume is False  # defaults for new and migrated databases
        for track in tracks:
            player.queue_add_last(track)
        player.set_repeat(True)
        player.queue_sort(QueueOrder.TITLE)
        player.shutdown()

        restored = new_player()
        assert restored.repeat is True and restored.status().repeat is True and restored.consume is False
        assert ids(restored) == ["a", "b", "c"]
        assert store.load_session().repeat is True
        restored.set_consume(True)
        restored.shutdown()

        again = new_player()
        assert again.consume is True and again.repeat is False and again.status().consume is True
        assert store.load_session().consume is True
        again.shutdown()
    finally:
        store.close()
        repo.close()


def test_harness_startup_notice_mentions_the_queue_modes(tmp_path, tagged, monkeypatch):
    from musicmatch.harness.loop import Harness

    db_path = str(tmp_path / "musicmatch.db")
    repo = SQLiteTrackRepository(db_path=db_path)
    store = SQLitePlaybackStore(db_path)
    track = tagged("a")
    repo.insert_track(track)
    store.save_queue([track.id])
    store.save_session(track.id, 12.0, 12.0, False, volume=80, consume=True)
    store.close()
    ui = MagicMock()
    agent = MagicMock()
    agent.model_name = "test"
    monkeypatch.setattr("builtins.input", lambda _prompt="": (_ for _ in ()).throw(EOFError()))
    Harness(agent=agent, ui=ui, registry=CommandRegistry(), database=repo).start()
    assert ui.render_saved_playback.call_args.kwargs == {"repeat": False, "consume": True}
    repo.close()


# ----------------------------------------------------------------------
# Commands
# ----------------------------------------------------------------------


@pytest.fixture
def player():
    mock = MagicMock()
    mock.state = PlayerState.STOPPED
    mock.repeat = False
    mock.consume = False
    mock.status.return_value = PlayerStatus(state=PlayerState.STOPPED, volume=80, queue=[meta("trk_1"), meta("trk_2")])
    with patch("musicmatch.services.player.get_player_service", return_value=mock):
        yield mock


@pytest.fixture
def ctx():
    return CommandContext(ui=MagicMock(), agent=MagicMock(), db=MagicMock(), registry=None)


def test_every_queue_command_follows_the_queue_dash_naming_rule():
    registry = CommandRegistry()
    queue_commands = [cls() for cls in PLAYER_COMMANDS if cls.__name__.startswith("Queue")]
    names = {cmd.get_name() for cmd in queue_commands}
    assert names == {"/queue", "/queue-play", "/queue-add", "/queue-add-last", "/queue-remove", "/queue-clear",
                     "/queue-repeat", "/queue-consume", "/queue-shuffle", "/queue-sort"}
    for cmd in queue_commands:
        assert all(alias in ("/fila",) for alias in cmd.get_aliases())  # no off-pattern aliases were added
    # Nothing outside the family is named after the queue, and /play no longer advertises 'queue'.
    others = [cmd for cmd in registry.get_all_commands() if cmd.get_name() not in names]
    assert not any("queue" in cmd.get_name() for cmd in others)
    assert "queue" not in PlayCommand().get_description() and "queue" not in PlayCommand.usage
    for name in names:
        assert registry.lookup_map[name].get_name() == name


def test_queue_play_command_and_the_former_spelling(ctx, player):
    QueuePlayCommand().execute([], ctx)
    PlayCommand().execute(["queue"], ctx)
    assert player.play_queue.call_count == 2
    player.status.return_value = PlayerStatus(state=PlayerState.STOPPED, volume=80)
    QueuePlayCommand().execute([], ctx)
    assert player.play_queue.call_count == 2 and "vazia" in ctx.ui.render_warning.call_args.args[0]


@pytest.mark.parametrize("command_class, attribute, setter", [
    (QueueRepeatCommand, "repeat", "set_repeat"),
    (QueueConsumeCommand, "consume", "set_consume"),
])
def test_queue_mode_switches_toggle_or_set(ctx, player, command_class, attribute, setter):
    set_mode = getattr(player, setter)
    command_class().execute([], ctx)
    set_mode.assert_called_with(True)
    setattr(player, attribute, True)
    command_class().execute([], ctx)
    set_mode.assert_called_with(False)
    command_class().execute(["ON"], ctx)
    set_mode.assert_called_with(True)
    command_class().execute(["desligar"], ctx)
    set_mode.assert_called_with(False)
    command_class().execute(["maybe"], ctx)
    assert set_mode.call_count == 4 and command_class().get_name() in ctx.ui.render_error.call_args.args[0]


def test_queue_shuffle_and_sort_commands(ctx, player):
    QueueShuffleCommand().execute([], ctx)
    player.queue_shuffle.assert_called_once()

    for arg, order in (("title", QueueOrder.TITLE), ("gênero", QueueOrder.GENRE),
                       ("Artist", QueueOrder.ARTIST), ("album", QueueOrder.ALBUM)):
        QueueSortCommand().execute([arg], ctx)
        player.queue_sort.assert_called_with(order)
    ctx.ui.render_info.assert_not_called()

    for bad in ([], ["bpm"]):
        QueueSortCommand().execute(bad, ctx)
        assert "/queue-sort <title | genre | artist | album>" in ctx.ui.render_error.call_args.args[0]
    assert player.queue_sort.call_count == 4

    player.status.return_value = PlayerStatus(state=PlayerState.STOPPED, volume=80, queue=[meta("trk_1")])
    QueueShuffleCommand().execute([], ctx)
    QueueSortCommand().execute(["title"], ctx)
    assert "uma só faixa" in ctx.ui.render_info.call_args.args[0]

    player.status.return_value = PlayerStatus(state=PlayerState.STOPPED, volume=80)
    QueueShuffleCommand().execute([], ctx)
    QueueSortCommand().execute(["album"], ctx)
    assert player.queue_shuffle.call_count == 1 and player.queue_sort.call_count == 4
    assert "vazia" in ctx.ui.render_warning.call_args.args[0]


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------


def test_queue_mode_rendering(capsys, tmp_path):
    ui = ConsoleUI()
    for kind, message in (("QUEUE_REORDERED", "Fila embaralhada (3 faixas)."),
                          ("REPEAT_CHANGED", "Repetir fila: ligado."),
                          ("CONSUME_CHANGED", "Remover faixas tocadas: ligado.")):
        ui.render_player_event(PlayerEvent(kind=kind, state=PlayerState.STOPPED, message=message))
    ui.render_player_event(PlayerEvent(kind="QUEUE_REPEATED", state=PlayerState.PLAYING,
                                       message="Repetir fila: recomeçando", background=True))
    out = capsys.readouterr().out
    assert "🔀  Fila embaralhada (3 faixas). Veja a nova ordem com /queue." in out
    assert "🔁  Repetir fila: ligado." in out and "🧹  Remover faixas tocadas: ligado." in out
    assert out.endswith("MusicMatch > ")
    ui.render_player_event(PlayerEvent(kind="QUEUE_ENTRY_CONSUMED", state=PlayerState.PLAYING,
                                       track=meta("trk_1"), background=True))
    assert capsys.readouterr().out == ""  # the entry just leaves the queue, no interruption

    present = tmp_path / "x.wav"
    present.write_bytes(b"x")
    queue = [meta("trk_1", path=str(present))]
    ui.render_player_status(PlayerStatus(state=PlayerState.STOPPED, volume=80, queue=queue, repeat=True))
    out = capsys.readouterr().out
    assert "🔁 repetir: ligado" in out and "/queue-sort <title|genre|artist|album>" in out
    assert "remover tocadas" not in out and "/queue-consume [on|off]" in out
    ui.render_player_status(PlayerStatus(state=PlayerState.STOPPED, volume=80, queue=queue, consume=True))
    out = capsys.readouterr().out
    assert "🧹 remover tocadas: ligado" in out and "repetir: ligado" not in out
    ui.render_player_status(PlayerStatus(state=PlayerState.STOPPED, volume=80, repeat=True))
    assert "Repetir fila: ligado (/queue-repeat off" in capsys.readouterr().out
    ui.render_player_status(PlayerStatus(state=PlayerState.STOPPED, volume=80, consume=True))
    assert "Remover faixas tocadas: ligado (/queue-consume off" in capsys.readouterr().out

    ui.render_player_event(PlayerEvent(kind="QUEUE_ENDED", state=PlayerState.STOPPED,
                                       message="Nenhuma faixa da fila pôde ser reproduzida."))
    assert capsys.readouterr().out == "⏹️   Nenhuma faixa da fila pôde ser reproduzida.\n"
    ui.render_player_event(PlayerEvent(kind="QUEUE_ENDED", state=PlayerState.STOPPED))
    assert capsys.readouterr().out == "⏹️   Fim da fila de reprodução.\n"

    ui.render_saved_playback(3, None, 0.0, repeat=True)
    assert capsys.readouterr().out == "🎧 Fila: 3 faixa(s) · 🔁 Repetir fila\n\n"
    ui.render_saved_playback(3, None, 0.0, consume=True)
    assert capsys.readouterr().out == "🎧 Fila: 3 faixa(s) · 🧹 Remover tocadas\n\n"


def test_session_rows_from_previous_versions_gain_the_queue_modes_off(tmp_path):
    import sqlite3

    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE player_session (id INTEGER PRIMARY KEY CHECK (id = 1), current_track_id TEXT,
        position_seconds REAL NOT NULL DEFAULT 0, listened_seconds REAL NOT NULL DEFAULT 0,
        play_counted INTEGER NOT NULL DEFAULT 0, volume INTEGER, state TEXT NOT NULL DEFAULT 'STOPPED',
        queue_cursor INTEGER NOT NULL DEFAULT 0, current_entry INTEGER, updated_at TEXT)""")
    conn.execute("INSERT INTO player_session (id, volume) VALUES (1, 55)")
    conn.commit()
    conn.close()
    store = SQLitePlaybackStore(db)
    try:
        saved = store.load_session()
        assert saved.volume == 55 and saved.repeat is False and saved.consume is False
        store.save_session(None, 0.0, 0.0, False, volume=55, repeat=True)
        assert store.load_session().repeat is True
        store.save_session(None, 0.0, 0.0, False, volume=55, consume=True)
        assert store.load_session().consume is True and store.load_session().repeat is False
    finally:
        store.close()
