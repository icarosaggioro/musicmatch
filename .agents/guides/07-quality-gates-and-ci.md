# 07. Quality Gates and CI

## Rules

1. **MUST** run CI on every pull request to `main` and on every push to `main`.
2. **MUST** make these checks required for merge: **lint, type check, tests, build, dependency vulnerability scan**.
3. **MUST** make CI run the same commands a developer runs locally. Provide one script (for example `scripts/check` or `make check`) that runs them in order.
4. **MUST** fail closed. A gate that cannot run (missing token, unreachable service) fails the job or is reported as explicitly skipped, never as a silent pass.
5. **MUST** pin third-party actions and tools: an exact version or commit SHA for third-party actions, a major version at most for first-party ones. Never `latest` or a moving branch.
6. **SHOULD** give each workflow the minimum `permissions` it needs.
7. **SHOULD** cancel superseded runs with `concurrency` so old pushes do not burn minutes.
8. **SHOULD** keep CI under ten minutes. Split or cache when it grows.
9. **SHOULD** use path filters to skip unrelated modules, but make sure required checks still report. Skipped workflows can leave a required check pending forever; add a lightweight job that reports success when the filter skips the real one.

## Standard Pipeline

1. Checkout.
2. Set up runtime at the pinned version (one place defines the version).
3. Install dependencies from the lockfile (`npm ci`, `pip install -r requirements.txt`).
4. Lint and format check.
5. Type check.
6. Test.
7. Build.
8. Dependency vulnerability scan at a defined severity threshold.
9. (Pull requests only) Automated AI code review, advisory.

## Automated AI Code Review

Run an AI reviewer on pull requests as an extra, **advisory** layer. LivroJogo's setup is the reference.

**Must-have settings**
- **Trigger:** `opened`, `synchronize`, `reopened`, `ready_for_review`.
- **Skip:** draft PRs, bot-authored PRs (`dependabot[bot]` and any `[bot]` actor), to save budget and reduce noise.
- **Pin the action** to an exact version.
- **Pin the model** with a repository variable (for example `OCR_LLM_MODEL`), with an explicit fallback. A silent free-tier default makes review quality vary without notice.
- **Secrets** in the repository secret store; never in the workflow file or logs.
- **Permissions:** `contents: read`, `pull-requests: write`, `issues: write`, nothing more.
- **Concurrency:** one run per PR, cancel the older one.
- **Advisory:** `continue-on-error: true` while the tool is being calibrated. A review outage or false positive must not block delivery.
- **Incremental and sticky:** one summary comment updated in place, and new line comments only for new changes.
- **Rule file** in the repo (for example `.github/ocr-rules.json`) that scopes review by path and excludes lockfiles, binaries, media, and data files.

**Path-scoped rules, example**
- Backend: injection, authorization, input validation against schema, N+1 queries.
- Frontend: strict typing, no `any`, hook dependency arrays, error boundaries.
- Mobile: null safety, resource disposal, async error handling.

**Operate it, do not just install it** (details in guide 15)
- Record the decision in an ADR (cost model, model choice, advisory status).
- Treat a model change as a behavior change: note it in the PR and in the changelog, like a dependency upgrade.
- Spot-check it: when a finding is dismissed as noise, note it so the rules file can be tightened. Do not build a metrics program around it.
- Keep it advisory permanently. It is never a merge gate (decision D4); the overhead on individuals outweighs the benefit.

## Minimum Form

- One workflow: install, lint, types, tests, build, scan.
- `main` requires it.
- One command locally that does the same.

## Scale-up

- Separate workflows per module in a monorepo.
- Matrix builds for multiple runtime versions.
- Caching, reusable workflows, and a self-hosted runner for private infrastructure.

## Anti-Patterns

- A security scan that prints "token not configured, skipping" and passes (seen in LivroJogo's backend CI).
- CI on one runtime version, production on another (LivroJogo CI Python 3.13, production venv `python3.14`).
- A coverage or "tests passing" badge with no CI behind it (MusicMatch).
- `@latest` or branch references for actions.

## Checklist

- [ ] Required checks configured in repository settings.
- [ ] Local command equals CI commands.
- [ ] Scan fails when its token is missing, or the skip is visible.
- [ ] Runtime version defined in one place.
- [ ] AI review pinned, advisory, and excluded for drafts and bots.
