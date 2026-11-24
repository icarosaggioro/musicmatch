# 🎵 MusicMatch

> **AI-Native Local Music Management, Curation & DSP Playback System**  
> A hands-on, educational engineering laboratory exploring AI Agents, Digital Signal Processing (DSP), and Modern Systems Architecture.

[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/icarosaggioro/musicmatch/actions/workflows/ci.yml/badge.svg)](https://github.com/icarosaggioro/musicmatch/actions/workflows/ci.yml)
[![Architecture](https://img.shields.io/badge/architecture-Harness%20%7C%20Pydantic%20V2-orange.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 🎯 Project Purpose

**MusicMatch** is conceived under the unified lens of two specialized engineering disciplines:
1. **Modern Software Engineering**: Battle-tested design patterns (*Command Pattern*, *Event Loop Boundaries*, *Clean Architecture*, *Single Responsibility Principle*), autonomous AI agent orchestration, strict runtime data validation via **Pydantic V2**, and high-performance native interoperability with **Rust (PyO3/Maturin)**.
2. **Sound Engineering & DSP / Music AI**: Audio signal processing, psychoacoustics, MPEG audio standards (CBR/VBR bitrates, MDCT filterbanks, bit reservoir, ID3 tags), integrated perceptual loudness measurement (**LUFS / EBU R128**), BPM/harmony detection, and multimodal direct audio listening via **Gemini** models.

The overarching goal is to deliver an application running **100% locally on Windows**, engineered to index, audit, curate, and search massive audio collections (10,000 to 100,000+ tracks) with instant natural-language retrieval and complete user privacy.

---

## 🏛️ System Architecture

The project follows a didactic, incremental **Walking Skeleton** strategy: establishing high-level Python orchestration with typed contracts, simulated stubs, and an interactive harness before introducing low-level native Rust parsing and SQLite vector storage.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                             MUSICMATCH ARCHITECTURE                          │
├──────────────────────────────────────────────────────────────────────────────┤
│  [ Interface / Harness ]                                                     │
│    ├── ConsoleUI (Decoupled View: Banners, ReAct Observability, Diagnostics) │
│    ├── Command Registry (Slash Commands: /help, /status, /scan, /clear, /exit)│
│    └── Event Loop (Routing: Harness Commands vs Natural Language Prompts)    │
│                             │ (Direct In-Process or WebSockets / REST IPC)   │
│                             ▼                                                │
│  [ Orchestration & AI Layer - Python 3.14.6 ]                                │
│    ├── Google Antigravity SDK & Google GenAI SDK (Gemini 3.6 Flash)          │
│    ├── Pydantic V2 (Domain Models, Runtime Validation & JSON Schemas)        │
│    ├── SingleTurnAgent (ReAct reasoning loop with live observability)        │
│    │                                                                         │
│    │  import musicmatch_core (PyO3 / Maturin Bridge - Roadmap)               │
│    ▼                                                                         │
│  [ High-Performance DSP & Storage Layer - Rust ] (Roadmap)                  │
│    ├── Multi-threaded File Scanner (Rayon for 100k+ tracks)                  │
│    ├── Tag & Bitstream Parser (lofty / symphonia)                            │
│    ├── DSP Engine (BPM, LUFS EBU R128, Mini-Waveforms with SIMD)             │
│    └── Zero-GIL Batch Ingestion (SQLite + FTS5 + sqlite-vec)                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

- **Language & Runtime**: Python 3.14.6 or higher
- **Diagnostics (ADR 0019)**: unforeseen errors from any thread are written with their traceback to a rotating developer log (`data/logs/musicmatch.log`) and shown as one line with a reference, and the session continues (only a damaged database or exhausted memory ends it, gracefully); foreseen resource problems go to a persistent, de-duplicated Issue register fed through a single, non-blocking writer thread
- **Playback Persistence & Play Counts (ADR 0016)**: the queue (played tracks included), the paused position and the volume survive restarts; per-track and total play counters increase once a track has actually been heard for 60 seconds
- **Audio Playback (ADR 0015)**: `miniaudio` output (WASAPI/DirectSound on Windows, Core Audio on macOS, PulseAudio/ALSA/JACK on Linux) fed by the FFmpeg decoding pipeline, with an in-memory play queue
- **Acoustic Analysis (ADR 0014)**: `numpy` + `scipy` DSP engine (EBU R128 loudness, tempo, musical key, acoustic fingerprint) fed by a single streaming FFmpeg decode per file
- **Audio Metadata & Ingestion**: `mediafile` (unified tag parsing across MP3, FLAC, M4A, OGG, WAV) and `pyacoustid` (Chromaprint acoustic fingerprinting)
- **AI SDK**: `google-genai` (Gemini 3.6 Flash with Function Calling and Structured Outputs)
- **Domain Modeling & Contracts**: `pydantic` V2 (strict runtime data integrity and automatic JSON Schema generation)
- **Persistence & Search Engine**: Embedded SQLite with **FTS5** (*Full-Text Search*) inverted index, external content synchronization triggers, and BM25 relevance scoring
- **Business Service Layer**: `LibraryService` & `AudioScanner` encapsulating idempotent scanning, stat-cache, and hybrid search
- **Harness & Interface**: Decoupled Event Loop with Command Pattern and `ConsoleUI` renderer
- **Testing & Quality Assurance**: `pytest` and `pytest-asyncio`, run by `scripts/check.py` locally and in CI
- **Native High-Performance DSP Engine (Roadmap)**: Rust compiled via `PyO3` e `Maturin`

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.14.6 or higher** installed.
- **FFmpeg** on the `PATH` (or `MUSICMATCH_FFMPEG_PATH` in `.env`) — required for downloads and for playing/analysing M4A/AAC, Opus, WMA and AIFF files. Without it, MP3, FLAC, OGG and WAV still play and are analysed through the decoders bundled with `miniaudio`.
- An audio output device. No extra audio libraries are needed on Windows, macOS or Linux. On headless machines, set `MUSICMATCH_AUDIO_BACKEND=null` to run playback without sound.
- A **Google AI Studio** Gemini API Key — obtain for free at [aistudio.google.com](https://aistudio.google.com/).

### 1. Clone the Repository
```bash
git clone https://github.com/icarosaggioro/musicmatch.git
cd musicmatch
```

### 2. Create and Activate Virtual Environment
On Windows (PowerShell):
```powershell
python -m venv .ve
.\.ve\Scripts\Activate.ps1
```

### 3. Install Dependencies
Install in editable mode (`-e`) with all development and testing dependencies:
```powershell
pip install -e ".[dev]"
```

### 4. Configure Environment Variables
Copy the example environment file and insert your Gemini API key:
```powershell
cp .env.example .env
```
Edit `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
LOG_LEVEL=INFO
```

---

## 🎮 Usage Guide (Interactive Harness)

Launch MusicMatch directly from your terminal:
```powershell
musicmatch
```
*(Or alternatively: `python -m musicmatch.cli`)*

### A. Administrative Harness Commands (Slash Commands)
MusicMatch features fast administrative commands prefixed with `/` that execute system tasks deterministically without consuming LLM tokens:

| Command | Description |
| :--- | :--- |
| `/help` | Displays the complete list of commands and usage instructions. |
| `/status` | Shows the active Gemini model, total indexed tracks, and SQLite storage stats. |
| `/list [n]` | Lists tracks from the library with 20 items/page and interactive cancellation. |
| `/search <query>` | Performs instantaneous full-text search across the library using SQLite FTS5. |
| `/scan <path>` | Triggers the audio scanner directly (e.g., `/scan C:/Music`). Metadata only — fast and idempotent. |
| `/analyze [path] [--force] [--limit N] [--workers N]` | Measures loudness (LUFS/LRA), BPM, musical key (Camelot) and the acoustic fingerprint of pending tracks; incremental and resumable (`Ctrl+C` keeps finished work). `/analyze status` and `/analyze show <id>` inspect results. |
| `/play [id]` | Plays a track now. `/play` alone continues a paused track, even after restarting MusicMatch, or plays the queue. IDs can be shortened to a unique prefix, e.g. `/play 3fa2b9`; `/list` and `/search` show them. |
| `/pause` · `/stop` · `/next` · `/volume [0-100]` | `/pause` keeps the exact position, also across restarts (run it again or `/play` to continue); `/stop` returns to the first track of the queue; `/next` skips; volume uses a cubic taper and shows the current value without an argument. |
| `/queue` · `/queue-play` · `/queue-add <id>` · `/queue-add-last <id>` · `/queue-remove <id \| #pos>` · `/queue-clear` | Persistent play queue: show it (▶ current, ✓ already played), play it, add a track to play next, append to the end, remove every copy of a track or one entry by position, clear. Played tracks stay in the queue until you remove them, and the same track may be queued several times. Unavailable files are flagged and skipped with a notice. Every start prints a one-line queue status. Every queue command is named `/queue-<action>` (`/play queue` still works as the former spelling of `/queue-play`). |
| `/queue-repeat [on\|off]` · `/queue-consume [on\|off]` | Queue modes (ADR 0017), kept across restarts; no argument toggles. Repeat plays the whole queue again after the last track. Consume removes each track from the queue once it has been played (same rule as the play counter: 60 s heard, or the whole track) and playback moves on; tracks skipped early, stopped or unavailable stay. The two modes exclude each other. |
| `/queue-shuffle` · `/queue-sort <title\|genre\|artist\|album>` | Reorder the whole queue, also during playback: shuffle (the current track goes to the top and everything else follows), or sort by track name, genre then track name, artist then track name, or album then track number (the current track keeps playing at its new position). `/queue` always shows the real play order. |
| `/playlist [name]` · `/playlist-save <name>` · `/playlist-load <name> [--append]` · `/playlist-rename <name> <new name>` | Saved playlists (ADR 0018): list them or show one; save the play queue as a playlist; fill the queue with a playlist (replaces the queue after asking, or `--append`s to it); rename. Names ignore case and accents and can be shortened to a unique prefix. |
| `/playlist-remove <name> <id \| #pos>` | Take tracks out of a playlist: `<id>` removes every occurrence of the track, `#<position>` only the entry at that position (as numbered by `/playlist <name>`). The tracks stay in the library. |
| `/playlist-delete <name>` · `/playlist-delete-with-tracks <name>` | Delete a playlist and keep its tracks, or delete it and move its tracks' files to the Recycle Bin (unindexing them) behind the same count-verification gate as `/delete`. |
| `/playlist-import <file.m3u\|.m3u8> [name]` · `/playlist-export <name> [file \| folder] [--relative]` | Exchange playlists with other players as M3U/M3U8. Import matches entries by path, or by artist/title/duration for playlists from another machine, and tells you which folders to `/scan` for the rest. Export writes UTF-8 `.m3u8` to `<library>/Playlists` by default, with absolute or relative paths. |
| `/issue [id \| --dismissed \| --all]` · `/issue-dismiss <id... \| --all>` · `/issue-delete <id... \| --dismissed \| --all>` | Issue register (ADR 0019): problems found with your files and environment (corrupt, empty or unreadable files, names that break on Windows, missing tracks, empty playlists, no audio device…) are kept in the database, one per problem, and announced with a single summary line. List them, inspect one, dismiss (stop being told; stays silenced) or delete (forgotten; comes back if it happens again). |
| `/audit duplicates [--tags \| --exact \| --fuzzy]` | Finds duplicates: by default, the same recording (across encodes and bitrates) for analysed tracks and tags for the others; `--tags` forces tags, `--exact` identical audio and `--fuzzy` similar audio only. Recommends the highest-fidelity copy. |
| `/clear` | Clears the terminal screen. |
| `/exit` | Exits the application (*ergonomic aliases*: `sair`, `exit`, `quit`, `q`). |

### B. Interacting with the Intelligent ReAct Agent
Any user input that does not start with `/` is automatically routed to the AI Agent, which executes a transparent ReAct cycle with real-time observability logs:

- **Tool Execution (Function Calling)**:
  ```text
  MusicMatch > Please index the audio files in C:/Music/Collection
  ```
  *The agent detects user intent, invokes `scan_library`, validates ingested tracks through Pydantic, populates the database, and synthesizes a friendly summary.*

- **Fast Full-Text & Hybrid Search**:
  ```text
  MusicMatch > Find any Queen tracks with BPM above 110
  ```
  *The agent invokes the `search_tracks` tool, querying the local SQLite FTS5 index and returning exact domain matches without hallucination.*

- **Direct Audio & DSP Queries**:
  ```text
  MusicMatch > What is LUFS and how is the EBU R128 recommendation applied in audio normalization?
  MusicMatch > How does the MP3 bit reservoir affect audio cutting and seeking?
  ```
  *The agent answers directly with sound engineering domain knowledge without triggering unnecessary tool calls.*

---

## 🧪 Automated Testing & Coverage

The automated test suite covers the agent ReAct loop with deterministic mocks (zero API token cost), Pydantic runtime validations, harness routing, interactive `/list` pagination with cancellation, SQLite FTS5 triggers and search ranking, library services, web ingestion and promotion, library maintenance safeguards, and UI rendering. Current results are shown by the CI badge above.

```bash
# Run every quality gate (syntax, dependency health, test suite), exactly as CI does
python scripts/check.py

# Run only the tests
pytest
```

For a line-by-line coverage report, install `pytest-cov` (not part of the `dev` extras) and run:

```bash
pip install pytest-cov
pytest --cov=musicmatch --cov-report=term-missing
```

**Tests never touch real data (ADR 0021).** Each session runs in a temporary sandbox (catalog database, staging area, logs, library config and home folder, so `~/Music/MusicMatch` too), whatever your `.env` says. A guard fails any test that writes to the project tree, to your real `~/Music/MusicMatch`, or to the default catalog instead of its own in-memory database or `tmp_path`, and names the files it touched.

---

## 📚 Documentation & Architecture Decision Records (ADRs)

All architectural decisions and research references are persisted and versioned in the repository:
- [CONTEXT.md](CONTEXT.md): Ubiquitous Language dictionary defining strict domain terminology and terms to avoid.
- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md): System guidelines, engineering personas, and architectural roadmap.
- [docs/RESEARCH_INDEX.md](docs/RESEARCH_INDEX.md): Research map covering MPEG-1/2 Layer III specs, disk I/O strategies, SQLite FTS5/vector indexing, and agent framework comparisons.
- [docs/ROADMAP.md](docs/ROADMAP.md): Functional roadmap with the status of each feature front and links to its issues.
- [CHANGELOG.md](CHANGELOG.md): Release history.
- [docs/DATABASE_SCALING_SQLITE_VS_POSTGRESQL.md](docs/DATABASE_SCALING_SQLITE_VS_POSTGRESQL.md): Comparative benchmark and scaling architecture for 1M+ audio tracks (SQLite vs. PostgreSQL + pgvector).
- **Architecture Decision Records (ADRs)**:
  - [ADR 0001](docs/adr/0001-top-down-walking-skeleton-with-stubs.md): Top-Down Development via Walking Skeleton and Typed Tool Contracts.
  - [ADR 0002](docs/adr/0002-orchestrator-cli-repl.md): Orchestrator Architecture and CLI Observability REPL.
  - [ADR 0003](docs/adr/0003-didactic-incremental-evolution.md): Didactic Incremental Evolution Strategy.
  - [ADR 0004](docs/adr/0004-data-lifecycle-and-first-tool-selection.md): Data Lifecycle and First Tool Selection (`scan_library`).
  - [ADR 0005](docs/adr/0005-structured-cli-harness-and-commands.md): Structured CLI Harness with Command Registry and View Separation.
  - [ADR 0006](docs/adr/0006-domain-modeling-and-runtime-validation-with-pydantic.md): Domain Modeling and Runtime Validation with Pydantic.
  - [ADR 0007](docs/adr/0007-sqlite-persistence-with-fts5-and-service-layer.md): SQLite Persistence with FTS5 and Domain Service Layer.
  - [ADR 0008](docs/adr/0008-database-scaling-and-postgresql-migration-roadmap.md): Database Scaling Strategy and PostgreSQL Migration Roadmap.
  - [ADR 0009](docs/adr/0009-library-idempotency-stat-cache-and-lifecycle-policy.md): Library Idempotency, Track Identity via Full SHA-256 Path Hash, Stat-Cache, and Non-Destructive Lifecycle Policy.
  - [ADR 0010](docs/adr/0010-yt-dlp-integration-and-packaging-strategy.md): yt-dlp Integration, Dependency Management, and CI/CD Packaging Strategy.
  - [ADR 0011](docs/adr/0011-web-ingestion-two-stage-staging-and-managed-library-taxonomy.md): Web Ingestion Pipeline, Two-Stage Staging Architecture, and Managed Library Taxonomy.
  - [ADR 0012](docs/adr/0012-managed-library-governance-resolution-and-safeguards.md): Managed Library Location Governance, Cross-Platform Resolution, and Write-Access Safeguards.
  - [ADR 0013](docs/adr/0013-library-maintenance-consolidation-and-deletion-safeguards.md): Library Maintenance, Consolidation Imports, and Two-Tier Deletion Safeguards.
  - [ADR 0014](docs/adr/0014-acoustic-analysis-pipeline-and-fingerprint-deduplication.md): Acoustic Analysis Pipeline, Real Signal Metrics, and Fingerprint-Based Duplicate Detection.
  - [ADR 0015](docs/adr/0015-cross-platform-audio-playback-engine-and-play-queue.md): Cross-Platform Audio Playback Engine, Output Library Selection, and Play Queue.
  - [ADR 0016](docs/adr/0016-persistent-play-queue-resume-and-play-counting.md): Persistent Play Queue, Resume Point, and Play Counting.
  - [ADR 0017](docs/adr/0017-queue-playback-modes-repeat-consume-shuffle-and-sort.md): Queue Playback Modes (Repeat, Consume, Shuffle, Sort) and the `/queue-<action>` Command Family.
  - [ADR 0018](docs/adr/0018-saved-playlists-m3u-import-export-and-playlist-commands.md): Saved Playlists, M3U Import/Export, and the `/playlist-<action>` Command Family.
  - [ADR 0019](docs/adr/0019-diagnostics-developer-log-issue-register-and-thread-safe-reporting.md): Diagnostics: Developer Log, Issue Register, and Thread-Safe Reporting.
  - [ADR 0020](docs/adr/0020-issue-auto-resolution-and-remedies.md): Issue Auto-Resolution and Remedies (proposed).
  - [ADR 0021](docs/adr/0021-test-isolation-session-sandbox-and-filesystem-guard.md): Test Isolation: Session Sandbox, Side-Effect-Free Imports, and a Filesystem Guard.

---

## 📄 License

This project is licensed under the terms of the **MIT License** — see the [LICENSE](LICENSE) file for details.  
Copyright (c) 2026 Ícaro Saggioro.

