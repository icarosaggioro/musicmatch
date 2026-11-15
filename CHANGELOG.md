# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.2.0] - 2026-11-15
### Added
- Real audio ingestion: `/scan` reads tags with `mediafile` across MP3, FLAC, M4A, AAC, OGG, WAV, WMA, AIFF and Opus, and reports scan and persistence metrics.
- Idempotent re-scans (ADR 0009): stat-cache on file modification time and size skips unchanged files; track IDs are a deterministic SHA-256 of the canonical path.
- Non-destructive track lifecycle: files that disappear are marked `MISSING` instead of being deleted from the catalog.
- Web ingestion with `yt-dlp` (ADR 0010, ADR 0011): `/download <url|search> [--format mp3]` downloads into a session-based staging area, with SSRF, live-stream and duration safeguards.
- Staging and promotion: `/staging [list | show | promote | discard]` and `/promote <session_id> [--all | --track <id>]` move tracks into the managed library taxonomy (`Artists/<Artist>/<Album>`, `Artists/<Artist>/Singles`, `Various Artists/<Album>`, `Collections/<Name>`).
- Managed library location governance (ADR 0012): cross-platform default under `~/Music/MusicMatch/`, write-access probe, and refusal of system-critical paths.
- `/model [name]` shows or changes the active LLM.
- Library maintenance suite (Front 5, ADR 0013): `/audit [duplicates | prune]`, `/delete` (moves files to the OS Recycle Bin via `send2trash`), `/prune`, `/retag`, `/unindex`, and `/library [status | set-path | import | reorganize | clear]`, with confirmation and count-verification gates for batch operations.
- SDLC framework adopted (`.agents/` rules, guides and skills), with project rules in `.agents/rules/project.md`.
- Quality gates: `scripts/check.py` runs the same checks locally and in GitHub Actions CI on every push and pull request.
- Advisory AI code review on pull requests, scoped by `.github/ocr-rules.json`.
- Test guards that fail when the supported Python version drifts between `project.md`, `pyproject.toml` and CI, when egg-info is tracked, or when the package version disagrees with `pyproject.toml`.

### Changed
- Slash commands refactored into a modular command pattern with a single lookup registry.
- Minimum supported Python is now 3.14.6 (was 3.11 in packaging metadata); CI runs on Python 3.14.
- `musicmatch.__version__` is read from the installed package metadata, so `pyproject.toml` is the single source of the version.
- AI code review reads its model from the `CI_OCR_LLM_MODEL` repository variable.

### Fixed
- `/download` no longer aborts a single-track download with a false "maximum number of downloads reached" error (#4).

### Removed
- `src/musicmatch.egg-info/` build artifacts from version control; `*.egg-info/`, `build/` and `dist/` are ignored.

---

## [0.1.0] - 2026-09-06
### Adicionado
- **Arquitetura Base (Walking Skeleton)**:
  - Sistema de orquestração em Python 3.14 com separação de responsabilidades (Clean Architecture / DDD).
  - Padrão **Command** no Harness interativo desacoplado da interface gráfica (`ConsoleUI`).
  - Despachante de comandos (`CommandRegistry`) com suporte a slash commands: `/help`, `/status`, `/scan`, `/search`, `/list`, `/clear`, `/exit`.
  - Persistência em **SQLite com FTS5** (*Full-Text Search*) e tabela de conteúdo externo sincronizada por gatilhos nativos (`AFTER INSERT`, `AFTER UPDATE`, `AFTER DELETE`).
  - Busca híbrida ranqueada por relevância Okapi BM25 combinada a filtros relacionais (BPM, gênero).
  - Contratos de domínio fortemente tipados com **Pydantic V2** (`Track`, `ScanResult`).
  - Camada de serviços de negócio (`LibraryService`) desacoplando o banco de dados das interfaces.
  - Orquestração de agentes com o **Google Antigravity SDK** e integração com modelos **Gemini 3.6 Flash** via `google-genai`.
  - Suíte de testes automatizados com `pytest` (73 testes unitários e de integração, 98% de cobertura).
- **Documentação Arquitetural**:
  - ADRs 0001 a 0009 documentando todas as decisões fundamentais do sistema.

[Unreleased]: https://github.com/icarosaggioro/musicmatch/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/icarosaggioro/musicmatch/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/icarosaggioro/musicmatch/releases/tag/v0.1.0
