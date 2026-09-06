# 🎵 MusicMatch

> **AI-Native Local Music Management, Curation & DSP Playback System**  
> A hands-on, educational engineering laboratory exploring AI Agents, Digital Signal Processing (DSP), and Modern Systems Architecture.

[![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-87%20passed-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/coverage-98%25-success.svg)]()
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

- **Language & Runtime**: Python 3.14.6 (compatible with Python 3.11+)
- **Audio Metadata & Ingestion**: `mediafile` (unified tag parsing across MP3, FLAC, M4A, OGG, WAV) and `pyacoustid` (Chromaprint acoustic fingerprinting)
- **AI SDK**: `google-genai` (Gemini 3.6 Flash with Function Calling and Structured Outputs)
- **Domain Modeling & Contracts**: `pydantic` V2 (strict runtime data integrity and automatic JSON Schema generation)
- **Persistence & Search Engine**: Embedded SQLite with **FTS5** (*Full-Text Search*) inverted index, external content synchronization triggers, and BM25 relevance scoring
- **Business Service Layer**: `LibraryService` & `AudioScanner` encapsulating idempotent scanning, stat-cache, and hybrid search
- **Harness & Interface**: Decoupled Event Loop with Command Pattern and `ConsoleUI` renderer
- **Testing & Quality Assurance**: `pytest`, `pytest-asyncio`, `pytest-cov`, `coverage` (**98% code coverage**, 87 tests)
- **Native High-Performance DSP Engine (Roadmap)**: Rust compiled via `PyO3` e `Maturin`

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.11 or higher** installed.
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
| `/scan <path>` | Triggers the audio scanner directly (e.g., `/scan C:/Music`). |
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

The project includes **73 automated unit tests** covering the agent ReAct loop with deterministic mocks (zero API token cost), Pydantic runtime validations, harness routing, interactive `/list` pagination with cancellation, SQLite FTS5 triggers and search ranking, library service use cases, and UI rendering:

```powershell
# Run all tests
pytest

# Run tests with detailed line-by-line coverage report
pytest --cov=musicmatch --cov-report=term-missing
```

### Current Coverage Report: **98%**
```text
Name                                    Stmts   Miss  Cover
-----------------------------------------------------------
src\musicmatch\__init__.py                  1      0   100%
src\musicmatch\agent\core.py               49      4    92%
src\musicmatch\cli.py                      10      1    90%
src\musicmatch\commands\__init__.py         3      0   100%
src\musicmatch\commands\base.py            13      1    92%
src\musicmatch\commands\registry.py       150      1    99%
src\musicmatch\config.py                   11      0   100%
src\musicmatch\domain\models.py            24      0   100%
src\musicmatch\harness\__init__.py          2      0   100%
src\musicmatch\harness\loop.py             37      0   100%
src\musicmatch\services\__init__.py         2      0   100%
src\musicmatch\services\library.py         37      1    97%
src\musicmatch\storage\__init__.py          3      0   100%
src\musicmatch\storage\mock_db.py          23      0   100%
src\musicmatch\storage\schema.py            6      0   100%
src\musicmatch\storage\sqlite_repo.py     139      5    96%
src\musicmatch\tools\__init__.py            3      0   100%
src\musicmatch\tools\scanner.py             6      0   100%
src\musicmatch\tools\search.py              6      0   100%
src\musicmatch\ui\__init__.py               2      0   100%
src\musicmatch\ui\renderer.py              66      0   100%
-----------------------------------------------------------
TOTAL                                     593     13    98%
```

---

## 📚 Documentation & Architecture Decision Records (ADRs)

All architectural decisions and research references are persisted and versioned in the repository:
- [CONTEXT.md](CONTEXT.md): Ubiquitous Language dictionary defining strict domain terminology and terms to avoid.
- [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md): System guidelines, engineering personas, and architectural roadmap.
- [docs/RESEARCH_INDEX.md](docs/RESEARCH_INDEX.md): Research map covering MPEG-1/2 Layer III specs, disk I/O strategies, SQLite FTS5/vector indexing, and agent framework comparisons.
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

---

## 📄 License

This project is licensed under the terms of the **MIT License** — see the [LICENSE](LICENSE) file for details.  
Copyright (c) 2026 Ícaro Saggioro.

