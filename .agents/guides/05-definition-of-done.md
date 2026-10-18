# 05. Definition of Done

A change is done when **all** applicable items are true. This list is the shared exit criterion for issues and PRs. It is intentionally short.

## Definition of Done

1. **Behavior:** the acceptance criteria in the issue are met and demonstrated (test, screenshot, or log).
2. **Tests:** new or changed behavior has automated tests. A bug fix has a regression test that fails without the fix.
3. **Gates:** every required CI check is green on the final commit.
4. **Review:** required review is complete and all blocking comments are resolved. AI findings are triaged.
5. **Docs:** README, changelog, runbook, or ADR is updated when behavior, configuration, or operations change.
6. **Data safety:** migrations are tested on realistic data; a backup or rollback path is stated for anything destructive.
7. **Security:** no secrets in the diff; new dependencies are justified; inputs from outside are validated.
8. **Operability:** logs, metrics, or status checks cover new failure modes; the PR describes how to roll back.
9. **Clean history:** commit subject follows the convention and the issue is linked.

## Applying It

- Not every item applies to every change. Mark the non-applicable ones with a reason in the PR ("no docs impact: internal refactor").
- "Done" means merged, not "code written". A PR with a failing check is not done.
- If an item cannot be met, the PR says which, why, and what follow-up issue tracks it.

## Solo Profile

For a repo with one engineer, the Definition of Done is five items:

1. CI is green on the final commit.
2. The behavior is covered by a test (a regression test for a bug fix).
3. AI review findings are triaged at final review (fixed, or dismissed with a reason).
4. Docs and changelog are updated when behavior changes.
5. A rollback is noted for any data or deploy change.

Secret scanning covers "no secrets in the diff". The nine-item list above applies to the team profile.

## Minimum Form

Put the list in the PR template as a checklist. The author ticks it; the reviewer spot-checks it.

## Scale-up

- Add performance or accessibility criteria for user-facing features.
- Add a feature-flag removal date for flagged changes.
- Add a "released and verified in production" step if you want to measure delivery, not just merge.

## AI Note

- An agent **MUST** satisfy the same list. If the agent says "done", the evidence is in the PR: test output, links, and a clean check run.
- Agents tend to report success from reading code, not from running it. Require the actual commands and results in the PR description.
