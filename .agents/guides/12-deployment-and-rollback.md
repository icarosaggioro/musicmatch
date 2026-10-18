# 12. Deployment and Rollback

## Rules

1. **MUST** deploy from an immutable reference (a tag or the release branch), never from a developer's branch.
2. **MUST** have the deploy pipeline verify the reference as its first step and fail with a clear error when it is wrong. LivroJogo's production job aborts if the ref is not `refs/heads/release/lorevault-publish`.
3. **MUST** trigger production deploys manually (`workflow_dispatch` or an approval step) in a protected environment. Integration environments may deploy automatically.
4. **MUST** run only one deploy per environment at a time (`concurrency` group) with a timeout.
5. **MUST** take a data snapshot before any migration that changes a persisted schema (guide 13).
6. **MUST** gate success on a healthcheck, not on "the process started". The check retries with a short back-off, and the pipeline fails if the service never reports healthy.
7. **MUST** have a rollback that is documented before the deploy and automated where practical.
8. **MUST** publish a deploy summary (what version, what snapshot, gate results, rollback status) in the CI run.
9. **SHOULD** deploy only the modules that changed.
10. **SHOULD** keep integration and production in separate environments, with separate configuration and credentials.

## Standard Deploy Steps

1. Verify reference.
2. Stop the service gracefully, if it must stop.
3. Check out the code; update the runtime environment.
4. Write configuration from secrets and variables (never print them).
5. Snapshot data (and media if relevant).
6. Run migrations; collect static files.
7. Start the service.
8. Healthcheck gate: local, blocking. Public endpoint: at least a warning, and block if you can.
9. On failure: roll back (see below).
10. Always: write the deploy summary.

## Rollback

- **Code:** redeploy the previous tag.
- **Data:** restore the pre-deploy snapshot. Before overwriting the failed state, **preserve it** under a timestamped name (`.failed-<timestamp>`) so you can investigate.
- **Decide fast:** a rollback criterion is written down. For example: healthcheck not operational after N attempts, or error rate above a threshold for M minutes.
- **After rollback:** restart services against the restored data, verify with the same healthcheck, and open an incident (guide 14).

## Healthcheck Design

- Provide a `/status` or `/health` endpoint that reports each subservice (database, queue, cache) and an overall status.
- Distinguish *alive* (process runs) from *ready* (dependencies work). Gate on ready.
- Do not expose internal detail to the public endpoint. Keep the detailed one on an authenticated or internal path.

## Minimum Form

- Manual production trigger with a ref guard.
- Snapshot, healthcheck, and a written rollback step.
- Deploy summary.

## Scale-up

- Blue-green or canary deployment.
- Automated rollback on error-rate alarms.
- Infrastructure as code and ephemeral preview environments.
- Progressive delivery with feature flags.

## AI Note

- Agents **MUST NOT** trigger production deploys unless a human explicitly requested that specific deploy in the current session. Approval for one deploy does not extend to the next.
- Agents may prepare a deploy: bump the version, check the ref, draft the notes. A human presses the button.
- When an agent edits deploy scripts, treat the PR as high risk: require a human reviewer who understands the environment.

## Checklist

- [ ] Reference verified by the pipeline.
- [ ] Snapshot succeeded before migration.
- [ ] Healthcheck gate passed.
- [ ] Rollback step known and tested at least once.
- [ ] Deploy summary recorded.
