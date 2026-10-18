# 10. Documentation

## Rules

1. **MUST** keep documentation in the repository, written in English, and changed through pull requests like code.
2. **MUST** give every repository a `README.md` with the minimum sections below.
3. **MUST** give every repository a `CHANGELOG.md` (guide 11) and an agent rules file (guide 15).
4. **MUST** keep one source of truth per fact. Versions, test counts, ADR counts, and command lists live in one place and are linked, or are generated. Do not hand-write numbers that tools can compute.
5. **MUST** use one canonical name per audience. An internal project name and a commercial product name may both exist (LivroJogo is the internal project; Lore Vault is the commercial product). Document the mapping once in the README and never invent a third spelling.
6. **MUST** mark documents that are no longer current at the top: `Status: historical`, `Status: superseded by <link>`, or `Status: legacy`. Do not leave them to be mistaken for current guidance.
7. **SHOULD** keep infrastructure details (hosts, IPs, ports) in an operations document, not in policy documents, because they change faster.
8. **SHOULD** write for a new teammate on their first day. If setup takes more than the steps in the README, fix the README.
9. **SHOULD** keep a short documentation hub (`docs/README.md`) when `docs/` passes about ten files. It says where to start and what each document answers.

## README Minimum Sections

1. What it is, in two sentences.
2. Status and limitations. State what does not work or is not proven.
3. Quick start: prerequisites, install, configure, run, test. Commands copy-pasteable.
4. Project layout: one line per top-level directory.
5. Configuration: every environment variable, with `.env.example`.
6. How to contribute: link to branching, commit, and review guides.
7. License.

## Types of Documents

| Type | Purpose | Lives in |
|---|---|---|
| README | Orientation and quick start | repo root |
| Agent rules | Instructions to AI agents, in force | `.agents/rules/` or `AGENTS.md` |
| ADR | Costly decisions | `docs/adr/` |
| Runbook | How to operate a service | `docs/runbooks/` |
| Spec or PRD | What to build | `docs/` |
| Changelog | What shipped | `CHANGELOG.md` |
| Glossary | Domain language | `CONTEXT.md` or `docs/glossary.md` |

## Language Policy and Legacy Documents

When a language policy starts (for example, "from now on, English"), the policy **MUST** state what happens to existing documents: migrate on next edit, freeze with a `legacy` header, or delete. A policy that only says "from now on" leaves a mixed corpus.

## Claims and Badges

- A badge or number in a README **MUST** come from a tool (CI badge, coverage service) or be removed.
- Limitations belong on the first screen, not in an appendix.

## Minimum Form

- README with the sections above.
- `CHANGELOG.md`.
- Agent rules file.
- `docs/adr/` once the first decision is worth recording.

## Scale-up

- A docs site generated from the same files.
- Doc linting (links, spelling) in CI.
- Ownership per document and a yearly review.

## AI Note

- Agents read the docs you point them to. Keep the agent rules short and link to the longer documents instead of duplicating them.
- Agents generate plausible but stale docs. Review any doc an agent writes for facts it could not know (versions, URLs, counts).
- Do not let agents "refresh" historical documents. They are records, not drafts.

## Checklist

- [ ] README quick start works on a clean machine.
- [ ] Docs changed in the same PR as the behavior.
- [ ] No hand-written counts or versions that duplicate another file.
- [ ] Out-of-date documents are marked.
