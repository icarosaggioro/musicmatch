# 0010. yt-dlp Integration Strategy, Dependency Management and CI/CD Packaging

## Context
To implement **Roadmap Front 1** (web ingestion and media download from platforms such as YouTube, SoundCloud and Bandcamp), MusicMatch needs the **`yt-dlp`** engine.

An in-depth architecture, security and software engineering analysis was carried out ([`docs/YT-DLP_TECHNICAL_AND_SECURITY_REPORT.md`](../YT-DLP_TECHNICAL_AND_SECURITY_REPORT.md)), along with an empirical investigation of how the largest open-source media projects on GitHub structure this integration (references: **spotDL**, **MeTube** and **yt-dlg**).

The following critical factors were assessed:
1. **Accelerated *Bitrot***: Video platforms change signature algorithms (`n-sig`), JavaScript challenges and attestation tokens (WebPO / Botguard) every week. Freezing `yt-dlp` code inside the repository leads to constant obsolescence and functional breakage.
2. **Impact on the Repository and Tooling**: `yt-dlp` has more than 1,700 specialized extractors and more than 50 MB of code. Copying that code into the [`src/`](../../src) folder pollutes Git history, degrades linters (`ruff`, `flake8`), contaminates test coverage reports (`pytest-cov`) and breaks static checks in CI/CD.
3. **Continuous Integration (GitHub Actions) and Production Builds**: We investigated how desktop executables (.exe) and production packages are built. Packagers such as **PyInstaller**, **Nuitka** and **Docker** images inspect the virtual environment (`site-packages`) and embed the installed `yt-dlp` transparently in the final binary, without requiring its source code to live in the project folder.
4. **Local Clone Availability**: The developer already keeps an active copy of the repository at `<yt-dlp-clone>`.

---

## Decision

1. **Strict Source Code Isolation (Zero Vendoring in `src/`)**:
   - The `yt-dlp` source code will **not** be copied into [`src/`](../../src) nor kept as a loose folder in the MusicMatch repository.
   - The MusicMatch Git repository stays 100% original work, lightweight and focused on the music, DSP and agent domain.

2. **Official Declarative Dependency in `pyproject.toml`**:
   - Adopt `yt-dlp` as a declared dependency in [`pyproject.toml`](../../pyproject.toml) (`yt-dlp>=2025.01.01`).
   - This guarantees native compatibility with virtual environments, Docker containers and clean GitHub Actions runners.

3. **Local Development Environment with an Editable Install (`-e`)**:
   - For the local development cycle, the MusicMatch virtual environment (`.ve`) is linked directly to the existing local repository at `<yt-dlp-clone>`:
     ```powershell
     .ve\Scripts\pip install -e <yt-dlp-clone>
     ```
   - This avoids duplicated disk space and allows debugging with breakpoints and continuous updates via `git pull` inside the `<yt-dlp-clone>` folder.

4. **Adaptation and Architectural Safety Layer (Adapter Pattern)**:
   - The application will not use `yt-dlp` directly from interface commands or agents.
   - All access goes through the [`AudioDownloaderService`](../../src/musicmatch/services/downloader.py) service, which applies the documented safety locks:
     - Blocks the local protocol (`enable_file_urls: False`).
     - Prevents DoS with a duration limit (`match_filter` against 24/7 live streams).
     - Mitigates SSRF (validation and sanitization of external URLs).
     - Prevents path traversal via `prepare_filename` and canonical IDs.
     - Runs asynchronously, decoupled from the REPL main thread.

5. **CI/CD and Packaging Strategy**:
   - **GitHub Actions (CI)**: Runners set up Python, install dependencies via `pip install -e .` (with package caching enabled) and run tests with the download layer mocked.
   - **Production / Desktop Executable**: When building the final executable with PyInstaller (`pyinstaller -F`), the packager collects the `yt-dlp` binaries and modules from the virtualenv, delivering a single self-contained `.exe` to the end user.

6. **Physical Location of Downloaded Files**:
   - Downloaded audio lives in the dedicated `data/downloads/` folder (already ignored in `.gitignore`) or in a path configured via `.env` (`MUSICMATCH_DOWNLOAD_DIR`).
   - When a download finishes, the file is automatically cataloged by the `AudioScanner` in the SQLite database (`tracks` and `tracks_fts`).

---

## Consequences

- **Maximum Maintainability**: Corrective YouTube updates are picked up via `pip install -U yt-dlp` or `git pull` in `<yt-dlp-clone>`, without touching MusicMatch code.
- **Lean Repository**: No Git bloat, and very fast clone and commit times.
- **Assured Code Quality**: Linters, formatters and test coverage keep analyzing strictly the MusicMatch modules.
- **CI/CD Compliance**: The GitHub pipeline runs deterministically and reproducibly on any machine, without coupling to fixed local paths.
