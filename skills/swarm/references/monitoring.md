# Event-driven goal watchdog

Each accepted milestone schedules exactly one lightweight wakeup at its due
horizon. CTRL always owns the tracker, including for its own durable goal; MOTHER
never receives the clock. The worker proposes the
milestone and horizon but never owns or wakes the clock. At due time the tracker
reads compact raw diff, process, test, dependency, and artifact evidence. It
does not poll early, request status prose, run a full audit per ping, or create a
monitoring task, subagent, file, or second ledger.

A successful check records its receipt and either accepts the next milestone
with one new due event or closes the goal. A documented initialization/readiness
latency condition permits one evidence-bound reschedule. Otherwise the canonical
miss ladder applies. Duplicate due delivery is idempotent because the scheduled
event is consumed once. `monitoring.heartbeat_minutes` remains only a fallback
integrity audit that recreates a lost or missing due event; it is not a second
progress clock. The scheduled receipt tied to the durable goal survives
compaction without a private heartbeat ledger.

Apply EVENT: a passive snapshot is not itself an update. Surface only changed
attention, blocker, handoff, acceptance, or release in one natural line by
default. Use host state, the latest material owner update, and the existing
receipt. Expand only when truth requires it; never impose fixed fields, narrate
routine progress, or ask owners to report more.

Internally classify observed state as `active`, `attention`, `ready`, or
`unknown`; do not call a task progressing when no material signal supports it.
Compute duration from the host timestamp for entering active production,
integration, or review. If the host does not expose it, use CTRL's first
observed active timestamp, prefix the duration with `~`, and never present it as
CPU time or uninterrupted effort.

The watchdog is an internal control surface. Do not rewrite the task-tree receipt
for unchanged observations, narrate between horizons, or repeat terminal tasks.
Missing freshness alone is unknown; only raw evidence at a consumed due event can
advance the goal or count a miss.

Count meaningful progress only when an owner returns a changed inspectable
artifact, claim-matched proof execution, a cleared prerequisite, or a newly
integrated composed result. Activity, elapsed time, task count, status prose,
planning, polling, and lane-local approval do not reset a stall. Silence alone
is not a stall. When the configured material-change threshold is reached, issue
exactly one bounded same-surface recovery; never wake or steer healthy lanes.
If the result is unchanged, return the exact blocker and unblock condition,
release or reassign under existing authority, and keep unaffected lanes moving.
Do not manufacture checkpoints, replacement owners, polling loops, queues,
daemons, or status narration.

For a deployable lane, report the LEAD's immutable integration SHA, independent
REVIEW, correction, lease, deployment, rollback, or production-proof state as
applicable. A pending
shared-surface lease is `attention`, not progress; keep disjoint lanes moving.
CTRL observes the lease receipt while MOTHER, when justified, serializes the portfolio boundary; neither absorbs the LEAD's
deployment work.

During Boost `hands_off`, keep this passive heartbeat; EVENT still decides
whether anything surfaces. Do not message, wake, steer, or poll an owner.
Terminal and attention events may still advance integration. If the host cannot
passively wait, read task state, expose timing, or control goals, report the
exact missing capability and resulting claim limit instead of pretending
continuous monitoring or compliant role startup occurred.
