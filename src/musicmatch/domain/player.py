"""Playback Domain Models (ADR 0015, ADR 0016).

The player reports everything through these Pydantic models: the console renders them
today and a GUI can consume the same objects (or their JSON) later.
"""

import os
from enum import Enum
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from musicmatch.domain.models import Track
from musicmatch.domain.text import fold_text

# Volume 0..100 -> linear amplitude with a cubic taper (the mapping PulseAudio uses for its
# software volume): equal steps sound like equal loudness changes, 50 -> -18 dB, 0 -> mute.
DEFAULT_VOLUME = 80


def volume_to_gain(volume: int) -> float:
    if not 0 <= volume <= 100:
        raise ValueError("volume must be between 0 and 100")
    return (volume / 100.0) ** 3


# Play counting (ADR 0016): a play counts after 60 s of actual listening. Nobody keeps listening
# for a minute to a track they are not interested in. Tracks shorter than that count when
# heard to the end.
DEFAULT_PLAY_COUNT_SECONDS = 60.0


def play_count_threshold(duration_seconds: Optional[float], seconds: float = DEFAULT_PLAY_COUNT_SECONDS) -> float:
    """Seconds of actual listening after which a play is counted."""
    if seconds <= 0:
        raise ValueError("the play-count threshold must be positive")
    if duration_seconds and duration_seconds > 0:
        return min(seconds, duration_seconds)
    return seconds


class PlayerState(str, Enum):
    STOPPED = "STOPPED"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"


PlayerEventKind = Literal[
    "TRACK_STARTED",  # a track began playing
    "TRACK_FINISHED",  # a track played to its end
    "TRACK_MISSING",  # a requested/queued track's file is unavailable (skipped)
    "TRACK_ERROR",  # a track could not be decoded/played (skipped)
    "DEVICE_ERROR",  # no usable audio output device; playback stopped
    "PAUSED",
    "RESUMED",
    "STOPPED",
    "QUEUE_ENDED",  # the queue ran out after the last track
    "VOLUME_CHANGED",
    "QUEUE_CHANGED",
    "QUEUE_REORDERED",  # /queue-shuffle or /queue-sort reordered the queue
    "QUEUE_REPEATED",  # repeat mode: the queue ran out and playback wrapped to the first entry
    "REPEAT_CHANGED",  # /queue-repeat turned repeat mode on or off
    "CONSUME_CHANGED",  # /queue-consume turned consume mode on or off
    "QUEUE_ENTRY_CONSUMED",  # consume mode: a played entry left the queue as playback moved on
    "QUEUE_LOADED",  # /playlist-load replaced the queue with a playlist, or appended one to it
    "PLAY_COUNTED",  # listening passed the play-count threshold: track and total counters increased
    "PERSISTENCE_ERROR",  # the queue/session/counters could not be saved (playback continues)
]


# ----------------------------------------------------------------------
# Queue ordering (/queue-sort)
# ----------------------------------------------------------------------


class QueueOrder(str, Enum):
    """Sort keys accepted by /queue-sort; ties keep their current relative order (stable sort)."""

    TITLE = "title"  # track name
    GENRE = "genre"  # genre, then track name
    ARTIST = "artist"  # artist, then track name
    ALBUM = "album"  # album name, then track number

    @property
    def label(self) -> str:
        return _ORDER_LABELS[self]


_ORDER_LABELS = {
    QueueOrder.TITLE: "nome da faixa",
    QueueOrder.GENRE: "gênero e nome da faixa",
    QueueOrder.ARTIST: "artista e nome da faixa",
    QueueOrder.ALBUM: "álbum e número da faixa",
}

_ORDER_ALIASES = {
    "title": QueueOrder.TITLE, "track": QueueOrder.TITLE, "name": QueueOrder.TITLE,
    "titulo": QueueOrder.TITLE, "faixa": QueueOrder.TITLE, "nome": QueueOrder.TITLE,
    "genre": QueueOrder.GENRE, "genero": QueueOrder.GENRE,
    "artist": QueueOrder.ARTIST, "artista": QueueOrder.ARTIST,
    "album": QueueOrder.ALBUM,
}

# Placeholders written by the scanner when a tag is missing: they sort after every real value.
_MISSING_TAGS = {"", "unknown artist", "unknown album", "unknown genre"}


_fold = fold_text  # case- and accent-insensitive collation ('Érase' sorts with 'erase', not after 'z')


def parse_queue_order(token: str) -> Optional[QueueOrder]:
    """'title' | 'genre' | 'artist' | 'album' (Portuguese names and accents accepted)."""
    return _ORDER_ALIASES.get(_fold(token))


def _text_key(text: Optional[str]) -> Tuple[int, str]:
    folded = _fold(text)
    return (1, "") if folded in _MISSING_TAGS else (0, folded)


def queue_sort_key(track: Track, order: QueueOrder) -> tuple:
    """Sort key of a queue entry for the given order.

    Album order groups same-named albums by folder before the track number, so two different
    'Greatest Hits' do not interleave (a compilation shares one folder across artists).
    Entries without a track number go after the numbered ones of their album.
    """
    title = _text_key(track.title)
    if order == QueueOrder.TITLE:
        return (title,)
    if order == QueueOrder.GENRE:
        return (_text_key(track.genre), title)
    if order == QueueOrder.ARTIST:
        return (_text_key(track.artist), title)
    folder = _fold(os.path.dirname(track.file_path.replace("\\", "/")))
    number = track.track_number
    return (_text_key(track.album), folder, (0, number) if number is not None else (1, 0), title)


class PlayerEvent(BaseModel):
    """Something the user should know about; emitted synchronously or from the playback thread."""

    kind: PlayerEventKind
    state: PlayerState
    track: Optional[Track] = None
    message: Optional[str] = None
    background: bool = Field(
        default=False, description="True when raised by the playback thread (e.g. auto-advance), not by a command"
    )


class PlayerStatus(BaseModel):
    """Snapshot of the player for status views (/queue, a GUI transport bar)."""

    state: PlayerState
    current: Optional[Track] = None
    position_seconds: float = Field(default=0.0, ge=0)
    volume: int = Field(ge=0, le=100)
    queue: List[Track] = Field(default_factory=list, description="Every queue entry; played ones stay until removed")
    current_index: Optional[int] = Field(
        default=None, ge=0, description="0-based queue entry being played/paused (None: out-of-queue track or idle)"
    )
    next_index: int = Field(default=0, ge=0, description="0-based queue entry that plays next (queue cursor)")
    resume_available: bool = Field(
        default=False, description="PAUSED: /play or /pause continues the current track at position_seconds"
    )
    total_plays: int = Field(default=0, ge=0, description="Library-wide counted plays")
    repeat: bool = Field(default=False, description="Repeat mode: after the last entry the queue starts over")
    consume: bool = Field(default=False, description="Consume mode: played entries leave the queue")
    output_backend: Optional[str] = Field(default=None, description="Audio API in use, e.g. 'WASAPI', 'Core Audio', 'PulseAudio'")
