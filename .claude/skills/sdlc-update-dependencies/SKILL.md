---
name: sdlc-update-dependencies
description: "Use for Dependabot PRs, security advisories, or when adding a dependency. Assess risk, read release notes, run the suite, and verify the package is the intended one."
---

# Update Dependencies

**Trigger:** Dependabot PR or security alert. **Guide:** 08 (in `.agents/guides/`).

**Routine update (patch or minor):**
1. Check CI. It must be green.
2. Skim the release notes for anything that touches how you use the package.
3. Merge when green. Batch low-risk updates to reduce noise.

**Major update:**
1. Read the migration guide and the breaking changes.
2. Check for deprecated APIs you use. Search the code.
3. Run the full suite locally, and run the app. Look for runtime warnings.
4. Fix breakages in the same PR, or open a branch of your own for the migration.
5. Update lockfiles and docs.
6. Record notable changes in the changelog.

**Security advisory:**
1. Read the advisory. Is the vulnerable code path reachable from your code?
2. Upgrade to the fixed version, or apply the documented mitigation.
3. If no fix exists, write the exception in the issue with a review date.
4. High severity: fix within a few working days. Critical and reachable: treat as a hotfix (`sdlc-hotfix`).

**Adding a new dependency:**
1. State why it is needed, why not the standard library, its license, and its maintenance status.
2. Verify the package name and publisher. Typosquats exist.
3. Pin it and commit the lockfile.

**With an AI agent:** do not let it add packages without stating the reason. Check that the package exists and is the intended one.
