---
name: sdlc-hotfix
description: "Use for a critical production defect. Decide rollback versus fix-forward, branch from main, test first, keep the CI gates, bump the PATCH version, release, and verify. Never trigger the production deploy without explicit human confirmation."
---

# Hotfix Production

**Trigger:** critical defect in production. **Guides:** 11, 12, 13, 14 (in `.agents/guides/`).

1. **Decide: roll back or fix forward?** Roll back (`sdlc-rollback`) if the last release caused it and rollback is safe. Fix forward only if rollback is riskier, for example after an irreversible data migration.
2. **Declare an incident** (`sdlc-incident`) for Sev 1 and Sev 2. Name the lead.
3. **Branch from `main`:** `fix/<issue-number>-<short-description>`. `main` is the release source; do not branch from a stale tag unless you maintain older versions.
4. **Write the failing test first, then the smallest fix.** No refactors, no unrelated changes.
5. **Open a PR** with `Risk and rollback` filled in. Team profile: a second person reviews it, even under time pressure. Solo profile: read the diff in the PR view and triage the AI review findings; the 24-hour cooling-off does not apply to a hotfix, but CI does.
6. **Run all required checks.** Do not bypass them. A hotfix that skips CI is how a second incident starts.
7. **Bump the PATCH version** and update the changelog in the same PR or an immediate follow-up.
8. **Release** with the normal procedure (`sdlc-cut-release`): tag, promote, deploy with the snapshot and healthcheck gates.
9. **Verify:** healthcheck, smoke test of the broken flow, watch the logs.
10. **Close out:** write the post-incident note and open follow-up issues. Team profile: hold the blameless review within five working days.

**Stop and ask a human before:** triggering the production deploy. A human confirms that specific deploy, even from an agent-prepared PR.
