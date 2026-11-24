"""Issue reporting (ADR 0019): the thread-safe front door for foreseen resource problems.

Architecture
------------
    any thread                 issue writer thread              catalog database
    report_issue(...) ──put──> queue ──batch──> SQLiteIssueStore.record ──> issues table
    (never blocks/raises)      (single writer: owns all issue writes, one transaction per batch)

- Services and background threads (playback, auto-advance, analysis, scanner) never print
  and never write issues themselves: they call report_issue(), which only enqueues. A decoder
  or auto-advance thread can therefore never stall on a SQLite lock held by a long /scan, and a
  broken issue store can never break the operation that found the problem.
- Bursts (500 unreadable files in one scan) are written in one transaction.
- The REPL thread reads and changes issues (/issue commands) through the same store, after
  flush() so what it lists includes everything reported so far.
- The process-wide reporter is installed by the application entry point (cli.main); until
  then report_issue() is a no-op, so tests and library use never write to the real database.
- How many issues were newly opened is counted, so the UI can show one summary line
  ("3 novos problemas — veja /issue") instead of one line per problem.
"""

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from musicmatch.domain.issues import IssueKind, IssueReport, SubjectType
from musicmatch.storage.issue_store import SQLiteIssueStore

logger = logging.getLogger(__name__)

_STOP = object()
_MAX_BATCH = 500


class IssueReporter:
    def __init__(self, store: SQLiteIssueStore) -> None:
        self.store = store
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._new_lock = threading.Lock()
        self._new = 0
        self._closed = False
        self._thread = threading.Thread(target=self._run, name="musicmatch-issue-writer", daemon=True)
        self._thread.start()

    def report(self, report: IssueReport) -> None:
        """Queues a report; returns immediately. Safe from any thread."""
        if self._closed:
            logger.warning("Issue reported after shutdown, not persisted: %s %s", report.kind, report.subject_key)
            return
        self._queue.put(report)

    def flush(self, timeout: float = 5.0) -> bool:
        """Waits until every queued report is persisted; False on timeout."""
        deadline = time.monotonic() + timeout
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._queue.all_tasks_done.wait(remaining)
        return True

    def take_new_count(self) -> int:
        """Issues newly opened since the last call (recurrences and dismissed ones do not count)."""
        with self._new_lock:
            count, self._new = self._new, 0
        return count

    def close(self, timeout: float = 5.0) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(_STOP)
        self._thread.join(timeout=timeout)

    def _run(self) -> None:
        stop = False
        while not stop:
            item = self._queue.get()
            batch: List[IssueReport] = []
            taken = 1
            if item is _STOP:
                stop = True
            else:
                batch.append(item)
            while not stop and len(batch) < _MAX_BATCH:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                taken += 1
                if item is _STOP:
                    stop = True
                else:
                    batch.append(item)
            try:
                if batch:
                    opened = self.store.record(batch)
                    with self._new_lock:
                        self._new += opened
            except Exception:  # never let the writer die: the next batch may succeed
                logger.exception("Could not persist %d issue report(s)", len(batch))
            finally:
                for _ in range(taken):
                    self._queue.task_done()


# ----------------------------------------------------------------------
# Process-wide reporter
# ----------------------------------------------------------------------

_reporter: Optional[IssueReporter] = None
_reporter_lock = threading.Lock()


def configure_issue_reporter(db_path: Union[str, Path]) -> IssueReporter:
    """Installs the process-wide reporter on the catalog database (called by cli.main)."""
    global _reporter
    with _reporter_lock:
        previous = _reporter
        _reporter = IssueReporter(SQLiteIssueStore(db_path))
    if previous is not None:
        previous.close()
        previous.store.close()
    return _reporter


def set_issue_reporter(reporter: Optional[IssueReporter]) -> Optional[IssueReporter]:
    """Replaces the process-wide reporter (tests); returns the previous one."""
    global _reporter
    with _reporter_lock:
        previous, _reporter = _reporter, reporter
    return previous


def current_issue_reporter() -> Optional[IssueReporter]:
    return _reporter


def shutdown_issue_reporter() -> None:
    """Persists what is still queued and releases the store (application exit)."""
    global _reporter
    with _reporter_lock:
        reporter, _reporter = _reporter, None
    if reporter is not None:
        reporter.close()
        reporter.store.close()


def report_issue(
    kind: IssueKind,
    subject_key: str,
    message: str,
    *,
    subject_type: SubjectType,
    subject_label: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    source: Optional[str] = None,
) -> None:
    """Reports a foreseen problem with a resource or the environment. Never raises, never blocks."""
    reporter = _reporter
    if reporter is None:
        return
    try:
        reporter.report(IssueReport(kind=IssueKind(kind), subject_type=subject_type, subject_key=str(subject_key),
                                    message=message, subject_label=subject_label, details=details or {},
                                    source=source))
    except Exception:
        logger.exception("Could not queue an issue report (%s, %s)", kind, subject_key)
