# RUSH to SWARM migration map

| RUSH mechanism | Decision | SWARM destination | Compatibility |
| --- | --- | --- | --- |
| Outcome, proof, subtraction, and general-rule doctrine | KEEP / MERGE | compact `SKILL.md` principles | preserves outcome and claim limits |
| MOTHER, LEAD, ARCHITECT, DOER, REVIEW guidance | PROMOTE | runtime authority checks | legacy titles remain readable |
| TASK, SUBTASK, ASSIST, ADVISOR | MERGE / REFINE | DOER task granularity and EXPERT advice | old records remain projection aliases |
| Role-bound model config | REFINE | intelligence tiers separate from authority | RUSH config remains accepted |
| Heartbeat and one-recovery guidance | PROMOTE | liveness, WAITING, deadlock, recovery transitions | existing heartbeat semantics retained |
| Console title/timestamp inference | REFINE | CTRL/observability projection | no new canonical authority |
| Immutable handoffs and review contract | PROMOTE | leases, integration identity, independent review gate | review remains required |
| RUSH user-facing names | RETIRE from new surfaces | SWARM metadata, docs, console copy | legacy config/commands/state remain readable |

## Adaptive depth

SWARM does not require a fixed hierarchy. Atomic work routes `CTRL → DOER`; simple work earns MOTHER only when orchestration/state/lifecycle helps; a LEAD appears for a genuine independent workstream; ARCHITECT and multiple LEADs appear only for real cross-cutting system design. Runtime selection considers scope, architecture impact, independent tasks, dependencies, uncertainty, blast radius, specialisation, useful parallelism, and coordination cost. As work narrows, idle workers retire and a no-longer-needed LEAD collapses to a smaller route without restarting compatible work.

## Result

Preserved: outcome fidelity, least-useful hierarchy, bounded recovery, evidence-matched review. Simplified: role language and configuration. Promoted: authority, lifecycle, liveness, version, lease, and completion invariants. Retired: duplicate organisational labels and new RUSH-facing product language.

The public migration must rename the existing repository rather than bootstrap a new unrelated history. Before that external action, scan the complete Git history for secrets and independently review the exact SHA.

## Hygiene and configuration

`hygiene` is the compact global policy surface: zero-day NONE archiving after verification, LOW/HIGH review windows, stale delay, completed retention, and pinned policy. It joins the existing validated identity, roles, model/reasoning, lane/WIP, heartbeat/retry, review, lifecycle, telemetry, compatibility, and CTRL settings. The loader uses packaged defaults then one selected global config; direct user, project, and session instructions may govern task behavior but are not configuration file-merge layers. Invalid input fails clearly. Safety invariants stay outside configuration.

`efficiency.mode` accepts CONSERVE, BALANCED, FAST, or MAX (default BALANCED); `efficiency.doer_wip_limit` accepts 1-8 (default 3) and controls bounded worker ownership. The loader supports packaged defaults plus one selected global config path only; it does not merge project or invocation configuration. Restore reactivates an archived task while retaining an immutable archive-history entry with its timestamp, prior state, and restore reason.
