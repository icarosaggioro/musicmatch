# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]
### Added
- Developer log (ADR 0019): unforeseen errors, including uncaught exceptions in background threads (playback, analysis) and Python warnings, are written with their traceback to `data/logs/musicmatch.log` (rotating; `LOG_LEVEL`, `MUSICMATCH_LOG_DIR`). The screen shows one line with a reference to find the entry, and the session continues; only a damaged catalog database or exhausted memory ends MusicMatch, after saving the playback state (exit code 1).
- Issue register (ADR 0019): foreseen problems with files and the environment are kept in the database, one per problem (recurrences are counted, not duplicated): unreadable, empty or corrupt files, tracks with no duration, names that are not portable to Windows or paths over 260 characters, missing or undecodable tracks during playback and analysis, incomplete playlist imports, empty playlists, files that could not go to the Recycle Bin, tags not written on promotion, no audio device, playback state not saved. Each command that registers problems ends with one summary line, and startup shows how many are open.
- `/issue [id | --dismissed | --all]`, `/issue-dismiss <id... | --all>` (stop being told; the problem stays silenced) and `/issue-delete <id... | --dismissed | --all>` (forget it; it is registered again if it recurs). Dismissed issues not seen again for 180 days (`MUSICMATCH_ISSUE_RETENTION_DAYS`) are purged at startup; open ones never are.
- Saved playlists (ADR 0018): `/playlist [name]` lists them or shows one; `/playlist-save <name>` saves the play queue; `/playlist-load <name> [--append]` fills the queue with a playlist; `/playlist-rename`; `/playlist-delete` (the tracks stay); `/playlist-delete-with-tracks` (the tracks' files go to the Recycle Bin behind the `/delete` count-verification gate). Names ignore case and accents and accept a unique prefix; replacing a playlist or a non-empty queue asks first.
- `/playlist-remove <name> <id | #position>` takes tracks out of a playlist: by ID it removes every occurrence of the track, by position only that entry.
- `/playlist-import <file> [name]` and `/playlist-export <name> [file | folder] [--relative]` exchange M3U/M3U8 playlists with other players. Import matches entries by path or, for playlists from another machine, by artist/title/duration, and lists the folders to `/scan` for files not yet in the catalog. Export writes UTF-8 `.m3u8` (default: `<library>/Playlists`) with absolute or relative paths.
- Queue playback modes (ADR 0017): `/queue-repeat [on|off]` repeats the whole queue; `/queue-consume [on|off]` removes each track from the queue once it has been played (60 s heard, or the whole track) and playback moves on, while tracks skipped early, stopped or unavailable stay. Both modes are kept across restarts, shown in `/queue` and in the startup line, and exclude each other; keeping played tracks remains the default.
- `/queue-shuffle` and `/queue-sort <title|genre|artist|album>` reorder the whole queue, also during playback: shuffle puts the current track on top with everything else after it; sort (track name; genre then track name; artist then track name; album then track number) keeps the current track playing at its new position. Sorting ignores case and accents and puts missing tags (`Unknown Artist`, …) last.
- `/queue-play` plays the queue, completing the `/queue-<action>` command family.
- Persistent play queue (ADR 0016): the queue is saved in the catalog database and keeps played tracks until you remove them (a cursor marks the next entry; `/queue` shows ▶ current and ✓ played). The same track may be queued several times; `/queue-remove #<position>` removes a single entry and `/queue-remove <id>` every copy.
- `/pause` keeps the exact position, also across restarts; leaving MusicMatch while a track plays pauses it in place (the position is autosaved every 5 seconds). `/stop` returns to the first track of the queue.
- Every start prints a one-line queue status: `Fila: N faixa(s) · Última tocada: <faixa> · Tempo: <posição>`.
- Play counting: once a track has actually been heard for 60 seconds (`MUSICMATCH_PLAY_COUNT_SECONDS`; shorter tracks when heard to the end), its play counter and the total play counter increase and a play-history entry is recorded. Counts appear in `/search`, `/queue` and `/status`.
- Audio playback on Windows, macOS and Linux (Front 3, ADR 0015): `/play <id | queue>`, `/pause` (toggle), `/stop`, `/next`, `/volume [0-100]`, and the play queue commands `/queue`, `/queue-add <id>` (plays next), `/queue-add-last <id>`, `/queue-remove <id>` and `/queue-clear`. Playback runs in the background with click-free pause/volume changes and automatic advance through the queue.
- Missing tracks are reported when played, refused when queued, flagged in `/queue` and skipped with a notice during playback. Undecodable files and missing audio devices are reported clearly.
- Track IDs can be abbreviated to any unique prefix in playback commands; `/list` and `/search` now show the short ID of each track.
- New setting `MUSICMATCH_AUDIO_BACKEND` to force an output API (for example `wasapi`, `coreaudio`, `pulseaudio`, `alsa` or `null` for machines without sound).
- Without FFmpeg, MP3, FLAC and Ogg Vorbis files can now be analysed (and played) through the decoders bundled with `miniaudio`; previously only WAV.
- Acoustic analysis pipeline (Front 2, ADR 0014): `/analyze [path] [--force] [--limit N] [--workers N]` decodes each file once (FFmpeg, with a standard-library WAV fallback) and measures integrated loudness and Loudness Range (EBU R128 / BS.1770-4), sample peak, tempo with confidence, musical key with Camelot code, an acoustic fingerprint (`mmfp1`) and a waveform summary for future GUI rendering.
- Analysis is incremental, parallel and resumable: only new, modified or outdated tracks are decoded; results are saved as they complete; Ctrl+C cancels cleanly without leaving the REPL. `/analyze status` shows coverage and `/analyze show <id>` shows every metric of a track.
- Acoustic duplicate detection: `/audit duplicates --exact` (identical fingerprint, any tags or container) and `/audit duplicates --fuzzy` (same recording across encodes and bitrates); the `/audit` dashboard reports analysis coverage and exact acoustic duplicate groups.
- `/scan` reports how many scanned tracks still await acoustic analysis; `/search` shows BPM, key (Camelot) and LUFS.
- New settings: `MUSICMATCH_FFMPEG_PATH` and `MUSICMATCH_ANALYSIS_WORKERS`.
- Roadmap shows the delivery status of each feature front, linked to its tracking issues.
- Test guard (`tests/test_docs_links.py`) that fails when project docs link to machine-local `file:` paths or to repository files that do not exist.

### Changed
- `/audit duplicates` trusts the audio over the tags: analysed tracks are grouped by acoustic similarity (the same recording across encodes and bitrates included) and only tracks without a fingerprint fall back to artist and title. `--tags` keeps the previous behaviour (#28, #30).
- Importing MusicMatch no longer opens the catalog database or creates the staging folder: the process-wide services open them on first use (ADR 0021).
- New setting `MUSICMATCH_LIBRARY_CONFIG`: where `/library set-path` persists the chosen library (default unchanged: `data/library_config.json`).
- Scan and playback messages are shorter: the file path and the advice are in the issue (`/issue`). `/scan` says how many files were not indexed instead of "files with errors ignored".
- `/play queue` is superseded by `/queue-play` (the old spelling is still accepted); `/play` is now documented as `/play [id]`.
- The end-of-queue notice now says why the queue stopped (e.g. no playable track while repeating).
- LUFS, musical key and the measured BPM (when confident) are projected onto the catalog; a BPM that came from a tag is never overwritten (`bpm_source`: `tag`, `default` or `dsp`), and the measured one is kept in the analysis and shown by `/analyze show` (#29). Projected values appear in the catalog, so searches, BPM filters and the AI agent use real values. A new `track_analysis` table stores the detailed results; existing databases are migrated automatically.
- NumPy (>= 2.0), SciPy and miniaudio are now runtime dependencies.
- Re-scanning modified files updates their catalog rows in place (upsert) instead of replacing them, so play counts and queue entries are preserved.
- Roadmap translated to English and renamed from `docs/ROADMAP_PROXIMAS_FUNCIONALIDADES.md` to `docs/ROADMAP.md`.
- Remaining Portuguese docs translated to English: `PROJECT_CONTEXT.md`, `docs/RESEARCH_INDEX.md`, `docs/DATABASE_SCALING_SQLITE_VS_POSTGRESQL.md`, ADR 0010, the `[0.1.0]` changelog section and the comments in `pyproject.toml`. The yt-dlp reports were translated and renamed to `docs/YT-DLP_TECHNICAL_REPORT.md` (with its `.json` summary) and `docs/YT-DLP_TECHNICAL_AND_SECURITY_REPORT.md`.
- README no longer hard-codes test counts or a coverage table that went stale; it lists ADRs 0010 to 0013, the roadmap and the changelog, and explains that coverage reports need `pytest-cov`, which is not in the `dev` extras.
- Machine-local `file:///c:/...` links in the docs replaced with relative repository links, or with links to the public yt-dlp repository; local clone paths in ADR 0010 replaced with a placeholder.
- CI jobs now time out: Quality Gates after 15 minutes and the AI code review after 20 (aligned with its 15-minute review task limit), instead of GitHub's 360-minute default. A test guards that every job declares a timeout.

### Fixed
- Every natural-language prompt failed before reaching Gemini: the SDK could not describe the injected `service` parameter of the agent tools. Injected parameters are now hidden from the model, and a test builds the real request.
- The test suite wrote to real data: the project's `data/musicmatch.db` and `data/staging/`, and the default Managed Library `~/Music/MusicMatch` in the user's home folder. Tests now run in a per-session sandbox, and a guard fails any test that writes outside it (ADR 0021).
- Background output (e.g. "now playing" on auto-advance) no longer interleaves with multi-line views such as `/queue`: console output is serialized.
- Files whose name is not valid UTF-8 were silently skipped by `/scan`; they are now reported.
- Unquoted Windows paths lost their backslashes in every command (`/scan C:\Music` reached the command as `C:Music`); command lines now keep backslashes literal while still honouring quotes.
- A full-text index created over pre-existing rows (very old databases) is now rebuilt; previously the first update could corrupt it.
- `/library reorganize` no longer removes moved tracks from the catalog: a stray trailing comma turned the new path into a tuple after the old record had been deleted. Moved records are now re-keyed in place, keeping their metadata and acoustic analysis.
- `scripts/check.py` no longer prints a hard-coded "197 tests" in its success summary.
- `pyproject.toml` declares the license as an SPDX expression (`license = "MIT"` plus `license-files`) and requires `setuptools>=77.0.0`, removing the setuptools deprecation warning; the old table form stops being supported after 2027-02-18. The license itself is unchanged.

---

## [0.2.0] - 2026-11-15
### Added
- Real audio ingestion: `/scan` reads tags with `mediafile` across MP3, FLAC, M4A, AAC, OGG, WAV, WMA, AIFF and Opus, and reports scan and persistence metrics.
- Idempotent re-scans (ADR 0009): stat-cache on file modification time and size skips unchanged files; track IDs are a deterministic SHA-256 of the canonical path.
- Non-destructive track lifecycle: files that disappear are marked `MISSING` instead of being deleted from the catalog.
- Web ingestion with `yt-dlp` (ADR 0010, ADR 0011): `/download <url|search> [--format mp3]` downloads into a session-based staging area, with SSRF, live-stream and duration safeguards.
- Staging and promotion: `/staging [list | show | promote | discard]` and `/promote <session_id> [--all | --track <id>]` move tracks into the managed library taxonomy (`Artists/<Artist>/<Album>`, `Artists/<Artist>/Singles`, `Various Artists/<Album>`, `Collections/<Name>`).
- Managed library location governance (ADR 0012): cross-platform default under `~/Music/MusicMatch/`, write-access probe, and refusal of system-critical paths.
- `/model [name]` shows or changes the active LLM.
- Library maintenance suite (Front 5, ADR 0013): `/audit [duplicates | prune]`, `/delete` (moves files to the OS Recycle Bin via `send2trash`), `/prune`, `/retag`, `/unindex`, and `/library [status | set-path | import | reorganize | clear]`, with confirmation and count-verification gates for batch operations.
- SDLC framework adopted (`.agents/` rules, guides and skills), with project rules in `.agents/rules/project.md`.
- Quality gates: `scripts/check.py` runs the same checks locally and in GitHub Actions CI on every push and pull request.
- Advisory AI code review on pull requests, scoped by `.github/ocr-rules.json`.
- Test guards that fail when the supported Python version drifts between `project.md`, `pyproject.toml` and CI, when egg-info is tracked, or when the package version disagrees with `pyproject.toml`.

### Changed
- Slash commands refactored into a modular command pattern with a single lookup registry.
- Minimum supported Python is now 3.14.6 (was 3.11 in packaging metadata); CI runs on Python 3.14.
- `musicmatch.__version__` is read from the installed package metadata, so `pyproject.toml` is the single source of the version.
- AI code review reads its model from the `CI_OCR_LLM_MODEL` repository variable.

### Fixed
- `/download` no longer aborts a single-track download with a false "maximum number of downloads reached" error (#4).

### Removed
- `src/musicmatch.egg-info/` build artifacts from version control; `*.egg-info/`, `build/` and `dist/` are ignored.

---

## [0.1.0] - 2026-09-06
### Added
- **Base Architecture (Walking Skeleton)**:
  - Orchestration system in Python 3.14 with separated responsibilities (Clean Architecture / DDD).
  - **Command** pattern in the interactive harness, decoupled from the presentation layer (`ConsoleUI`).
  - Command dispatcher (`CommandRegistry`) supporting the slash commands `/help`, `/status`, `/scan`, `/search`, `/list`, `/clear`, `/exit`.
  - Persistence in **SQLite with FTS5** (*Full-Text Search*) and an external-content table kept in sync by native triggers (`AFTER INSERT`, `AFTER UPDATE`, `AFTER DELETE`).
  - Hybrid search ranked by Okapi BM25 relevance combined with relational filters (BPM, genre).
  - Strongly typed domain contracts with **Pydantic V2** (`Track`, `ScanResult`).
  - Business service layer (`LibraryService`) decoupling the database from the interfaces.
  - Agent orchestration with the **Google Antigravity SDK** and integration with **Gemini 3.6 Flash** models via `google-genai`.
  - Automated test suite with `pytest` (73 unit and integration tests, 98% coverage at the time of this release).
- **Architecture Documentation**:
  - ADRs 0001 to 0009 recording every foundational decision of the system.

[Unreleased]: https://github.com/icarosaggioro/musicmatch/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/icarosaggioro/musicmatch/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/icarosaggioro/musicmatch/releases/tag/v0.1.0
