# ETA and heartbeat persistence contract

Every observed task forecast keeps an immutable accepted baseline estimate and
ETA. The current forecast may change, but the baseline never does. A forecast
projection includes the current ETA range, confidence, status, declared
progress basis, last material heartbeat, last calculation time, reason code,
short human reason, and receipt/source.

Forecast revisions are append-only records with:

`time`, `previous`, `current`, `delta_from_baseline`, `confidence`,
`reason_code`, `short_reason`, and `receipt/source`.

Reports are observed task-owner planning input only; they do not prove host or
user authority, acceptance, or task progress. They must bind to an observed
task/project and a typed runtime receipt. A caller-supplied authority label is
never accepted.

Allowed reason codes are `scope_discovered`, `dependency`, `failed_proof`,
`environment`, `underestimated_complexity`, `owner_capacity_change`,
`material_progress`, `state_change`, `completion`, and `heartbeat_stale`.
Large baseline drift lowers confidence and marks the task for attention.

Heartbeats are bounded liveness events, not prompts or model calls. Emit one at
task state change, material progress/checkpoint, blocker or dependency change,
ETA revision, and completion. An active lane may receive at most one scheduled
wake. There is no repeated polling. An unchanged heartbeat updates liveness
only and creates no forecast revision. Subagent observations roll into their
master task and are never counted as a second task or second ETA.

Progress is derived only from declared milestones, checkpoints, and receipts.
No percentage is fabricated from elapsed time or token volume. Missing or
partial receipts remain `no_data` or `partial` for the UI.
