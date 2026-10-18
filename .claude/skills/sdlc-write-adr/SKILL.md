---
name: sdlc-write-adr
description: "Use when a decision is costly to reverse (core technology, data model, security posture, delivery capability, or a convention). Write a one-page ADR from the template, open it for review, and link it."
---

# Write an ADR

**Trigger:** a decision that is costly to reverse. **Guide:** 09 (in `.agents/guides/`).

1. **Check whether you need one.** Does it change core tech, data model, security posture, delivery capability, or a convention? If you can undo it in a day, use the PR description instead.
2. **Pick the next number:** `docs/adr/NNNN-kebab-case-title.md`. Never reuse a number.
3. **Write it on one page,** from the template in R1:
   - **Status:** Proposed.
   - **Context:** the forces and constraints. What made this decision necessary?
   - **Decision:** specific and testable. "We will use X" plus the rules that follow from it.
   - **Consequences:** the good and the bad. If there are no downsides, you missed them.
   - **Alternatives considered:** one line each on why not.
4. **Open a PR** with the ADR (and the change, if it is small). Ask for review from the architecture steward.
5. **Discuss in the PR,** update the ADR, and set Status: Accepted on merge.
6. **Link it:** from the code or docs that implement it, and from the agent rules file when agents must follow it.
7. **Superseding:** write a new ADR, mark the old one `Superseded by NNNN`. Do not edit an accepted ADR's decision.

**With an AI agent:** provide the context and constraints, then review the "Alternatives" and "Consequences" sections hardest. Agents default to generic statements there.
