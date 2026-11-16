# Index of Researched Topics and Items

This document is a quick-reference map of every concept, pattern, technology and component investigated while designing the project.

---

## 1. Audio Engineering & the MP3 Standard
* **MPEG-1/2 Audio Layer III (ISO/IEC 11172-3 / 13818-3)**:
  * Psychoacoustic modeling (absolute threshold of hearing, frequency masking, temporal masking: *pre-masking* and *post-masking*).
  * Hybrid filter bank (32 polyphase sub-bands + MDCT with long/short windows for transients and *pre-echo* mitigation).
  * Channel modes (Stereo, Joint Stereo: Mid/Side and Intensity Stereo).
  * Frame structure (11/12-bit syncword, bitrate, sample rate, padding, frame size calculation).
  * *Bit Reservoir* (the `main_data_begin` field and its impact on cutting/seeking).
  * Metadata and tags (ID3v1 in the last 128 bytes, ID3v2.3/v2.4 with flexible frames and APIC images).
  * Bitrate modes (CBR, VBR with Xing/LAME/VBRI headers, ABR).
  * Acoustic artifacts (*pre-echo*, *swishing/birdies*, abrupt frequency cutoffs at low bitrates).

---

## 2. Architecture for Large Audio Libraries (10k to 100k+ Tracks)
* **Disk I/O and Scaling Techniques**:
  * *Selective / range-based parsing* (reading the first KBs for ID3v2 and the last bytes for ID3v1 without loading the whole file).
  * Multiple-format support (MP3, FLAC with `VORBIS_COMMENT`, AAC/M4A with `moov/udta` atoms).
* **Local Database & Indexing**:
  * SQLite with the **FTS5** extension (*Full-Text Search*) for instant text search.
  * Embedded vector search via **`sqlite-vec` / `sqlite-vss`**.
  * List / interface virtualization (*virtual scrolling / windowing*) to render only the items visible in the viewport.
* **Batch Audio Metrics and Processing**:
  * *Audio fingerprinting* for acoustic deduplication (Chromaprint / AcoustID).
  * Loudness normalization (EBU R128 / LUFS / ReplayGain 2.0).
  * Ultra-light *waveform* cache (peak/RMS vectors condensed into a few bytes per track).
  * Harmonic and rhythmic analysis (BPM detection, beat grid, *Camelot Wheel* / musical key).
  * Detection of *fake lossless / upscaled transcodes* (spectral audit of cutoffs at 16 kHz).

---

## 3. Agent Orchestration & AI Frameworks
* **Agent Frameworks Compared**:
  * **LangGraph**: Directed state graphs, persistence/checkpoints (*time travel*), deterministic control and *human-in-the-loop*.
  * **CrewAI**: An approach based on human roles (*Crews, Agents, Tasks, Manager*).
  * **Microsoft AutoGen (v0.4 / Magentic-One)**: A conversational actor model for debates and open-ended tasks.
  * **LlamaIndex Workflows**: Event-driven flows focused on data and RAG.
* **High-Volume Asynchronous Queue Orchestrators**:
  * BullMQ, Inngest, Celery/Arq, and native SQLite queues with worker threads.
* **Selected Framework**: **Google Antigravity SDK**, with a subagent architecture and hybrid cloud/on-device support.

---

## 4. Google AI & Antigravity Ecosystem
* **Google Antigravity SDK (`google-antigravity`)**:
  * Conceptual pillars: `Agent`, `Conversation`, `Connection`.
  * Hybrid configuration:
    * `LocalAgentConfig`: Connects to cloud models (Gemini).
    * `LiteRTAgentConfig`: Runs **100% on-device/locally on GPU (CUDA/DirectX) or NPU** with the **Gemma 4** family (no API key).
    * `LocalOpenAIAgentConfig`: Connects to local servers (Ollama, LM Studio).
  * Delegation to and orchestration of autonomous subagents (`enable_subagents=True`, `SubagentConfig`).
  * Native MCP (*Model Context Protocol*) integration.
  * Periodic triggers, background events, lifecycle hooks and security policies.
* **Google Gemini API (Interactions API / GenAI SDK)**:
  * Reference models: `gemini-3.6-flash`, `gemini-3.1-pro-preview`.
  * **Native multimodal audio input**: The model processes raw audio files (.mp3, .wav) to identify instruments, arrangements, timbres, transcriptions and vocal emotion.
  * Massive context window (1M+ tokens) for cross-analysis of discographies and catalogs.
  * Guaranteed structured outputs (*Structured Outputs / JSON Schema*).
  * **Gemini Live API**: Bidirectional audio streaming over WebSockets for real-time voice assistants and conversational DJs.

---

## 5. Interface & Runtime Technologies (Desktop & Web)
* **Platform Concepts Analyzed**:
  * **Electron**: Embedded Chromium + Node.js (very mature, high RAM use).
  * **Tauri (v2)**: The OS native WebView + a Rust backend (ultra-light, high I/O performance).
  * **WebUI / pywebview**: A minimalist approach where a local backend opens a native web window or the browser.
  * **WASM (WebAssembly)**: Binary code in the browser (`minimp3.wasm`, DSP in *AudioWorklets*, SQLite WASM/OPFS).
* **Status**: *Options mapped; the final choice of graphical interface is still to be made.*

---

## 6. Confirmed Stack and Languages (Python 3.14.6 + Rust)
* **Python 3.14.6**:
  * Agent orchestrator (Google Antigravity SDK).
  * Integration with the Gemini APIs and on-device models (LiteRT).
  * API and WebSocket server (FastAPI).
* **Rust**:
  * Compiled native extension (`musicmatch_core`) for high-speed algorithms.
  * Multi-threaded disk scanning with `Rayon`.
  * Reading and handling metadata and bitstreams (`lofty`, `symphonia`).
  * Numerical DSP engine (BPM, LUFS, waveform peaks with SIMD).
* **Interoperability Bridge**:
  * **`PyO3` + `Maturin`**: Builds native C-ABI binaries (`.pyd`) consumed directly from Python with no IPC overhead.

---

## 7. Grill-Me Results (Rust Adoption & FFI Patterns)
* **Removing the GIL/FFI Bottleneck**: Rust writes indexing results directly to the local SQLite database in batches (*batch insert*). No large arrays of objects cross the Python/Rust bridge.
* **Asynchronous Event Communication**: Rust fires asynchronous events (progress notifications/callbacks) to Python, keeping the main thread and the UI 100% responsive.
* **Resilience and Auditing**: Rust isolates decoding errors and corrupted files without using `panic!`, writing integrity reports for the Antigravity Auditor Agent to process.
* **Build & Distribution**: `Maturin` for simplified development (`maturin develop`) and for producing pre-compiled binaries (.pyd) that are transparent to the end user.

---

## 8. Persistence & Large-Scale Growth (1,000,000+ Tracks)
* **Detailed Comparative Study**:
  * Full document in [`docs/DATABASE_SCALING_SQLITE_VS_POSTGRESQL.md`](DATABASE_SCALING_SQLITE_VS_POSTGRESQL.md).
  * Architecture Decision Record: [ADR 0008 - Database Scaling Strategy and PostgreSQL Migration Roadmap](adr/0008-database-scaling-and-postgresql-migration-roadmap.md).
* **Consolidated Guidelines**:
  * **Current Phase (Development & Medium Scale)**: Keep embedded **SQLite with FTS5** for agility, in-memory unit tests (`:memory:`) and zero-infrastructure distribution.
  * **Advanced Phase / Production at Scale (1M Tracks)**: Planned migration to **PostgreSQL 16+** with the extensions:
    * **`pgvector`**: HNSW indexes with `halfvec` (16-bit float) vectors and *Iterative Index Scan* to combine strict acoustic filters with LLM semantic search without node exhaustion.
    * **`pg_trgm`**: GIN indexes for phonetic and fuzzy search by artist and genre.
    * **CPU Parallelism**: Multi-threaded execution of queries with mathematical similarity formulas (harmonic BPM, Gaussian time decay).
    * **Full Concurrency (MVCC)**: Massive ingestion from Rust (`tokio-postgres` via `COPY`) without locking readers or agents.

---

## 9. Idempotency, Canonical Identity and Library Lifecycle
* **Architecture Decision Record**: [ADR 0009 - Library Idempotency, Track Identity via Full SHA-256 Path Hash, Stat-Cache, and Non-Destructive Lifecycle Policy](adr/0009-library-idempotency-stat-cache-and-lifecycle-policy.md).
* **Domain Guidelines**:
  * **Canonical Identity**: A deterministic primary key (`trk_<sha256_full>`) based on the normalized, lowercase OS path.
  * **Stat-Cache**: Instant validation via `os.stat` (`mtime` + `file_size`) to skip redundant I/O on repeated scans.
  * **Multi-Location Library**: The library is the catalog persisted in SQLite, so music can be spread freely across multiple disks, folders or USB drives.
  * **Soft-Delete and Absolute Safety**: Inaccessible files become `MISSING` without losing acoustic data or playlists.
  * **Two-Step Manual Purge**: Permanent deletion of orphans is restricted to an explicit command with the phrase `PLEASEPRETTYPLEASE`.
  * **Opportunistic Auditor Subagent**: A background AI agent investigates missing files and reconciles files moved or renamed from inside to outside the library without blocking the UI.

---

## 10. Functional Evolution Roadmap and Next Real Features
* **Full Specification Document**: [`docs/ROADMAP.md`](ROADMAP.md).
* **Integration Architecture Decision**: [ADR 0010 - yt-dlp Integration Strategy, Dependency Management and CI/CD Packaging](adr/0010-yt-dlp-integration-and-packaging-strategy.md).
* **Front 1 Architecture Decision**: [ADR 0011 - Web Ingestion Pipeline, Two-Stage Staging Architecture, and Managed Library Taxonomy](adr/0011-web-ingestion-two-stage-staging-and-managed-library-taxonomy.md).
* **Library Governance Decision**: [ADR 0012 - Managed Library Location Governance, Cross-Platform Resolution, and Write-Access Safeguards](adr/0012-managed-library-governance-resolution-and-safeguards.md).
* **Maintenance, Consolidation and Deletion Decision**: [ADR 0013 - Library Maintenance, Consolidation Imports, and Two-Tier Deletion Safeguards](adr/0013-library-maintenance-consolidation-and-deletion-safeguards.md).
* **Mapped Strategic Fronts**:
  1. **Front 1: Web Ingestion and Safe Download with `yt-dlp`**: Asynchronous integration, SSRF/DoS hardening, audio extraction to MP3/FLAC and automatic cataloging.
  2. **Front 2: Acoustic DSP Engine and Real Fingerprinting**: Chromaprint via `pyacoustid`, EBU R128/LUFS loudness measurement, acoustic BPM and the Camelot Wheel.
  3. **Front 3: Integrated Terminal Audio Playback (Player Engine)**: A concurrent local player with transport commands (`/play`, `/pause`, `/resume`, `/stop`) and visual progress.
  4. **Front 4: "Vibe" Curation & Semantic Search with Google Gemini**: Batch mood enrichment and natural-language search.
  5. **Front 5: Library Auditor, Consolidation & Safe Deletion (ADR 0009 & ADR 0013)**: The `/unindex`, `/delete` (with send2trash and double confirmation), `/audit` (dashboard and smart deduplication), `/retag` and `/library import` commands.
  6. **Front 6: Multi-Turn Conversational Session in the REPL**: Continuous stateful conversation via `google-genai` and support for autonomous subagents.
