# 0019. Diagnostics: Developer Log, Issue Register, and Thread-Safe Reporting

## Context
Services and commands reported every problem by printing to the screen, ad hoc (100+ `render_error`/`render_warning` calls in 19 files). This mixed three different things:
- **Failures the design did not foresee (bugs).** The REPL's error boundary printed `str(e)` and discarded the traceback; about ten `except Exception: pass` blocks (mostly in playback threads) hid them completely. Nothing was left to diagnose.
- **Foreseen problems with resources or the environment.** Corrupt, empty or unreadable files; non-portable names; missing tracks; empty playlists; no audio device. The user saw a transient message, or only a count: `/scan` printed "N files with errors" with no way to learn which files or why.
- **User mistakes** (wrong usage, unknown playlist).

MusicMatch also runs work on several threads: audio decoding, auto-advance, the play-count ticker, analysis workers. None of them can print safely while the user types, and none should block on the database.

## Decision

### 1. Three channels
| What | Where | On screen |
| :--- | :--- | :--- |
| **Unforeseen failure (bug)** | **Developer log**: rotating text file `data/logs/musicmatch.log` (1 MB × 5, UTF-8) | One line with a short reference (`ref. a3f9c2`) to find the traceback |
| **Foreseen resource/environment problem** | **Issue register**: `issues` table in the catalog database | One summary line per command ("3 novos problemas registrados — veja /issue"), reviewed with `/issue` |
| **User mistake** | Nowhere (unchanged) | Immediate feedback, as before |

User mistakes stay out of this work on purpose. Recording them is a separate future feature, **usage data collection** (habits, interface friction points), not error handling.

### 2. Developer log
- **One entry point.** `configure_logging()` is called only by `cli.main`, never on import, so tests and library use never write into the project's data folder. Level comes from `LOG_LEVEL`, folder from `MUSICMATCH_LOG_DIR`.
- **Never the console**, which belongs to the UI.
- **Every thread is covered:**
  - `sys.excepthook` (main thread) and `threading.excepthook` (playback, auto-advance, analysis workers, the issue writer) send uncaught exceptions to the file instead of printing them over the prompt.
  - The log format names the thread.
  - Python warnings are captured.
- **Third-party noise.** Chatty libraries (google-genai, httpx, urllib3, yt-dlp) are limited to WARNING.
- **Silent swallows.** The former `except: pass` spots in the player (listeners, ticker, session close) now log. Unforeseen scanner, analysis and promotion failures are logged with their traceback, separated from the foreseen ones (which become issues).

### 3. Error boundary and graceful exit: "exit only when necessary"
- **An unforeseen error in a command or in the agent is contained.** The traceback is logged with a reference, and the screen shows one line with the command, a truncated reason (useful when the cause is environmental, e.g. a connection error) and the log location. The session continues: the command failed, but SQLite transactions rolled back and the player state is consistent. Stopping the music over a bug in `/playlist-export` would cost the user more than the bug.
- **Only a fatal error ends the session, gracefully.** Fatal means the catalog database is damaged (`database disk image is malformed`, `file is not a database`) or memory is exhausted. The loop stops and the existing shutdown path pauses and saves the playback state. Queued issues are persisted, the log records it, and the exit code is 1.
- **An error outside every command boundary**, or at startup, is logged with a reference and ends the process with exit code 1.

### 4. The Issue register
An **Issue** is a foreseen problem with a resource or the environment, kept for the user to review.

| Column | Meaning |
| :--- | :--- |
| `kind` | Catalogued in `IssueKind`, each with a category (`RESOURCE` \| `ENVIRONMENT`), severity (`ERROR` \| `WARNING`) and a label in the interface language. |
| `subject_type`, `subject_key`, `subject_label` | What it is about: a file or folder path, a track ID, `playlist:<id>`, `audio-output`… plus a human label. |
| `message`, `details` (JSON), `source` | The latest occurrence, structured extras (lists capped at 200 items) and the operation that found it (`scan`, `player`, `analysis`, `playlist`, `library`, `promotion`). |
| `status`, `occurrences`, `first_seen`, `last_seen`, `dismissed_at` | Lifecycle. |

- **Identity is `(kind, subject_key)`, enforced by a UNIQUE index.** Meeting the same problem again bumps `occurrences` and `last_seen`; it never adds a row. A rescan of a library with 500 broken files therefore neither floods the list nor the screen.
- **Environment problems are stored too** (no audio device, playback state not saved), at the user's request, with category `ENVIRONMENT`.
- **No foreign key to the subject.** Many subjects never enter the catalog (a corrupt file, a device, an M3U file).
- **No `CHECK` on `status`.** New states (e.g. `RESOLVED`, [ADR 0020](0020-issue-auto-resolution-and-remedies.md)) need no table rebuild.

**Dismiss vs. delete** are both offered, because they mean different things:
- **Dismiss** (`/issue-dismiss`): "I know, stop telling me." The issue is **kept** as `DISMISSED`. A recurrence updates its counters but never reopens it, and it is not counted as new. The dismissed row is the memory of that decision.
- **Delete** (`/issue-delete`): "forget it." The row is removed; if the problem happens again, it is registered as a new open issue.

**Retention runs at every start.** Startup is the right moment: one thread, nothing else writing yet. "Purge everything at restart" would be the wrong rule, because it would erase dismissed issues and defeat their purpose. The rules:
- Open issues are **never** purged automatically: they still need attention.
- Dismissed issues are purged once **not seen again** for `MUSICMATCH_ISSUE_RETENTION_DAYS` (default 180). A problem that keeps recurring stays silenced.
- A cap of 5,000 dismissed issues, least recently seen first, bounds the table.
- Deleted issues are gone at once.

### 5. Thread-safe reporting (the architectural change)
```
any thread                    issue writer thread                    catalog database
report_issue(...) ──put──>  queue ──batch (≤500)──>  SQLiteIssueStore.record  ──>  issues
(never blocks, never raises)   (single writer: owns all issue writes; one transaction per batch)
```
- **Reporters only enqueue.** Services and background threads never print and never write issues themselves: they call `report_issue()`. Consequences:
  - A decoder or auto-advance thread can never stall on a SQLite lock held by a long `/scan`.
  - A broken issue store can never break the operation that found the problem: the writer logs the failure and survives for the next batch.
- **One writer.** The writer owns the issue writes and batches bursts (500 unreadable files, one transaction). The REPL thread reads and changes issues (`/issue*`) through the same store after `flush()`, so listings include everything reported so far. The store has its own connection (`check_same_thread=False`, a lock), like the playback store.
- **No-op until configured.** The process-wide reporter is installed by `cli.main` on the catalog database, so tests and library use never write to real data.
- **New-issue counting.** The reporter counts newly opened issues; the REPL turns them into one summary line after each command, including commands that failed afterwards. Recurrences and dismissed issues are not "new".
- **Console output lock.** Playback events are rendered by background threads while the REPL thread may be printing a multi-line view (`/queue`, `/issue`). Every `render_*` method now holds one re-entrant lock, so blocks never interleave. Prompts (`input`) never hold it, so a background thread never waits for the user to type.

### 6. Issue sources (first wave)
| Source | Kinds |
| :--- | :--- |
| Scanner (`/scan`, `/library`) | `FILE_UNREADABLE` (stat/read errors), `FILE_EMPTY` (0 bytes, not indexed), `TAGS_UNREADABLE` (corrupt or unrecognised audio: `mediafile.UnreadableFileError`), `AUDIO_EMPTY` (indexed, zero duration), `NAME_NOT_PORTABLE` (per file and per folder: characters illegal on Windows, trailing space/dot, reserved device names, bytes that are not UTF-8), `PATH_TOO_LONG` (≥ 260 characters) |
| Player (foreground and auto-advance) | `TRACK_FILE_MISSING`, `AUDIO_UNDECODABLE`, `AUDIO_DEVICE_UNAVAILABLE`, `PLAYBACK_STATE_NOT_SAVED` |
| Analysis | `AUDIO_UNDECODABLE` (a DSP crash is additionally logged with its traceback) |
| Playlists | `PLAYLIST_IMPORT_INCOMPLETE` (one per imported file, listing unresolved entries), `PLAYLIST_EMPTY` (on `/playlist-load` and by a startup check, since playlists empty silently when their tracks leave the Library) |
| Library maintenance / promotion | `TRASH_FAILED`, `TAGS_NOT_WRITTEN` |

A file name with bytes that are not valid UTF-8 cannot be stored in SQLite. It is reported and kept out of the catalog until renamed; before, it silently increased the scanner's error count. Scan and playback messages became shorter: the path and the advice live in the issue.

### 7. Commands: the `/issue-<action>` family
- `/issue [id | --dismissed | --all]` lists open issues (the 50 most recent, with a summary by kind and the count of dismissed ones), shows one in detail (subject, occurrences, first/last seen, category, source, details, suggestion), or lists the dismissed ones / all of them.
- `/issue-dismiss <id...> | --all` and `/issue-delete <id...> | --dismissed | --all`. IDs accept `12` or `#12`, several at once. Bulk deletion asks first.
- At startup, one line next to the queue status: `🩺 Problemas em aberto: N · /issue para revisar`.

## Consequences
- Every bug leaves a traceback, from any thread, findable from a reference on screen. A bug in one command no longer costs the session.
- Resource problems are persistent, de-duplicated and reviewable, and they don't flood the screen.
- Services have one way to report problems (`report_issue`) that is safe from any thread and cannot block playback.
- The first wave covers the scanner, player, analysis, playlists and deletion/promotion. The remaining commands' ad-hoc messages are migrated incrementally.

### Known limitations
- Issues do not close themselves yet: a fixed problem stays open until dismissed or deleted. Auto-resolution and remedies are designed in [ADR 0020](0020-issue-auto-resolution-and-remedies.md).
- Files marked `MISSING` by a rescan (Soft Delete) are not issues: a disconnected drive would produce thousands. `/audit` reports them, and playing one raises `TRACK_FILE_MISSING`.
- `/download`, `/library import` (locked files), `/retag` and `/promote` still report only on screen (next wave).
