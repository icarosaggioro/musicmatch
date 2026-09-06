# 0009. Library Idempotency, Track Identity via Full SHA-256 Path Hash, Stat-Cache, and Non-Destructive Lifecycle Policy

## Context
As MusicMatch scales toward indexing large local music libraries (50,000 to 100,000+ tracks), the system must guarantee strict idempotency during file scanning and ingestion. Re-scanning an existing folder must never duplicate tracks, corrupt primary key constraints, or waste massive CPU/disk I/O cycles recalculating expensive audio DSP metrics (BPM, LUFS, Waveform summaries) on unchanged files.

Furthermore, local music collections on modern desktop environments are dynamic:
1. Users frequently store music across multiple disparate directories, partitions, or external storage drives (USB/SSD).
2. Files and folders are frequently moved, renamed, or retagged.
3. External drives may be temporarily detached, causing naive file scanners to execute accidental hard deletions, destroying user playlists, play history, and cached acoustic metadata.

## Decision
1. **Track Identity via Full SHA-256 Canonical Path Hash**:
   - The primary key (`id`) of a `Track` is deterministically generated as:  
     `"trk_" + hashlib.sha256(canonical_path.lower().encode("utf-8")).hexdigest()` (full 64-character hex string).
   - In NTFS/Windows, path resolution strictly canonicalizes relative segments, standardizes separators to forward slashes (`/`), and lowercases the drive and folder paths for hashing, while preserving the user's original casing in `file_path` for UI presentation.
2. **Decoupled Multi-Directory Library Concept**:
   - The **Library** is defined as the aggregate catalog stored in the SQLite database, completely decoupled from any single directory root. Users are free to index tracks from arbitrary folders across any number of drives.
3. **Stat-Cache for Zero-Cost Re-Scans**:
   - Add `file_mtime` (`REAL`) and `file_size` (`INTEGER`) to the `tracks` table and `Track` domain model.
   - During scanning, filesystem metadata (`os.stat`) is evaluated in microseconds:
     - **Unchanged (`mtime` and `file_size` match database)**: File is skipped immediately without opening tags or audio streams ($O(1)$ per file).
     - **Modified (`mtime` or `file_size` changed)**: Re-parse tags and update the database record.
4. **Non-Destructive Lifecycle & Soft-Delete (`AVAILABLE` vs. `MISSING`)**:
   - Under no circumstances will the scanner automatically delete missing records from the database.
   - A `status` column (`'AVAILABLE'` | `'MISSING'`) is maintained on `tracks` with a B-tree index (`idx_tracks_status`).
   - Scoped scans at completion evaluate missing files strictly within their target directory subtree and flag them as `MISSING`.
   - Missing tracks remain visible in `/list` and `/search` with explicit labels (`[ARQUIVO INDISPONÍVEL]`), preserving playlists and historical DSP calculations.
5. **Fast Relocation Heuristic**:
   - When a newly found file matches a currently `MISSING` track by exact `file_size` in bytes, duration, title, and artist, the system migrates the record: updating its `id` and `file_path` and restoring status to `AVAILABLE` without recomputing DSP.
6. **Two-Stage Purge Protocol**:
   - Permanent removal of missing tracks requires an explicit user command (`/prune`) guarded by a strict two-stage confirmation requiring the passphrase:  
     `PLEASEPRETTYPLEASE`.
7. **Opportunistic Auditor Subagent (Library Healer)**:
   - When runtime playback or tooling encounters an unavailable track, an autonomous, low-priority background subagent is spawned to investigate sibling directories, check drive status, and reconcile bulk moves without freezing the UI thread.

## Consequences
- **True Idempotency**: Re-scanning any library folder 1,000 times produces identical database state in seconds.
- **Data Safety**: Disconnecting an external hard drive never causes catastrophic library wipes.
- **High Performance**: Stat-cache avoids hours of redundant DSP/tag re-evaluations.
- **Deterministic Identity**: Absolute immunity to hash collisions and enterprise linter security warnings.
- **Future-Proof**: Sets the exact architectural seam for the future Rust engine and Acoustic Fingerprint (Chromaprint) integration.
