# R2. Anti-Patterns

Patterns seen in the reference projects, or common in small teams, that the compendium rules are designed to prevent. Each entry says what to do instead.

| # | Anti-pattern | Seen in | Why it hurts | Do instead (guide) |
|---|---|---|---|---|
| 1 | **Security gate that silently passes.** The scan prints "token not configured, skipping" and exits 0. | LivroJogo backend and frontend CI | A missing secret turns the gate off with no signal. | Fail closed or make the skip loud (07, 08) |
| 2 | **Runtime version drift.** CI on 3.13, production venv on 3.14. README says 3.14+, `pyproject.toml` says `>=3.11`. | LivroJogo, MusicMatch | Bugs that appear only in production. | Define the version in one place (07, 10) |
| 3 | **Stale numbers in docs.** Test counts that differ between README, CHANGELOG, and code. ADR count that disagrees with the folder. | MusicMatch | Readers stop trusting the docs. | Generate numbers or omit them (06, 09, 10) |
| 4 | **Badges with no gate.** A "tests passing, 98% coverage" badge with no CI behind it. | MusicMatch | A claim, not evidence. | Badge only from a tool (06, 10) |
| 5 | **A stray spelling of the product name.** The internal name (LivroJogo) and the commercial name (Lore Vault) are legitimate; "LoreVault" is accidental. | LivroJogo | Confuses search and agents. | One name per audience, one documented mapping (10) |
| 6 | **Policy "from now on" with no legacy plan.** New language rule, old documents left unmarked. | MusicMatch | Mixed corpus; no one knows what applies. | State migrate, freeze, or delete (00, 10) |
| 7 | **Operational data in the policy doc.** LAN IPs, hosts, and ports in the SDLC spec. | LivroJogo | Policy goes stale when infrastructure changes. | Move topology to an ops document (10) |
| 8 | **Documentation sprawl without supersession marks.** About 45 overlapping files in `docs/`. | Benchmarks | Readers cannot tell which file is authoritative. | Hub plus `Status:` header on each file (10) |
| 9 | **No CI for a suite everyone relies on.** Hundreds of tests, nothing runs them automatically. | MusicMatch, Benchmarks | Regressions reach `main` silently. | Required CI on every PR (06, 07) |
| 10 | **No independent review.** One author, no PR trail. | Benchmarks, partly MusicMatch | Nobody else catches mistakes. | Self-review checklist, outside reviewer for high risk (04, 16) |
| 11 | **Convention not enforced.** Commit messages that skip the format. | MusicMatch | History is inconsistent; changelogs cannot be generated. | PR title as commit, optional lint (02) |
| 12 | **Silent free-tier fallback for AI review.** The model defaults to `openrouter/free` when the variable is missing. | LivroJogo | Review quality changes without notice. | Pin the model; missing variable is visible (07, 15) |
| 13 | **Qualitative "good results" for AI review.** No data on accepted versus dismissed findings. | LivroJogo | Cannot tell noisy rules from useful ones. | Spot-check and tighten rules; no metrics program (15) |
| 14 | **Public endpoint check that only warns.** | LivroJogo CD | A broken proxy can pass a deploy. | Block on public failure if you can (12) |
| 15 | **Agent output accepted on its word.** "Tests pass" with no output. | General | False confidence. | Require commands and results (05, 15) |
| 16 | **Agent weakens tests to get green.** | General | Real bugs ship. | Review the test diff (06, 15) |
| 17 | **Hotfix that skips CI.** | General | A second incident. | Keep gates, shorten the change instead (S06) |
| 18 | **Backups never restored.** | General | Data loss on the day you need them. | Quarterly restore test (13) |
| 19 | **Automatic hard delete.** | General | User data loss when a drive is offline. | Soft delete, explicit confirmation (13) |
| 20 | **Moving refs for tools.** `@latest`, branch references for actions. | General | Surprise breakage and supply-chain risk. | Pin versions (07) |

## How to Use This List

- In reviews, use it as a quick scan.
- When a new anti-pattern appears twice, add it here and add a rule or a CI check to the guide that prevents it.
- Entries tagged "General" come from common practice, not from the reference projects.
