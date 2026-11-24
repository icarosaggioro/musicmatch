"""Developer log (ADR 0019): unforeseen errors, with tracebacks, in a rotating text file.

This is the channel for failures our design did not foresee (bugs, broken invariants). It is
for whoever maintains MusicMatch, not for the listener: the screen only gets a one-line notice
with a short reference that finds the entry in the file.

- One rotating UTF-8 file (data/logs/musicmatch.log, 1 MB x 5); never the console, which
  belongs to the UI (and a log line printed by a background thread would garble the prompt).
- Every thread is covered: uncaught exceptions in the main thread (sys.excepthook) and in any
  background thread (threading.excepthook: playback, auto-advance, analysis workers, the issue
  writer) land in the file instead of being printed over the prompt or lost.
- Python warnings are captured; chatty third-party libraries are limited to WARNING.
- Logging is configured by the application entry point (cli.main), never on import, so tests
  and library use never write into the project's data folder.
"""

import logging
import logging.handlers
import sqlite3
import sys
import threading
import uuid
from pathlib import Path
from typing import Optional, Union

LOG_FILE_NAME = "musicmatch.log"
_FORMAT = "%(asctime)s %(levelname)-8s [%(threadName)s] %(name)s: %(message)s"
_NOISY_LOGGERS = ("google", "google_genai", "httpx", "httpcore", "urllib3", "yt_dlp", "asyncio")

logger = logging.getLogger("musicmatch")
_log_path: Optional[Path] = None
_handler: Optional[logging.Handler] = None


def configure_logging(log_dir: Union[str, Path, None] = None, level: Union[str, int, None] = None) -> Path:
    """Routes the 'musicmatch' logger (and warnings, uncaught exceptions) to the rotating log file.
    Idempotent: calling it again replaces the previous file handler. Returns the log file path."""
    global _log_path, _handler
    from musicmatch.config import settings

    directory = Path(log_dir or settings.LOG_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_FILE_NAME
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=5, encoding="utf-8", delay=True)
    handler.setFormatter(logging.Formatter(_FORMAT))

    root = logging.getLogger()
    if _handler is not None:
        root.removeHandler(_handler)
        _handler.close()
    root.addHandler(handler)
    root.setLevel(logging.WARNING)  # third-party code: warnings and errors only
    logger.setLevel(_level(level if level is not None else settings.LOG_LEVEL))
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.captureWarnings(True)
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_uncaught_in_thread
    _handler, _log_path = handler, path
    return path


def log_path() -> Optional[Path]:
    """The configured log file (None when logging was not configured, e.g. in tests)."""
    return _log_path


def new_error_ref() -> str:
    """Short reference shown on screen and written with the traceback, to find one in the other."""
    return uuid.uuid4().hex[:6]


def log_unexpected(message: str, exc: BaseException, ref: Optional[str] = None) -> str:
    """Logs an unforeseen exception with its traceback; returns the reference to show the user."""
    ref = ref or new_error_ref()
    logger.error("%s [ref %s]", message, ref, exc_info=(type(exc), exc, exc.__traceback__))
    return ref


def is_fatal(exc: BaseException) -> bool:
    """Failures after which MusicMatch cannot go on safely (ADR 0019: exit only when necessary):
    the catalog database is damaged, or memory is exhausted. Everything else is contained to the
    command that failed."""
    if isinstance(exc, MemoryError):
        return True
    if isinstance(exc, sqlite3.DatabaseError) and not isinstance(
        exc, (sqlite3.OperationalError, sqlite3.IntegrityError, sqlite3.ProgrammingError, sqlite3.InterfaceError)
    ):
        return True  # e.g. "database disk image is malformed", "file is not a database"
    text = str(exc).lower()
    return isinstance(exc, sqlite3.OperationalError) and ("malformed" in text or "not a database" in text)


def _level(value: Union[str, int]) -> int:
    if isinstance(value, int):
        return value
    resolved = logging.getLevelName(str(value).strip().upper())
    return resolved if isinstance(resolved, int) else logging.INFO


def _log_uncaught(exc_type, exc, tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    logger.critical("Uncaught exception in the main thread", exc_info=(exc_type, exc, tb))
    sys.__excepthook__(exc_type, exc, tb)  # the process is dying: the terminal still deserves the reason


def _log_uncaught_in_thread(args) -> None:
    if args.exc_type is SystemExit:
        return
    name = args.thread.name if args.thread is not None else "?"
    logger.error("Uncaught exception in thread %s", name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
