# 0021. Test Isolation: Session Sandbox, Side-Effect-Free Imports, and a Filesystem Guard

## Context
While building the diagnostics work ([ADR 0019](0019-diagnostics-developer-log-issue-register-and-thread-safe-reporting.md)) we found that the test suite wrote to real data:
- **`data/musicmatch.db` and `data/staging/` in the project.** Merely *importing* the command registry created them: the process-wide services (`library_maintenance_service`, `library_service`, `acoustic_analysis_service`, `audio_downloader_service`) were built at import time, opening the catalog database and creating the staging folder at the configured (real) paths.
- **`~/Music/MusicMatch`, the default Managed Library in the user's real home folder.**
- **Tests that fell back to the global catalog database**, because they did not inject their own (the REPL tests, an agent tool test, a dispatcher test). They also shared state with each other.

On a developer's machine, those paths hold the real library, catalog and play history. A developer's `.env` (`DATABASE_PATH`, `MUSICMATCH_LIBRARY_DIR`) or a library chosen with `/library set-path` (persisted in a hard-coded `data/library_config.json`) made it worse: tests would have resolved to the real library.

## Decision
1. **Importing never creates files.** The process-wide services open their resources on first use (lazy properties, the pattern `TrackPromotionService` already followed). The downloader resolves its staging folder at construction but creates it only when a session is created. The library-location config path became a setting (`MUSICMATCH_LIBRARY_CONFIG`, default unchanged) so it can be redirected like every other data path.
2. **Every test session runs in a sandbox.** `tests/conftest.py` is loaded before any test module, so before any application code. It creates a temporary folder and points everything at it:
   - `DATABASE_PATH`, `MUSICMATCH_STAGING_DIR`, `MUSICMATCH_LOG_DIR`, `MUSICMATCH_LIBRARY_CONFIG`;
   - `HOME` and `USERPROFILE`, so `~/Music/MusicMatch` resolves inside the sandbox;
   - an empty `MUSICMATCH_LIBRARY_DIR`.

   Because python-dotenv never overrides existing variables, a developer's `.env` can no longer aim the tests at real data. The sandbox is deleted at the end of the session.
3. **A per-test filesystem guard.** An autouse fixture snapshots these locations before each test (about 1 ms) and fails the test at teardown if it created, modified or deleted anything in them, listing the paths:
   - the project tree (tooling output such as `__pycache__`, `.pytest_cache` and coverage files is ignored);
   - the real `~/Music/MusicMatch`;
   - the sandbox's **default** data folder.

   The last one means a test relying on the global catalog or staging area fails too. Tests must inject their dependencies (an in-memory `SQLiteTrackRepository`, `tmp_path`), which also keeps them independent of execution order.
4. **The protection is itself tested** (`tests/test_test_isolation.py`):
   - the guard's snapshot logic;
   - a fresh interpreter importing every `musicmatch` module must create nothing;
   - the session's settings, home, managed library and staging folder must resolve inside the sandbox;
   - an inner pytest session with the real `conftest.py` must fail tests that write into its project or fall back to the default database, and pass the clean one.

## Consequences
- Running the tests can no longer damage or pollute a real library, catalog, play history or home folder, whatever the developer's `.env` says.
- A new test that leaks fails immediately and names the files it touched. A new module-level service that opens resources at import fails the import test.
- Production behaviour is unchanged, except that importing MusicMatch no longer opens the database or creates folders as a side effect: they appear on first use.

### Known limitations
- The guard watches the project tree, the default Managed Library and the sandbox's default data folder, not the whole disk. A test writing to another absolute path would not be caught.
- Process-wide services cache the repository they open first; tests that use them must inject or patch their dependencies, as the guard now enforces.
