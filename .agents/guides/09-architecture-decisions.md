# 09. Architecture Decisions

## Purpose

An Architecture Decision Record (ADR) captures a decision that is costly to reverse, together with its context and consequences, so the reason survives when the people who made it forget or leave.

## When to Write One

**MUST** write an ADR when the decision:

- changes a core technology, framework, database, or hosting model;
- sets a data model or identity scheme that is hard to migrate;
- defines a security, privacy, or licensing posture;
- adds a CI or delivery capability with ongoing cost (for example automated AI review);
- sets a convention many people must follow.

**Do not** write one for local refactors, library patch bumps, or choices easy to undo. Put those in the PR description.

## Rules

1. **MUST** store ADRs in `docs/adr/` as `NNNN-kebab-case-title.md`, numbered in order and never reused.
2. **MUST** use the template (R1): Title, Status, Context, Decision, Consequences, and Alternatives considered.
3. **MUST** keep an ADR short: one page is the target. If it needs ten, it is a design document, so link it.
4. **MUST** treat accepted ADRs as immutable. To change a decision, write a new ADR that supersedes the old one and update the old one's status to `Superseded by NNNN`.
5. **SHOULD** write the ADR in the same PR as the change, or before it when the decision needs review.
6. **SHOULD** state the decision in testable terms, so reviewers and agents can check conformance. For example: "Track identity is the SHA-256 of the canonical lowercase path; the scanner never hard-deletes records."
7. **SHOULD** list rejected alternatives with one line on why, so the same debate does not repeat.
8. **MUST** keep the ADR index count out of other docs. Do not write "ADRs 0001 to 0009" in a changelog; link to the folder.

## Statuses

`Proposed` → `Accepted` → (`Deprecated` | `Superseded by NNNN`). `Rejected` records a decision not to do something.

## Minimum Form

- A `docs/adr/` folder.
- Each ADR has Context, Decision, Consequences.
- At least one ADR before the first production release, covering stack and data storage.

## Scale-up

- ADR review in PRs with a required architecture reviewer.
- A short index file or generated table of ADRs.
- Link ADRs from code comments at the decision's enforcement point.

## AI Note

- Agents are good at drafting ADRs from a discussion but cannot know your constraints. Give them the context and review the "Alternatives" and "Consequences" sections hardest; that is where drafts are generic.
- Put the decisions agents must obey into the agent rules file with a link to the ADR (guide 15). An ADR the agent never reads does not guide it.
- Record AI-tooling decisions as ADRs too: which model, which review action, what advisory status, what cost ceiling.

## Checklist

- [ ] Decision is costly to reverse.
- [ ] Context says what forced the decision.
- [ ] Decision is specific and testable.
- [ ] Consequences include the downsides.
- [ ] Linked from the PR and, if relevant, the agent rules.
