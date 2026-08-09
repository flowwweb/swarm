# Passive heartbeat

MOTHER keeps a current operational view of the hierarchy without waking or
steering owners. At each `monitoring.heartbeat_minutes` interval, inspect every
active descendant in the existing task tree: direct children and grandchildren
at minimum, plus deeper active descendants when present.

Prefer a passive host snapshot such as a bounded `wait_threads` timeout using
current cursors. Batch only when the host limits targets. Use a read primitive
only when passive wait is unavailable or an attention event needs detail. Never
send a task message merely to request heartbeat status, and never create a
monitoring task, subagent, file, or second ledger.

For each active task, emit one sentence in task-tree order:

```text
<title> — <state>: <current artifact or material progress>; working <duration>.
```

Use only host state, the latest material owner update, and the existing receipt.
States are `active`, `attention`, `ready`, or `unknown`; do not call a task
progressing when no material signal supports it. Compute duration from the host
timestamp for entering active production, integration, or review. If the host
does not expose it, use MOTHER's first observed active timestamp, prefix the
duration with `~`, and never present it as CPU time or uninterrupted effort.

The heartbeat is an ephemeral user control surface. Do not rewrite the task-tree
receipt for unchanged observations, narrate between intervals, or repeat terminal
tasks after their handoff has been reported. A heartbeat observation is neither
a work update nor an unchanged update for stall accounting. Missing freshness
alone reports `unknown`; it does not authorize messaging, recovery, interruption,
or reassignment. A real failure, attention event, or material stall continues
through the existing bounded recovery rules.

During Boost `hands_off`, keep this passive heartbeat and compact user summary,
but do not message, wake, steer, or poll an owner. Terminal and attention events
may still advance integration. If the host cannot passively wait, read task
state, or expose timing, report the exact missing capability and the resulting
claim limit instead of pretending continuous monitoring occurred.
