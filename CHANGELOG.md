# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]
### Added
- Roadmap shows the delivery status of each feature front, linked to its tracking issues.
- Test guard (`tests/test_docs_links.py`) that fails when project docs link to machine-local `file:` paths or to repository files that do not exist.

### Changed
- Roadmap translated to English and renamed from `docs/ROADMAP_PROXIMAS_FUNCIONALIDADES.md` to `docs/ROADMAP.md`.
- Remaining Portuguese docs translated to English: `PROJECT_CONTEXT.md`, `docs/RESEARCH_INDEX.md`, `docs/DATABASE_SCALING_SQLITE_VS_POSTGRESQL.md`, ADR 0010, the `[0.1.0]` changelog section and the comments in `pyproject.toml`. The yt-dlp reports were translated and renamed to `docs/YT-DLP_TECHNICAL_REPORT.md` (with its `.json` summary) and `docs/YT-DLP_TECHNICAL_AND_SECURITY_REPORT.md`.
- README no longer hard-codes test counts or a coverage table that went stale; it lists ADRs 0010 to 0013, the roadmap and the changelog, and explains that coverage reports need `pytest-cov`, which is not in the `dev` extras.
- Machine-local `file:///c:/...` links in the docs replaced with relative repository links, or with links to the public yt-dlp repository; local clone paths in ADR 0010 replaced with a placeholder.

### Fixed
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
