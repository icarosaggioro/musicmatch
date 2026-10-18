# 04. Code Review

## Purpose

Review exists to catch defects, spread knowledge, and keep the design coherent. It is not a gate for style: formatters and linters own style.

## Rules

1. **MUST** have every change reviewed before merge. One human reviewer is the minimum.
2. **MUST** review within one business day of the request. A review that waits longer is a process bug.
3. **MUST** have changes touching security, authentication, data migrations, or production configuration reviewed by someone who understands that area.
4. **MUST** block merge on unresolved review comments marked as blocking.
5. **SHOULD** label comments: `blocking`, `suggestion`, or `question`. Unlabeled comments are suggestions.
6. **SHOULD** approve with comments when the only remaining issues are non-blocking.
7. **MUST NOT** approve a PR you do not understand. Ask for a walkthrough instead.

## What Reviewers Look For

1. Does it solve the issue and meet its acceptance criteria?
2. Is it correct under failure, not only on the happy path?
3. Are there tests, and do they fail without the change?
4. Security: input validation, authorization, secrets, injection, unsafe deserialization.
5. Data: migrations are reversible or backed up, no destructive operations without safeguards.
6. Simplicity: could it be smaller or reuse something existing?
7. Operability: logging, error messages, rollback path.
8. Docs and changelog updated when behavior changes.

## Solo-Developer Teams

When there is no second reviewer:

- The sole engineer is both author and final reviewer. The automated AI review (guide 07) is the second pair of eyes; triage its findings at final review.
- Re-read your own diff in the PR view, not in the editor, after a break. The self-review checklist in R1 is optional and meant for high-risk changes.
- **MUST** wait at least 24 hours before merging a destructive migration or a data deletion. Other changes merge when CI is green and the diff has been read.
- **SHOULD** find an outside reviewer for any change with high blast radius (data loss, security).
- Branch protection requires a PR and the CI checks, with **zero** required approvals. A PR author cannot approve their own PR on GitHub, so requiring one would block every merge.

## AI Code Review

AI review is an **extra** reviewer. It does not replace the human reviewer (see guide 07 for the CI setup and guide 15 for operations).

- The review runs automatically when the PR is marked ready. Findings stay on the PR until an engineer is assigned for the final review.
- The **final reviewer** triages every AI finding (fix it, or dismiss it with a one-line reason in the thread) and then approves. The author may fix findings earlier. Silence is not allowed.
- AI findings **never** block merge by themselves; the tool is permanently advisory (decision D4).
- A human reviewer **MUST NOT** rely on a clean AI review as a reason to skim. A clean pass means the tool found nothing, not that the code is right.

## Author Duties

- Self-review before requesting review.
- Keep the PR small and the description honest about risk.
- Respond to every comment. Resolve it by changing code or explaining why not.
- Do not mark a thread resolved for the reviewer; let them.

## Minimum Form

- One human approval before merge.
- A PR template with a review section.
- Author triages AI findings.

## Scale-up

- CODEOWNERS per path, required reviews from owners.
- Two approvals for high-risk paths.
- Review-time metrics: time to first review, review rounds.

## Checklist (Reviewer)

- [ ] Understood the intent and the diff.
- [ ] Verified tests cover the change.
- [ ] Checked security and data impact.
- [ ] Labeled comments.
- [ ] Approved or requested changes explicitly.
