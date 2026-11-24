"""Tests for the playback engine and play queue (ADR 0015).

Most tests use FakeOutput: an audio "device" that pulls PCM from the engine at 20x real time
and records it, so playback order, silence during pause and volume can be checked on the
actual samples. Tracks are pure tones with distinct frequencies, so the recorded audio tells
which track played. A few tests use miniaudio's NULL backend, which runs the real device
stack at real-time pace without any sound hardware.
"""

import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from audio_synth import SR, sine, write_wav
from musicmatch.domain.models import Track
from musicmatch.domain.player import PlayerState, volume_to_gain
from musicmatch.services.audio_decoder import AudioDecoder, _load_miniaudio
from musicmatch.services.player import (
    MiniaudioOutput,
    PlaybackUnavailableError,
    PlayerService,
    _Session,
    is_track_available,
)

HAS_MINIAUDIO = _load_miniaudio() is not None
HAS_FFMPEG = shutil.which("ffmpeg") is not None


class FakeHandle:
    backend = "Fake"

    def __init__(self, output, sample_rate, channels, pull):
        self.output, self.sample_rate, self.channels, self.pull = output, sample_rate, channels, pull
        self.blocks = []
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        block = 1024
        while not self._closed.is_set():
            self.blocks.append(self.pull(block).copy())
            time.sleep(block / self.sample_rate / self.output.speed)

    def close(self):
        self._closed.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)

    @property
    def audio(self):
        return np.concatenate(self.blocks) if self.blocks else np.zeros((0, self.channels), dtype=np.float32)


class FakeOutput:
    def __init__(self, speed=20.0, fail=False):
        self.speed, self.fail = speed, fail
        self.handles = []

    def open(self, sample_rate, channels, pull):
        if self.fail:
            raise PlaybackUnavailableError("no audio device in this test")
        handle = FakeHandle(self, sample_rate, channels, pull)
        self.handles.append(handle)
        return handle


def dominant_hz(audio: np.ndarray, sample_rate: int = SR) -> float:
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    audible = np.nonzero(np.abs(mono) > 1e-4)[0]
    mono = mono[audible[0]:audible[-1] + 1]  # trim leading/trailing silence only
    spectrum = np.abs(np.fft.rfft(mono * np.hanning(mono.size)))
    return float(np.fft.rfftfreq(mono.size, 1 / sample_rate)[np.argmax(spectrum)])


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2))) if audio.size else 0.0


@pytest.fixture
def tones(tmp_path):
    """Factory: tone track (1 s by default) with its own frequency."""

    def make(name, freq, seconds=1.0, status="AVAILABLE"):
        path = write_wav(tmp_path / f"{name}.wav", sine(freq, seconds, -6.0))
        return Track(id=f"trk_{name}", title=name, artist="Tester", album="Tones", genre="Test",
                     duration_seconds=seconds, bitrate_kbps=1411, bpm=120, file_path=str(path), status=status)

    return make


@pytest.fixture
def player_factory():
    players = []

    def make(output=None, decoder=None, volume=100):
        player = PlayerService(
            decoder=decoder or AudioDecoder(ffmpeg_path=None, use_miniaudio=False, timeout_seconds=None),
            output=output if output is not None else FakeOutput(),
            volume=volume,
        )
        events = []
        player.add_listener(events.append)
        players.append(player)
        return player, events

    yield make
    for player in players:
        player.shutdown()


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def kinds(events):
    return [e.kind for e in events]


def test_a_track_played_from_idle_plays_to_the_end_and_stops(tones, player_factory):
    output = FakeOutput()
    player, events = player_factory(output)
    track = tones("a440", 440.0)

    assert player.play_track(track) is True
    assert player.state == PlayerState.PLAYING and player.status().current.id == "trk_a440"
    assert wait_for(lambda: player.state == PlayerState.STOPPED)
    assert kinds(events) == ["TRACK_STARTED", "PLAY_COUNTED", "TRACK_FINISHED"]
    assert [e.background for e in events] == [False, True, True]
    assert player.status().current is None

    audio = output.handles[0].audio
    played = audio[np.abs(audio).max(axis=1) > 0]
    assert abs(played.shape[0] - SR) < 1024  # the whole second, no more, no less
    assert dominant_hz(played) == pytest.approx(440.0, abs=2.0)


def test_queue_add_plays_next_add_last_appends_and_played_tracks_stay(tones, player_factory):
    output = FakeOutput()
    player, events = player_factory(output)
    a, b, c = tones("a", 330.0), tones("b", 550.0), tones("c", 770.0)
    assert player.queue_add_last(a) and player.queue_add_last(b) and player.queue_add_next(c)
    assert [t.id for t in player.status().queue] == ["trk_c", "trk_a", "trk_b"]

    assert player.play_queue() is True
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))
    started = [e.track.id for e in events if e.kind == "TRACK_STARTED"]
    assert started == ["trk_c", "trk_a", "trk_b"]
    assert [dominant_hz(h.audio) for h in output.handles] == [
        pytest.approx(770.0, abs=3), pytest.approx(330.0, abs=3), pytest.approx(550.0, abs=3)
    ]
    status = player.status()
    assert [t.id for t in status.queue] == ["trk_c", "trk_a", "trk_b"]  # playing never removes entries
    assert status.next_index == 0 and status.current_index is None  # the end resets to the start


def test_missing_tracks_are_notified_and_never_played(tones, player_factory, tmp_path):
    player, events = player_factory()
    soft_deleted = tones("gone", 440.0, status="MISSING")
    assert not is_track_available(soft_deleted)

    assert player.play_track(soft_deleted) is False
    assert player.queue_add_last(soft_deleted) is False
    assert kinds(events) == ["TRACK_MISSING", "TRACK_MISSING"]
    assert player.status().queue == [] and player.state == PlayerState.STOPPED

    # A queued file that disappears later (e.g. drive unplugged) is skipped with a notice,
    # but stays in the queue: it plays again once the drive is back.
    first, vanishing, last = tones("first", 330.0, 0.5), tones("vanishing", 440.0), tones("last", 660.0, 0.5)
    for track in (first, vanishing, last):
        player.queue_add_last(track)
    Path(vanishing.file_path).unlink()
    events.clear()
    player.play_queue()
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))
    ignored = ("TRACK_FINISHED", "PLAY_COUNTED")
    assert [(e.kind, e.track.id if e.track else None) for e in events if e.kind not in ignored] == [
        ("TRACK_STARTED", "trk_first"),
        ("TRACK_MISSING", "trk_vanishing"),
        ("TRACK_STARTED", "trk_last"),
        ("QUEUE_ENDED", None),
    ]
    assert [t.id for t in player.status().queue] == ["trk_first", "trk_vanishing", "trk_last"]


def test_requesting_a_missing_track_keeps_the_current_one_playing(tones, player_factory):
    player, events = player_factory(FakeOutput(speed=1.0))
    player.play_track(tones("long", 440.0, seconds=5.0))
    assert player.play_track(tones("gone", 550.0, status="MISSING")) is False
    assert player.state == PlayerState.PLAYING and player.status().current.id == "trk_long"


def test_pause_fades_out_releases_the_device_and_continues_at_the_same_position(tones, player_factory):
    output = FakeOutput(speed=4.0)
    player, events = player_factory(output)
    player.play_track(tones("long", 440.0, seconds=5.0))
    assert wait_for(lambda: player.status().position_seconds > 0.5)

    assert player.pause() is True and player.state == PlayerState.PAUSED
    first = output.handles[0]
    assert first._closed.is_set()  # the device is released while paused
    last_audible = [block for block in first.blocks if block.any()][-1]
    assert np.abs(last_audible[-1]).max() < 1e-3  # faded out to silence: no click at the cut
    assert np.abs(last_audible[:64]).max() > 10 * np.abs(last_audible[-64:]).max()
    position = player.status().position_seconds
    time.sleep(0.2)
    assert player.status().position_seconds == position and player.status().resume_available
    assert player.pause() is False  # already paused

    assert player.toggle_pause() is True and player.state == PlayerState.PLAYING
    assert len(output.handles) == 2
    assert kinds(events) == ["TRACK_STARTED", "PAUSED", "RESUMED"]
    assert events[1].message == events[2].message == f"em 00:0{int(position)}"
    assert wait_for(lambda: player.status().position_seconds > position + 0.2)
    assert wait_for(lambda: player.state == PlayerState.STOPPED, timeout=5)
    remaining = np.count_nonzero(np.abs(output.handles[1].audio).max(axis=1))
    assert remaining == pytest.approx((5.0 - position) * SR, abs=0.05 * SR)  # nothing replayed or lost


def test_volume_uses_a_cubic_taper_and_is_applied_to_the_output(tones, player_factory):
    assert volume_to_gain(100) == 1.0 and volume_to_gain(0) == 0.0
    assert volume_to_gain(50) == pytest.approx(0.125)
    with pytest.raises(ValueError):
        volume_to_gain(101)

    output = FakeOutput(speed=4.0)
    player, events = player_factory(output)
    player.play_track(tones("long", 440.0, seconds=5.0))
    assert wait_for(lambda: len(output.handles[0].blocks) > 10)
    loud = rms(np.concatenate(output.handles[0].blocks[2:8]))
    player.set_volume(50)
    mark = len(output.handles[0].blocks)
    assert wait_for(lambda: len(output.handles[0].blocks) > mark + 8)
    quiet = rms(np.concatenate(output.handles[0].blocks[mark + 2:mark + 8]))
    assert quiet / loud == pytest.approx(0.125, rel=0.05)
    assert player.volume == 50 and events[-1].kind == "VOLUME_CHANGED"
    with pytest.raises(ValueError):
        player.set_volume(-1)


def test_stop_resets_to_the_start_of_the_queue_and_next_skips(tones, player_factory):
    player, events = player_factory(FakeOutput(speed=1.0))
    a, b, c = tones("a", 330.0, 5.0), tones("b", 550.0, 5.0), tones("c", 660.0, 5.0)
    for track in (a, b, c):
        player.queue_add_last(track)
    player.play_queue()
    assert player.next() is True and player.status().current.id == "trk_b"
    assert player.status().current_index == 1 and player.status().next_index == 2

    assert player.stop() is True and player.state == PlayerState.STOPPED
    status = player.status()
    assert status.current is None and not status.resume_available
    assert status.next_index == 0 and [t.id for t in status.queue] == ["trk_a", "trk_b", "trk_c"]
    assert events[-1].kind == "STOPPED"
    assert player.stop() is False

    assert player.play() is True and player.status().current.id == "trk_a"  # from the start again
    player.next()
    player.next()
    assert player.status().current.id == "trk_c"
    assert player.next() is False and player.state == PlayerState.STOPPED  # past the end: reset
    assert kinds(events)[-1] == "QUEUE_ENDED" and player.status().next_index == 0


def test_undecodable_tracks_are_reported_and_skipped(tones, player_factory, tmp_path):
    player, events = player_factory()
    broken_path = tmp_path / "broken.wav"
    broken_path.write_bytes(b"RIFF....WAVEjunk-not-audio")
    broken = tones("ok", 440.0, 0.5).model_copy(update={"id": "trk_broken", "file_path": str(broken_path)})
    player.queue_add_last(broken)
    player.queue_add_last(tones("fine", 660.0, 0.5))
    player.play_queue()
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))
    relevant = [(e.kind, e.track.id if e.track else None) for e in events if e.kind in ("TRACK_ERROR", "TRACK_STARTED")]
    assert relevant == [("TRACK_ERROR", "trk_broken"), ("TRACK_STARTED", "trk_fine")]


def test_missing_audio_device_stops_and_keeps_the_cursor_on_the_entry(tones, player_factory):
    player, events = player_factory(FakeOutput(fail=True))
    player.queue_add_last(tones("a", 440.0))
    assert player.play_queue() is False
    assert kinds(events)[-1] == "DEVICE_ERROR" and "no audio device" in events[-1].message
    assert player.state == PlayerState.STOPPED
    status = player.status()
    assert [t.id for t in status.queue] == ["trk_a"] and status.next_index == 0  # retry later with /play


def test_queue_remove_and_clear_keep_the_cursor_consistent(tones, player_factory):
    player, _ = player_factory(FakeOutput(speed=1.0))
    a, b, c = tones("a", 330.0, 5.0), tones("b", 550.0, 5.0), tones("c", 660.0, 5.0)
    for track in (a, b, a, c):
        player.queue_add_last(track)
    player.play_queue()
    player.next()  # now playing entry 2 (b); cursor on entry 3 (a)
    assert (player.status().current_index, player.status().next_index) == (1, 2)

    player.queue_add_next(c)  # plays right after b
    assert [t.id for t in player.status().queue] == ["trk_a", "trk_b", "trk_c", "trk_a", "trk_c"]
    assert player.queue_remove("trk_a") == 2  # entries before and after the cursor
    status = player.status()
    assert [t.id for t in status.queue] == ["trk_b", "trk_c", "trk_c"]
    assert (status.current_index, status.next_index) == (0, 1)  # still b playing, c next

    assert player.queue_remove_at(1).id == "trk_b"  # the playing entry: it keeps playing, off-queue
    assert player.state == PlayerState.PLAYING and player.status().current_index is None
    assert player.queue_remove("trk_zzz") == 0
    assert player.queue_clear() == 2 and player.status().queue == [] and player.status().next_index == 0


def test_listeners_can_call_back_and_broken_listeners_are_isolated(tones, player_factory):
    player, events = player_factory()
    seen_states = []
    player.add_listener(lambda e: seen_states.append(player.status().state))  # re-entrant: no deadlock
    player.add_listener(lambda e: 1 / 0)  # a broken view must not break playback
    player.play_track(tones("a", 440.0, 0.5))
    assert wait_for(lambda: "TRACK_FINISHED" in kinds(events))
    assert wait_for(lambda: seen_states and seen_states[-1] == PlayerState.STOPPED)


def test_end_of_a_replaced_track_is_ignored(tones, player_factory):
    player, events = player_factory(FakeOutput(speed=1.0))
    player.play_track(tones("old", 330.0, 5.0))
    old_session = player._session
    player.play_track(tones("new", 550.0, 5.0))
    events.clear()
    player._on_session_end(old_session)  # a late end-of-track signal from the old device
    assert events == [] and player.status().current.id == "trk_new"


def test_session_pull_pads_with_silence_and_never_raises():
    class Stream:
        format = type("F", (), {"sample_rate": 8000, "channels": 2})()

        def chunks(self):
            yield np.ones((100, 2), dtype=np.float32)

        def close(self):
            pass

    ended = []
    session = _Session(Track(id="trk_x", title="x", artist="x", album="x", genre="x", duration_seconds=1,
                             bitrate_kbps=1, bpm=1, file_path="x"),
                       Stream(), threading.Event(), lambda: 1.0, ended.append)
    session.start()
    session.wait_prebuffer()
    out = session.pull(256)
    assert out.shape == (256, 2) and out[:100].all() and not out[100:].any()
    assert wait_for(lambda: ended == [session])
    session._gain_source = lambda: 1 / 0  # a failure inside the device callback
    assert session.pull(64).shape == (64, 2)
    session.close()


@pytest.mark.skipif(not HAS_MINIAUDIO, reason="miniaudio not installed")
def test_real_device_stack_plays_in_real_time(tones, player_factory):
    player, events = player_factory(MiniaudioOutput(backend="null"))
    started = time.time()
    assert player.play_track(tones("a", 440.0, seconds=1.0)) is True
    assert player.status().output_backend == "Null"
    assert wait_for(lambda: "TRACK_FINISHED" in kinds(events), timeout=10)
    assert time.time() - started >= 0.9  # paced by the (virtual) device clock, not instantly


@pytest.mark.skipif(not HAS_MINIAUDIO, reason="miniaudio not installed")
def test_unknown_audio_backend_is_rejected():
    with pytest.raises(PlaybackUnavailableError, match="wasapi"):
        MiniaudioOutput(backend="gramophone")


@pytest.mark.skipif(not (HAS_MINIAUDIO and HAS_FFMPEG), reason="needs miniaudio and FFmpeg")
def test_compressed_formats_play_through_ffmpeg(tones, player_factory, tmp_path):
    source = tones("src", 440.0, seconds=1.0)
    m4a = tmp_path / "song.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", source.file_path, "-c:a", "aac", str(m4a)], check=True)
    output = FakeOutput()
    player, events = player_factory(output, decoder=AudioDecoder(timeout_seconds=None))
    assert player.play_track(source.model_copy(update={"id": "trk_m4a", "file_path": str(m4a)}))
    assert wait_for(lambda: "TRACK_FINISHED" in kinds(events))
    assert dominant_hz(output.handles[0].audio) == pytest.approx(440.0, abs=2.0)


def test_play_by_id_continues_the_queue_only_when_it_was_in_progress(tones, player_factory):
    player, events = player_factory()
    a, b, extra = tones("a", 330.0, 0.5), tones("b", 550.0, 0.5), tones("extra", 880.0, 0.5)
    player.queue_add_last(a)
    player.queue_add_last(b)

    player.play_track(extra)  # idle player: only this track plays
    assert wait_for(lambda: player.state == PlayerState.STOPPED)
    assert [e.track.id for e in events if e.kind == "TRACK_STARTED"] == ["trk_extra"]

    events.clear()
    player.play_queue()  # a is playing ...
    player.play_track(extra)  # ... interrupted by a track played by ID ...
    assert wait_for(lambda: "QUEUE_ENDED" in kinds(events))  # ... then the queue goes on with b
    assert [e.track.id for e in events if e.kind == "TRACK_STARTED"] == ["trk_a", "trk_extra", "trk_b"]
