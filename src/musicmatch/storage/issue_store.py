"""Issue persistence (ADR 0019).

The store owns its own connection to the catalog database (check_same_thread=False,
serialized by a lock), like the playback store: it is written by the issue writer thread and
read/changed by the /issue commands on the REPL thread. SQLite (WAL) arbitrates with the
catalog repository's connection.
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from musicmatch.domain.issues import Issue, IssueKind, IssueReport
from musicmatch.storage.schema import apply_schema

MAX_DETAIL_ITEMS = 200  # lists in 'details' (e.g. unresolved playlist entries) are capped


def _details_json(details: dict) -> Optional[str]:
    if not details:
        return None
    capped = {k: (v[:MAX_DETAIL_ITEMS] if isinstance(v, list) else v) for k, v in details.items()}
    return json.dumps(capped, ensure_ascii=False, default=str)


def _row_to_issue(row: sqlite3.Row) -> Issue:
    details = {}
    if row["details"]:
        try:
            details = json.loads(row["details"])
        except ValueError:
            details = {"raw": row["details"]}
    return Issue(
        id=row["id"], kind=IssueKind(row["kind"]), category=row["category"], severity=row["severity"],
        subject_type=row["subject_type"], subject_key=row["subject_key"], subject_label=row["subject_label"],
        message=row["message"], details=details, source=row["source"], status=row["status"],
        occurrences=row["occurrences"], first_seen=row["first_seen"], last_seen=row["last_seen"],
        dismissed_at=row["dismissed_at"],
    )


class SQLiteIssueStore:
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

    # -- writes from the reporter ----------------------------------------------
    def record(self, reports: Iterable[IssueReport]) -> int:
        """Upserts a batch in one transaction; returns how many issues were newly opened.
        A recurrence refreshes the row but never changes its status: dismissed stays dismissed."""
        opened = 0
        with self._lock, self._conn:
            for report in reports:
                kind = IssueKind(report.kind)
                row = self._conn.execute(
                    "SELECT id FROM issues WHERE kind = ? AND subject_key = ?;", (kind.value, report.subject_key)
                ).fetchone()
                if row is None:
                    self._conn.execute(
                        """
                        INSERT INTO issues (kind, category, severity, subject_type, subject_key, subject_label,
                                            message, details, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (kind.value, kind.category, kind.severity, report.subject_type, report.subject_key,
                         report.subject_label, report.message, _details_json(report.details), report.source),
                    )
                    opened += 1
                else:
                    self._conn.execute(
                        """
                        UPDATE issues SET occurrences = occurrences + 1, last_seen = datetime('now'),
                               message = ?, details = ?, subject_label = COALESCE(?, subject_label),
                               source = COALESCE(?, source)
                        WHERE id = ?;
                        """,
                        (report.message, _details_json(report.details), report.subject_label, report.source, row["id"]),
                    )
        return opened

    # -- reads and user actions (REPL thread) ------------------------------------
    def list(self, status: Optional[str] = "OPEN", limit: int = 50, offset: int = 0) -> List[Issue]:
        where, params = ("WHERE status = ?", [status]) if status else ("", [])
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM issues {where} ORDER BY last_seen DESC, id DESC LIMIT ? OFFSET ?;",
                (*params, int(limit), int(offset)),
            ).fetchall()
        return [_row_to_issue(row) for row in rows]

    def get(self, issue_id: int) -> Optional[Issue]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM issues WHERE id = ?;", (int(issue_id),)).fetchone()
        return _row_to_issue(row) if row else None

    def count(self, status: Optional[str] = "OPEN") -> int:
        with self._lock:
            if status:
                return self._conn.execute("SELECT COUNT(*) FROM issues WHERE status = ?;", (status,)).fetchone()[0]
            return self._conn.execute("SELECT COUNT(*) FROM issues;").fetchone()[0]

    def counts_by_kind(self, status: Optional[str] = "OPEN") -> Dict[IssueKind, int]:
        where, params = ("WHERE status = ?", (status,)) if status else ("", ())
        with self._lock:
            rows = self._conn.execute(
                f"SELECT kind, COUNT(*) AS n FROM issues {where} GROUP BY kind ORDER BY n DESC, kind;", params
            ).fetchall()
        return {IssueKind(row["kind"]): row["n"] for row in rows}

    def dismiss(self, ids: Optional[List[int]] = None) -> int:
        """Dismisses the given open issues (all open ones when ids is None)."""
        sql = "UPDATE issues SET status = 'DISMISSED', dismissed_at = datetime('now') WHERE status = 'OPEN'"
        return self._change(sql, ids)

    def delete(self, ids: Optional[List[int]] = None, status: Optional[str] = None) -> int:
        """Deletes the given issues, or every issue (optionally only those with `status`)."""
        if ids is None and status is not None:
            with self._lock, self._conn:
                return self._conn.execute("DELETE FROM issues WHERE status = ?;", (status,)).rowcount
        return self._change("DELETE FROM issues WHERE 1 = 1", ids)

    def purge(self, retention_days: int, max_dismissed: int = 5000) -> int:
        """Startup retention (ADR 0019). Open issues are never purged: they still need attention.
        Dismissed issues are kept (they stop the same problem from being raised again) until not
        seen again for `retention_days`; beyond `max_dismissed`, the least recently seen go first."""
        with self._lock, self._conn:
            purged = self._conn.execute(
                "DELETE FROM issues WHERE status = 'DISMISSED' AND last_seen < datetime('now', ?);",
                (f"-{int(retention_days)} days",),
            ).rowcount
            purged += self._conn.execute(
                """
                DELETE FROM issues WHERE id IN (
                    SELECT id FROM issues WHERE status = 'DISMISSED'
                    ORDER BY last_seen DESC, id DESC LIMIT -1 OFFSET ?
                );
                """,
                (int(max_dismissed),),
            ).rowcount
        return purged

    def _change(self, sql: str, ids: Optional[List[int]]) -> int:
        with self._lock, self._conn:
            if ids is None:
                return self._conn.execute(sql + ";").rowcount
            total = 0
            for start in range(0, len(ids), 500):
                chunk = [int(i) for i in ids[start:start + 500]]
                marks = ",".join("?" * len(chunk))
                total += self._conn.execute(f"{sql} AND id IN ({marks});", chunk).rowcount
            return total

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
