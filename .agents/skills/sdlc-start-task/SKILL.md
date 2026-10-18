---
name: sdlc-start-task
description: "Use when picking up an issue or beginning a new piece of work. Read the acceptance criteria, create the correctly named branch from an updated main, verify the baseline, and record a short plan."
---

# Start a Task

**Trigger:** you pick up an issue. **Guides:** 01, 03 (in `.agents/guides/`).

1. Read the issue and its acceptance criteria. If they are missing or untestable, fix the issue first.
2. Confirm scope. If the work is bigger than a few days, split it into child issues.
3. Update local `main`: `git checkout main && git pull origin main`.
4. Create the branch: `git checkout -b <type>/<issue-number>-<kebab-description>`.
5. Read the relevant docs: ADRs touching the area, the glossary, the agent rules file.
6. Verify the baseline: run the project check command on the clean branch. If it fails now, stop and report it before changing anything.
7. Write down the plan in the issue: three to five bullets of what you will change and how you will test it.

**Stop and ask a human if:** the issue needs a decision that is costly to reverse (write an ADR first, see `sdlc-write-adr`), or touches production data.

**With an AI agent:** give it the issue link, the acceptance criteria, and the agent rules file. Ask it to state its plan before coding, and review the plan.
