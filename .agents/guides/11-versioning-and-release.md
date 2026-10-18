# 11. Versioning and Release

## Versioning

1. **MUST** use Semantic Versioning `vMAJOR.MINOR.PATCH`.
   - MAJOR: incompatible changes to a public interface, data contract, or behavior users rely on.
   - MINOR: backward-compatible features.
   - PATCH: backward-compatible fixes.
2. **MUST** version independently each deployable module in a multi-module repo (for example backend, frontend, mobile), and say so in the release notes.
3. **MUST** define the version in one file per module. Other places read it or reference it.
4. **SHOULD** use pre-release identifiers (`-rc.1`) for candidate builds that need testing.
5. **SHOULD** treat a database schema change that cannot be rolled back as at least a MINOR bump and call it out in the notes.
6. Mobile apps that need a monotonically increasing build number (for example Android `versionCode`) **MUST** increment it on every release (`version: X.Y.Z+<n>`).

## Changelog

1. **MUST** keep `CHANGELOG.md` in [Keep a Changelog](https://keepachangelog.com/) format: `Unreleased`, then one section per release with date, grouped as Added, Changed, Deprecated, Removed, Fixed, Security.
2. **MUST** add the entry in the PR that makes the change, not at release time.
3. **MUST NOT** use the changelog to store counts that go stale (test totals, ADR numbers).
4. **SHOULD** write entries for users and operators, not as commit logs.

## Release Procedure

1. All required checks green on `main`.
2. A version-bump PR merges to `main`, updating the version file and moving `Unreleased` to the new version in the changelog.
3. Create an **annotated** tag on `main` (`vX.Y.Z`), or promote `main` to the remote release branch if that is your pattern (guide 01).
4. The deploy pipeline runs against that immutable reference (guide 12).
5. Verify in the target environment: healthcheck, smoke test of one critical flow.
6. Publish the release (GitHub Release or equivalent) with notes: what changed, migrations, rollback instructions.

## Minimum Form

- SemVer tags on `main`.
- `CHANGELOG.md` updated per PR.
- Release notes on every release.

## Scale-up

- Automated release notes from Conventional Commit types.
- Release trains on a fixed cadence.
- Signed tags and artifacts.
- Backport branches for supported older versions.

## AI Note

- Agents may draft release notes from the diff. Review them for user-visible impact and for anything the diff cannot show (for example data migrations).
- Do not let an agent choose the version number alone. It must justify the bump from the change types.
- The release procedure is a good candidate for a reusable agent skill (LivroJogo packages its go-live process this way). The skill **MUST** stop and ask before pushing a tag or triggering production.

## Checklist

- [ ] Bump PR merged with updated version and changelog.
- [ ] Tag created and pushed from `main`.
- [ ] Post-deploy verification done.
- [ ] Release notes published, with rollback instructions.
