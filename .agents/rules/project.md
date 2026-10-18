---
trigger: always_on
---

# Project Rules

Project-owned. The SDLC package never overwrites this file.

- Name: MusicMatch
- team-profile: solo
- ships-to-users: no
- Stack and forbidden choices: Python 3.14.6+ (Clean Architecture + DDD), Pydantic V2, SQLite FTS5, mediafile, pyacoustid, send2trash, yt-dlp, google-genai (Gemini 3.6 Flash); future: Rust (PyO3/Maturin). Forbidden: heavy ORMs (Django, SQLAlchemy); keep SQLite queries direct and explicit in storage/sqlite_repo.py. Never call os.remove directly on audio files; always use send2trash via LibraryMaintenanceService.
- Commit scopes: core, scanner, commands, services, storage, harness, ui, ai, downloader, maintenance, ci, docs, sdlc
- Release pattern: tag

## Commands
- install: pip install -e ".[dev]"
- check: python scripts/check.py

## Data contracts and safety
- Domain models: strongly typed Pydantic V2 models in src/musicmatch/domain/ (Track, ScanResult, LibraryAuditReport, DuplicateGroup, ImportResult, ReorganizeResult).
- Safety rules: Direct physical file deletion without OS Recycle Bin (send2trash) is strictly forbidden. Database catalog resets (/clear, /library clear) require interactive confirmation. Batch operations require confirmation gates.

## Docs map
- Requirements: README.md, docs/ROADMAP_PROXIMAS_FUNCIONALIDADES.md
- Glossary: CONTEXT.md
- ADRs: docs/adr/
- Environments and topology: CONTEXT.md
