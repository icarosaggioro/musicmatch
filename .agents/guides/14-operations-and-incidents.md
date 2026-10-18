# 14. Operations and Incidents

## Rules

1. **MUST** give every production service a **runbook**: what it does, how to start, stop, and check it, where the logs are, how to roll back, and who to call.
2. **MUST** expose a health endpoint (guide 12) and know who looks at it.
3. **MUST** name an **owner** and a **backup owner** for each service. One person alone is a single point of failure.
4. **MUST** define severities and what each requires.
5. **MUST** run a blameless post-incident review for every Sev 1 and Sev 2 incident, within five working days.
6. **SHOULD** centralize logs and keep enough history to investigate (for example 30 days), with no secrets or personal data in them.
7. **SHOULD** alert on symptoms users feel (errors, latency, unavailability), not on every internal metric.
8. **SHOULD** keep an incident log (date, impact, cause, fix, follow-ups) as a searchable list.

## Severities

| Level | Definition | Response |
|---|---|---|
| Sev 1 | Service down, data loss or exposure | Drop everything. Roll back first, diagnose after. |
| Sev 2 | Major feature broken, or significant degradation | Same day. Fix or roll back. |
| Sev 3 | Minor defect with a workaround | Normal queue. |
| Sev 4 | Cosmetic or low impact | Backlog. |

## Incident Procedure

1. **Detect:** alert or report. Note the time.
2. **Declare:** name an incident lead and a communicator. Open a channel or thread.
3. **Stabilize:** prefer rollback over a fix-forward unless rollback is the riskier option. Preserve evidence (guide 13).
4. **Communicate:** tell affected users in plain terms, then update at a regular interval.
5. **Resolve:** confirm with the healthcheck and a smoke test.
6. **Review:** write the post-incident review (template in R1) and open issues for follow-ups.

## Post-Incident Review

Blameless, factual, and short. It contains: timeline, impact, root cause, what worked, what did not, and action items with owners and dates. Ask "what let this happen?", never "who did this?".

## Solo Profile

Applies when `ships-to-users: yes`. Stabilize (prefer rollback), preserve evidence, and write a five-line note afterwards: what happened, when, cause, fix, follow-up. Keep one page of runbook per service. The severity table and the formal blameless review apply in the team profile.

## Minimum Form

- A runbook per service.
- A health endpoint.
- Severity table and a named owner.
- A post-incident review for serious incidents.

## Scale-up

- On-call rotation and paging.
- Error budgets and formal SLOs.
- Game days and chaos testing.
- Status page for customers.

## AI Note

- Agents can summarize logs and draft timelines, which helps. They **MUST NOT** change production state during an incident unless a human incident lead directs the exact action.
- Runbooks are good agent inputs: write them as clear, ordered steps with commands and expected output.
- Log agent actions on production-adjacent systems so a post-incident review can reconstruct what happened.

## Checklist

- [ ] Runbook exists and was read by someone who did not write it.
- [ ] Owner and backup named.
- [ ] Health endpoint reports every dependency.
- [ ] Incident review scheduled for Sev 1 and Sev 2.
