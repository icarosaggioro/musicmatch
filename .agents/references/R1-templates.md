# R1. Templates

Copy these into a repository and edit. Each template is short on purpose.

---

## 1. Pull Request Template

Save as `.github/pull_request_template.md`.

```markdown
## Summary
<!-- What changed and why, in two or three sentences. -->

## Issue
Closes #

## How it was tested
<!-- Exact commands and results, or the manual steps taken. -->

## Risk and rollback
<!-- What could go wrong? How do we undo it? -->

## Screenshots
<!-- For UI changes. Delete if not applicable. -->

## Definition of Done
- [ ] CI is green on the final commit
- [ ] The behavior is covered by a test (regression test for a bug fix)
- [ ] AI review findings are triaged (fixed, or dismissed with a reason)
- [ ] Docs and changelog updated, or not needed: ______
- [ ] Rollback noted for data or deploy changes, or not applicable
```

The team profile adds the remaining items from guide 05.

---

## 2. Issue Templates

**Bug** (`.github/ISSUE_TEMPLATE/bug.md`)

```markdown
## What happened

## What I expected

## Steps to reproduce
1.
2.

## Environment and version

## Logs or screenshots

## Severity
<!-- Sev 1 / 2 / 3 / 4, see the operations guide -->
```

**Feature** (`.github/ISSUE_TEMPLATE/feature.md`)

```markdown
## Problem
<!-- Who needs this and why? -->

## Proposed behavior

## Acceptance criteria
- [ ] <observable, testable statement>

## Out of scope

## Notes and links
```

**Chore** (`.github/ISSUE_TEMPLATE/chore.md`)

```markdown
## What and why

## Acceptance criteria
- [ ]
```

---

## 3. ADR Template

Save as `docs/adr/NNNN-kebab-case-title.md`.

```markdown
# NNNN. Title in Plain Words

Status: Proposed | Accepted | Deprecated | Superseded by NNNN | Rejected
Date: YYYY-MM-DD

## Context
What forces made a decision necessary? Constraints, requirements, history.

## Decision
What we will do, stated specifically and testably.

## Consequences
What becomes easier. What becomes harder. New risks and costs.

## Alternatives considered
- Option A: why not.
- Option B: why not.
```

---

## 4. README Skeleton

```markdown
# Project Name

Two sentences: what it is and who it is for.

## Status and limitations
What works, what does not, what is unproven.

## Quick start
Prerequisites, install, configure, run, test. Copy-pasteable commands.

## Project layout
One line per top-level directory.

## Configuration
Every environment variable, with a pointer to `.env.example`.

## Contributing
Link to branching, commit, and review guides.

## License
```

---

## 5. Changelog Entry (Keep a Changelog)

```markdown
## [Unreleased]
### Added
### Changed
### Fixed
### Security

## [1.2.0] - 2026-10-12
### Added
- Short, user-facing description (#123).
```

---

## 6. Runbook Skeleton

Save as `docs/runbooks/<service>.md`.

```markdown
# Runbook: <service>

## What it does

## Owners
Primary: ______   Backup: ______

## Start, stop, restart
Commands.

## Health check
URL and expected output.

## Logs
Where, and how to search them.

## Common failures
| Symptom | Likely cause | Action |

## Rollback
Steps and the location of the pre-deploy snapshot.

## Escalation
Who to call and when.
```

---

## 7. Post-Incident Review

```markdown
# Incident: <short title>   Sev: __   Date: YYYY-MM-DD

## Summary

## Impact
Who and what was affected, for how long.

## Timeline (UTC)
- hh:mm detection
- hh:mm declaration
- hh:mm mitigation
- hh:mm resolution

## Root cause

## What went well

## What did not

## Action items
| Action | Owner | Due | Issue |
```

---

## 8. Self-Review Checklist (solo developers, high-risk changes)

Optional on ordinary PRs in the solo profile.

```markdown
- [ ] I waited and re-read the diff in the PR view, not the editor.
- [ ] I ran lint, types, tests, and build.
- [ ] I tested the failure paths, not only the happy path.
- [ ] I checked for secrets, personal data, and local files.
- [ ] I described the risk and rollback.
- [ ] For destructive migrations or data deletions: 24 hours passed since I opened the PR.
- [ ] I triaged every AI review finding.
```

---

## 9. Agent Rules File Skeleton

In repos that use the SDLC package, general rules live in `.agents/rules/instructions.md` and only project-specific rules go in `.agents/rules/project.md`. Use this skeleton for repos outside the package. Save as `AGENTS.md`.

````markdown
# Agent Rules

## Project
One line and the stack. List what is forbidden.

## Language
- Chat with people: <language>.
- Files, comments, branches, commits, PRs: English.

## Git
- Never commit to `main` or the release branch.
- Branch: `<type>/<issue-number>-<kebab-description>`.
- Commits: Conventional Commits, scopes: <list>.
- Open a PR linked to the issue; do not merge it.
- Add a `Co-Authored-By` trailer for commits you materially wrote.

## Commands
```text
install: <command>
check:   <command>   # lint, types, tests, build
```

## Safety
- No destructive data operations without explicit human approval naming the target.
- No production deploys or secret changes without explicit approval for that action.
- Do not send secrets or customer data to external services.
- Validate data against <schema path>.

## Docs map
- Requirements: <path>
- Glossary: <path>
- SDLC compendium: <path>
- ADRs: `docs/adr/`
````

---

## 10. AI Code Review Workflow (reference)

Modeled on LivroJogo's `ci-livrojogo-codereview.yml`. Adjust names and the model; keep the structure.

```yaml
name: ci-codereview

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

concurrency:
  group: ci-codereview-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  review:
    name: AI Code Review
    # Skip drafts and bots.
    if: >-
      github.event.pull_request.draft == false &&
      github.event.pull_request.user.type != 'Bot' &&
      github.actor != 'dependabot[bot]' &&
      !endsWith(github.actor, '[bot]')
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      issues: write
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: alibaba/open-code-review@v1.12.13   # pin an exact version
        continue-on-error: true                    # advisory while calibrating
        with:
          llm_url: 'https://openrouter.ai/api/v1'
          llm_auth_token: ${{ secrets.CI_OPENROUTER_API_KEY }}
          llm_model: ${{ vars.OCR_LLM_MODEL }}     # pin the model; avoid a free-tier fallback
          llm_protocol: 'openai'
          language: 'English'
          sticky_summary: 'true'
          incremental: 'true'
          checkpoint_range: 'true'
          rule: '.github/ocr-rules.json'
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

Differences from the reference: `OCR_LLM_MODEL` has no `openrouter/free` fallback, so a missing variable is visible instead of silently changing review quality. Verify the input names against the action's documentation for the version you pin.

Rules file skeleton (`.github/ocr-rules.json`):

```json
{
  "rules": [
    { "path": "backend/**/*.py", "rule": "Review for security, input validation, N+1 queries.", "merge_system_rule": true },
    { "path": "frontend/src/**/*.{ts,tsx}", "rule": "Review for strict typing, no any, hook dependencies.", "merge_system_rule": true },
    { "path": "**/{package-lock.json,poetry.lock,pnpm-lock.yaml,pubspec.lock}", "rule": "Skip lockfiles." },
    { "path": "**/*.{png,jpg,jpeg,gif,webp,ico,svg,sqlite3,woff,woff2,ttf}", "rule": "Skip binary and data files." }
  ]
}
```

---

## 11. Dependabot (reference)

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/backend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
  - package-ecosystem: "npm"
    directory: "/frontend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```
