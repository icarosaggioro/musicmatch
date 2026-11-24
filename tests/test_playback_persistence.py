"""Persistent queue, resume point and play counters (ADR 0016).

"Restarting the application" is simulated by shutting a PlayerService down and building a
new one on the same database file: everything the user expects to survive must come back
from SQLite, not from memory.
"""

import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from audio_synth import SR, sine, tag_file, write_wav
from musicmatch.domain.models import Track
from musicmatch.domain.player import PlayerState, play_count_threshold
from musicmatch.services.audio_decoder import AudioDecoder
from musicmatch.services.library import LibraryService
from musicmatch.services.player import PlayerService
from musicmatch.storage.playback_store import SQLitePlaybackStore
from musicmatch.storage.sqlite_repo import SQLiteTrackRepository
from test_player_service import FakeOutput, dominant_hz, kinds, wait_for


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "musicmatch.db")


@pytest.fixture
def repo(db_path):
    r = SQLiteTrackRepository(db_path=db_path)
    yield r
    r.close()


@pytest.fixture
def store(db_path, repo):
    s = SQLitePlaybackStore(db_path)
    yield s
    s.close()


@pytest.fixture
def add_track(repo, tmp_path):
    """Writes a WAV (one or more tone segments of 1 s) and registers it in the catalog."""

    def make(name, freqs=(440.0,), duration_tag=None):
        signal = np.concatenate([sine(f, 1.0, -6.0) for f in freqs])
        path = write_wav(tmp_path / f"{name}.wav", signal)
        stat = path.stat()
        track = Track(id=f"trk_{name}", title=name, artist="Tester", album="Tones", genre="Test",
                      duration_seconds=len(freqs) if duration_tag is None else duration_tag,
                      bitrate_kbps=1411, bpm=120, file_path=str(path), file_mtime=stat.st_mtime, file_size=stat.st_size)
        repo.insert_track(track)
        return track

    return make


def make_player(store, speed=20.0, **kwargs):
    output = FakeOutput(speed=speed)
    player = PlayerService(
        decoder=AudioDecoder(ffmpeg_path=None, use_miniaudio=False, timeout_seconds=None),
        output=output, volume=100, store=store, tick_seconds=0.02, autosave_seconds=0.05, **kwargs,
    )
    events = []
    player.add_listener(events.append)
    return player, events, output


# ----------------------------------------------------------------------
# Threshold rule
# ----------------------------------------------------------------------


def test_play_count_threshold_rule():
    assert play_count_threshold(300.0) == 60.0  # one minute of actual listening
    assert play_count_threshold(45.0) == 45.0  # shorter tracks: heard to the end
    assert play_count_threshold(0.0) == 60.0 and play_count_threshold(None) == 60.0  # unknown duration
    assert play_count_threshold(300.0, seconds=30.0) == 30.0  # MUSICMATCH_PLAY_COUNT_SECONDS
    with pytest.raises(ValueError):
        play_count_threshold(100.0, seconds=0)


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


def test_store_keeps_duplicates_in_order_and_follows_the_catalog(store, repo, add_track):
    a, b = add_track("a"), add_track("b")
    store.save_queue([a.id, b.id, a.id, a.id])
    assert [t.id for t in store.load_queue()] == ["trk_a", "trk_b", "trk_a", "trk_a"]

    relocated = a.model_copy(update={"id": "trk_a_moved", "file_path": a.file_path + ".moved"})
    repo.relocate_track(a.id, relocated)  # Fast Relocation rewrites the ID: entries follow it
    assert [t.id for t in store.load_queue()] == ["trk_a_moved", "trk_b", "trk_a_moved", "trk_a_moved"]

    repo.delete_track("trk_a_moved")  # /unindex: its entries leave the queue, the others stay
    assert [t.id for t in store.load_queue()] == ["trk_b"]
    store.save_queue(["trk_b", "trk_does_not_exist"])
    assert [t.id for t in store.load_queue()] == ["trk_b"]


def test_store_session_round_trip(store, add_track, repo):
    a = add_track("a")
    assert store.load_session().track is None
    store.save_session(a.id, 83.25, 80.0, True, volume=35)
    saved = store.load_session()
    assert (saved.track.id, saved.position_seconds, saved.listened_seconds, saved.play_counted, saved.volume) == (
        "trk_a", 83.25, 80.0, True, 35)
    repo.delete_track(a.id)
    gone = store.load_session()
    assert gone.track is None and gone.position_seconds == 0.0 and gone.volume == 35


def test_record_play_updates_track_total_and_history_atomically(store, repo, add_track):
    a, b = add_track("a"), add_track("b")
    first, second, third = store.record_play(a.id, 130.0), store.record_play(a.id, 131.0), store.record_play(b.id, 90.0)
    assert [(r.track_play_count, r.total_plays) for r in (first, second, third)] == [(1, 1), (2, 2), (1, 3)]
    assert repo.get_track(a.id).play_count == 2 and repo.get_track(a.id).last_played_at
    assert repo.get_stats()["total_plays"] == 3
    assert [h[0] for h in store.recent_history()] == ["trk_b", "trk_a", "trk_a"]

    repo.delete_track(a.id)  # history and total survive unindexing
    assert store.total_plays() == 3 and [h[0] for h in store.recent_history()] == ["trk_b", None, None]
    assert store.record_play("trk_gone", 10.0).total_plays == 4  # unindexed while playing still counts


def test_rescanning_a_modified_file_keeps_its_play_count_and_queue_entries(tmp_path, repo, store):
    music = tmp_path / "music"
    path = tag_file(write_wav(music / "song.wav", sine(440, 1.0, -6.0)), title="Song", artist="Band")
    library = LibraryService(repository=repo)
    library.scan_and_ingest(str(music))
    track = repo.get_all_tracks()[0]
    store.record_play(track.id, 60.0)
    store.save_queue([track.id, track.id])

    tag_file(path, title="Song (Remastered)", artist="Band")  # external retag changes mtime/size
    os.utime(path, (time.time(), time.time() + 5))
    assert library.scan_and_ingest(str(music)).tracks_updated == 1

    updated = repo.get_track(track.id)
    assert updated.title == "Song (Remastered)" and updated.play_count == 1
    assert [t.id for t in store.load_queue()] == [track.id, track.id]


def test_databases_from_previous_versions_gain_the_new_columns_and_tables(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE tracks (id TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL,
        album TEXT NOT NULL, genre TEXT NOT NULL, duration_seconds REAL NOT NULL, bitrate_kbps INTEGER NOT NULL,
        bpm REAL NOT NULL, file_path TEXT UNIQUE NOT NULL, mood TEXT, lufs REAL)""")
    conn.execute("INSERT INTO tracks VALUES ('trk_old','Old','A','B','G',10,128,120,'/m/old.mp3',NULL,NULL)")
    conn.commit()
    conn.close()
    store = SQLitePlaybackStore(db)  # the store alone can bring an old database up to date
    try:
        assert store.record_play("trk_old", 5.0).track_play_count == 1  # UPDATE fires the FTS trigger
        store.save_queue(["trk_old"])
        assert [t.play_count for t in store.load_queue()] == [1]
    finally:
        store.close()
    repo = SQLiteTrackRepository(db_path=db)
    try:
        assert [t.id for t in repo.search_fulltext("Old")] == ["trk_old"]  # index rebuilt, not corrupted
        assert repo.conn.execute("PRAGMA integrity_check;").fetchone()[0] == "ok"
    finally:
        repo.close()


# ----------------------------------------------------------------------
# Player + store: queue, resume and counting across "restarts"
# ----------------------------------------------------------------------


def test_duplicates_are_queued_played_and_counted_each_time(store, repo, add_track):
    a, b = add_track("a", (440.0,)), add_track("b", (660.0,))
    player, events, output = make_player(store)
    for track in (a, b, a, a):
        assert player.queue_add_last(track)
    assert "3x" in events[-1].message
    assert [t.id for t in player.status().queue] == ["trk_a", "trk_b", "trk_a", "trk_a"]

    assert player.queue_remove_at(3).id == "trk_a"  # removing one copy keeps the others
    assert [t.id for t in player.status().queue] == ["trk_a", "trk_b", "trk_a"]

    player.play_queue()
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))
    assert [e.track.id for e in events if e.kind == "TRACK_STARTED"] == ["trk_a", "trk_b", "trk_a"]
    assert repo.get_track("trk_a").play_count == 2 and repo.get_track("trk_b").play_count == 1
    assert store.total_plays() == 3 and player.status().total_plays == 3
    player.shutdown()


def test_queue_and_paused_position_survive_a_restart(store, add_track):
    first = add_track("first", (300.0, 300.0, 600.0, 600.0))  # tone changes at 2 s
    second, third = add_track("second", (700.0,)), add_track("third", (800.0,))
    player, events, _ = make_player(store, speed=1.0)
    for track in (first, second, third, second):
        player.queue_add_last(track)
    player.set_volume(35)
    player.play_queue()
    assert wait_for(lambda: player.status().position_seconds >= 2.3, timeout=6)
    assert player.pause() is True
    paused_at = player.status().position_seconds
    assert 2.3 <= paused_at < 3.5
    player.shutdown()  # leaving the application

    restarted, events, output = make_player(store)
    status = restarted.status()
    assert status.state == PlayerState.PAUSED and status.resume_available
    assert status.current.id == "trk_first" and status.position_seconds == pytest.approx(paused_at, abs=0.01)
    assert (status.current_index, status.next_index) == (0, 1)
    assert [t.id for t in status.queue] == ["trk_first", "trk_second", "trk_third", "trk_second"]
    assert status.volume == 35

    assert restarted.play() is True  # '/play' (or '/pause') continues where the user paused
    resumed = next(e for e in events if e.kind == "RESUMED")
    assert resumed.track.id == "trk_first" and resumed.message.startswith("em 00:0")
    assert wait_for(lambda: len(output.handles) >= 2)
    assert dominant_hz(output.handles[0].audio) == pytest.approx(600.0, abs=3)  # second half only
    resumed_frames = np.count_nonzero(np.abs(output.handles[0].audio).max(axis=1))
    assert resumed_frames == pytest.approx((4.0 - paused_at) * SR, abs=0.1 * SR)
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))
    assert [e.track.id for e in events if e.kind == "TRACK_STARTED"] == ["trk_second", "trk_third", "trk_second"]
    assert len(restarted.status().queue) == 4  # everything played, nothing removed
    restarted.shutdown()


def test_stop_survives_a_restart_as_a_reset_to_the_first_track(store, add_track):
    a, b = add_track("a", (440.0,) * 3), add_track("b", (660.0,) * 3)
    player, _, _ = make_player(store, speed=1.0)
    player.queue_add_last(a)
    player.queue_add_last(b)
    player.play_queue()
    player.next()
    assert wait_for(lambda: player.status().position_seconds >= 0.5, timeout=5)
    player.stop()
    player.shutdown()

    saved = store.load_session()
    assert (saved.state, saved.track.id, saved.position_seconds, saved.queue_cursor) == ("STOPPED", "trk_b", 0.0, 0)
    restarted, events, _ = make_player(store)
    assert restarted.state == PlayerState.STOPPED and not restarted.status().resume_available
    restarted.play()
    assert next(e for e in events if e.kind == "TRACK_STARTED").track.id == "trk_a"
    restarted.shutdown()


def test_exit_while_playing_and_crashes_keep_the_position(store, add_track, db_path):
    long_track = add_track("long", (440.0,) * 6)
    player, _, _ = make_player(store, speed=1.0)
    player.play_track(long_track)
    assert wait_for(lambda: player.status().position_seconds >= 1.0, timeout=5)
    # A crash (no shutdown): the periodic autosave already stored a recent position.
    assert wait_for(lambda: store.load_session().position_seconds >= 0.8, timeout=3)
    player.shutdown()  # a clean exit (/exit or Ctrl+C) saves the exact position
    saved = store.load_session()
    assert saved.track.id == "trk_long" and saved.position_seconds >= 0.99


def test_counting_threshold_pauses_and_accumulation_across_sessions(store, repo, add_track):
    track = add_track("four", (440.0,) * 4)
    player, events, _ = make_player(store, speed=1.0, play_count_seconds=2.0)  # 60 s by default
    player.play_track(track)
    assert wait_for(lambda: player.status().position_seconds >= 1.2, timeout=5)
    player.pause()
    time.sleep(1.2)  # paused time is not listening time
    assert "PLAY_COUNTED" not in kinds(events)
    player.shutdown()
    assert repo.get_track(track.id).play_count == 0
    saved = store.load_session()
    assert saved.state == "PAUSED" and saved.listened_seconds == pytest.approx(saved.position_seconds, abs=0.05)

    restarted, events, _ = make_player(store, speed=1.0, play_count_seconds=2.0)
    restarted.play()  # resume: the 1.2 s heard before the restart still count
    assert wait_for(lambda: "PLAY_COUNTED" in kinds(events), timeout=5)
    counted = next(e for e in events if e.kind == "PLAY_COUNTED")
    assert counted.background and "1" in counted.message
    assert restarted.status().position_seconds < 3.2  # counted at ~2 s of listening, before the end
    assert wait_for(lambda: restarted.state == PlayerState.STOPPED, timeout=5)
    assert kinds(events).count("PLAY_COUNTED") == 1  # never twice for one play-through
    assert repo.get_track(track.id).play_count == 1 and store.total_plays() == 1
    restarted.shutdown()


def test_default_threshold_is_sixty_seconds_of_listening(store, add_track):
    player, _, _ = make_player(store)
    session_track = add_track("song", (440.0,), duration_tag=240.0)
    player.play_track(session_track)
    assert player._session.threshold == 60.0
    player.shutdown()


def test_skipping_early_does_not_count(store, repo, add_track):
    a, b = add_track("a", (440.0,) * 4), add_track("b", (660.0,))
    player, events, _ = make_player(store, speed=1.0, play_count_seconds=2.0)
    player.queue_add_last(a)
    player.queue_add_last(b)
    player.play_queue()
    assert wait_for(lambda: player.status().position_seconds >= 0.5, timeout=5)
    player.next()
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events), timeout=5)
    assert repo.get_track("trk_a").play_count == 0 and repo.get_track("trk_b").play_count == 1
    player.shutdown()


@pytest.mark.parametrize("duration_tag", [600.0, 0.0])
def test_wrong_or_missing_duration_tags_still_count_a_full_listen(store, repo, add_track, duration_tag):
    track = add_track("short", (440.0,), duration_tag=duration_tag)  # really 1 s long
    player, events, _ = make_player(store)
    player.play_track(track)
    assert wait_for(lambda: "TRACK_FINISHED" in kinds(events))
    assert repo.get_track(track.id).play_count == 1


def test_persistence_failures_are_reported_once_and_never_stop_the_music(store, add_track):
    a = add_track("a", (440.0,))
    broken = MagicMock(wraps=store)
    broken.save_queue.side_effect = sqlite3.OperationalError("database is locked")
    player, events, _ = make_player(broken)
    player.queue_add_last(a)
    player.queue_add_last(a)
    assert kinds(events).count("PERSISTENCE_ERROR") == 1
    assert player.play_queue() is True
    player.shutdown()


def test_harness_announces_the_saved_session_at_startup(store, add_track, db_path, monkeypatch):
    from musicmatch.commands.registry import CommandRegistry
    from musicmatch.harness.loop import Harness

    a = add_track("a")
    store.save_queue([a.id, a.id])
    store.save_session(a.id, 75.0, 70.0, False, volume=60)
    ui = MagicMock()
    agent = MagicMock()
    agent.model_name = "test"
    repo = SQLiteTrackRepository(db_path=db_path)
    harness = Harness(agent=agent, ui=ui, registry=CommandRegistry(), database=repo)
    monkeypatch.setattr("builtins.input", lambda _prompt="": (_ for _ in ()).throw(EOFError()))
    harness.start()
    queue_size, track, position = ui.render_saved_playback.call_args.args
    assert (queue_size, track.id, position) == (2, "trk_a", 75.0)
    repo.close()


def test_process_wide_player_restores_from_the_catalog_database(store, add_track, db_path):
    from musicmatch.services import player as player_module

    a = add_track("a")
    store.save_queue([a.id])
    player_module.shutdown_player_service()
    try:
        restored = player_module.get_player_service(db_path)
        assert [t.id for t in restored.status().queue] == ["trk_a"]
        assert player_module.get_player_service(db_path) is restored
    finally:
        player_module.shutdown_player_service()
