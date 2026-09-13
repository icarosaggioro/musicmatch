# 0011. Web Ingestion Pipeline, Two-Stage Staging Architecture, and Managed Library Taxonomy

## Context
Following the adoption of `yt-dlp` as an external dependency ([ADR 0010](file:///c:/WebApps/musicmatch/docs/adr/0010-yt-dlp-integration-and-packaging-strategy.md)), the system requires a comprehensive architectural specification for **Feature Front 1: Web Ingestion & Secure Download**.

Web-sourced audio ingestion presents distinct systems and domain engineering challenges:
1. **Audio Transcoding Quality**: Blindly re-encoding modern web audio streams (predominantly Opus or AAC) into MP3 320 kbps incurs lossy-to-lossy degradation, introduces psychoacoustic artifacts, and wastes CPU cycles.
2. **Metadata Noise**: Web video titles are notoriously polluted with SEO keywords, marketing tags, video resolutions, and release brackets (e.g., `(Official Music Video) [4K Remastered] ft. Jay-Z`).
3. **Session Clutter & Concurrency**: Direct, unmanaged downloads into the library mix files across disparate download jobs, creating partial states if downloads fail or are abandoned.
4. **Library Fragmentation for Compilations**: A naive `<Artist>/<Album>/` directory structure shatters multi-artist compilation albums (soundtracks, OSTs, festival sets) into dozens of isolated single-track artist folders on disk. Furthermore, user-curated thematic mixtapes need to be kept physically unified in a single directory.
5. **Denial-of-Service (DoS) and Traversal Risks**: Massive playlists, infinite live streams, and untrusted remote filenames threaten system stability.

---

## Decision

1. **Native Bitstream Preservation by Default**:
   - The downloader extracts the highest quality native audio stream without re-encoding (typically `.m4a` with AAC or `.opus`), remuxing the container losslessly.
   - An explicit flag (`--format mp3`) or global environment setting allows optional transcoding to MP3 320 kbps via FFmpeg for legacy portability.

2. **Two-Stage Ingestion Architecture (Staging vs. Managed Library)**:
   - **Stage 1 (Staging Area)**: Incoming downloads land in an isolated, timestamped directory (`data/staging/<session_id>/`) managed by a self-contained `session.json` manifest. Files in this stage are temporary and not mixed across sessions.
   - **Stage 2 (Track Promotion)**: The user inspects the staged session and promotes individual tracks to the Managed Library or discards the session as a whole.
   - **Lifecycle Alerts**: Pending sessions persist across runs. MusicMatch alerts the user on application startup and shutdown whenever unresolved sessions remain in the Staging Area.

3. **Managed Library Directory Taxonomy**:
   - When promoting tracks to the canonical `Managed Library Directory`, the filesystem structure follows a three-namespace taxonomy:
     - **Artist Albums**: `<Managed_Root>/Artists/<Artist>/<Album>/<Artist> - <Title>.<ext>`
     - **Artist Singles**: `<Managed_Root>/Artists/<Artist>/Singles/<Artist> - <Title>.<ext>` (used when album metadata is absent)
     - **Compilation Albums**: `<Managed_Root>/Various Artists/<Album>/<Track_Number> - <Artist> - <Title>.<ext>` (triggered when `albumartist` is `"Various Artists"` or ID3 `TCMP=1` is present)
     - **User Collections**: `<Managed_Root>/Collections/<Collection_Name>/<Artist> - <Title>.<ext>` (triggered via the `--collection "<Name>"` promotion flag, keeping user mixtapes physically united)

4. **Safe Promotion and Collision Invariant**:
   - If a staged track targeted for promotion matches an existing file path or canonical ID in the destination library, the transfer is blocked. The staged file is retained, and the conflict is reported to the user without silent overwriting.

5. **Hybrid Metadata Sanitization and Extended Metadata**:
   - A fast, deterministic regex parser cleans titles, stripping SEO noise (`(Official Video)`, `[4K]`, `(Audio)`, `(Lyrics)`).
   - Removed semantic facets (e.g., `Remastered`, `Live 1985`, `Acoustic`, `Feat. Artist`) are preserved in the domain model as `extended_metadata: Dict[str, Any]` and projected into the `tracks_fts` full-text search index, enabling instant searchability without polluting canonical titles.

6. **Search-to-Download with AI Assist**:
   - The CLI command `/download <query>` directly queries YouTube via `ytsearch5:`, rendering an instant candidate table (Title, Channel, Duration, Views) for single-item numeric selection.
   - Ambiguous, lyrical, or phonetic queries (e.g., `"nanana song with horns"`) can be flagged with `--ai-assist` to route through Google Gemini for canonical artist and title deduction prior to querying YouTube.

7. **Playlist Cap and Atomic Cancellation**:
   - Playlist ingestion requires explicit user intent (`/download --playlist <url>`) and is bounded by a hard cap of 50 tracks per batch with interactive confirmation.
   - Cancellation via `Ctrl+C` or network drops triggers immediate atomic cleanup of partial artifacts (`.part`, `.ytdl`), guaranteeing that the Staging Area contains only 100% complete, playable tracks.

8. **Staging Subcommands**:
   - System administrative commands are exposed through the Command Registry:
     - `/staging`: Lists active sessions and pending track counts.
     - `/staging show <session_id>`: Displays detailed track attributes for a session.
     - `/staging promote <session_id> [track_idx] [--collection <name>]`: Validates tags and moves tracks into the Managed Library.
     - `/staging discard <session_id>`: Deletes the session directory and purges unpromoted audio files.

---

## Consequences

- **Acoustic Integrity**: Preserves original compression bitstreams without lossy-to-lossy generation loss.
- **Physical Cleanliness**: Eliminates disk clutter, prevents accidental mixing of downloads, and solves the multi-artist compilation fragmentation problem.
- **Data Safety**: Non-destructive promotion protects existing library files from silent overwrites.
- **Rich Retrieval**: Extended metadata keeps canonical titles clean while expanding FTS5 full-text search capabilities.
- **Predictable Operational Lifecycle**: Explicit session resolution ensures temporary downloads are never lost or orphaned in the background.

