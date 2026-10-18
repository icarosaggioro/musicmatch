---
name: sdlc-bootstrap-repo
description: "Use when creating a new repository or adopting the SDLC package in an existing one. Set up hygiene files, branch protection, CI with required checks, the review workflow, templates, and agent rules."
---

# Bootstrap a New Repo

**Trigger:** a new project is created. **Guides:** all, mainly 00, 07, 10, 15 (in `.agents/guides/`).

**Repository**
1. Create the repo with a clear name. Use one canonical product name in docs and code.
2. Add `.gitignore` (environments, secrets, local data, build output), `LICENSE`, and `.env.example`.
3. Protect `main`: require PRs, require the CI checks, block force pushes. Solo profile: require **zero** approvals (an author cannot approve their own PR). Team profile: require one. Verify the settings after saving, and check that your hosting plan supports branch protection on private repos.
4. Fill in `.agents/rules/project.md` (`team-profile`, `ships-to-users`, stack, scopes, commands).

**Code and checks**
5. Define the runtime version in **one** place.
6. Add lint, formatter, type checker, and test runner with the project's standard config.
7. Add one local command that runs them all (for example `scripts/check` or `make check`).
8. Add the CI workflow: install, lint, types, tests, build, dependency scan. Make it fail closed.
9. Add Dependabot, weekly.

**Documentation**
10. `README.md` with the minimum sections (guide 10).
11. `CHANGELOG.md` with an `Unreleased` section.
12. `docs/adr/` with ADR 0001: stack and data storage.
13. Copy the SDLC package (`AGENTS.md`, `.agents/`, `.github/`) into the repo. The agent rules are then in place; only `project.md` is yours to fill in.
14. PR template, issue templates, and `CONTRIBUTING.md` or a link to this compendium.

**AI**
15. Add the AI code review workflow: pinned action and model, drafts and bots excluded, advisory, path-scoped rules file. Record the decision in an ADR.

**Roles**
16. Write the owner and backup owner in `CODEOWNERS` or `CONTRIBUTING.md`.

**Done when:** a new teammate can clone the repo, run the check command, and open a PR that passes CI, using only the README.
