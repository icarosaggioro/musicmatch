# 02. Commits and Pull Requests

## Commit Messages

**MUST** follow Conventional Commits:

```text
<type>(<scope>): <subject>

<optional body, bullet points>

<optional footer: Closes #123, BREAKING CHANGE: ..., Co-Authored-By: ...>
```

- **Types:** `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `ci`, `chore`, `revert`.
- **Scope:** the affected module, from a list defined in the repo (for example `backend`, `frontend`, `mobile`, `auth`). The list lives in the agent rules file or `CONTRIBUTING.md`, in one place.
- **Subject:** imperative, lowercase, no trailing period, 72 characters or fewer. It says what the change does, not what you did.
- **Body:** explain *why* when it is not obvious. Use bullets for multi-part changes.
- **Breaking change:** `!` after the type or scope plus a `BREAKING CHANGE:` footer.
- **Language:** English.

Good: `fix(backend): isolate redis broker and celery nodenames across environments`

Not acceptable: `Archaitectures definitions to expand library services` (no type, unclear scope, typo).

## Pull Requests

1. **MUST** link the issue (`Closes #N`) or state why none exists.
2. **MUST** use the PR template (R1) with: summary, why, how it was tested, risk and rollback, and screenshots when the UI changes.
3. **MUST** have a title that is a valid commit subject. With squash merge, the title becomes the commit.
4. **SHOULD** stay small: aim for under 400 changed lines, excluding generated files and lockfiles. A large change is split, or the PR explains why it cannot be.
5. **SHOULD** open as **draft** while work is in progress. Draft PRs do not trigger paid AI review (guide 07).
6. **MUST** pass every required check and have the required approval before merge.
7. **Merge method:** squash merge by default, so `main` reads as one commit per change. Use a merge commit only when the individual commits are meaningful and clean.

## Minimum Form

- A commit-msg convention in the agent rules file.
- A PR template file in the repo.
- Required checks on `main`.

## Scale-up

- Add a commit-message lint in CI or a local hook once the convention starts to drift.
- Generate release notes from commit types (guide 11).

## AI Note

- Add a `Co-Authored-By` trailer for commits materially written by an AI agent, so history shows where AI took part.
- The agent's PR description must state what was tested. "Tests pass" is not enough; list the commands or the manual checks.
- Never accept an agent-written PR description without reading the diff it describes.

## Checklist

- [ ] Subject matches `<type>(<scope>): <subject>`.
- [ ] Issue linked.
- [ ] Tests and risk described.
- [ ] Diff small enough to review in one sitting.
