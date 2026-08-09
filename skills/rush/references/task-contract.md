# Compact task contract

Aim for 120 words or less. Use only the lines that carry a current decision,
boundary, or proof obligation; link source material instead of pasting history,
doctrine, or a crew map. Exceed the target only when required to preserve a
material safety, authority, or outcome constraint.

```text
<role-icon>ROLE - artifact name

Surface: user-visible host task; parent task title/ID. In Codex, use a Codex task.
Execution: active usage profile; resolved role model/reasoning; requested tier.
Portfolio outcome: full user result this artifact must preserve.
Outcome/FUA: one inspectable user-relevant artifact.
Non-negotiables: exact must-haves this lane may not redefine.
Owns: exact mutable paths or external authority; prior owner release when transferred.
Boundaries: collisions and authority limits, never a hidden scope cut.
Input: exact revision and essential sources.
Execute first: first artifact-producing action; exact non-mutating surface receipt when consequential.
Heartbeat: active-since source and one-sentence material status; passive reads only.
Done/proof: observable completion and claim-matched checks.
Review route: reviewer or accepting task title/ID.
Child-task authority: none, or a bounded named child set for this owner.
Internal delegation: bounded subagents allowed or disallowed; never portfolio lanes.
On stall: configured recovery budget, then exact blocker and release.
Stop/handoff: terminal condition, accepting route, and immediate successor/unblock when deferred.
```

The template is a selection guide, not a form. Always preserve the outcome,
ownership, boundaries, proof, and terminal handoff; omit other lines when they
add no useful control. Add spend, viewport, rollback, or serial-handoff
constraints only when relevant. Do not prescribe an unrequested implementation
choice.

Ready for review stops active work and frees capacity, but the owner remains the
mutable correction route until acceptance, explicit transfer, or exact blocker.
Before any transfer, the old owner stops and releases, MOTHER records it in the
existing receipt, and the new owner acknowledges it; uncertainty stays
read-only. If the accepting route cannot receive a terminal handoff, try once,
take one liveness snapshot, then send the unchanged immutable handoff to the
nearest live ancestor or user and release. Never self-accept.

Before sending, verify that the task:

- fits no active owner;
- produces a concrete outcome rather than speculative reuse;
- cannot collide with another mutable owner;
- invents no product behavior or acceptance threshold;
- preserves portfolio non-negotiables and requested consequential capabilities;
- is a user-visible host task when it represents a RUSH portfolio lane;
- uses the configured role model and reasoning when the host supports and
  permits saved-config selection, or when its required direct request exists;
- starts with exactly one configured role emoji and uses MOTHER, STEP MOTHER,
  LEAD, or a concise contextual task role at the correct hierarchy level, with
  no separator between the emoji and that role;
- uses one familiar role word when possible and a short concrete artifact;
  prefer fewer characters when the result stays clear and obvious, but keep a
  longer label when it is the most accurate familiar term;
- does not substitute a subagent for a required Codex task;
- has an event-driven review return and terminal handoff instead of polling or
  waiting without an escalation route.

When child-task authority is granted, use `coordination.preferred_lane_width`
as a soft shape for already-justified children. It is not permission to create
children, a required count, or a hard maximum. STEP MOTHER and LEAD contracts
name their bounded child set. TASK, REVIEW, and consequential planning owners
may receive the same authority only when every child independently passes the
normal lane test; otherwise they keep bounded subtasks internal.

The handoff returns the artifact, proof, unresolved P0-P2 issues, claim limits,
and accepting owner. It does not self-accept.

## Provisioning receipt

If creation returns only a provisioning handle, take one bounded inventory or
host-supported setup observation. A handle is setup evidence, not delegation.
Without a materialized task ID or host resolver, classify it as unmaterialized
setup failure: it has no owner, consumes no capacity, and cannot block a
duplicate retry. Preserve the handle only as diagnostic evidence, then spend the
configured recovery budget on one representative canary retry through a real
user-visible host task surface, preferably removing a suspect optional setup
parameter without changing the artifact contract. Fan out only after a real task
ID starts material work. While setup is unresolved, MOTHER may perform immediate
safety containment only; all non-emergency artifact work remains delegated and
must not be absorbed into MOTHER or hidden work. If the canary also remains
unmaterialized, stop creation and report the exact host setup blocker.
