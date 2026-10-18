---
name: sdlc-implement-change
description: "Use while implementing a change on a feature branch. Test first, make small conventional commits, run the project check command, keep the diff focused, update docs, and note the rollback."
---

# Implement a Change

**Trigger:** working in a feature branch. **Guides:** 02, 05, 06, 08 (in `.agents/guides/`).

1. **Test first when the behavior is clear.** Write the failing test, then the code. For a bug, write the regression test first and watch it fail.
2. **Work in small steps.** Commit each coherent step with a Conventional Commit message.
3. **Run the project check command often** (lint, types, tests). Do not wait for CI to find what you can find in seconds.
4. **Keep the diff focused.** Unrelated cleanups go in a separate branch.
5. **Handle failure paths,** not only the happy path: bad input, missing data, timeouts, partial failure.
6. **Check for secrets and local data** in the diff: tokens, `.env` contents, databases, personal data.
7. **Update docs and the changelog** in the same branch when behavior, configuration, or operations change.
8. **Note the rollback.** If the change touches data or deployment, write how to undo it.
9. **Re-read your own diff** in the diff viewer before pushing.

**Stop and ask a human if:** you need to disable or weaken a test, change a migration that already ran elsewhere, or add a dependency you cannot justify in one sentence.

**With an AI agent:** require it to run the checks and show the output. Review the test diff as carefully as the code diff; agents sometimes weaken tests to get green.
