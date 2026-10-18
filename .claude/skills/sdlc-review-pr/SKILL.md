---
name: sdlc-review-pr
description: "Use when asked to review a pull request. Read the description and tests first, check correctness, security, data and operability, label comments, and decide explicitly. In solo repos act as final reviewer and triage the AI findings."
---

# Review a Pull Request

**Trigger:** review requested. **Guide:** 04 (in `.agents/guides/`).

1. **Respond within one business day.** If you cannot, say so and name someone else.
2. Read the description and the linked issue first. Do you understand what this should do?
3. Check CI. If it is red, ask the author to fix it before you invest time.
4. Read the AI review summary as a hint list, not as a verdict.
5. Read the **tests first.** Do they describe the intended behavior and fail without the change?
6. Read the production diff:
   - Correctness on failure paths.
   - Security: input validation, authorization, secrets.
   - Data: migrations, deletions, backups.
   - Simplicity: could this be smaller or reuse existing code?
   - Operability: logging, errors, rollback.
7. Run it if the change is risky or visual. Reading is not enough for UI or deployment changes.
8. Label comments: `blocking`, `suggestion`, `question`.
9. Decide explicitly: **Approve**, **Approve with comments**, or **Request changes**.
10. After the author responds, re-check only what changed.

**Never:** approve something you do not understand, or approve because the AI review is clean. In the team profile, never approve your own PR.

**Solo repos:** you are the final reviewer. Treat the AI review as the second pair of eyes, triage its findings, and re-read the diff in the PR view after a break.

**Review time budget:** if a review takes more than an hour, the PR is too big. Ask for a split.
