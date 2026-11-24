# 0020. Issue Auto-Resolution and Remedies (Auto-Fix)

**Status: Proposed, not implemented.** It records the basics of the idea, to be refined before implementation.

## Context
[ADR 0019](0019-diagnostics-developer-log-issue-register-and-thread-safe-reporting.md) introduced the Issue register: problems are recorded, de-duplicated, dismissed or deleted by the user. Two natural next steps were identified and deliberately postponed:
1. **Auto-resolution.** An issue should close by itself when its condition is observed to be gone. Otherwise the list rots: a reconnected drive, a replaced file or a refilled playlist leaves stale open issues.
2. **Remedies (auto-fix).** Most kinds of issue have a known fix, often an existing command. The register could offer it, and run it on request.

These are different things: **resolution observes, a remedy acts.** Auto-resolution changes only the register; a remedy changes the library or the files.

## Proposed decision

### 1. Auto-resolution
- **A new status `RESOLVED`**, with `resolved_at` and a short `resolution` text ("arquivo encontrado no /scan de 2026-11-20"). The `issues` table needs only new nullable columns: ADR 0019 left `status` without a CHECK for this.
- **Only observation closes an issue.** A component that can see the condition is gone reports it, e.g. `resolve_issue(kind, subject_key, resolution)`, through the same thread-safe reporter (single writer). Nothing is resolved by guessing or by time.

| Kind | Observed resolution |
| :--- | :--- |
| `TRACK_FILE_MISSING` | The track plays, or a scan finds the file available (including Fast Relocation). |
| `FILE_EMPTY`, `TAGS_UNREADABLE`, `FILE_UNREADABLE`, `AUDIO_EMPTY` | A scan of the folder indexes the file fine, or the file no longer exists. |
| `NAME_NOT_PORTABLE`, `PATH_TOO_LONG` | A scan of the folder no longer finds the path (renamed or moved). |
| `AUDIO_UNDECODABLE` | The track plays or is analysed successfully. |
| `PLAYLIST_EMPTY` | The playlist has tracks again, or was deleted. |
| `PLAYLIST_IMPORT_INCOMPLETE` | A re-import of the same file resolves every entry. |
| `AUDIO_DEVICE_UNAVAILABLE`, `PLAYBACK_STATE_NOT_SAVED` | Playback starts / the state is saved successfully. |
| `TRASH_FAILED`, `TAGS_NOT_WRITTEN` | The track is deleted / tags are written (`/retag`) successfully. |

- **Scoped negative evidence.** A scan resolves file issues **only inside the scanned folder**. "Not seen" elsewhere proves nothing.
- **A resolved issue that recurs reopens** (unlike a dismissed one, which stays silent): the problem came back.
- **Retention:** resolved issues are purged at startup after 30 days.
- **UI:** the startup line and the per-command summary may mention resolutions ("2 problemas resolvidos"). `/issue --resolved` lists them.

### 2. Remedies (auto-fix)
- **A remedy catalog** maps each `IssueKind` to zero or more remedies. Each remedy has a label, the **command it runs**, whether it is destructive, and whether it applies to a batch:
  - `TRACK_FILE_MISSING` → `/scan <folder>` (re-check), `/unindex <id>`.
  - `FILE_EMPTY` / `TAGS_UNREADABLE` → move the file to the Recycle Bin (destructive), or dismiss.
  - `PLAYLIST_EMPTY` → `/playlist-delete <name>`.
  - `NAME_NOT_PORTABLE` → rename to a sanitized name, then rescan (destructive for external tools that reference the old name).
  - `TAGS_NOT_WRITTEN` → retry the tag write.
- **Remedies run through the existing commands**, via the command registry, never through private shortcuts. Every safeguard applies unchanged: ADR 0013 confirmations and count-verification gates, Recycle Bin only.
- **Proposed commands:**
  - `/issue-fix <id> [remedy]` shows the remedies of an issue and runs the chosen one, after confirmation for destructive remedies.
  - `/issue-fix --kind <KIND>` applies one remedy to every open issue of a kind, behind a count-verification gate.
  - `--dry-run` previews what would be run.
- **A remedy's outcome is observed, not assumed.** The issue is resolved only when the command's own observation reports it (section 1), which closes the loop without special cases.
- **The suggestion text already stored** in `details["sugestão"]` (ADR 0019) is the seed of this catalog, and the first step: showing the exact command.

### 3. Future ideas to evaluate
- Grouping views (by folder, by kind), and issues as input for the AI agent (a tool that explains and proposes remedies).
- Correlating issues with usage data collection, once that feature exists.

## Consequences (expected)
- The register stays truthful without manual cleaning, and common problems become one command away from a fix, with no new path around the existing safeguards.
- Each issue source must also report resolutions. That is the main implementation cost, and the reason to do it per source, incrementally.
