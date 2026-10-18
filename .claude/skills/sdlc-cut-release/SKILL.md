---
name: sdlc-cut-release
description: "Use when releasing what is on main. Choose the SemVer bump, open the version and changelog PR, tag or promote, stop for human confirmation before the production deploy, verify, and publish release notes."
---

# Cut a Release

**Trigger:** ready to ship what is on `main`. **Guides:** 11, 12, 13 (in `.agents/guides/`).

**Before**
1. Confirm `main` is green and nothing risky is half-merged.
2. Decide the version from the change types: breaking → MAJOR, features → MINOR, fixes → PATCH.
3. List which modules changed. Deploy only those.

**Prepare**
4. Open a PR that bumps the version file(s) and moves `Unreleased` to the new version in `CHANGELOG.md`. For Android, increment the `versionCode`.
5. Review and merge it.

**Promote**
6. Create an annotated tag on `main`: `git tag -a vX.Y.Z -m "..."` and push it, **or** promote `main` to the remote release branch if that is your pattern.
7. **Stop. A human confirms the production deploy.**
8. Trigger the deploy workflow for the changed modules only.

**Verify**
9. Watch the deploy: snapshot, migration, healthcheck, summary.
10. Smoke test one critical flow and the main changed feature.
11. Check logs and error rates for a short period.

**Publish**
12. Create the release with notes: what changed, migrations, known issues, rollback instructions.
13. Tell users or stakeholders if the release changes behavior they rely on.

**If it fails:** `sdlc-rollback`.

**With an AI agent:** it may prepare steps 1 to 6 and draft the notes. It does not perform step 8 without an explicit instruction for that deploy.

**Project release skill:** if this repo has its own release skill (for example `go-live`), follow that one; this skill is the generic fallback.
