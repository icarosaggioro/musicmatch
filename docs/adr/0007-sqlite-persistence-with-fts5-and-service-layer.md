# 0007. SQLite Persistence with FTS5 and Domain Service Layer

## Context
During the Walking Skeleton phase (ADR 0001), `MockDatabase` served as a lightweight in-memory storage stub. However, scaling to large local libraries (10,000 to 100,000+ tracks) requires ACID disk persistence, transactional batch inserts, and instant search capabilities. 

Traditional relational searches using `LIKE '%term%'` force full table scans ($O(N)$), causing severe disk I/O penalties and offering zero relevance ranking. Conversely, pure FTS5 tables lack constraints (`PRIMARY KEY`, `UNIQUE file_path`) and cannot efficiently filter by numeric acoustic attributes (e.g., `bpm BETWEEN 120 AND 130` or `duration_seconds`).

Additionally, presenting business operations directly in CLI commands or LLM tools creates tight coupling with storage mechanisms.

## Decision
1. **Embedded SQLite with FTS5 External Content Tables**:
   - Establish `tracks` as the master relational table holding primary keys, unique constraints, and numeric acoustic metrics.
   - Establish `tracks_fts` as an FTS5 virtual table configured with `content='tracks'`, `content_rowid='rowid'`, and `tokenize='unicode61'`.
2. **Automatic Trigger-Based Synchronization**:
   - Implement three SQLite triggers (`AFTER INSERT`, `AFTER DELETE`, `AFTER UPDATE` on `tracks`) that synchronize the inverted index automatically without application overhead.
3. **BM25 Relevance Ranking & Hybrid Search**:
   - Leverage SQLite FTS5's built-in Okapi BM25 ranking (`ORDER BY fts.rank`) joined with relational `WHERE` clauses for hybrid queries (e.g., text query + genre filter + BPM range).
4. **Domain Service Layer (`LibraryService`)**:
   - Introduce `LibraryService` as the unified application case-of-use layer orchestrating track addition, batch scanning, updates, deletions, and hybrid searches.
   - Decouple AI tools (`scan_library`, `search_tracks`) and Harness commands (`/scan`, `/search`) from raw SQL.
5. **In-Memory SQLite for Testing**:
   - Enable `:memory:` databases for unit testing, maintaining zero-disk isolation and execution times under 2 seconds for the full test suite.

## Consequences
- Instant full-text searches with prefix and boolean support in microseconds.
- Zero risk of index desynchronization due to native database triggers.
- Clean architectural seam separating presentation, business logic, and database operations.
- Clean path for future Rust integration (`PyO3`), where Rust can write batch transactions directly into `tracks` and let triggers maintain FTS5.
