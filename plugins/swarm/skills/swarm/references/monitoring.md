# Optional alert-only WATCHDOG

WATCHDOG is an alert-only scoped sensor, not a role, worker, reviewer, manager,
planner, or acceptance authority. It may bind to an accountable LEAD or
persistent SPECIALIST goal, never CTRL. Do not create a watchdog task or role
card. An unbound goal has no watchdog clock, check, receipt, or alert.

An explicit binding names one durable goal, its watched owner, and one acyclic
alert route of existing stable role/ID targets ending at CTRL or human attention.
At most one watchdog and one due event may exist for a goal. No identity repeats.
Ordinary alerts route first to the watched owner. An owner-integrity alert skips
that owner and follows the prevalidated route to existing authority. REVIEW may
investigate and surface disputed evidence but gains no acceptance authority.

At the due event or a material failure signal, WATCHDOG performs exactly three
checks:

1. **Progress:** milestone, deadline, goal alignment, raw artifact, diff,
   process, test, and dependency evidence.
2. **Flow integrity:** blocked dependencies, ownership collisions, duplicate
   effort, stale owners, idle capacity, and unnecessary topology.
3. **Outcome integrity:** user intent, applicable quality guidance, role
   authority, required gates, independent review, and proof claim limits.

It emits only `CLEAR`, `ATTENTION`, or `BLOCKER`, with compact evidence and the
exact accountable decision-owner role/ID from the validated route. `CLEAR` is
internal. An unchanged evidence digest, severity, and decision owner produces no
duplicate surfaced alert. Only material evidence, severity, or accountable-owner
change may surface again.

`ATTENTION` for optimization or adaptation requires demonstrated benefit clearly
greater than coordination overhead plus change cost. The smallest reversible
candidate wins; a larger structural change requires proportionally stronger
evidence. `BLOCKER` means progress, flow, quality, authority, proof, or goal
alignment is materially broken. WATCHDOG reports the consequence; it never
selects or applies a correction.

A usage WATCHDOG remains bound to the accountable LEAD goal and samples only
bounded host-reported usage/capacity receipts at its declared due event or a
material capacity signal. Classify that snapshot as `FLOW_INTEGRITY`. Keep
`CLEAR` internal. Surface `ATTENTION` only when a material threshold,
capacity state, or decision owner changes. Use `BLOCKER` only when no permitted
task or subagent structure can progress. A usage limit alone is adaptation
evidence for the next safe boundary, not an interruption or blocker.

One evidence-backed readiness delay may reschedule once. Repeated misses increase
severity and route the alert to the next accountable owner; they do not create
another authority or authorize recovery. Clock and receipt maintenance is the only
WATCHDOG mutation. It cannot poll early, request status prose, reassign, recover,
collapse, restructure, spawn, implement, review, gate, accept, or invent proof.

Missing, self-referential, cyclic, fabricated, or wrong-scope routes fail closed
and emit no authoritative receipt. A WATCHDOG receipt can never satisfy a named
gate, independent REVIEW, lane completion, or final composed acceptance.

## Owner-heard micro-review after an alert

An alert opens a short evidence case; it is not a fault finding. The normal case
is asynchronous and includes the accountable decision owner and watched owner.
The watched owner receives the evidence, provides causal context and a preferred
remedy, and may identify an external constraint such as connectivity, provider
failure, unavailable credentials, dependency blockage, or a bad plan. Add at
most one independent SPECIALIST or REVIEW only when evidence is technically
disputed, the owner may have crossed an integrity boundary, or the decision
owner lacks the relevant expertise. Do not create a meeting, quorum, committee,
or recurring status ritual.

Before consequential change, the decision owner records:

- the best-supported cause: external constraint, dependency/authority blockage,
  plan mismatch, execution gap, or unknown;
- remaining uncertainty and the watched owner's account;
- the same-constraints counterfactual: whether another owner or topology would
  probably have produced a better result;
- expected benefit versus transition, coordination, correction, and change cost;
- the smallest reversible response and its revisit or reversal condition.

A single delay, outage, tool/provider failure, or ambiguous alert cannot remove
an owner. Start with continue/observe, remove the external blocker, clarify the
plan, add bounded help, or adjust the deadline. Reassignment, retirement, or
structural change requires repeated comparable evidence or a clear safety,
authority, or integrity breach, plus benefit greater than total transition cost.

Urgent safety, security, destructive-action, or authority risk may justify
temporary containment before the owner responds. Preserve evidence, name the
reversal condition, and never represent containment as a permanent competence
judgment. If the owner is genuinely unreachable past the verified decision
horizon, make only the smallest reversible continuity change and revisit it when
the owner can respond. Consequential CTRL-owner decisions remain human-owned.

## CTRL feed integrity

The optional WATCHDOG checks valid bound requests without becoming their owner: the intake/acceptance surface is not work progress, so a due open request without a later surfaced transition is `ATTENTION/OUTCOME_INTEGRITY`; due blocked or later-progressed-but-idle is `ATTENTION/TRAJECTORY`. Orphaned, unsurfaced, and idle records remain explicit CTRL audit blockers. An orphan derives one fixed global `BLOCKER/FLOW_INTEGRITY` signal routed to CTRL; this is not a WATCHDOG identity, task/CTRL binding, receipt clock, decision, or mutation. A bound sensor emits only through its exact eligible LEAD/SPECIALIST binding, never CTRL, and cannot transition, recover, reprioritize, complete, or correct a request.

WATCHDOG may audit recent CTRL messages against EVENT's outcome, inline proof,
remaining risk, and next material checkpoint order. Activity narration, task
chatter, fabricated proof, or duplicate orchestration detail fails closed and
requires one compliant correction. Unchanged snapshots remain silent. This feed
check does not expand WATCHDOG beyond the three responsibilities above.
