# 01. Source Control and Branching

## Rules

1. **MUST** protect `main`: no direct pushes, no force pushes, merges only through a pull request.
2. **MUST** do all work on a short-lived branch created from an up-to-date `main`.
3. **MUST** name branches `<type>/<issue-number>-<kebab-case-description>`, for example `fix/166-celery-redis-isolation`. Omit the number only when no issue exists.
4. **MUST** use these types, which match the commit types in guide 02: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `ci`, `chore`.
5. **SHOULD** keep a branch alive for at most three working days. If it lives longer, split the work or merge behind a feature flag.
6. **SHOULD** delete the branch after merge.
7. **MUST NOT** commit secrets, local databases, virtual environments, build output, or large binaries. `.gitignore` is part of the repo from day one.

Bot branches keep their tool's naming (for example `dependabot/pip/backend/idna-3.20`).

## Minimum Form

- A protected `main`.
- Feature branches that merge by pull request.
- A `.gitignore` that covers environments, secrets, local data, and build output.

## Production Promotion

Production deploys come from an **immutable reference**, never from an arbitrary branch tip. Choose one of two patterns and write it in the repo:

- **Tag-based (default):** a SemVer tag on `main` triggers or authorizes the deploy.
- **Release-branch-based:** a remote-only release branch is fast-forwarded from `main`, as LivroJogo does with `git push origin main:release/<name>`. Nobody creates or checks out that branch locally.

In both cases the deploy pipeline **MUST** check the ref and refuse any other (see guide 12).

## Scale-up

- Add required reviewers per path (CODEOWNERS) when more than one team touches a repo.
- Add merge queues when CI time and PR volume make rebases painful.
- Add long-lived `release/x.y` branches only when you must patch older versions.

## AI Note

- Agents work on a branch, never on `main` and never on the release branch.
- The agent rules file (guide 15) states the branch naming rule so the agent follows it without being told each time.

## Checklist

- [ ] `main` is protected in the hosting settings (this cannot be verified from the clone, so check it).
- [ ] Branch name matches the pattern.
- [ ] Branch started from the current `main`.
- [ ] No secrets or local data in the diff.
