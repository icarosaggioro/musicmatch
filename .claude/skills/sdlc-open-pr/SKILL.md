---
name: sdlc-open-pr
description: "Use when a branch is ready for review. Run all checks, push, open the PR with a valid title and the PR template, link the issue, and mark it ready so the AI review runs."
---

# Open a Pull Request

**Trigger:** the branch is ready for review. **Guides:** 02, 04, 05, 07 (in `.agents/guides/`).

1. Run the full project check command locally. All green.
2. Push the branch: `git push -u origin <branch>`.
3. **Open as a draft first** if you want CI feedback before a human looks. Draft PRs do not trigger the paid AI review.
4. Title: a valid Conventional Commit subject. It becomes the squash commit.
5. Fill the PR template:
   - **Summary:** what changed and why.
   - **Issue:** `Closes #N`.
   - **Testing:** exact commands and results, or manual steps taken.
   - **Risk and rollback:** what could go wrong and how to undo it.
   - **Screenshots:** for UI changes.
   - **Definition of Done checklist:** tick what applies, state why the rest does not.
6. Review your own diff in the PR view. Fix what you would have flagged.
7. Mark **Ready for review.** This triggers the AI review.
8. Wait for CI. Do not request human review on a red build unless you are asking for help.
9. **AI findings:** fix the ones you agree with. Leave the rest on the PR; the engineer assigned for the final review triages them.
10. Request the human reviewer and reply to every comment. Solo repos: you are the final reviewer; triage the findings, re-read the diff in the PR view, and merge once CI is green.

**Stop and ask a human if:** CI keeps failing for reasons you do not understand, or the PR has grown beyond roughly 400 lines. Split it.
