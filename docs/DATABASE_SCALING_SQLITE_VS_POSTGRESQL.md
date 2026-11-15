# Engineering Technical Study: SQLite vs PostgreSQL at Large Scale (1,000,000 Tracks)

**Project**: MusicMatch  
**Date**: 2026-09-05  
**Author**: Software Engineering & DSP / AI Architect  
**Status**: Technical Reference & Future Migration Roadmap  

---

## 1. Context and Scenario Assumptions

MusicMatch aims to manage large audio collections with high performance, combining Artificial Intelligence agent orchestration (**Google Antigravity SDK**), audio signal processing / DSP in **Rust**, and expressive natural-language or deterministic queries.

This study formally assesses how sustainable the current persistence engine (**SQLite with FTS5**) is compared with a migration to **PostgreSQL (with `pgvector` and `pg_trgm`)**, under the following boundary conditions:

1. **Catalog Volume**: 1,000,000 indexed music tracks.
2. **Deterministic / Procedural Multi-Criteria Queries**:
   * **BPM**: Range filters, percentage tolerance ($\pm 5\%$) and harmonic relationships ($0.5\times$ *half-time*, $2.0\times$ *double-time*).
   * **Release Year**: Time-proximity windows with Gaussian decay (e.g. the 80s, the 90s, $\pm 3$ years).
   * **Music Genre**: Categorical and hierarchical similarity (e.g. *House* $\approx$ *Tech-House*).
   * **Artist**: Approximate matching and style-similarity graphs.
   * **Title**: Deliberately lower priority in recommendation/vibe searches.
   * **Extended Musical Metrics**: Composition type, meter (time signature 4/4, 3/4), key (*Camelot Wheel* / Key), *Loudness* (LUFS EBU R128).
3. **LLM-Driven Semantic Queries**:
   * Needs a vector component (*embeddings* of audio, mood, lyrics and semantic descriptions).
   * Hybrid queries: combining strict relational constraints (*hard filters*) with ordering by cosine similarity of dense vectors.
4. **Traditional Maintenance Tooling**:
   * Availability, ergonomics and depth of classic administration tools (DBeaver, DataGrip, pgAdmin, visual `EXPLAIN ANALYZE` execution plans).
5. **Maintenance Complexity**:
   * Given moderate weight (technical quality and scalability of the solution outweigh setup complexity).

---

## 2. Sizing and Data Volume for 1,000,000 Tracks

### A. Relational Table and Structured Metadata
* **Typical row**: ID (UUID or short string), Title, Artist, Album, Genre, Year, Duration, Bitrate, BPM, Key, Meter, Composition Type, File Path, Mood, LUFS, Timestamps.
* **Average tuple size**: ~600 bytes.
* **Raw storage (1M records)**: **~600 MB**.
* **Relational B-Tree Indexes**:
  * `(bpm)`, `(year)`, `(genre)`, `(artist)`, `(file_path)`: **~350 MB to 500 MB**.

### B. Text / Trigram Component
* Phonetic and fuzzy search by artist, album and genre (to absorb typos):
  * **GIN indexes with `pg_trgm` or FTS5**: **~500 MB to 800 MB**.

### C. Vector Component (Vibe / Audio / LLM Embeddings)
* **Vector Dimension**: 768 dimensions (standard Gemini text embeddings or audio embeddings such as CLAP/MuLan).
* **Raw Vector Storage**:
  * In `Float32` (4 bytes/dim): $768 \times 4 = 3{,}072\text{ bytes/track} \times 10^6 \approx \mathbf{3.07\text{ GB}}$.
  * In `Halfvec` / Float16 (2 bytes/dim): $768 \times 2 = 1{,}536\text{ bytes/track} \times 10^6 \approx \mathbf{1.54\text{ GB}}$.
* **HNSW (Hierarchical Navigable Small World) Vector Index**:
  * Neighborhood graph overhead: $1.3\times$ to $1.8\times$ the size of the raw vectors: **~2.5 GB to 5.0 GB**.

> **Consolidated Storage Summary**:
> * **Total on Disk (Relational + FTS + HNSW Vectors)**: **~6 GB to 9 GB**.
> * **Recommended Operating Memory (RAM)**: At least **4 GB to 8 GB** dedicated to the database to keep HNSW index pages cached and avoid random reads on SSD/NVMe.

---

## 3. Comparative Analysis of the Engines

```
                    ┌────────────────────────────────────────────────────────┐
                    │                   MUSICMATCH ENGINE                    │
                    │                1,000,000 Music Tracks                  │
                    └──────────────────────────┬─────────────────────────────┘
                                               │
               ┌───────────────────────────────┴───────────────────────────────┐
               ▼                                                               ▼
┌──────────────────────────────┐                              ┌──────────────────────────────┐
│       SQLite 3 + FTS5        │                              │   PostgreSQL 16 + pgvector   │
│   (Embedded / In-Process)    │                              │       (Client / Server)      │
├──────────────────────────────┤                              ├──────────────────────────────┤
│ • Latency: ~10-30 µs         │                              │ • Latency: ~300-800 µs       │
│ • Single file (local .db)    │                              │ • Daemon/Service (Port 5432) │
│ • Single-Core per Query      │                              │ • Parallel Multi-Core        │
│ • Single-Writer Lock (WAL)   │                              │ • Full MVCC (Multi-write)    │
│ • `sqlite-vec` experimental  │                              │ • Industrial `pgvector`      │
│ • Tooling: Basic             │                              │ • Tooling: Enterprise        │
└──────────────────────────────┘                              └──────────────────────────────┘
```

### 3.1. SQLite: Strengths and Critical Bottlenecks

#### Advantages
1. **Zero-IPC Read Latency**:
   * SQLite runs directly in the application's memory space (Python, or Rust via C-ABI FFI). There is no TCP serialization, OS context switch or loopback networking. Single reads take microseconds.
2. **Zero-Dependency Architecture**:
   * The whole catalog lives in a single file (`musicmatch.db`).
   * Simple atomic backup (a direct file copy or the `VACUUM INTO` command).
   * Distribution to the end user without managing Windows background services.
3. **Simple Batch Writes from Rust**:
   * The `rusqlite` crate lets Rust threads open direct transactions with low memory use.

#### Bottlenecks at 1,000,000 Tracks
1. **No Query Parallelism (Single-Core Bottleneck)**:
   * A query computing weighted mathematical similarity formulas (harmonic BPM + year proximity with exponential decay + genre distances) over tens of thousands of candidates runs on **a single CPU thread**. On modern 8- to 16-core CPUs, SQLite leaves 85-95% of the hardware idle, resulting in latencies of 300 ms to 1,200 ms.
2. **Write Concurrency (Single Writer in WAL)**:
   * WAL (*Write-Ahead Logging*) mode allows many simultaneous readers but **only one writer at a time**.
   * If the Rust scanner is running the initial indexing or a background LUFS/BPM update, attempts by the Antigravity agent or the UI to persist preferences or tags will hit lock contention (`SQLITE_BUSY`).
3. **Limits of the Vector Ecosystem (`sqlite-vec`)**:
   * Although `sqlite-vec` is promising, it still lacks mature vector quantization, highly partitioned on-disk HNSW algorithms, and *Iterative Index Scanning* combined with relational filtering for 1M records. Keeping 1M vectors in RAM with SQLite undermines the lightness of the desktop app.

---

### 3.2. PostgreSQL: Strengths and Trade-Offs

#### Advantages
1. **True Query Parallelism (`Parallel Query Execution`)**:
   * The Postgres query planner splits scans and similarity calculations across multiple *parallel worker threads*. Intensive numeric distance calculations and analytic functions over 1M rows run in 30 ms to 80 ms.
2. **Vector Maturity with `pgvector`**:
   * Native support for **HNSW** and **IVFFlat** indexes.
   * Support for **`halfvec`** types (16-bit) and binary quantization, halving RAM use.
   * Support for **Iterative Index Search**: strict filters (`WHERE bpm BETWEEN 120 AND 130 AND year >= 1990`) are evaluated in coordination with the HNSW graph traversal, avoiding the classic problem of exhausted vector nodes.
3. **Full MVCC and Row-Level Locks**:
   * Reads and writes do not block each other. The Rust scanner can ingest tracks continuously while the agent queries metadata and computes recommendations without contention.
4. **Advanced Fuzzy Text Search (`pg_trgm`)**:
   * Matching artists and titles by trigram similarity with GIN indexes, handling typos better than traditional FTS.
5. **Industrial-Grade Traditional Tooling**:
   * DBeaver, DataGrip and pgAdmin provide full graphical views of execution plans (`EXPLAIN (ANALYZE, BUFFERS)`), pinpointing disk I/O versus memory cache usage.
   * Extensions such as `pg_stat_statements` identify bottlenecks in LLM-generated queries in real time.

#### Disadvantages / Trade-Offs
1. **Service / Daemon Requirement**:
   * Requires running a PostgreSQL server process (a Windows service or a Docker container).
   * For a desktop app, this adds packaging complexity, network port allocation (5432) and firewall permissions.
2. **IPC / Loopback TCP Latency**:
   * Adds a minimum latency floor of ~300 µs to 800 µs per request due to the client-server network protocol (negligible for complex queries, but noticeable in loops with thousands of single queries).
3. **Baseline Memory Use**:
   * PostgreSQL with a buffer pool configured for 1M rows persistently allocates 1 GB to 2 GB of RAM.

---

## 4. Direct Comparison Table

| Project Requirement | SQLite (with FTS5 + `sqlite-vec`) | PostgreSQL (with `pgvector` + `pg_trgm`) |
| :--- | :--- | :--- |
| **Relational Scale (1M tracks)** | Handles simple indexed (B-Tree) queries well. | Handles it with room to spare; excellent cost-based optimizer. |
| **Weighted Multi-Criteria Similarity** | Slow on complex calculations (single-core CPU). | **Very fast** with multi-threaded parallelism. |
| **Vector Component (1M embeddings)** | Experimental; high risk of RAM saturation. | **Industrial production** (HNSW + `halfvec` + Iterative Scan). |
| **Ingestion vs AI Agent Concurrency** | Risk of lock contention (`database is locked`). | **Full concurrency** via MVCC and row-level locks. |
| **Fuzzy Matching (Artist/Album)** | Limited to FTS5 prefixes/tokens. | **Excellent** via `pg_trgm` (GIN trigrams). |
| **Single-Read Latency** | **~10 to 30 µs** (in-memory C-ABI). | ~300 to 800 µs (loopback TCP protocol). |
| **Maintenance / Traditional Tooling** | Simple tools (DB Browser, SQLiteStudio). | **Clear leader** (DBeaver, DataGrip, detailed EXPLAIN). |
| **Desktop Installation and Portability** | **Perfect**: a single local file, zero config. | Medium/High: requires a running daemon or Docker. |

---

## 5. Proposed PostgreSQL Model for 1M Tracks

### DDL: Schema with Relational, Fuzzy Text and Vector Support

```sql
-- Enable the required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Main tracks table
CREATE TABLE tracks (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    artist VARCHAR(255) NOT NULL,
    album VARCHAR(255) NOT NULL,
    genre VARCHAR(100) NOT NULL,
    year SMALLINT,
    bpm REAL NOT NULL CHECK(bpm > 0),
    composition_type VARCHAR(50), -- e.g. 'Instrumental', 'Vocal', 'Remix', 'Acoustic'
    meter VARCHAR(10) DEFAULT '4/4', -- e.g. '4/4', '3/4', '6/8'
    musical_key VARCHAR(10),        -- e.g. '8A', '11B' (Camelot Wheel)
    duration_seconds REAL NOT NULL CHECK(duration_seconds >= 0),
    bitrate_kbps INTEGER NOT NULL,
    file_path TEXT UNIQUE NOT NULL,
    mood VARCHAR(100),
    lufs REAL,
    -- Dense 768-dimension vector in half precision (Float16) to save RAM
    embedding halfvec(768),
    created_at TIMESTAMPTZ DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ DEFAULT clock_timestamp()
);

-- B-Tree indexes for numeric and window filters
CREATE INDEX idx_tracks_bpm ON tracks(bpm);
CREATE INDEX idx_tracks_year ON tracks(year);
CREATE INDEX idx_tracks_key ON tracks(musical_key);
CREATE INDEX idx_tracks_comp_type ON tracks(composition_type);

-- Trigram GIN indexes for fuzzy search on Artist and Genre
CREATE INDEX idx_tracks_artist_trgm ON tracks USING gin (artist gin_trgm_ops);
CREATE INDEX idx_tracks_genre_trgm ON tracks USING gin (genre gin_trgm_ops);

-- HNSW vector index (cosine similarity)
CREATE INDEX idx_tracks_embedding_hnsw 
ON tracks USING hnsw (embedding halfvec_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

---

### Example Hybrid Recommendation / Similarity Query

The query below shows how PostgreSQL resolves, in a single pass:
1. **B-Tree Pre-Filtering**: Narrows the sample space to viable tracks.
2. **Harmonic BPM Score**: Rewards the actual tempo or its half-time and double-time variations.
3. **Year Decay**: A Gaussian function for time proximity.
4. **Genre / Artist Similarity**: Fuzzy trigrams.
5. **Semantic Vector Similarity**: Cosine distance generated by the LLM.
6. **Minimal Weight for the Title**: As required, the title does not distort the musical ranking.

```sql
WITH candidates AS (
    SELECT 
        id, title, artist, album, genre, year, bpm, musical_key,
        -- Harmonic BPM similarity
        CASE 
            WHEN abs(bpm - :target_bpm) <= 4 THEN 1.0
            WHEN abs(bpm - (:target_bpm * 0.5)) <= 3 THEN 0.8
            WHEN abs(bpm - (:target_bpm * 2.0)) <= 6 THEN 0.8
            ELSE 0.2
        END AS bpm_score,
        -- Gaussian year decay (tolerance centered on the target year)
        exp(-power(coalesce(year, :target_year) - :target_year, 2) / 20.0) AS year_score,
        -- Genre similarity via trigrams
        similarity(genre, :target_genre) AS genre_score,
        -- LLM-driven vibe/semantic vector similarity
        (1 - (embedding <=> :target_vector::halfvec)) AS semantic_score
    FROM tracks
    WHERE 
        -- Fast filters via traditional indexes
        bpm BETWEEN (:target_bpm * 0.45) AND (:target_bpm * 2.1)
        AND year BETWEEN (:target_year - 15) AND (:target_year + 15)
)
SELECT 
    id, title, artist, album, genre, year, bpm, musical_key,
    -- Final weighted ranking (title ignored in the score)
    (
        0.35 * semantic_score +
        0.25 * bpm_score +
        0.25 * genre_score +
        0.15 * year_score
    ) AS similarity_score
FROM candidates
ORDER BY similarity_score DESC
LIMIT 50;
```

---

## 6. Conclusion and Strategic Recommendation

### Technical Decision: **Migrate to PostgreSQL with `pgvector` in the High-Scale Phase**

1. **Fit for the 1 Million Track Level**:
   * SQLite works perfectly up to 100,000 tracks. However, at **1,000,000 tracks with dense 768-dimension vectors and weighted multi-criteria queries**, SQLite's lack of CPU parallelism and the immaturity of its large-scale vector indexes degrade the user experience.
2. **First-Class Vector Support**:
   * `pgvector` with `halfvec` and HNSW keeps 1M vectors indexed in ~1.5 GB to 2 GB of RAM with sub-40 ms responses.
3. **Concurrency Isolation**:
   * The multi-threaded Rust scanner (`Rayon`) and the AI agent (`Google Antigravity SDK`) can read and write simultaneously without file locks.
4. **Enterprise-Grade Tooling**:
   * Full ease of inspecting and tuning execution plans via DBeaver / DataGrip.

---

## 7. Practical Migration Roadmap

To make the transition smooth and avoid rework when the project reaches the advanced stage:

### Phase 1: Preserve the Current Abstraction Layer (Today)
* MusicMatch already uses the **Repository Pattern** (`SQLiteTrackRepository`) and models validated by **Pydantic V2** (`Track`).
* **Action**: Keep the agent tools (`tools/search.py`, `tools/scanner.py`) and services (`LibraryService`) decoupled from raw SQL.

### Phase 2: Implement `PostgresTrackRepository` (Future Phase)
* Create a `PostgresTrackRepository` class implementing the same public method interface (`insert_track`, `insert_batch`, `search_combined`, `get_stats`).
* In Python, use high-performance asynchronous drivers (`asyncpg` or `psycopg3`).
* In Rust (`musicmatch_core`), use the `tokio-postgres` crate with binary `COPY` operations to ensure ingestion above 30,000 tracks/second.

### Phase 3: Environment and Execution
* Set up a local `docker-compose.yml` manifest with the official `pgvector/pgvector:pg16` image.
* Add a configuration flag to `.env` (`DATABASE_BACKEND=sqlite` or `DATABASE_BACKEND=postgres`), allowing transparent switching between the local SQLite and the PostgreSQL cluster.
