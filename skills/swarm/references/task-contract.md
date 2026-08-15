# Compact task contract

Use CORE + role + these fields. Atomic/simple tasks omit every inapplicable field. A durable task keeps only its exact current decision and proof boundary.

For every new SWARM objective, the opening user-visible task completes mandatory
Step 0 first: derive a concise specific objective, use the host task-title tool to set
`🐙CTRL - <objective>` by default, pin the task, and verify both receipts. Only
`role_icons.enabled = false` removes title emojis. If a tool is unavailable or a receipt fails, state the exact blocker
and continue only with truthful internal CTRL identity. Only then create or
continue exactly one matching durable goal before routing work. Its contract
records the chosen topology and which visible task owns each mutable artifact.
Hidden subagents are execution capacity, not a replacement for required SWARM
task ownership.

```text
ROLE — artifact
PURPOSE: objective and acceptance/non-negotiables.
OWNERSHIP: owner, exact mutable surface, canonical artifact/version.
BOUNDARIES: dependencies, proof/claim limits, no hidden scope change.
ESCALATION: accepting route or exact blocker.
MODE: CTRL_DIRECT or CTRL_DELEGATED, with the direct-work predicate receipt.
GOAL: stable goal ID, objective version, measurable milestone, and locally chosen review horizon; optional WATCHDOG binding is separate and names the watched owner plus validated alert route.
ACCEPTANCE: typed lane kind, exact ArtifactIdentity, required named gates, bound owning LEAD identity, and accepting REVIEW route; CODE has at least one gate and only NON_CODE non-artifact work may use an explicit empty contract.
INCIDENTS: LEAD consultation receipt for matching unresolved `.codex/swarm/incidents.jsonl` records.
```

An objective amendment increments the version and records authority, reason, requirements delta, new baseline, and prior-miss relevance. A genuinely new project links a distinct successor goal; it never rewrites the prior history.

## Durable request ledger

Each accepted user request has one private, atomic repo-local record: safe request/goal/task IDs, accountable owner, derived outcome digest, accepting route, next due event, state, safe evidence/transition receipts, the last published event/message/surface plus feed sequence, and immutable history. Never store raw user text, artifact body/path, credentials, or host identity claims. `OPEN` and `BLOCKED` remain unresolved through interruption, restart, heartbeat, reprioritization, or objective amendment. Only evidence-backed completion, explicit user supersession, or explicit user cancellation is terminal. The ledger is continuity, not task/gate/review authority: reload must revalidate current runtime facts before a composed or archive claim. A fresh runtime derives its feed-sequence floor from the persisted cursor and accepts only a newly published, fully validated later event; it never reconstructs old feed authority.

Use `REQUEST_PENDING` only between durable staging and matching acceptance/activation. It is non-runnable and blocks worker/artifact work, stale/collapse handling, closeout, and archive until accepted or CTRL rolls it back from an exact surfaced blocker. A single record changes per lifecycle call; shared proof can advance multiple same-task requests only through separate calls. CTRL cannot silently delete or overwrite an accepted request.

Integration-ready means immutable artifact identity, required proof state, and an explicit accepting route. `UNVERIFIED` remains open. A composed rendered product needs its composed render comparison when visual work is in scope.

Gate receipts use only `PASS`, `FAIL`, or `TIMEOUT` and name the exact contract
artifact. Source-semantic review cannot close the lane. A material defect found
after handoff adds one local causal record; minor failures do not. Daily fold may
generalize only distinct repeated or demonstrably generalizable candidates backed
by contrasting regression proof; ineligible candidates remain pending until an
explicit reasoned rejection. The private Git-ignored ledger uses structured safe
evidence references and serialized cross-process updates, never a repo command,
person-specific rule, or credential value.

A SPECIALIST interface is only a current decision/dependency reference. The specialist persists one exact cross-cutting truth surface; it does not acquire a lane. Record both the short profession and a stable instance identity so multiple specialists—including multiple ARCHITECTs, MOTHERs, or DEVELOPERs—can coexist without overlapping ownership. MOTHER is advisory only. A DOER may use a temporary wildcard ASSIST for a bounded independent subtask, but never for acceptance or authority transfer. Detailed role and recovery rationale is lazy-loaded from the matching reference.

WATCHDOG is not a role or task-contract owner. When explicitly bound, its receipt
records only the goal, watched owner, due evidence digest, one of `CLEAR`,
`ATTENTION`, or `BLOCKER`, and the validated accountable decision owner. It never
records or authorizes a recovery decision.
