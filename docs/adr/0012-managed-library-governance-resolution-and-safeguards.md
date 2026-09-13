# 0012. Managed Library Location Governance, Cross-Platform Resolution, and Write-Access Safeguards

## Context
Following the establishment of the two-stage staging and managed library taxonomy ([ADR 0011](file:///c:/WebApps/musicmatch/docs/adr/0011-web-ingestion-two-stage-staging-and-managed-library-taxonomy.md)), the system requires a definitive architectural contract for resolving, configuring, and guarding the physical location of the **Managed Library Directory**.

Without strict governance, several system risks emerge:
1. **Platform Divergence**: Inconsistent default locations across Windows, Linux, and macOS.
2. **Permission Failures**: Staging promotion operations failing mid-transfer because the destination storage is read-only, non-writable, or unformatted.
3. **Catastrophic Path Selection**: Accidental assignment of operating system critical roots (e.g., `C:\`, `/`, `C:\Windows`, or the project's own source code directory) as the music storage root.
4. **Removable Media Disconnection**: External drives or USB storage being unmounted while the user attempts promotion operations.

---

## Decision

1. **Cross-Platform Canonical Default**:
   - The default location resolves dynamically to the user's personal Music directory across all major platforms using standard library `pathlib.Path.home()`:
     - **Windows**: `%USERPROFILE%\Music\MusicMatch\` (e.g., `C:\Users\<User>\Music\MusicMatch\`)
     - **Linux**: `~/Music/MusicMatch/` (complying with XDG `$XDG_MUSIC_DIR/MusicMatch`)
     - **macOS**: `~/Music/MusicMatch/`
   - This ensures the application behaves predictably and natively regardless of operating system, without writing massive audio collections inside the project source tree.

2. **Resolution Precedence Hierarchy**:
   - The active Managed Library path is resolved via a three-tier precedence hierarchy:
     1. **Environment Override**: `MUSICMATCH_LIBRARY_DIR` defined in `.env` (highest priority; ideal for CI/CD and automation).
     2. **Dynamic Configuration**: Persistent setting recorded in SQLite or `data/config.json` via the CLI command `/library set-path <path>`.
     3. **System Fallback**: Standard cross-platform OS path (`~/Music/MusicMatch/`).

3. **Mandatory Write-Access Probe**:
   - Before any directory is accepted or persisted as the Managed Library, the system executes an **Atomic Write Probe**:
     - Attempts to write a hidden file (`.musicmatch_probe`) and immediately delete it.
     - If the probe encounters `PermissionError`, `OSError`, or read-only flags, the path is rejected on the spot, and the user is alerted to select a writable volume.

4. **Critical Path Guard**:
   - The registration mechanism strictly disallows:
     - Filesystem roots (`C:\`, `/`, `/etc`, `/usr`, `/var`).
     - Operating system and program directories (`C:\Windows`, `C:\Program Files`, `C:\Program Files (x86)`).
     - The active project root directory (preventing audio downloads from polluting source code).

5. **Automatic Namespace Scaffolding**:
   - Upon successful path verification, the system automatically initializes the three canonical top-level taxonomy namespaces ([ADR 0011](file:///c:/WebApps/musicmatch/docs/adr/0011-web-ingestion-two-stage-staging-and-managed-library-taxonomy.md)):
     - `<Library_Root>/Artists/`
     - `<Library_Root>/Various Artists/`
     - `<Library_Root>/Collections/`

6. **Storage Disconnection Guard**:
   - If a promotion command (`/staging promote`) is triggered while the configured library drive is disconnected or unreachable, the system halts with an explicit error:
     `[!] Error: Managed Library at '<path>' is unreachable. Please reconnect the storage volume or set a new path with /library set-path.`
   - Under no circumstances will tracks be silently diverted to an arbitrary temporary directory. Staged files remain 100% safe in the Staging Area.

7. **Path Relocation Policy**:
   - Modifying the library path via `/library set-path` updates the destination for all subsequent track promotions.
   - Pre-existing tracks remain valid and playable at their current registered file paths in the database (consistent with the multi-directory catalog design established in [ADR 0009](file:///c:/WebApps/musicmatch/docs/adr/0009-library-idempotency-stat-cache-and-lifecycle-policy.md)).

---

## Consequences

- **True Portability**: Uniform user experience and filesystem etiquette across Windows, macOS, and Linux.
- **Fail-Fast Safety**: Invalid permissions or unwritable disks are intercepted during setup rather than failing mid-transfer during track promotion.
- **System Protection**: Eliminates any possibility of users accidentally designating critical OS roots as music directories.
- **Decoupled Relocation**: Users can freely redirect future downloads to new storage drives without incurring forced, risky bulk data migrations.
