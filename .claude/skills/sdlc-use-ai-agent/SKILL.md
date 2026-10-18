---
name: sdlc-use-ai-agent
description: "Use when delegating a task to an AI agent or supervising one. Define scope and off-limits actions, require a plan first, require real check output, review the full diff, and capture repeated mistakes in rules or CI."
---

# Use an AI Agent on a Task

**Trigger:** you delegate work to an AI agent. **Guide:** 15 (in `.agents/guides/`).

**Before you start**
1. The task has an issue with testable acceptance criteria.
2. The repo has an agent rules file. If it does not, add one first (`sdlc-bootstrap-repo`).
3. Decide the scope: which files, which commands, which environments. State what is off-limits: `main`, the release branch, production, real data.
4. Check what the agent can read and send. No secrets, no customer data, no restricted source to an external model.
5. Give the agent scoped credentials, not administrator ones.

**While it works**
6. Ask for a **plan first** and review it before the agent changes code.
7. Keep it on a feature branch. Commits with `Co-Authored-By` trailers where the agent materially wrote them.
8. Require it to run lint, types, and tests and to show the output.
9. Watch for scope creep, new dependencies, and tests that were deleted, weakened, or skipped.
10. Interrupt early if it is looping or inventing APIs.

**Before you merge**
11. Read the full diff. You own it.
12. Run the checks yourself or confirm CI is green on the final commit.
13. Triage the AI code review findings and the human review comments (`sdlc-open-pr`, `sdlc-review-pr`).
14. Verify the PR description matches the diff and states what was really tested.

**After**
15. If the agent made a mistake that could recur, add a line to the agent rules file or a check to CI.
16. Note the model and settings if you are evaluating the agent's quality. Missing data is recorded as missing, not zero.

**Never allow without explicit, specific approval:** pushing to `main`, triggering a production deploy, running destructive data operations, rotating secrets, or changing CI gates.
