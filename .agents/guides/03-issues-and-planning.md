# 03. Issues and Planning

## Rules

1. **MUST** open an issue before writing code for any non-trivial feature, fix, or refactor. Trivial exceptions: typo fixes, comment edits, and dependency bumps from a bot.
2. **MUST** write acceptance criteria: observable statements that tell you when the issue is done. "Improve performance" is not a criterion; "p95 under 300 ms on the list endpoint with 10k rows" is.
3. **MUST** use issue templates for `bug`, `feature`, and `chore` (R1). Optional in the solo profile.
4. **SHOULD** keep an issue small enough to finish in a few days. Larger work becomes an epic with child issues.
5. **SHOULD** use few labels: type (`bug`, `feature`, `chore`, `docs`), priority (`p0`–`p2`), and status only if the tracker lacks one.
6. **SHOULD** review the backlog monthly (quarterly in the solo profile): close stale issues with a one-line reason, re-rank the rest.
7. **MUST** record a decision in the issue or an ADR when the discussion settles a design question, so the reason survives the thread.

## Minimum Form

- Issue templates.
- A rule that PRs link their issue.
- One person who triages new issues weekly.

## Bug Reports

A bug issue contains: what happened, what was expected, steps to reproduce, environment and version, logs or screenshots, severity. Without a reproduction, the first task is to make one.

## Scale-up

- Add milestones when you ship on a cadence.
- Add a short written roadmap (one page) when more than one person plans work.
- Add SLAs for bug triage by severity once you have users.

## AI Note

- An agent receiving an issue should get the acceptance criteria and links to relevant docs. Vague issues produce vague code; tightening the issue is cheaper than reviewing a wrong PR.
- Let agents draft issues from logs or user feedback, but a human confirms scope and priority.
- Do not paste secrets, customer data, or production logs with personal data into an issue that an external model will read.

## Checklist

- [ ] Issue states the problem, not the solution only.
- [ ] Acceptance criteria are testable.
- [ ] Priority set.
- [ ] Linked from the PR.
