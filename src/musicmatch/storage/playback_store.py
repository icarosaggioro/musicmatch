"""Persistent playback state: play queue, resume point, queue modes, play counters and history (ADR 0016, 0017).

Why a separate store (and connection)?
The player writes from background threads: auto-advance when a track ends, and a periodic
ticker that saves the position and counts plays. The catalog repository's connection
belongs to the main (REPL) thread, so this store opens its own connection to the same
database file, with `check_same_thread=False` and a lock that serializes its operations.
SQLite (WAL mode) arbitrates between the two connections.
"""

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

from musicmatch.domain.models import Track
from musicmatch.storage.schema import apply_schema
from musicmatch.storage.sqlite_repo import row_to_track

TOTAL_PLAYS_KEY = "total_plays"


@dataclass(frozen=True)
class SavedSession:
    """The last played track and its position, the player state, the queue cursor and queue modes."""

    track: Optional[Track]
    position_seconds: float
    listened_seconds: float
    play_counted: bool
    volume: Optional[int]
    state: str = "STOPPED"  # 'PAUSED' = resume point; 'STOPPED' = restart from the queue start
    queue_cursor: int = 0
    current_entry: Optional[int] = None
    repeat: bool = False
    consume: bool = False


@dataclass(frozen=True)
class PlayRecord:
    track_play_count: int
    total_plays: int


class SQLitePlaybackStore:
    def __init__(self, db_path: Union[str, Path]) -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        if self.db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL;")
        apply_schema(self._conn)

    # -- queue --------------------------------------------------------------
    def load_queue(self) -> List[Track]:
        """Queued tracks in order (duplicates preserved); entries of unindexed tracks are gone."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT t.* FROM play_queue q JOIN tracks t ON t.id = q.track_id ORDER BY q.position;"
            ).fetchall()
        return [row_to_track(row) for row in rows]

    def save_queue(self, track_ids: List[str]) -> None:
        """Replaces the persisted queue (a queue is short: a full rewrite keeps order trivially right)."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM play_queue;")
            self._conn.executemany(
                "INSERT INTO play_queue (position, track_id) SELECT ?, id FROM tracks WHERE id = ?;",
                list(enumerate(track_ids)),
            )

    # -- resume point -------------------------------------------------------
    def load_session(self) -> SavedSession:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT s.position_seconds, s.listened_seconds, s.play_counted, s.volume,
                       s.state AS session_state, s.queue_cursor, s.current_entry, s.repeat_mode,
                       s.consume_mode, t.*
                FROM player_session s LEFT JOIN tracks t ON t.id = s.current_track_id
                WHERE s.id = 1;
                """
            ).fetchone()
        if row is None:
            return SavedSession(track=None, position_seconds=0.0, listened_seconds=0.0, play_counted=False, volume=None)
        track = row_to_track(row) if row["id"] is not None else None
        return SavedSession(
            track=track,
            position_seconds=float(row["position_seconds"] or 0.0) if track else 0.0,
            listened_seconds=float(row["listened_seconds"] or 0.0) if track else 0.0,
            play_counted=bool(row["play_counted"]) if track else False,
            volume=row["volume"],
            state=row["session_state"] if track and row["session_state"] in ("PAUSED", "STOPPED") else "STOPPED",
            queue_cursor=max(0, int(row["queue_cursor"] or 0)),
            current_entry=row["current_entry"] if track else None,
            repeat=bool(row["repeat_mode"]),
            consume=bool(row["consume_mode"]),
        )

    def save_session(
        self,
        track_id: Optional[str],
        position_seconds: float,
        listened_seconds: float,
        play_counted: bool,
        volume: int,
        state: str = "STOPPED",
        queue_cursor: int = 0,
        current_entry: Optional[int] = None,
        repeat: bool = False,
        consume: bool = False,
    ) -> None:
        with self._lock, self._conn:
            exists = track_id is not None and self._conn.execute(
                "SELECT 1 FROM tracks WHERE id = ?;", (track_id,)
            ).fetchone()
            self._conn.execute(
                """
                INSERT INTO player_session (id, current_track_id, position_seconds, listened_seconds,
                                            play_counted, volume, state, queue_cursor, current_entry,
                                            repeat_mode, consume_mode, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    current_track_id = excluded.current_track_id,
                    position_seconds = excluded.position_seconds,
                    listened_seconds = excluded.listened_seconds,
                    play_counted = excluded.play_counted,
                    volume = excluded.volume,
                    state = excluded.state,
                    queue_cursor = excluded.queue_cursor,
                    current_entry = excluded.current_entry,
                    repeat_mode = excluded.repeat_mode,
                    consume_mode = excluded.consume_mode,
                    updated_at = excluded.updated_at;
                """,
                (
                    track_id if exists else None,
                    round(float(position_seconds), 3) if exists else 0.0,
                    round(float(listened_seconds), 3) if exists else 0.0,
                    int(bool(play_counted)) if exists else 0,
                    int(volume),
                    state if exists and state in ("PAUSED", "STOPPED") else "STOPPED",
                    max(0, int(queue_cursor)),
                    current_entry if exists else None,
                    int(bool(repeat)),
                    int(bool(consume)),
                ),
            )

    # -- counters -----------------------------------------------------------
    def record_play(self, track_id: str, listened_seconds: float) -> PlayRecord:
        """Atomically counts one play: track counter, total counter and a history entry."""
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE tracks SET play_count = play_count + 1, last_played_at = datetime('now') WHERE id = ?;",
                (track_id,),
            )
            self._conn.execute(
                """
                INSERT INTO playback_stats (key, value) VALUES (?, 1)
                ON CONFLICT(key) DO UPDATE SET value = value + 1;
                """,
                (TOTAL_PLAYS_KEY,),
            )
            # A track unindexed while playing still counts in the total; its history row is anonymous.
            self._conn.execute(
                """
                INSERT INTO play_history (track_id, listened_seconds)
                VALUES ((SELECT id FROM tracks WHERE id = ?), ?);
                """,
                (track_id, round(float(listened_seconds), 3)),
            )
            track_row = self._conn.execute("SELECT play_count FROM tracks WHERE id = ?;", (track_id,)).fetchone()
            total_row = self._conn.execute(
                "SELECT value FROM playback_stats WHERE key = ?;", (TOTAL_PLAYS_KEY,)
            ).fetchone()
        return PlayRecord(
            track_play_count=int(track_row["play_count"]) if track_row else 0,
            total_plays=int(total_row["value"]) if total_row else 0,
        )

    def total_plays(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT value FROM playback_stats WHERE key = ?;", (TOTAL_PLAYS_KEY,)).fetchone()
        return int(row["value"]) if row else 0

    def recent_history(self, limit: int = 20) -> List[Tuple[Optional[str], str, float]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT track_id, played_at, listened_seconds FROM play_history ORDER BY id DESC LIMIT ?;",
                (int(limit),),
            ).fetchall()
        return [(row["track_id"], row["played_at"], row["listened_seconds"]) for row in rows]

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
