---
trigger: always_on
---

# SDLC Rules

Package-owned: identical in every repo and replaced on package updates. Put project-specific rules in `.agents/rules/project.md` (read it too). Guides: `.agents/guides/`. Version: `.agents/SDLC_VERSION`.

## Language
- Chat: the language the user writes in.
- Everything stored in the repo (files, code, comments, branches, commits, PRs, issues): English.

## Git
- Never commit or push to `main` or a release branch. Never force-push.
- One branch per task: `<type>/<issue-number>-<kebab-description>`. Types: feat, fix, refactor, perf, test, docs, ci, chore.
- Commits: `<type>(<scope>): <subject>`. Imperative, lowercase, 72 characters max. Scopes are listed in `project.md`.
- Add a `Co-Authored-By` trailer to commits you materially wrote.
- Open a PR that links its issue (`Closes #N`) and fills the PR template. Do not merge it.

## Working rules
- Every non-trivial change traces to an issue with testable acceptance criteria. Ask if they are missing.
- Run the check command from `project.md` before pushing. Report real results; never claim tests passed without running them.
- A bug fix includes a regression test that failed before the fix.
- Never delete, skip, or weaken a test to get CI green.
- Keep diffs small and focused. No unrelated refactors.
- New dependency: state why, and verify the package exists and is the intended one.
- Update docs and the changelog when behavior changes.
- Never put secrets, tokens, or personal data in code, logs, or prompts.

## Ask a human first, naming the exact action
- Production deploys, tags, releases, secret changes, CI gate changes.
- Destructive data operations (drop, delete, reset, `rm -rf` on data paths) and migrations on real data.
- Sending private source or customer data to an external service.

Approval for one action does not carry over to the next.

## Profiles (set in project.md)
- `team-profile: solo`: the sole engineer is author and final reviewer; Definition of Done has five items (below); 24 h cooling-off only for destructive data changes.
- `team-profile: team`: one approval from someone other than the author; Definition of Done per guide 05.
- `ships-to-users: yes`: guides 11 to 14 apply (release, deployment, data safety, operations).

## Definition of Done (solo)
CI green · behavior covered by a test · AI review findings triaged at final review · docs and changelog updated · rollback noted for data or deploy changes.

## AI code review
It runs automatically on ready PRs and is advisory only. The final reviewer triages its findings, then approves.

## Skills
When starting one of these kinds of task, open `.agents/skills/<name>/SKILL.md` and follow it:
sdlc-start-task · sdlc-implement-change · sdlc-open-pr · sdlc-review-pr · sdlc-fix-bug · sdlc-hotfix · sdlc-write-adr · sdlc-update-dependencies · sdlc-cut-release · sdlc-rollback · sdlc-incident · sdlc-bootstrap-repo · sdlc-use-ai-agent
