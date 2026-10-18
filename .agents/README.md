# SDLC Package

Rules, guides, skills, and templates that guide the software development lifecycle in this repository. Copied in from the master compendium; do not edit the package-owned files here, change the master and copy again.

## Layout

| Path | Owner | Purpose |
|---|---|---|
| `/AGENTS.md` | package | Pointer so any agent tool finds the rules |
| `.agents/rules/instructions.md` | package | General rules, identical in every repo |
| `.agents/rules/project.md` | **project** | Stack, scopes, commands, profile. Never overwritten |
| `.agents/guides/` | package | Normative guides 00 to 16 (read on demand, not loaded each session) |
| `.agents/skills/sdlc-*/` | package | Procedures an agent follows for common tasks |
| `.agents/references/` | package | R1 templates, R2 anti-patterns |
| `.agents/SDLC_VERSION` | package | Version of the package this repo carries |
| `.github/pull_request_template.md` | package | PR template with the Definition of Done |
| `.github/workflows/ci-codereview.yml` | package | Advisory AI code review (needs secrets, see below) |

Project-specific skills live next to the `sdlc-*` ones and keep their own names.

If the repo was installed with `--harness claude`, it also has a `CLAUDE.md` (imports the two rules files) and `.claude/skills/sdlc-*`, which are copies of the skills above for Claude Code. Do not edit the copies; they are refreshed by the installer.

## Settings the review workflow needs

- Secret `CI_OPENROUTER_API_KEY`.
- Variable `OCR_LLM_MODEL` (pin a model; there is deliberately no fallback).
- Set a spend limit on the API key.

## Updating

From the SDLC compendium repository, run `python tools/install_package.py <this-repo>` (use `python3` on Linux and macOS) for a dry run, then add `--apply`. It replaces only package-owned files and keeps your `project.md`. Check `.agents/SDLC_VERSION` to see which version a repo carries.

## Where to read more

Guide 00 explains the profiles (`solo` and `team`) and how to read the guides. Start there, then open the guide that matches the task.
