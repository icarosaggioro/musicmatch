---
name: sdlc-fix-bug
description: "Use when handling a bug report or a failing check. Reproduce it, write a failing regression test, fix the cause with the smallest change, look for sibling defects, and prevent recurrence."
---

# Fix a Bug

**Trigger:** bug report or failing check. **Guides:** 03, 05, 06 (in `.agents/guides/`).

1. **Reproduce it.** No reproduction, no fix. If you cannot, ask the reporter for steps, environment, version, and logs.
2. **Open or update the issue** with the reproduction and severity. Link duplicates.
3. **Write a failing regression test** that captures the bug. Commit it first if you like; it should fail.
4. **Find the cause,** not only the symptom. Ask why the bug was possible and why tests did not catch it.
5. **Fix it with the smallest correct change.** Keep refactors out.
6. **Confirm** the regression test passes and the full suite still passes.
7. **Look for siblings:** the same mistake elsewhere in the code. Fix them or file issues.
8. **Prevent recurrence:** a lint rule, a type, an agent-rules line, or a CI check, when the class of bug is likely to return.
9. **PR:** `fix(<scope>): <subject>`, link the issue, describe cause and test.
10. **Production bug?** Follow `sdlc-hotfix` for hotfixes and `sdlc-incident` for incidents.

**With an AI agent:** give it the reproduction, ask for the failing test first, and check that the fix addresses the cause and not just the test.
