"""Audio Player Engine (ADR 0015): cross-platform playback, transport controls and play queue.

Architecture
------------
                 decoder thread                       audio device thread (miniaudio)
    PcmStream ──> _Session._produce ──> bounded buffer ──> _Session.pull ──> OS audio API
    (FFmpeg / miniaudio / wave)         (~4 s of PCM)      (volume ramp,     (WASAPI, Core Audio,
                                                            pause, EOF)       PulseAudio/ALSA, ...)

- Decoding reuses the AudioDecoder of the analysis pipeline (ADR 0014), so every format the
  scanner indexes can be played. The watchdog is disabled: playback paces decoding in real time.
- Output goes through the AudioOutput interface. MiniaudioOutput is the implementation
  (self-contained wheels for Windows, macOS and Linux); tests and headless machines use the
  miniaudio NULL backend or a fake output. A sounddevice/PortAudio output could be added
  behind the same interface without touching the engine.
- The device callback must never block or raise: `pull` only copies from the buffer, applies
  a per-block gain ramp (click-free pause/stop/volume) and pads underruns with silence.
- End of track is detected by the engine (the device has no notion of it) and handled on a
  short-lived thread, because a device cannot be closed from inside its own callback.
- PlayerService is thread-safe (one RLock). Events are collected under the lock and emitted
  after releasing it, so listeners (console, future GUI) may call back into the player.
- The player never writes to the catalog: it works on Track snapshots, so no SQLite
  connection is touched from playback threads.
"""

import atexit
import collections
import ctypes
import logging
import os
import random
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Deque, Dict, List, Optional, Protocol, Tuple

import numpy as np

from musicmatch.config import settings
from musicmatch.domain.issues import IssueKind
from musicmatch.domain.models import Track
from musicmatch.domain.player import (
    DEFAULT_VOLUME,
    PlayerEvent,
    PlayerEventKind,
    PlayerState,
    PlayerStatus,
    QueueOrder,
    play_count_threshold,
    queue_sort_key,
    volume_to_gain,
)
from musicmatch.services.audio_decoder import (
    AudioDecodeError,
    AudioDecoder,
    DecodeCancelled,
    DecoderUnavailableError,
    PcmStream,
    _load_miniaudio,
)
from musicmatch.services.issues import report_issue

logger = logging.getLogger(__name__)

PlayerListener = Callable[[PlayerEvent], None]
_PREBUFFER_SECONDS = 0.5
_MAX_BUFFER_SECONDS = 4.0


class PlaybackUnavailableError(RuntimeError):
    """No audio output is usable (library missing, no device, invalid backend)."""


def is_track_available(track: Track) -> bool:
    """A track is playable when it is not soft-deleted and its file exists on disk."""
    return track.status != "MISSING" and os.path.isfile(track.file_path)


# ----------------------------------------------------------------------
# Audio output abstraction
# ----------------------------------------------------------------------


class OutputHandle(Protocol):
    backend: str

    def start(self) -> None: ...

    def close(self) -> None: ...


class AudioOutput(Protocol):
    def open(self, sample_rate: int, channels: int, pull: Callable[[int], np.ndarray]) -> OutputHandle: ...


class _MiniaudioHandle:
    def __init__(self, device, pull: Callable[[int], np.ndarray]) -> None:
        self._device = device
        self._pull = pull
        self.backend = device.backend

    def _generator(self):
        frames = yield b""
        while True:
            frames = yield self._pull(frames)

    def start(self) -> None:
        generator = self._generator()
        next(generator)
        self._device.start(generator)

    def close(self) -> None:
        try:
            self._device.stop()
        finally:
            self._device.close()


_ALSA_ERROR_HANDLER = None  # keeps the ctypes callback alive for the whole process


def _silence_alsa_diagnostics() -> None:
    """Routes libasound's diagnostics away from stderr (Linux only).

    While probing for a device, libasound prints dozens of "ALSA lib ... cannot find card"
    lines straight to the terminal on machines without a sound card (servers, WSL,
    containers). MusicMatch reports a single clear DEVICE_ERROR instead.
    """
    global _ALSA_ERROR_HANDLER
    if _ALSA_ERROR_HANDLER is not None or not sys.platform.startswith("linux"):
        return
    try:
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        handler_type = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
        _ALSA_ERROR_HANDLER = handler_type(lambda *_args: None)
        asound.snd_lib_error_set_handler(_ALSA_ERROR_HANDLER)
    except (OSError, AttributeError):
        pass  # no ALSA on this system: nothing to silence


class MiniaudioOutput:
    """Playback through miniaudio: WASAPI/DirectSound/WinMM, Core Audio, PulseAudio/ALSA/JACK."""

    def __init__(self, backend: Optional[str] = None, buffer_msec: int = 100) -> None:
        _silence_alsa_diagnostics()
        self._ma = _load_miniaudio()
        if self._ma is None:
            raise PlaybackUnavailableError(
                "O pacote 'miniaudio' não está instalado: reinstale o MusicMatch (pip install -e .)."
            )
        self._backends = None
        name = (backend if backend is not None else settings.AUDIO_BACKEND).strip()
        if name:
            member = getattr(self._ma.Backend, name.upper(), None)
            if member is None:
                options = ", ".join(b.name.lower() for b in self._ma.Backend)
                raise PlaybackUnavailableError(f"Backend de áudio desconhecido '{name}'. Opções: {options}.")
            self._backends = [member]
        self._buffer_msec = buffer_msec

    def open(self, sample_rate: int, channels: int, pull: Callable[[int], np.ndarray]) -> OutputHandle:
        ma = self._ma
        try:
            device = ma.PlaybackDevice(
                output_format=ma.SampleFormat.FLOAT32,
                nchannels=channels,
                sample_rate=sample_rate,
                buffersize_msec=self._buffer_msec,
                backends=self._backends,
                app_name="MusicMatch",
            )
        except ma.MiniaudioError as exc:
            detail = ", código ".join(str(part) for part in exc.args) or type(exc).__name__
            raise PlaybackUnavailableError(
                f"nenhum dispositivo de saída de áudio disponível (miniaudio: {detail}). "
                "Verifique se há uma saída de som ativa ou defina MUSICMATCH_AUDIO_BACKEND no .env."
            ) from exc
        return _MiniaudioHandle(device, pull)


# ----------------------------------------------------------------------
# One playing track
# ----------------------------------------------------------------------


class _Session:
    """Decoder thread + buffer + device pull callback for a single track."""

    def __init__(
        self,
        track: Track,
        stream: PcmStream,
        cancel: threading.Event,
        gain_source: Callable[[], float],
        on_end: Callable[["_Session"], None],
        start_offset: float = 0.0,
        base_listened: float = 0.0,
        counted: bool = False,
        threshold: float = float("inf"),
    ) -> None:
        self.track = track
        self.start_offset = start_offset  # where in the file decoding started (resume)
        self.base_listened = base_listened  # seconds heard before this session (previous app run)
        self.counted = counted  # this play-through was already counted
        self.threshold = threshold  # seconds of listening that make it count
        self.stream = stream
        self.sample_rate = stream.format.sample_rate
        self.channels = stream.format.channels
        self.cancel = cancel
        self.paused = False
        self.error: Optional[str] = None
        self.frames_played = 0
        self.handle: Optional[OutputHandle] = None
        self._gain_source = gain_source
        self._on_end = on_end
        self._chunks: Deque[np.ndarray] = collections.deque()
        self._offset = 0
        self._buffered = 0
        self._producer_done = False
        self._ended = False
        self._gain: Optional[float] = None
        self._max_buffer = int(_MAX_BUFFER_SECONDS * self.sample_rate)
        self._cond = threading.Condition()
        self._producer = threading.Thread(target=self._produce, name="musicmatch-player-decoder", daemon=True)

    # -- producer (decoder thread) -----------------------------------------
    def start(self) -> None:
        self._producer.start()

    def _produce(self) -> None:
        try:
            for chunk in self.stream.chunks():
                block = np.ascontiguousarray(chunk, dtype=np.float32)
                with self._cond:
                    while self._buffered >= self._max_buffer and not self.cancel.is_set():
                        self._cond.wait(0.1)
                    if self.cancel.is_set():
                        return
                    self._chunks.append(block)
                    self._buffered += block.shape[0]
                    self._cond.notify_all()
        except DecodeCancelled:
            pass
        except AudioDecodeError as exc:
            self.error = str(exc)
        except Exception as exc:  # never let a decoder bug kill playback silently
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._cond:
                self._producer_done = True
                self._cond.notify_all()

    def wait_prebuffer(self, timeout: float = 2.0) -> None:
        target = int(_PREBUFFER_SECONDS * self.sample_rate)
        with self._cond:
            self._cond.wait_for(lambda: self._buffered >= target or self._producer_done, timeout=timeout)

    @property
    def failed_before_audio(self) -> bool:
        with self._cond:
            return self._producer_done and self.error is not None and self._buffered == 0 and self.frames_played == 0

    # -- consumer (audio device thread) ------------------------------------
    def pull(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, self.channels), dtype=np.float32)
        finished = False
        try:
            with self._cond:
                target = 0.0 if self.paused else self._gain_source()
                if self._gain is None:
                    self._gain = target
                if self.paused and self._gain == 0.0:
                    return out  # fully faded out: hold position, consume nothing
                filled = 0
                while filled < frames and self._chunks:
                    head = self._chunks[0]
                    take = min(frames - filled, head.shape[0] - self._offset)
                    out[filled:filled + take] = head[self._offset:self._offset + take]
                    filled += take
                    self._offset += take
                    if self._offset >= head.shape[0]:
                        self._chunks.popleft()
                        self._offset = 0
                self._buffered -= filled
                self.frames_played += filled
                if filled:
                    if self._gain != target:  # click-free ramp towards the new gain
                        out[:filled] *= np.linspace(self._gain, target, filled, dtype=np.float32)[:, None]
                    elif target != 1.0:
                        out[:filled] *= target
                self._gain = target
                self._cond.notify_all()
                finished = filled < frames and self._producer_done and not self._chunks
        except Exception as exc:  # the device thread must never see an exception
            self.error = f"{type(exc).__name__}: {exc}"
            finished = True
        if finished and not self._ended:
            self._ended = True
            threading.Thread(target=self._on_end, args=(self,), name="musicmatch-player-advance", daemon=True).start()
        return out

    def fade_out(self, timeout: float = 0.25) -> None:
        """Ramps the output to silence before the device is closed (no click on pause/stop/skip)."""
        if self.handle is None or self._ended:
            return
        with self._cond:
            self.paused = True
            self._cond.wait_for(lambda: self._gain == 0.0 or self._ended, timeout=timeout)

    @property
    def position_seconds(self) -> float:
        return self.start_offset + self.frames_played / float(self.sample_rate)

    @property
    def listened_seconds(self) -> float:
        """Audio actually delivered to the device (pauses do not count, resumes accumulate)."""
        return self.base_listened + self.frames_played / float(self.sample_rate)

    def close(self) -> None:
        self.cancel.set()
        with self._cond:
            self._cond.notify_all()
        if self.handle is not None:
            try:
                self.handle.close()
            except Exception:
                logger.warning("Could not close the audio output of %s", self.track.file_path, exc_info=True)
        if self._producer.is_alive():
            self._producer.join(timeout=3.0)
        try:
            self.stream.close()
        except Exception:
            logger.warning("Could not close the decoder of %s", self.track.file_path, exc_info=True)


# ----------------------------------------------------------------------
# Player service (transport + queue + persistence + play counting)
# ----------------------------------------------------------------------


class PlaybackStore(Protocol):
    """Persistence port implemented by storage.playback_store.SQLitePlaybackStore (ADR 0016)."""

    def load_queue(self) -> List[Track]: ...

    def save_queue(self, track_ids: List[str]) -> None: ...

    def load_session(self): ...

    def save_session(self, track_id: Optional[str], position_seconds: float, listened_seconds: float,
                     play_counted: bool, volume: int, state: str = "STOPPED", queue_cursor: int = 0,
                     current_entry: Optional[int] = None, repeat: bool = False,
                     consume: bool = False) -> None: ...

    def record_play(self, track_id: str, listened_seconds: float): ...

    def total_plays(self) -> int: ...


@dataclass
class _ResumePoint:
    """A paused track: /pause or /play continues it where it was paused."""

    track: Track
    position_seconds: float
    listened_seconds: float
    counted: bool


class PlayerService:
    """Thread-safe audio player with a persistent queue, pause/resume point and play counters.

    Queue model (ADR 0016): the queue is a persistent list of entries (duplicates allowed) with
    a cursor. Playing moves the cursor and never removes entries; only the user removes them.
      - _current_entry: index of the entry playing/paused (None for a track played by ID).
      - _cursor: index of the entry that plays next.
    /pause keeps a resume point (also across restarts); /stop resets to the start of the queue.

    Queue modes (ADR 0017):
      - repeat: the end of the queue wraps to the first entry instead of stopping.
      - consume: an entry that counted as played (play-count rule) leaves the queue when
        playback moves on from it. Repeat and consume exclude each other.
      - shuffle / sort reorder the whole queue; playback continues from the current entry
        (sort: at its new position; shuffle: moved to the top).
    """

    def __init__(
        self,
        decoder: Optional[AudioDecoder] = None,
        output: Optional[AudioOutput] = None,
        volume: int = DEFAULT_VOLUME,
        store: Optional[PlaybackStore] = None,
        play_count_seconds: Optional[float] = None,
        tick_seconds: float = 1.0,
        autosave_seconds: float = 5.0,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._decoder = decoder or AudioDecoder(timeout_seconds=None)
        self._output = output
        self._store = store
        self._count_seconds = play_count_seconds if play_count_seconds is not None else settings.PLAY_COUNT_SECONDS
        play_count_threshold(None, self._count_seconds)  # validate the setting early
        self._lock = threading.RLock()
        self._queue: List[Track] = []
        self._cursor = 0
        self._current_entry: Optional[int] = None
        self._continue_queue = False  # after a track played by ID: carry on with the queue?
        self._repeat = False  # repeat mode: the end of the queue wraps to the first entry
        self._consume = False  # consume mode: played entries leave the queue
        self._rng = rng or random.Random()
        self._session: Optional[_Session] = None
        self._resume: Optional[_ResumePoint] = None
        self._last_track: Optional[Track] = None
        self._state = PlayerState.STOPPED
        self._volume = volume
        self._gain = volume_to_gain(volume)
        self._listeners: List[PlayerListener] = []
        self._backend: Optional[str] = None
        self._total_plays = 0
        self._persistence_errors: Dict[str, str] = {}  # last failure per operation (reported once)
        self._tick_seconds = tick_seconds
        self._autosave_seconds = autosave_seconds
        self._last_autosave = 0.0
        self._ticker: Optional[threading.Thread] = None
        self._ticker_stop = threading.Event()
        self.restore_error: Optional[str] = None
        if store is not None:
            self._restore()

    # -- persistence ----------------------------------------------------------
    def _restore(self) -> None:
        """Loads the queue, cursor, paused track and volume saved by the previous session."""
        try:
            queue = self._store.load_queue()
            saved = self._store.load_session()
            self._total_plays = self._store.total_plays()
        except Exception as exc:  # a damaged store must not prevent playback
            self.restore_error = f"{type(exc).__name__}: {exc}"
            return
        self._queue = list(queue)
        self._cursor = min(saved.queue_cursor, len(self._queue))
        if saved.volume is not None and 0 <= saved.volume <= 100:
            self._volume = saved.volume
            self._gain = volume_to_gain(saved.volume)
        self._repeat = bool(getattr(saved, "repeat", False))
        self._consume = bool(getattr(saved, "consume", False)) and not self._repeat
        self._last_track = saved.track
        if saved.track is not None and saved.state == "PAUSED":
            self._resume = _ResumePoint(saved.track, saved.position_seconds, saved.listened_seconds, saved.play_counted)
            entry = saved.current_entry
            valid = entry is not None and 0 <= entry < len(self._queue) and self._queue[entry].id == saved.track.id
            self._current_entry = entry if valid else None
            self._continue_queue = valid
            self._state = PlayerState.PAUSED

    def _persistence_failed(self, operation: str, exc: Exception) -> List[PlayerEvent]:
        message = f"Não foi possível salvar o estado da reprodução ({type(exc).__name__}: {exc})."
        if self._persistence_errors.get(operation) == message:
            return []  # report a recurring failure once, not on every save
        self._persistence_errors[operation] = message
        return [self._event("PERSISTENCE_ERROR", message=message, background=True)]

    def _persistence_ok(self, operation: str) -> None:
        self._persistence_errors.pop(operation, None)

    def _persist_queue(self) -> List[PlayerEvent]:
        if self._store is None:
            return []
        try:
            self._store.save_queue([t.id for t in self._queue])
            self._persistence_ok("queue")
            return []
        except Exception as exc:
            return self._persistence_failed("queue", exc)

    def _persist_session(self) -> List[PlayerEvent]:
        """Saves the last track/position, the state and the cursor.

        While a track plays it is saved as PAUSED at its position, so a crash or a closed
        terminal resumes there, exactly like an explicit /pause.
        """
        if self._store is None:
            return []
        if self._session is not None:
            s = self._session
            values = (s.track.id, s.position_seconds, s.listened_seconds, s.counted, "PAUSED")
        elif self._resume is not None:
            r = self._resume
            values = (r.track.id, r.position_seconds, r.listened_seconds, r.counted, "PAUSED")
        elif self._last_track is not None:
            values = (self._last_track.id, 0.0, 0.0, False, "STOPPED")
        else:
            values = (None, 0.0, 0.0, False, "STOPPED")
        track_id, position, listened, counted, state = values
        try:
            self._store.save_session(
                track_id, position, listened, counted, volume=self._volume, state=state,
                queue_cursor=self._cursor, current_entry=self._current_entry if state == "PAUSED" else None,
                repeat=self._repeat, consume=self._consume,
            )
            self._last_autosave = time.monotonic()
            self._persistence_ok("session")
            return []
        except Exception as exc:
            return self._persistence_failed("session", exc)

    # -- play counting --------------------------------------------------------
    def _maybe_count(self, session: _Session, completed: bool = False) -> List[PlayerEvent]:
        """Counts the play once the track was actually heard for the threshold (default 60 s).

        Tracks shorter than the threshold count when heard to the end; the real, decoded
        length is used at the end of the file because duration tags can be wrong or missing.
        """
        if session.counted:
            return []
        listened = session.listened_seconds
        due = listened >= session.threshold
        if completed and not due:
            due = listened + 0.25 >= play_count_threshold(session.position_seconds, self._count_seconds)
        if not due:
            return []
        session.counted = True
        events: List[PlayerEvent] = []
        track_count = session.track.play_count + 1
        if self._store is not None:
            try:
                record = self._store.record_play(session.track.id, listened)
                track_count, self._total_plays = record.track_play_count, record.total_plays
                self._persistence_ok("count")
            except Exception as exc:
                self._total_plays += 1
                events.extend(self._persistence_failed("count", exc))
        else:
            self._total_plays += 1
        session.track = session.track.model_copy(update={"play_count": track_count})
        self._sync_snapshots(session.track)
        events.insert(0, self._event(
            "PLAY_COUNTED", session.track,
            f"Reproduções da faixa: {track_count} · total: {self._total_plays}", background=True,
        ))
        return events

    def _sync_snapshots(self, track: Track) -> None:
        """Keeps the play count shown for every queued copy of the track up to date."""
        self._queue = [track if t.id == track.id else t for t in self._queue]
        if self._last_track is not None and self._last_track.id == track.id:
            self._last_track = track

    def _tick(self) -> None:
        """Runs every tick_seconds: counts plays as soon as they are due and autosaves the position."""
        events: List[PlayerEvent] = []
        with self._lock:
            session = self._session
            if session is not None and self._state == PlayerState.PLAYING:
                events.extend(self._maybe_count(session))
                if time.monotonic() - self._last_autosave >= self._autosave_seconds:
                    events.extend(self._persist_session())
        self._emit(events)

    def _tick_loop(self) -> None:
        while not self._ticker_stop.wait(self._tick_seconds):
            try:
                self._tick()
            except Exception:  # the ticker must outlive any single failure
                logger.exception("Player ticker failed")

    def _ensure_ticker(self) -> None:
        if self._ticker is None or not self._ticker.is_alive():
            self._ticker_stop.clear()
            self._ticker = threading.Thread(target=self._tick_loop, name="musicmatch-player-ticker", daemon=True)
            self._ticker.start()

    # -- listeners ------------------------------------------------------------
    def add_listener(self, listener: PlayerListener) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: PlayerListener) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def _event(self, kind: PlayerEventKind, track: Optional[Track] = None, message: Optional[str] = None,
               background: bool = False) -> PlayerEvent:
        return PlayerEvent(kind=kind, state=self._state, track=track, message=message, background=background)

    def _emit(self, events: List[PlayerEvent]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for event in events:
            _report_player_issue(event)
            for listener in listeners:
                try:
                    listener(event)
                except Exception:  # a broken view must never break playback, but it is a bug
                    logger.exception("Player listener failed on %s", event.kind)

    # -- status ---------------------------------------------------------------
    @property
    def state(self) -> PlayerState:
        return self._state

    @property
    def volume(self) -> int:
        return self._volume

    @property
    def total_plays(self) -> int:
        return self._total_plays

    @property
    def repeat(self) -> bool:
        return self._repeat

    @property
    def consume(self) -> bool:
        return self._consume

    def status(self) -> PlayerStatus:
        with self._lock:
            session, resume = self._session, self._resume
            if session is not None:
                current, position = session.track, session.position_seconds
            elif resume is not None:
                current, position = resume.track, resume.position_seconds
            else:
                current, position = None, 0.0
            return PlayerStatus(
                state=self._state,
                current=current,
                position_seconds=round(position, 2),
                volume=self._volume,
                queue=list(self._queue),
                current_index=self._current_entry if current is not None else None,
                next_index=self._cursor,
                output_backend=self._backend,
                resume_available=self._state == PlayerState.PAUSED and resume is not None,
                total_plays=self._total_plays,
                repeat=self._repeat,
                consume=self._consume,
            )

    # -- queue ----------------------------------------------------------------
    def queue_add_next(self, track: Track) -> bool:
        """Queues a track to play right after the current one ('/queue-add'). Duplicates are allowed."""
        return self._queue_insert(track, at_cursor=True)

    def queue_add_last(self, track: Track) -> bool:
        """Appends a track to the end of the queue ('/queue-add-last'). Duplicates are allowed."""
        return self._queue_insert(track, at_cursor=False)

    def _queue_insert(self, track: Track, at_cursor: bool) -> bool:
        with self._lock:
            if not is_track_available(track):
                events = [self._event("TRACK_MISSING", track, "Arquivo indisponível: a faixa não foi adicionada à fila.")]
                added = False
            else:
                index = self._cursor if at_cursor else len(self._queue)
                self._queue.insert(index, track)
                if self._current_entry is not None and self._current_entry >= index:
                    self._current_entry += 1
                copies = sum(1 for t in self._queue if t.id == track.id)
                note = f" (esta faixa aparece {copies}x na fila)" if copies > 1 else ""
                events = [self._event("QUEUE_CHANGED", track, f"Adicionada à fila na posição {index + 1}.{note}")]
                events.extend(self._persist_queue())
                events.extend(self._persist_session())
                added = True
        self._emit(events)
        return added

    def _remove_indices(self, indices: List[int]) -> List[PlayerEvent]:
        """Removes entries and shifts the cursor/current entry so playback order is unaffected."""
        doomed = set(indices)
        for index in sorted(doomed, reverse=True):
            if index < self._cursor:
                self._cursor -= 1
            if self._current_entry is not None:
                if index == self._current_entry:
                    self._current_entry = None  # the track keeps playing, now outside the queue
                elif index < self._current_entry:
                    self._current_entry -= 1
        self._queue = [t for i, t in enumerate(self._queue) if i not in doomed]
        self._cursor = min(self._cursor, len(self._queue))
        return self._persist_queue() + self._persist_session()

    def queue_remove(self, track_id: str) -> int:
        """Removes every queued occurrence of a track; returns how many entries were removed."""
        with self._lock:
            indices = [i for i, t in enumerate(self._queue) if t.id == track_id]
            events = self._remove_indices(indices) if indices else []
        self._emit(events)
        return len(indices)

    def queue_remove_at(self, position: int) -> Optional[Track]:
        """Removes the entry at a 1-based queue position (a single copy of a duplicated track)."""
        with self._lock:
            if not 1 <= position <= len(self._queue):
                return None
            removed = self._queue[position - 1]
            events = self._remove_indices([position - 1])
        self._emit(events)
        return removed

    def queue_clear(self) -> int:
        with self._lock:
            removed = len(self._queue)
            events = self._remove_indices(list(range(removed))) if removed else []
            self._cursor = 0
        self._emit(events)
        return removed

    def queue_load(self, tracks: List[Track], replace: bool = True, source: str = "") -> int:
        """Fills the queue with a playlist ('/playlist-load', ADR 0018). Unavailable tracks are kept
        (flagged in /queue, skipped with a notice), as everywhere else in the queue.

        replace=True: the queue becomes exactly `tracks`, from its first entry. A playing or paused
        track keeps going outside the queue and the loaded tracks follow it; from a stopped
        player nothing starts by itself. replace=False: the tracks are appended."""
        with self._lock:
            tracks = list(tracks)
            label = f": {source}" if source else ""
            if replace:
                self._queue = tracks
                self._cursor = 0
                self._current_entry = None
                if self._state != PlayerState.STOPPED:
                    self._continue_queue = True
                message = f"Fila substituída{label} ({len(tracks)} faixa(s))."
            else:
                self._queue.extend(tracks)
                message = f"{len(tracks)} faixa(s) adicionada(s) ao final da fila{label} ({len(self._queue)} no total)."
            events = [self._event("QUEUE_LOADED", message=message)]
            events.extend(self._persist_queue())
            events.extend(self._persist_session())
        self._emit(events)
        return len(tracks)

    # -- queue modes (ADR 0017) -------------------------------------------------
    def set_repeat(self, enabled: bool) -> None:
        """Repeat mode ('/queue-repeat'): after the last entry the queue starts over instead of stopping.
        Turning it on turns consume mode off (a queue that empties as it plays has nothing to repeat)."""
        with self._lock:
            self._repeat = bool(enabled)
            if self._repeat:
                message = "Repetir fila: ligado. Ao terminar a última faixa, a fila recomeça da primeira."
                if self._consume:
                    self._consume = False
                    message += " Remover faixas tocadas foi desligado: as faixas tocadas agora permanecem na fila."
            else:
                message = "Repetir fila: desligado. A reprodução para ao fim da fila."
            events = [self._event("REPEAT_CHANGED", message=message)]
            events.extend(self._persist_session())
        self._emit(events)

    def set_consume(self, enabled: bool) -> None:
        """Consume mode ('/queue-consume'): an entry that counted as played (the play-count rule)
        leaves the queue when playback moves on from it (it ends, /next, /play <id>). Entries
        skipped early, stopped, paused or unavailable stay. Turning it on turns repeat off.
        Entries already in the queue are not touched when the mode changes."""
        with self._lock:
            self._consume = bool(enabled)
            if self._consume:
                heard = f"{self._count_seconds:g} s"
                message = (
                    "Remover faixas tocadas: ligado. Cada faixa sai da fila quando é considerada tocada "
                    f"({heard} ouvidos, ou a faixa inteira se for mais curta) e a reprodução segue adiante."
                )
                if self._repeat:
                    self._repeat = False
                    message += " Repetir fila foi desligado: não há o que repetir numa fila que se esvazia."
            else:
                message = "Remover faixas tocadas: desligado. As faixas tocadas permanecem na fila."
            events = [self._event("CONSUME_CHANGED", message=message)]
            events.extend(self._persist_session())
        self._emit(events)

    def _consume_current(self, counted: bool, background: bool) -> List[PlayerEvent]:
        """Consume mode: removes the current entry once playback moves on from it, if it counted as played."""
        index = self._current_entry
        if not self._consume or index is None or not counted:
            return []
        events = [self._event("QUEUE_ENTRY_CONSUMED", self._queue[index], "Faixa tocada removida da fila.", background)]
        events.extend(self._remove_indices([index]))  # also shifts the cursor back by one
        return events

    def _move_on(self) -> List[PlayerEvent]:
        """Leaves the playing or paused track because something else plays next (/next, /play <id>)."""
        session, resume = self._session, self._resume
        events = self._end_session()
        counted = session.counted if session is not None else bool(resume is not None and resume.counted)
        self._resume = None
        events.extend(self._consume_current(counted, background=False))
        return events

    def queue_shuffle(self) -> int:
        """Shuffles the whole queue ('/queue-shuffle'). The playing/paused entry (or, between
        tracks, the entry due next) goes to the top, so every other entry plays after it.
        Returns the queue length (fewer than 2: nothing to shuffle, the queue is unchanged)."""

        def shuffle(indices: List[int], anchor: Optional[int]) -> List[int]:
            rest = [i for i in indices if i != anchor]
            head = [anchor] if anchor is not None else []
            arranged = head + rest
            # Re-draw a few times so the command visibly changes the order whenever it can.
            for _ in range(8):
                self._rng.shuffle(rest)
                arranged = head + rest
                if [self._queue[i].id for i in arranged] != [t.id for t in self._queue]:
                    break
            return arranged

        return self._reorder(shuffle, "embaralhad")

    def queue_sort(self, order: QueueOrder) -> int:
        """Sorts the whole queue ('/queue-sort'); stable, so ties keep their relative order. The
        playing/paused entry keeps playing at its new position and playback continues from there.
        Returns the queue length (fewer than 2: nothing to sort, the queue is unchanged)."""
        order = QueueOrder(order)
        return self._reorder(
            lambda indices, _anchor: sorted(indices, key=lambda i: queue_sort_key(self._queue[i], order)),
            "ordenad", f" por {order.label}",
        )

    def _anchor(self) -> Tuple[Optional[int], bool]:
        """The entry playback continues from: (index, is_current). The current entry when a queue
        entry is playing/paused; otherwise, mid-pass, the entry due next; otherwise none."""
        if self._current_entry is not None:
            return self._current_entry, True
        if 0 < self._cursor < len(self._queue):
            return self._cursor, False
        return None, False

    def _reorder(self, arrange: Callable[[List[int], Optional[int]], List[int]], participle: str, detail: str = "") -> int:
        """Reorders every entry (by index, so duplicated tracks stay distinct entries) and moves the
        current entry/cursor along with the anchor entry, so playback continues from it."""
        with self._lock:
            size = len(self._queue)
            if size < 2:
                return size
            anchor, is_current = self._anchor()
            arranged = arrange(list(range(size)), anchor)
            changed = [self._queue[i].id for i in arranged] != [t.id for t in self._queue]
            self._queue = [self._queue[i] for i in arranged]
            message = f"Fila {participle}a{detail} ({size} faixas)."
            if anchor is not None:
                position = arranged.index(anchor)
                if is_current:
                    self._current_entry, self._cursor = position, position + 1
                    where = "a faixa atual"
                else:
                    self._cursor = position
                    where = "a próxima faixa"
                message += f" A reprodução continua a partir da posição {position + 1} ({where})."
            if not changed:
                message += " A ordem já era essa."
            events = [self._event("QUEUE_REORDERED", message=message)]
            if changed:
                events.extend(self._persist_queue())
                events.extend(self._persist_session())
        self._emit(events)
        return size

    # -- transport ------------------------------------------------------------
    def play(self) -> bool:
        """'/play' without arguments: continue a paused track, otherwise play the queue from its cursor."""
        if self._state == PlayerState.PAUSED:
            return self.resume()
        if self._state == PlayerState.PLAYING:
            return False
        return self.play_queue()

    def play_queue(self) -> bool:
        """Plays the queue: continues a paused queue entry, otherwise starts at the cursor."""
        with self._lock:
            if self._state == PlayerState.PAUSED and self._current_entry is not None:
                ok, events = self._resume_locked()
            elif self._state == PlayerState.PLAYING and self._current_entry is not None:
                return True  # the queue is already playing
            elif not self._queue:
                return False
            else:
                events = self._end_session()
                self._resume = None
                self._current_entry = None
                if self._cursor >= len(self._queue):
                    self._cursor = 0
                ok, more = self._advance(background=False)
                events.extend(more)
            events.extend(self._persist_session())
        self._emit(events)
        return ok

    def play_track(self, track: Track) -> bool:
        """Plays a track now, from its beginning. If the queue was in progress it continues with the
        next entry afterwards; from an idle player only this track plays. Missing files are
        reported and the current track (if any) keeps playing."""
        with self._lock:
            if not is_track_available(track):
                events = [self._event("TRACK_MISSING", track, "Arquivo indisponível no disco.")]
                ok = False
            else:
                queue_in_progress = self._current_entry is not None or (
                    self._state != PlayerState.STOPPED and self._continue_queue
                )
                events = self._move_on()
                self._current_entry = None
                self._continue_queue = queue_in_progress
                ok, started = self._start(track, background=False)
                events.extend(started)
                if not ok:
                    self._state = PlayerState.STOPPED
                events.extend(self._persist_session())
        self._emit(events)
        return ok

    def next(self) -> bool:
        """Skips to the next queue entry; at the end of the queue playback stops and resets."""
        with self._lock:
            events = self._move_on()
            self._current_entry = None
            ok, more = self._advance(background=False)
            events.extend(more)
            events.extend(self._persist_session())
        self._emit(events)
        return ok

    def pause(self) -> bool:
        """Pauses: releases the device but keeps the track and position (also across restarts)."""
        with self._lock:
            if self._state != PlayerState.PLAYING or self._session is None:
                return False
            events = self._end_session(keep_resume_point=True)
            self._state = PlayerState.PAUSED
            position = self._resume.position_seconds
            events.append(self._event("PAUSED", self._resume.track, f"em {_clock(position)}"))
            events.extend(self._persist_session())
        self._emit(events)
        return True

    def resume(self) -> bool:
        """Continues the paused track from where it was paused."""
        with self._lock:
            if self._state != PlayerState.PAUSED or self._resume is None:
                return False
            ok, events = self._resume_locked()
            events.extend(self._persist_session())
        self._emit(events)
        return ok

    def toggle_pause(self) -> bool:
        """Pauses when playing, resumes when paused. Returns False when nothing is loaded."""
        if self._state == PlayerState.PLAYING:
            return self.pause()
        if self._state == PlayerState.PAUSED:
            return self.resume()
        return False

    def stop(self) -> bool:
        """Stops playback and resets to the start of the queue (the queue itself is kept)."""
        with self._lock:
            track = self._session.track if self._session else (self._resume.track if self._resume else None)
            events = self._end_session()
            self._resume = None
            self._current_entry = None
            self._continue_queue = False
            self._cursor = 0
            self._state = PlayerState.STOPPED
            if track is not None:
                events.append(self._event("STOPPED", track, "A fila recomeçará da primeira faixa."))
            events.extend(self._persist_session())
        self._emit(events)
        return track is not None

    def set_volume(self, volume: int) -> None:
        gain = volume_to_gain(volume)  # validates 0..100
        with self._lock:
            self._volume = volume
            self._gain = gain
            events = [self._event("VOLUME_CHANGED", message=f"Volume: {volume}%")]
            events.extend(self._persist_session())
        self._emit(events)

    def shutdown(self) -> None:
        """Application exit: a playing track is paused in place (resumable after restart)."""
        self._ticker_stop.set()
        with self._lock:
            if self._session is not None:
                self._end_session(keep_resume_point=True)
                self._state = PlayerState.PAUSED
            self._persist_queue()
            self._persist_session()
            self._listeners.clear()
        if self._ticker is not None and self._ticker is not threading.current_thread():
            self._ticker.join(timeout=2.0)

    # -- internals (call with the lock held) ----------------------------------
    def _current_gain(self) -> float:
        return self._gain

    def _end_session(self, keep_resume_point: bool = False) -> List[PlayerEvent]:
        """Closes the current session after a last play-count check; optionally keeps a resume point."""
        session, self._session = self._session, None
        if session is None:
            return []
        session.fade_out()
        events = self._maybe_count(session)
        if keep_resume_point:
            self._resume = _ResumePoint(session.track, session.position_seconds, session.listened_seconds, session.counted)
        session.close()
        return events

    def _start(
        self,
        track: Track,
        background: bool,
        start_seconds: float = 0.0,
        base_listened: float = 0.0,
        counted: bool = False,
        kind: PlayerEventKind = "TRACK_STARTED",
    ) -> Tuple[bool, List[PlayerEvent]]:
        """Starts one track. Returns (ok, events); on DEVICE_ERROR the state is left STOPPED."""
        if not is_track_available(track):
            return False, [self._event("TRACK_MISSING", track, "Arquivo indisponível no disco: faixa pulada.", background)]
        cancel = threading.Event()
        try:
            stream = self._decoder.open(track.file_path, cancel, start_seconds=start_seconds)
        except (DecoderUnavailableError, AudioDecodeError) as exc:
            return False, [self._event("TRACK_ERROR", track, str(exc), background)]
        except Exception as exc:  # a decoder bug must skip the track, not crash the REPL/advance thread
            return False, [self._event("TRACK_ERROR", track, f"{type(exc).__name__}: {exc}", background)]

        session = _Session(
            track, stream, cancel, self._current_gain, self._on_session_end,
            start_offset=start_seconds, base_listened=base_listened, counted=counted,
            threshold=play_count_threshold(track.duration_seconds, self._count_seconds),
        )
        session.start()
        session.wait_prebuffer()
        if session.failed_before_audio:
            message = session.error
            session.close()
            return False, [self._event("TRACK_ERROR", track, message, background)]
        try:
            output = self._output or MiniaudioOutput()
            self._output = output
            handle = output.open(session.sample_rate, session.channels, session.pull)
            session.handle = handle
            handle.start()
        except PlaybackUnavailableError as exc:
            session.close()
            self._state = PlayerState.STOPPED
            return False, [self._event("DEVICE_ERROR", track, str(exc), background)]
        except Exception as exc:
            session.close()
            self._state = PlayerState.STOPPED
            return False, [self._event("DEVICE_ERROR", track, f"{type(exc).__name__}: {exc}", background)]
        self._backend = getattr(handle, "backend", None)
        self._session = session
        self._last_track = track
        self._state = PlayerState.PLAYING
        self._ensure_ticker()
        message = f"em {_clock(start_seconds)}" if start_seconds > 0 else None
        return True, [self._event(kind, track, message, background=background)]

    def _resume_locked(self) -> Tuple[bool, List[PlayerEvent]]:
        """Continues the resume point; a missing/broken file falls back to the queue."""
        point = self._resume
        ok, events = self._start(
            point.track, background=False, start_seconds=point.position_seconds,
            base_listened=point.listened_seconds, counted=point.counted, kind="RESUMED",
        )
        if ok:
            self._resume = None
            return True, events
        if events and events[-1].kind == "DEVICE_ERROR":
            self._state = PlayerState.PAUSED  # not the track's fault: stay paused, retry later
            return False, events
        self._resume = None
        was_entry = self._current_entry is not None
        self._current_entry = None
        if was_entry or self._continue_queue:
            ok, more = self._advance(background=False)
            return ok, events + more
        self._state = PlayerState.STOPPED
        return False, events

    def _advance(self, background: bool) -> Tuple[bool, List[PlayerEvent]]:
        """Plays the entry at the cursor; unavailable/broken entries are reported and skipped
        (they stay in the queue). After the last entry the cursor returns to the start and the
        player stops, or, in repeat mode, the queue starts over. Each entry is tried at most
        once per call, so a repeating queue with no playable entry still stops."""
        events: List[PlayerEvent] = []
        attempts = 0
        while attempts < len(self._queue):
            if self._cursor >= len(self._queue):
                if not self._repeat:
                    break
                self._cursor = 0
                events.append(self._event(
                    "QUEUE_REPEATED", message="Repetir fila: recomeçando da primeira faixa.", background=background
                ))
            index = self._cursor
            attempts += 1
            ok, started = self._start(self._queue[index], background)
            events.extend(started)
            if ok:
                self._current_entry = index
                self._cursor = index + 1
                self._continue_queue = True
                return True, events
            if started and started[-1].kind == "DEVICE_ERROR":
                return False, events  # not the entry's fault: the cursor stays on it
            self._cursor = index + 1
        exhausted = self._repeat and attempts > 0  # every entry was tried and none could play
        self._cursor = 0
        self._current_entry = None
        self._continue_queue = False
        self._state = PlayerState.STOPPED
        message = (
            "Nenhuma faixa da fila pôde ser reproduzida: a repetição foi interrompida."
            if exhausted else "Fim da fila: o próximo /play recomeça da primeira faixa."
        )
        events.append(self._event("QUEUE_ENDED", message=message, background=background))
        return False, events

    def _on_session_end(self, session: _Session) -> None:
        """Runs on a helper thread when a track drained (end of file or decode error)."""
        with self._lock:
            if session is not self._session:
                return  # stale: the user already stopped/skipped/paused this track
            self._session = None
            events = [] if session.error else self._maybe_count(session, completed=True)
            session.close()
            if session.error:
                events.append(self._event("TRACK_ERROR", session.track, session.error, background=True))
            else:
                events.append(self._event("TRACK_FINISHED", session.track, background=True))
            was_entry = self._current_entry is not None
            events.extend(self._consume_current(session.counted, background=True))
            self._current_entry = None
            if was_entry or self._continue_queue:
                _, more = self._advance(background=True)
                events.extend(more)
            else:
                self._state = PlayerState.STOPPED  # a single track played by ID from an idle player
            events.extend(self._persist_session())
        self._emit(events)


def _report_player_issue(event: PlayerEvent) -> None:
    """Player events about a resource or the environment become Issues (ADR 0019). Called outside
    the player lock, on whichever thread raised the event; report_issue() only enqueues."""
    track = event.track
    label = f"{track.artist} - {track.title}" if track is not None else None
    if event.kind == "TRACK_MISSING" and track is not None:
        report_issue(IssueKind.TRACK_FILE_MISSING, track.id, event.message or "Arquivo indisponível.",
                     subject_type="track", subject_label=label, source="player",
                     details={"arquivo": track.file_path,
                              "sugestão": "Reconecte o disco ou rode /scan na pasta para reconciliar o catálogo."})
    elif event.kind == "TRACK_ERROR" and track is not None:
        report_issue(IssueKind.AUDIO_UNDECODABLE, track.id, event.message or "Falha ao decodificar.",
                     subject_type="track", subject_label=label, source="player",
                     details={"arquivo": track.file_path})
    elif event.kind == "DEVICE_ERROR":
        report_issue(IssueKind.AUDIO_DEVICE_UNAVAILABLE, "audio-output", event.message or "Sem saída de áudio.",
                     subject_type="device", subject_label="Saída de áudio", source="player")
    elif event.kind == "PERSISTENCE_ERROR":
        report_issue(IssueKind.PLAYBACK_STATE_NOT_SAVED, "playback-state", event.message or "Falha ao salvar.",
                     subject_type="database", subject_label="Fila, posição e contadores", source="player")


def _clock(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"


# ----------------------------------------------------------------------
# Process-wide instance (created lazily: no audio device is touched until first use)
# ----------------------------------------------------------------------

_player: Optional[PlayerService] = None
_player_lock = threading.Lock()


_store = None


def get_player_service(db_path: Optional[str] = None) -> PlayerService:
    """The process-wide player, restored from the playback store of the catalog database."""
    global _player, _store
    with _player_lock:
        if _player is None:
            from musicmatch.storage.playback_store import SQLitePlaybackStore

            path = db_path or settings.DATABASE_PATH
            try:
                _store = SQLitePlaybackStore(path) if path != ":memory:" else None
            except Exception:
                _store = None  # playback still works, without persistence
            _player = PlayerService(store=_store)
        return _player


def shutdown_player_service() -> None:
    global _player, _store
    with _player_lock:
        player, _player = _player, None
        store, _store = _store, None
    if player is not None:
        player.shutdown()
    if store is not None:
        store.close()


atexit.register(shutdown_player_service)
