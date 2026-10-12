# 0013. Library Maintenance, Consolidation Imports, and Two-Tier Deletion Safeguards

## Context
While MusicMatch supports in-place library scanning across arbitrary storage paths ([ADR 0009](0009-library-idempotency-stat-cache-and-lifecycle-policy.md)) and web ingestion promotion into the canonical Managed Library Directory ([ADR 0011](0011-web-ingestion-two-stage-staging-and-managed-library-taxonomy.md), [ADR 0012](0012-managed-library-governance-resolution-and-safeguards.md)), users lacked mechanisms for physical collection maintenance: importing existing external music into the managed taxonomy, unindexing records from the database, permanently deleting unwanted audio files from disk, retagging tracks, and resolving acoustic duplicates. Unifying catalog-level removal with physical file deletion without explicit boundaries risks catastrophic, unrecoverable data loss in user collections.

## Decision
1. **Explicit Separation of Unindexing vs. Physical Deletion**:
   - `/unindex`: Purges track metadata and FTS5 search index records from the SQLite database while leaving the physical audio files on disk 100% untouched.
   - `/delete`: Moves physical audio files to the host Operating System Recycle Bin / Trash (via `send2trash`) and cascades record removal from the database. Direct unrecoverable file unlinking (`os.remove`) is strictly prohibited.
2. **Two-Tier Safety Protocol**:
   - **Single Track**: Interactive confirmation displaying track metadata. If the targeted file resides outside the Managed Library Directory in user personal directories, an explicit `External Storage Warning` is highlighted.
   - **Batch Sets**: Operations affecting multiple tracks (e.g., `/delete --missing`, `/delete --query <filter>`) require a `Count-Verification Gate`, demanding that the user type the exact integer count of targeted tracks before file operations commence.
3. **External Library Consolidation (`/library import`)**:
   - External directories can be ingested into the Managed Library via `/library import <path> [--copy | --move]`, formatting files into canonical `Artists/<Artist>/<Album>/` taxonomy.
   - In `--move` mode, the system enforces **Per-Item Pre-Flight Isolation**: individual files are checked for read, write, and source-deletion permissions before transferring. Any locked or restricted file is left untouched at its source path and reported in a summary at completion.
4. **Integrated Library Audit & Quality-First Deduplication (`/audit`)**:
   - `/audit` provides a diagnostic dashboard tracking missing files, untagged tracks, low bitrates (< 128 kbps), and duplicate groups.
   - `/audit duplicates` renders side-by-side comparisons of duplicate recordings, applying an automatic quality heuristic that recommends preserving the highest-fidelity bitstream (lossless/higher bitrate) while offering to unindex or trash degraded copies.
5. **Tag Modification & In-Library Reorganization**:
   - `/retag` updates ID3/Vorbis tags directly inside audio files via `mediafile` and synchronizes SQLite/FTS5.
   - `/library reorganize` re-evaluates file paths within the Managed Library Directory, realigning physical folders to match revised artist and album tags.

## Consequences
- **Zero Accidental Data Destruction**: The distinction between `/unindex` and `/delete`, combined with OS Recycle Bin routing and count-verification gates, prevents catastrophic library deletion accidents.
- **Controlled File Governance**: Users retain freedom to choose between non-destructive in-place scanning (`/scan`) and standardized canonical ingestion (`/library import`).
- **Acoustic Integrity**: Duplicate resolution proactively preserves high-resolution audio files based on objective signal and bitrate metrics.

