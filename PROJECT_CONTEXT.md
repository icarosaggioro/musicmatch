# MusicMatch - Project Context and Guidelines

## 1. Working Persona
The project is conceived and driven from the combined viewpoint of two engineering disciplines:
* **Software Engineer**: Systems architecture, data structures, concurrency, disk I/O optimization, local databases, asynchronous APIs, processing queues, Python-Rust interoperability and agent orchestration.
* **Sound Engineer / DSP & Music AI Specialist**: Audio signal processing, psychoacoustics, spectral analysis (FFT), loudness measurement (LUFS/EBU R128), BPM and harmony detection, music transcription, neural audio models and acoustic curation.

---

## 2. Defined Guidelines and Requirements

### A. Domain and Scope
* **Audio Handling and Playback**: Initial focus on the MP3 format, with an architecture that extends to other formats (FLAC, WAV, AAC, OGG, etc.).
* **Large Local Libraries**: Designed to manage and index large collections (10,000 to 100,000+ files) with high performance, low memory use and instant search.
* **Platform / Environment**: An application designed to run **locally on the user's PC (Windows)**, ensuring privacy, maximum disk access speed and independent operation.

### B. Extensive Use of Artificial Intelligence (AI-Native)
* **Agent Orchestration**: Uses the **Google Antigravity SDK** to orchestrate autonomous agents and subagents for task automation, curation and auditing.
* **Asynchronous Batch Processing**: Background task queues for indexing, mini-waveform generation, acoustic extraction and lyrics analysis without freezing the UI or interrupting playback.
* **Semantic & Multimodal Understanding**:
  * Lyrics analysis, mood identification, enriched metadata generation and natural-language search by musical affinity ("vibe").
  * Direct audio listening capabilities (multimodal via Gemini) to understand arrangements, timbres and musical characteristics.
  * Hybrid execution: cloud models (Gemini 3.6 Flash / 3.1 Pro) and local on-device models (Gemma 4 family via LiteRT/GPU).

### C. Confirmed Technology Stack
* **Orchestration & Backend Language**: **Python 3.14.6**
  * Responsible for agent orchestration with the **Google Antigravity SDK**, AI integrations with `google-genai`, and the local service layer (FastAPI / WebSockets).
* **High-Performance & DSP Language**: **Rust**
  * Responsible for critical disk I/O (multi-threaded scanning of 100k files with Rayon), tag/header reading (`lofty`/`symphonia`), numerical DSP algorithms (BPM, LUFS, mini-waveforms with SIMD) and very fast SQLite access.
  * **FFI Pattern / Zero GIL Overhead**: Rust processes the files and writes in batches directly to the local SQLite database, notifying Python through asynchronous events (without converting hundreds of thousands of objects in memory).
  * **Resilient Error Handling**: Corrupted or anomalous files are cataloged in an audit table for inspection by the Antigravity Auditor Agent.
  * **Interoperability Bridge**: **PyO3 + Maturin** (compiles native C-ABI Rust extensions consumable directly as Python modules, with no IPC overhead).
* **Data Validation & Domain Contracts**: **Pydantic V2** (`pydantic.BaseModel`)
  * Responsible for runtime integrity and validation of audio metadata and for generating JSON Schema contracts for the Gemini tools (`google-genai`).
* **Local Database**: Embedded **SQLite** with **FTS5** (instant text search) and a vector extension (`sqlite-vec`).
* **Interface & Harness**: An **Interactive Harness** with a separate presentation layer (`ConsoleUI`), a system command dispatcher (`CommandRegistry`) and decoupling for a future graphical interface (WebSockets / Desktop).

---

## 3. Architectural Direction

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            MUSICMATCH ARCHITECTURE                           │
├──────────────────────────────────────────────────────────────────────────────┤
│  [ Interface / Harness ]                                                     │
│    ├── ConsoleUI (Presentation, Banners, Decoupled ReAct Observability)      │
│    ├── Command Registry (Slash Commands: /help, /status, /scan, /exit)       │
│    └── Event Loop (Routing Commands vs Natural Language)                     │
│                             │ (Direct Call or WebSockets / REST IPC)         │
│                             ▼                                                │
│  [ Orchestration & AI Layer - Python 3.14.6 ]                                │
│    ├── Google Antigravity SDK (Main Agent and Autonomous Subagents)          │
│    ├── Google GenAI SDK (Gemini 3.6 Flash / 3.1 Pro Multimodal)              │
│    ├── Pydantic V2 (Domain Models, Validation and JSON Schemas)              │
│    ├── Local API Server (FastAPI / WebSockets)                               │
│    │                                                                         │
│    │  import musicmatch_core (PyO3 / Maturin Bridge - Dispatches Tasks)      │
│    ▼                                                                         │
│  [ High-Performance & DSP Layer - Rust ]                                     │
│    ├── Multi-threaded File Scanner (Rayon for 100k+ tracks)                  │
│    ├── Tag & Bitstream Parser (lofty / symphonia)                            │
│    ├── DSP Engine (BPM, LUFS EBU R128, Mini-Waveforms with SIMD)             │
│    ├── Error Handling & Integrity Log (no panics)                            │
│    └── Direct Batch Writes (SQLite + FTS5 + sqlite-vec)                      │
│                                                                              │
│  ◄── Asynchronous Completion / Progress Event to Python ─────────────────────┘
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Language and Naming Guidelines (Standard: EN-INT)

The project uses **International English (EN-INT)** as the single standard for technical and public documentation:

* **Source Code and Naming (EN-INT Required)**:
  * File and folder names
  * Module, package, class, function, variable and service names
  * Comments and docstrings in the source code
  * Git commit messages (Conventional Commits)
* **Technical and Public Documentation (`docs/`, `README.md`, ADRs - EN-INT Required)**:
  * All documents, architecture specifications, ADRs, technical reports and public texts are written in **International English (EN-INT)**.
  * Documents originally written in Portuguese were translated to English (issue #20).
* **Chat Interaction and Conversation**:
  * Conversations, explanations and answers in the chat with the user stay in **Portuguese (Brazil)** (or the user's preferred language for the session).
