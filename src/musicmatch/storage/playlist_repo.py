"""Playlist persistence (ADR 0018).

Playlists live in the catalog database and are only touched from the REPL thread, so the
repository works on the catalog repository's own connection (no second connection, and
in-memory test databases see the same data).
"""

import sqlite3
from typing import Iterable, List, Optional

from musicmatch.domain.playlist import Playlist, PlaylistSummary, playlist_name_key
from musicmatch.storage.sqlite_repo import row_to_track

_SUMMARY_SQL = """
SELECT p.id, p.name, p.created_at, p.updated_at,
       COUNT(t.id) AS track_count, COALESCE(SUM(t.duration_seconds), 0) AS duration_seconds
FROM playlists p
LEFT JOIN playlist_entries e ON e.playlist_id = p.id
LEFT JOIN tracks t ON t.id = e.track_id
{where}
GROUP BY p.id
ORDER BY p.name_key;
"""


class PlaylistNameTaken(ValueError):
    """Another playlist already uses this name (case- and accent-insensitive)."""


def _summary(row: sqlite3.Row) -> PlaylistSummary:
    return PlaylistSummary(
        id=row["id"], name=row["name"], track_count=row["track_count"],
        duration_seconds=float(row["duration_seconds"] or 0.0),
        created_at=row["created_at"] or "", updated_at=row["updated_at"] or "",
    )


class SQLitePlaylistRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # -- queries -------------------------------------------------------------
    def list_summaries(self) -> List[PlaylistSummary]:
        rows = self.conn.execute(_SUMMARY_SQL.format(where="")).fetchall()
        return [_summary(row) for row in rows]

    def get_summary(self, playlist_id: int) -> Optional[PlaylistSummary]:
        row = self.conn.execute(_SUMMARY_SQL.format(where="WHERE p.id = ?"), (playlist_id,)).fetchone()
        return _summary(row) if row else None

    def get(self, playlist_id: int) -> Optional[Playlist]:
        summary = self.get_summary(playlist_id)
        if summary is None:
            return None
        rows = self.conn.execute(
            """
            SELECT t.* FROM playlist_entries e JOIN tracks t ON t.id = e.track_id
            WHERE e.playlist_id = ? ORDER BY e.position;
            """,
            (playlist_id,),
        ).fetchall()
        return Playlist(**summary.model_dump(), tracks=[row_to_track(row) for row in rows])

    def find_by_name(self, name: str) -> Optional[PlaylistSummary]:
        row = self.conn.execute("SELECT id FROM playlists WHERE name_key = ?;", (playlist_name_key(name),)).fetchone()
        return self.get_summary(row["id"]) if row else None

    def find_by_name_prefix(self, prefix: str, limit: int = 10) -> List[PlaylistSummary]:
        key = playlist_name_key(prefix)
        if not key:
            return []
        upper = key[:-1] + chr(ord(key[-1]) + 1)
        rows = self.conn.execute(
            "SELECT id FROM playlists WHERE name_key >= ? AND name_key < ? ORDER BY name_key LIMIT ?;",
            (key, upper, int(limit)),
        ).fetchall()
        return [s for s in (self.get_summary(row["id"]) for row in rows) if s is not None]

    def playlists_containing(self, track_ids: Iterable[str], exclude_id: Optional[int] = None) -> List[str]:
        """Names of the playlists holding any of the tracks (warning before deleting tracks)."""
        ids = list(dict.fromkeys(track_ids))
        names: List[str] = []
        for start in range(0, len(ids), 500):  # stay below SQLite's bound-parameter limit
            chunk = ids[start:start + 500]
            marks = ",".join("?" * len(chunk))
            rows = self.conn.execute(
                f"""
                SELECT DISTINCT p.name, p.name_key FROM playlists p JOIN playlist_entries e ON e.playlist_id = p.id
                WHERE e.track_id IN ({marks}) AND p.id IS NOT ?;
                """,
                (*chunk, exclude_id),
            ).fetchall()
            names.extend(row["name"] for row in rows)
        return sorted(set(names), key=playlist_name_key)

    # -- changes -------------------------------------------------------------
    def create(self, name: str, track_ids: List[str]) -> PlaylistSummary:
        try:
            with self.conn:
                cursor = self.conn.execute(
                    "INSERT INTO playlists (name, name_key) VALUES (?, ?);", (name, playlist_name_key(name))
                )
                self._insert_entries(cursor.lastrowid, track_ids)
        except sqlite3.IntegrityError as exc:
            raise PlaylistNameTaken(name) from exc
        return self.get_summary(cursor.lastrowid)

    def replace_entries(self, playlist_id: int, track_ids: List[str]) -> PlaylistSummary:
        with self.conn:
            self.conn.execute("DELETE FROM playlist_entries WHERE playlist_id = ?;", (playlist_id,))
            self._insert_entries(playlist_id, track_ids)
            self.conn.execute("UPDATE playlists SET updated_at = datetime('now') WHERE id = ?;", (playlist_id,))
        return self.get_summary(playlist_id)

    def rename(self, playlist_id: int, new_name: str) -> PlaylistSummary:
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE playlists SET name = ?, name_key = ?, updated_at = datetime('now') WHERE id = ?;",
                    (new_name, playlist_name_key(new_name), playlist_id),
                )
        except sqlite3.IntegrityError as exc:
            raise PlaylistNameTaken(new_name) from exc
        return self.get_summary(playlist_id)

    def remove_track(self, playlist_id: int, track_id: str) -> int:
        """Removes every entry of the track; returns how many entries were removed."""
        with self.conn:
            removed = self.conn.execute(
                "DELETE FROM playlist_entries WHERE playlist_id = ? AND track_id = ?;", (playlist_id, track_id)
            ).rowcount
            if removed:
                self._touch(playlist_id)
        return removed

    def remove_at(self, playlist_id: int, index: int) -> bool:
        """Removes the entry at a 0-based index of the playlist order (stored positions may have
        gaps after tracks left the library, so the index is resolved against the current order)."""
        if index < 0:
            return False
        with self.conn:
            row = self.conn.execute(
                "SELECT position FROM playlist_entries WHERE playlist_id = ? ORDER BY position LIMIT 1 OFFSET ?;",
                (playlist_id, index),
            ).fetchone()
            if row is None:
                return False
            self.conn.execute(
                "DELETE FROM playlist_entries WHERE playlist_id = ? AND position = ?;", (playlist_id, row["position"])
            )
            self._touch(playlist_id)
        return True

    def _touch(self, playlist_id: int) -> None:
        self.conn.execute("UPDATE playlists SET updated_at = datetime('now') WHERE id = ?;", (playlist_id,))

    def delete(self, playlist_id: int) -> bool:
        with self.conn:
            return self.conn.execute("DELETE FROM playlists WHERE id = ?;", (playlist_id,)).rowcount > 0

    def _insert_entries(self, playlist_id: int, track_ids: List[str]) -> None:
        """Entries keep their order; IDs no longer in the catalog are skipped (the SELECT finds no row)."""
        self.conn.executemany(
            "INSERT INTO playlist_entries (playlist_id, position, track_id) SELECT ?, ?, id FROM tracks WHERE id = ?;",
            [(playlist_id, position, track_id) for position, track_id in enumerate(track_ids)],
        )
