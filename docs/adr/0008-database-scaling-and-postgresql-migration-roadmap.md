# 0008. Database Scaling Strategy and PostgreSQL Migration Roadmap for 1M+ Tracks

## Context
In ADR 0007, an embedded SQLite database with FTS5 and external content tables was adopted to serve local libraries between 10,000 and 100,000 tracks with zero deployment overhead.

However, as the project plans for large-scale operations involving **1,000,000+ tracks**, combined with:
1. Multi-criteria similarity queries (dynamic Gaussian year decay, harmonic BPM tolerance, categorical genre hierarchy, and composition/tempo metrics).
2. LLM-driven semantic retrieval requiring high-dimensional dense vector embeddings (e.g., 768 dimensions).
3. Heavy background ingestion via Rust scanners while AI agents and the UI query the database concurrently.
4. Need for industry-standard database management and profiling tools (DBeaver, DataGrip, visual execution plan inspection).

A technical investigation was performed comparing the feasibility of maintaining SQLite vs migrating to PostgreSQL with `pgvector` and `pg_trgm` (see detailed study in `docs/DATABASE_SCALING_SQLITE_VS_POSTGRESQL.md`).

## Decision
1. **Maintain SQLite for Current Development & Mid-Scale Testing**:
   - Keep SQLite with FTS5 as the primary persistence engine during the Walking Skeleton, CLI Harness, and initial agent integration phases.
   - Continue adhering to the Repository Pattern (`SQLiteTrackRepository`) and strict domain validation via Pydantic V2 (`Track`), preventing any database-specific SQL leaking into AI tools or service layers.
2. **Designate PostgreSQL + `pgvector` as the Target Engine for the 1M Scale Milestone**:
   - Officially approve PostgreSQL 16+ equipped with `pgvector` and `pg_trgm` as the target engine for the high-scale production phase.
   - Employ `halfvec` (16-bit floats) and HNSW indexing (`vector_cosine_ops`) to manage 1,000,000 dense vectors within ~1.5 to 2 GB of RAM.
   - Leverage PostgreSQL's native multi-threaded parallel query engine to execute complex weighted multi-criteria similarity calculations across CPU cores.
   - Utilize PostgreSQL's full MVCC and row-level locking to allow high-throughput batch ingestion from Rust (`Rayon` + `tokio-postgres` binary `COPY`) without locking readers or AI agent queries.
3. **Phased Migration Readiness**:
   - Introduce a polymorphic repository interface (`TrackRepositoryProtocol`) so that `PostgresTrackRepository` can be introduced alongside `SQLiteTrackRepository`.
   - Maintain engine-agnostic configuration via `.env` (`DATABASE_BACKEND=sqlite` or `DATABASE_BACKEND=postgres`).

## Consequences
- **Short-Term**: Zero friction during current active development; the project retains zero-install local SQLite convenience.
- **Future Preparation**: Clear architectural blueprint and DDL ready for deployment when 1M track benchmarking begins.
- **Infrastructure Requirement**: Future deployment at scale will require a local PostgreSQL instance (Windows Service or Docker container).
- **Comprehensive Reference**: Full volumetric analysis, DDL, and sample hybrid queries preserved in `docs/DATABASE_SCALING_SQLITE_VS_POSTGRESQL.md`.
