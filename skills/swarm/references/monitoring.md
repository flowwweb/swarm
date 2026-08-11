# Passive heartbeat

MOTHER keeps a current operational view of the hierarchy without waking or
steering owners. At each `monitoring.heartbeat_minutes` interval, inspect every
active descendant in the existing task tree: direct children and grandchildren
at minimum, plus deeper active descendants when present. The heartbeat state is
carried by the task tree and each role's active durable goal so it survives
compaction or continuation; never create a private heartbeat log.

Prefer a passive host snapshot such as a bounded `wait_threads` timeout using
current cursors. Batch only when the host limits targets. Use a read primitive
only when passive wait is unavailable or an attention event needs detail. Never
send a task message merely to request heartbeat status, and never create a
monitoring task, subagent, file, or second ledger.

Apply EVENT: a passive snapshot is not itself an update. Surface only changed
attention, blocker, handoff, acceptance, or release in one natural line by
default. Use host state, the latest material owner update, and the existing
receipt. Expand only when truth requires it; never impose fixed fields, narrate
routine progress, or ask owners to report more.

Internally classify observed state as `active`, `attention`, `ready`, or
`unknown`; do not call a task progressing when no material signal supports it.
Compute duration from the host timestamp for entering active production,
integration, or review. If the host does not expose it, use MOTHER's first
observed active timestamp, prefix the duration with `~`, and never present it as
CPU time or uninterrupted effort.

The heartbeat is an ephemeral user control surface. Do not rewrite the task-tree
receipt for unchanged observations, narrate between intervals, or repeat terminal
tasks after their handoff has been reported. A heartbeat observation is neither
a work update nor an unchanged update for stall accounting. Missing freshness
alone reports `unknown`; it does not authorize messaging, recovery, interruption,
or reassignment. A real failure, attention event, or material stall continues
through the existing bounded recovery rules.

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
MOTHER observes and serializes the lease boundary but does not absorb the LEAD's
deployment work.

During Boost `hands_off`, keep this passive heartbeat; EVENT still decides
whether anything surfaces. Do not message, wake, steer, or poll an owner.
Terminal and attention events may still advance integration. If the host cannot
passively wait, read task state, expose timing, or control goals, report the
exact missing capability and resulting claim limit instead of pretending
continuous monitoring or compliant role startup occurred.
