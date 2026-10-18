---
name: sdlc-incident
description: "Use during a production incident or outage. Assess severity, stabilize first (prefer rollback), preserve evidence, communicate, resolve, and write the post-incident note."
---

# Respond to an Incident

**Trigger:** alert, user report, or failed deploy. **Guide:** 14 (in `.agents/guides/`).

1. **Assess severity** using the table in guide 14. When unsure, treat it as higher.
2. **Declare:** name an incident lead and, if there are enough people, a communicator. Open a thread or channel. Note the time.
3. **Stabilize first.** Prefer rollback (`sdlc-rollback`) over a fix-forward unless rollback is riskier. Stop the damage before finding the cause.
4. **Preserve evidence:** logs, database copies, metrics screenshots, the failing request. Do not overwrite.
5. **Communicate:** one short message to affected users: what is wrong, what you are doing, when you will update. Then update on a regular interval.
6. **Diagnose** with the evidence. Write down hypotheses and what you check.
7. **Resolve:** fix or roll back, verify with the healthcheck and a smoke test, watch the system for a while.
8. **Close:** announce resolution and what users should do.
9. **Review within five working days:** blameless, with timeline, impact, root cause, what worked, what did not, and action items with owners.
10. **Follow through:** the action items become issues and get done.

**Roles:** one person decides, one person does, and one communicates. In a team of one, write the notes as you go and use the review to catch what you missed.

**With an AI agent:** use it to summarize logs and draft the timeline. Only a human acts on production, and every agent action on production-adjacent systems is logged.
