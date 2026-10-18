---
name: sdlc-rollback
description: "Use when a release fails its healthcheck or causes a regression. Apply the rollback criterion, preserve evidence, roll back code and if needed data from the pre-deploy snapshot, and verify. Prepare the commands; a human runs them against production."
---

# Roll Back a Release

**Trigger:** failed healthcheck, regression, or incident caused by a release. **Guides:** 12, 13, 14 (in `.agents/guides/`).

1. **Decide fast.** Use the written criterion: healthcheck not operational after N attempts, or error rate above the threshold for M minutes. Do not debug in production while users suffer.
2. **Check that rollback is safe.** Did the release run an irreversible migration? If yes, rollback means restore from the pre-deploy snapshot, and any data written since is lost or must be reconciled. A human decides.
3. **Preserve evidence.** Copy the failed database and logs aside under timestamped names (`.failed-<timestamp>`) before overwriting anything.
4. **Roll back the code:** redeploy the previous tag.
5. **Roll back the data if needed:** restore the snapshot taken before this deploy.
6. **Restart services** and run the healthcheck. It must pass.
7. **Smoke test** the critical flows.
8. **Communicate:** tell affected users what happened and what state the system is in.
9. **Record:** open or update the incident (`sdlc-incident`), note the version rolled back and why.
10. **Follow up:** open issues to fix the cause. The fix goes through the normal flow and is released again via `sdlc-cut-release`.

**Rule:** after a rollback, do not redeploy the same version until the cause is understood.

**With an AI agent:** do not let it run rollback commands against production on its own. It may prepare the commands and the evidence checklist.
