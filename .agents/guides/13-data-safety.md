# 13. Data Safety

## Principle

User data is the one asset you cannot rebuild from source. Treat any operation that can lose, corrupt, or expose it as high risk.

## Rules

1. **MUST** keep persistent data outside the application directory and outside version control. Databases, media, and uploads live on a separate path set by configuration.
2. **MUST** back up automatically on a schedule, and again immediately before any migration or destructive operation.
3. **MUST** define retention (for example 14 daily database snapshots, 7 media snapshots) and enforce it by script.
4. **MUST** test restoration. A backup you have never restored is a hope. Restore into a scratch environment at least quarterly and after changing the backup method.
5. **MUST** make migrations safe: forward-compatible where possible, tested on a copy of realistic data, with a stated rollback path.
6. **MUST NOT** hard-delete user records automatically. Use soft delete with an explicit status (for example `AVAILABLE` and `MISSING`), and make hard deletion a separate, confirmed, logged operation.
7. **MUST** preserve forensic evidence on failure: move the failed database aside under a timestamped name instead of overwriting it.
8. **SHOULD** use the database's online backup mechanism (for SQLite, `.backup`) instead of copying a live file, and fall back to a file copy only if the tool is missing.
9. **SHOULD** encrypt backups that leave the host and restrict who can read them.
10. **SHOULD** keep production data out of development and test environments. If you need realistic data, anonymize it.

## Migrations

1. Make each migration small and reversible when the engine allows.
2. Separate schema change from data backfill for large tables.
3. Deploy code that works with both the old and new schema, then migrate, then remove the old paths (expand and contract).
4. Never edit a migration that already ran in any shared environment; add a new one.
5. Run migrations in CI against a fresh database to prove they apply from zero.

## Idempotency and Lifecycle

For ingestion and scanning jobs, design for safe re-runs:

- Deterministic identity (for example a hash of a canonical key), so a re-run never duplicates.
- Cheap change detection (modification time and size) so unchanged items are skipped.
- A status instead of deletion when a source disappears, because a drive may be temporarily offline.

## SQLite Notes (small deployments)

- SQLite is a sound default for single-host systems. Plan the move to a client-server database before you need concurrent writes from many processes. Record the thresholds and the migration path in an ADR.
- Use WAL mode for better read concurrency, back up with `.backup`, and keep the database file outside the repo.

## Minimum Form

- A scheduled backup and a pre-migration snapshot.
- A written restore procedure, tried once.
- Soft delete by default.

## Scale-up

- Point-in-time recovery.
- Cross-region or off-site backup copies.
- Data classification and retention policy by data type.
- Migration tooling with automated dry runs.

## AI Note

- Agents **MUST NOT** run destructive data commands (`DROP`, `DELETE` without a scoped `WHERE`, `rm -rf` on data paths, migration reset) against any environment holding real data, without an explicit human instruction naming the target.
- Agents should write migrations but never apply them to production.
- Review every agent-written migration for irreversible operations and for locks on large tables.

## Checklist

- [ ] Data path is outside the repo and outside the deploy directory.
- [ ] Snapshot taken before the migration.
- [ ] Rollback path written.
- [ ] No automatic hard delete introduced.
- [ ] Restore tested within the last quarter.
