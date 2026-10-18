# 16. Roles and Responsibilities

## Principle

In a small organization one person usually holds several roles. What matters is that every responsibility has a **named owner** and a **backup**, and that the people who build something are not the only ones who can approve it.

## Roles

| Role | Responsibility | Minimum |
|---|---|---|
| **Repository owner** | Keeps the repo healthy: settings, branch protection, CI, secrets, dependency PRs, docs. | One named person per repo, one backup |
| **Author** | Writes the change, tests it, writes a clear PR. | Anyone on the team, including an AI agent with a human accountable |
| **Reviewer** | Reviews the change per guide 04. | At least one person other than the author |
| **Release manager** | Decides when to cut a release, runs the release procedure, verifies it. | Rotates, or one named person |
| **Service owner** | Owns a production service: runbook, alerts, incidents. | One owner plus a backup |
| **Incident lead** | Coordinates an incident. | Whoever is on duty |
| **Architecture steward** | Maintains ADRs and technical direction; reviews decisions that are hard to reverse. | One person, can be the repository owner |
| **AI steward** | Maintains the agent rules file, AI review configuration, model choices, and cost. | One person, can be the repository owner |

## Rules

1. **MUST** write the owners in a file (`CODEOWNERS` or a table in `CONTRIBUTING.md`) so people and agents can find them.
2. **MUST NOT** have a single person who is author, reviewer, and release approver for a production release in the team profile. In the solo profile, the rules in guide 04 apply instead (AI review as second pair of eyes, cooling-off for destructive data changes, an outside reviewer for high blast radius).
3. **SHOULD** rotate release manager and incident lead to spread knowledge.
4. **SHOULD** keep the owner list current. Review it when people join, leave, or change roles.
5. **MUST** treat an AI agent as a tool operated by an accountable human, not as a role. The human who runs the agent owns what it produces.

## Decision Rights

| Decision | Who decides | Record in |
|---|---|---|
| Merge a PR | Reviewer approves; author merges | PR |
| Cut a release | Release manager | Release notes |
| Roll back | Incident lead or release manager | Incident log |
| Adopt a dependency | Author proposes; reviewer approves | PR |
| Architectural change | Architecture steward with the team | ADR |
| Change agent rules or AI review settings | AI steward, reviewed by repository owner | PR and ADR |
| Make a rule blocking in CI | Repository owner with the team | PR and ADR |
| Grant access or rotate a secret | Repository owner | Access log |

## Solo Profile

One named owner per repository and no roles table. Add a backup owner when someone else can take over.

## Minimum Form

- One table of owners in each repo.
- Named backups.
- A rule that the author does not approve their own PR.

## Scale-up

- CODEOWNERS enforced in branch protection.
- Team charters and on-call rotations.
- A security champion per team.

## AI Note

- The human accountable for an agent is named in the PR (author or assignee). The agent is never the accountable party.
- Access for agents goes through the repository owner, with scoped tokens that expire.

## Checklist

- [ ] Every repo lists an owner and a backup.
- [ ] Every service lists an owner and a backup.
- [ ] No one approves their own release.
- [ ] Agent access is scoped and has a human owner.
