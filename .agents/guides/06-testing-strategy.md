# 06. Testing Strategy

## Rules

1. **MUST** have automated tests that run in CI on every PR. A suite that only runs on one laptop is not a safety net.
2. **MUST** add a regression test with every bug fix. The test fails before the fix and passes after.
3. **MUST** keep tests deterministic: no dependence on wall-clock time, random seeds without pinning, network access, or the order of other tests.
4. **MUST NOT** call real external services (payment, email, LLM providers, YouTube-like sources) from unit tests. Use fakes, recorded fixtures, or contract tests.
5. **SHOULD** follow a pyramid: many fast unit tests, fewer integration tests against real storage, a small number of end-to-end checks on critical user flows.
6. **SHOULD** treat a flaky test as a defect. Quarantine it, open an issue, fix or delete it within a week.
7. **SHOULD** keep test data small and in the repo. Large binaries, personal data, and real credentials stay out.
8. **MUST** make the suite pass on a fresh clone with one documented command.

## Layers

| Layer | What it proves | Speed target |
|---|---|---|
| Unit | A function or class behaves correctly in isolation | Seconds |
| Integration | Components work together with real storage (SQLite in-memory or a test DB) | Under a minute |
| Contract | Our code and an external API agree on the shape of requests and responses | Under a minute |
| End to end | A critical user flow works through the real stack | A few minutes, run on main or nightly if slow |

## Coverage

- **Ratchet, do not target** (team profile). Record the current coverage and forbid it from dropping on a PR. Raise the floor when it rises. In the solo profile, CI only reports coverage.
- Coverage is a signal, not a goal. A line executed by a test with no assertion adds nothing.
- Never publish a coverage or test-count claim that CI does not produce. Counts in READMEs go stale (see `.agents/references/R2-anti-patterns.md`, item 3).

## Minimum Form

- A test command documented in the README and run by CI.
- Regression test for every fix.
- No real network in unit tests.

## Scale-up

- Mutation testing on critical modules.
- Property-based tests for parsers, serializers, and money or state-machine logic.
- Load tests before major launches.
- Test the restore procedure for backups (guide 13).

## AI Note

- Agents must run the tests and show the result. A test suite an agent never ran gives no evidence.
- Beware of tests that an agent writes to match its own code. For critical logic, write or review the test first, or ask the agent to state the expected behavior from the issue before it implements.
- Agents may delete or weaken failing tests to "make CI green". Reviewers check the test diff, not only the production diff.
- When a bug is found in agent-written code, add the regression test, then ask whether the agent's rules file needs a line to prevent the class of bug.

## Checklist

- [ ] New behavior has tests.
- [ ] Bug fix includes a regression test.
- [ ] Tests pass locally with the documented command and in CI.
- [ ] No test was deleted or weakened without a reason in the PR.
