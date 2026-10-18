# 15. AI-Assisted Development

## Premise

Most code in these projects is written, reviewed, or tested with AI help. The goal is not to restrict that, but to make it **safe, reviewable, and cost-aware**. The central rule is that **AI output meets the same bar as human output**.

## Rules

1. **MUST** keep agent rules in every repository: a root `AGENTS.md` that points to `.agents/rules/instructions.md` (general rules, identical in every repo) and `.agents/rules/project.md` (project-specific rules). They are versioned, reviewed, and kept short.
2. **MUST** treat AI-authored changes like any other: same branch workflow, PR, CI gates, review, and Definition of Done.
3. **MUST** keep humans accountable. A named human owns each PR, whoever or whatever wrote it.
4. **MUST** run the tests and show the results. An agent claiming success without running anything is not evidence.
5. **MUST NOT** let agents push to `main` or the release branch, trigger production deploys, or run destructive data operations without an explicit human instruction for that specific action. Approval for one action does not carry over to the next.
6. **MUST NOT** put secrets, customer data, or restricted source in prompts to an external model. The rules file lists what is off-limits.
7. **SHOULD** record AI involvement in history with a `Co-Authored-By` trailer on commits the agent materially wrote.
8. **SHOULD** give agents scoped credentials and the least privilege needed.
9. **SHOULD** budget AI cost. Know what runs on paid models, set limits, and cut waste (skip drafts and bot PRs in review).
10. **SHOULD** record AI tooling choices (model, review action, thresholds) in an ADR and re-evaluate them periodically.

## The Agent Rules File

It tells an agent how to work in this repo. Keep it to what the agent cannot infer, and link to the longer documents.

**Contents**
1. Project one-liner and stack constraints (what is allowed, what is forbidden).
2. Language rules: chat language versus artifact language (see guide 00).
3. Git rules: never commit to `main`, branch naming, commit format, scope list, how to open a PR.
4. Commands: how to install, lint, type-check, test, build, in one block.
5. Data and safety rules: schema contracts to respect, destructive operations forbidden.
6. Documentation map: where the PRD, glossary, SDLC doc, and ADRs are.
7. Release rules: what the agent may prepare and what only a human triggers.

**Good examples:** LivroJogo's `.agents/rules/instructions.md` (stack, language, topology, schema contract, git golden rule, release steps) and MusicMatch's short `AGENTS.md` (language rules only). A good file combines the first's coverage with the second's brevity.

**Maintenance:** when an agent repeats a mistake, add a line to the rules file or a check to CI. Do not just correct the agent in chat; chat is forgotten.

## Skills and Playbooks

Package repeatable procedures as reusable **skills** or playbooks that agents and humans follow the same way (for example "go-live", "start a task", "write an ADR"). Each skill is a short, ordered checklist with explicit stop points where a human must confirm. LivroJogo stores its release procedure as `.agents/skills/go-live/SKILL.md`. In this compendium they are the `sdlc-*` skills under `.agents/skills/`.

## Reviewing AI-Written Code

Read it with more suspicion on these points:

- **Plausible but wrong:** code that looks idiomatic and fails on edge cases or misuses an API.
- **Invented dependencies and APIs:** packages or methods that do not exist, or are typosquats.
- **Weakened tests:** deleted assertions, skipped tests, mocks that make a test pass trivially.
- **Scope creep:** unrelated refactors mixed into the diff. Ask for a smaller PR.
- **Silent behavior changes:** changed defaults, swallowed exceptions, catch-all handlers.
- **Overconfident PR text:** a description that claims tests were run when no output is shown.

## Operating Automated AI Code Review

LivroJogo's Open Code Review is the reference (CI setup is in guide 07). Operating it well:

1. **Pin** the action version and the model. Change them through a PR, like a dependency.
2. **Triage at final review.** The review runs automatically when the PR is marked ready, and findings wait on the PR. The engineer assigned for the final review triages them (fix, or dismiss with a one-line reason) and then approves. There is no separate response-time target (decision D12). In a solo repo, that engineer is the sole developer.
3. **Spot-check, do not measure formally.** Note findings dismissed as noise so the rules file can be tightened. "Good results" is still an impression; if it ever has to be defended, count accepted versus dismissed findings over a few weeks.
4. **Tune** rules by path. If a rule is mostly noise, tighten or remove it.
5. **Keep it advisory.** It never becomes a merge gate (decision D4), because the overhead on individuals outweighs the benefit.
6. **Keep humans in the loop.** AI review adds a pair of eyes; it does not replace the human reviewer on security, data, or release changes.
7. **Control cost.** Exclude drafts, bots, lockfiles, binaries, and data files; review incrementally.

## Evidence Discipline for AI Work

Borrowed from the Benchmarks project, and useful whenever you evaluate an AI tool or an agent:

- **State the question and the measure before you collect results.** Decide what "better" means first.
- **Record the configuration.** Model name and version, settings, and tool versions go with every result.
- **Missing is not zero.** If a measurement is unavailable, record it as missing.
- **Do not over-claim.** Report limitations next to results. "No general ranking is established" is a perfectly good conclusion.
- **Verify by independent checks.** An agent's completion claim or a green public test suite is not sufficient evidence of correctness for critical logic.

## Minimum Form

- Agent rules file in every repo.
- AI changes go through the normal PR and CI.
- AI review in CI, advisory, pinned, triaged.
- No production actions by agents without explicit approval.

## Scale-up

- A shared library of skills across repos.
- Measured evaluation of agents on your own tasks before adopting a new model.
- Sandboxed environments for agents.
- A cost dashboard by repo and tool.

## Checklist

- [ ] Agent rules file present, short, and linked to docs.
- [ ] AI-authored commits carry the trailer.
- [ ] Tests were actually run; output is in the PR.
- [ ] AI review findings triaged.
- [ ] No secrets or restricted data in prompts.
