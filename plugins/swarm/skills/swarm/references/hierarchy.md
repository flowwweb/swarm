# SWARM hierarchy and specialist roles

Read this reference when shaping topology, selecting an owner, creating a
user-visible task, adding a SPECIALIST, or transferring ownership.

## One root, the shallowest useful shape

CTRL is the sole root and final composed authority. Use `CTRL_DIRECT` only for
one low-risk atomic outcome on one mutable surface with no cross-lane dependency
and measurable completion inside the direct-work horizon. Otherwise CTRL hires
a LEAD. A LEAD may hire DOERs for separable work that shortens accepted proof.

An existing CTRL never creates another CTRL by inference. CREATE, FORK,
PROMOTE, REPLACE, RENAME, SUCCESSOR, and RECOVER_AS_NEW each require a current
single-use explicit user authorization independently enforced by the actual
host task API and bound to the source CTRL, operation, target identity,
objective, and scope. A plugin-runtime request is non-authoritative. Missing,
mismatched, replayed, or in-process-only evidence emits a human-authority
blocker and no host action. Same-identity
restore is not CTRL creation; Researcher, Architect, LEAD, DOER, and REVIEW are
ordinary subordinate roles and do not consume CTRL authorization.

Create a visible task lane when any durable boundary matters: independent or
resumable ownership, a separate mutable surface or artifact, worktree isolation,
independent review or acceptance, separate handoff, or interruption-safe resumption.
Economics never overrides this boundary. Large work also uses a task
lane. Otherwise bounded small-to-medium work may use an in-task subagent when it
stays on one mutable surface and task startup, worktree, coordination, handoff,
integration, and review overhead do not clearly repay themselves. A subagent
never owns durable work and never replaces a qualifying visible lane merely
because it is easier to spawn.

Use this routing order:

1. Keep one atomic outcome with the current owner when coordination costs more.
2. Open a visible task lane when a durable boundary above applies.
3. Add a subagent only for bounded capacity within that lane.

If the host cannot create a required visible task, record the exact capability
blocker. A degraded subagent remains under the current accountable owner and
must bind an immutable checkpoint, task-topology resumption marker, and every
affected gate as `UNVERIFIED`; it cannot satisfy ownership, handoff, independent
review, or acceptance. Do not disguise a subagent as durable ownership. Artifact count,
configured capacity, shared keywords, and a visually complete tree never
justify a lane.

An internal approval gate is failed capacity, not a user decision. Cancel that
helper attempt, record the typed host-gate exception, and continue the same
bounded owner work without asking the user; user-reserved choices retain their
normal approval gates.

Choose the evidence-backed initial topology before the first mutable handoff.
Recompute it only when material task evidence changes an ownership, dependency,
integration, or acceptance fact; user direction remains the highest constraint.

Every durable CTRL, LEAD, and persistent SPECIALIST has one active goal with an
objective, stopping condition, authority boundary, and required proof. Finite
DOER, TASK, SUBTASK, ASSIST, ADVISOR, and REVIEW work does not automatically own
a goal. Goal ownership never grants topology, mutation, review, or acceptance
authority.

## Authority

CTRL owns the durable accepted-request inventory and human route; a LEAD owns each delegated request's live task and evidence transitions. Stored history never restores authority after restart. WATCHDOG may alert an eligible bound owner about a valid request, while orphaned records return only to CTRL's completion audit and never manufacture a sensor identity or correction.

| Function | Owns | Does not own |
| --- | --- | --- |
| CTRL | Intake, objective ledger, topology, authorized user-visible task materialization, shared-surface coordination, final composed acceptance, human route | Another CTRL without exact user authorization, LEAD implementation, or independent REVIEW |
| LEAD | One lane, decomposition, integration, incident consultation, exact-artifact gates, correction loop, lane completion, authorized deploy and rollback | Other lanes or final portfolio acceptance |
| DOER | One bounded workstream and its artifact handoff | Self-acceptance or topology |
| TASK / SUBTASK | One bounded artifact or execution unit | Parent ownership or acceptance |
| ASSIST | One temporary bounded assignment | Persistent ownership, integration, review, acceptance, or further authority |
| SPECIALIST | One persistent named truth surface, its invariants, evidence, and advisory gate | Scheduling, ownership transfer, mutation, integration, deploy, review, or acceptance |
| ADVISOR / EXPERT | One focused answer with evidence | Artifact ownership or authority |
| REVIEW | Independent verdict on the frozen plan or frozen completed artifact | Implementation, self-correction, deploy, or final composed acceptance |

CTRL may complete direct work only through its declared direct-work contract.
LEAD alone completes a LEAD-owned lane after independent exact-artifact review.
CTRL composes accepted lanes; it cannot impersonate LEAD or REVIEW.

## CTRL is orchestration, not default execution

Classify the actual work before mutation. CTRL may directly perform bounded
read-only inspection, coordination, plan/goal/receipt work, shared-surface
integration, and final composed acceptance. Substantive artifact-producing work
such as code edits, generated media, or provider/device/deploy actions routes to
a LEAD-owned lane with bounded DOER work whenever qualifying host lane capacity
is available. A qualifying lane is a routing fact, not a project, brand, route,
asset, or screen-specific rule.

The existing `CTRL_DIRECT` predicate remains a safe direct-work exception for a
single low-risk atomic outcome on one surface with no cross-lane dependency and
a measurable bounded horizon. It is an explicit exception recorded in the task
contract, never permission for CTRL to become the implementation owner by
default. Explicit user direction may change the default route only within the
recorded authority, safety, and host boundaries.

When no qualifying lane capacity exists, CTRL does not silently do the worker
work. Record the exact host capacity observation and one typed exception (for
example the existing capacity, host-gate, collision, or safety exception), bind
an immutable checkpoint and resumption marker when bounded fallback is allowed,
and leave affected proof gates `UNVERIFIED`. A hard block is preferable to an
unrecorded role violation.

## One-pass CTRL routing record

For each new user prompt that may cause mutation, CTRL resolves one compact
routing record before the first handoff or edit:

| Field | Required decision |
| --- | --- |
| `OBJECTIVE` | The user outcome and stopping condition |
| `OWNER` | Role plus exact mutable surface/artifact |
| `MODE` | `CTRL_DIRECT` for bounded read-only/coordination or genuinely atomic low-risk work; otherwise a LEAD lane with bounded DOER work |
| `DEPENDENCIES/PROOF` | Relevant dependencies, claims, gates, and accepting evidence |
| `CAPACITY` | Current host lane/subagent availability, configured ceilings, and exact receipt |
| `ACCEPTING_ROUTE` | Named LEAD/REVIEW/CTRL route that can accept the result |

This is a routing pass, not a heavyweight planning graph. Recompute only when
material evidence changes the owner, surface, dependency, capacity, or accepting
route. Before spawning any subagent, check both host availability and configured
WIP/parallel ceilings. A full ceiling records the typed `CAPACITY` exception and
keeps the work waiting or hard-blocked; it never authorizes CTRL to perform the
DOER work silently.

For new subagent/DOER assignments, the packaged medium profile defaults to
`gpt-5.6-luna` at `xhigh` within the model's declared capabilities. A user,
host, or project selection always wins. CTRL may choose another advertised
model/reasoning pair only when the choice is not explicit, and records the
adjustment plus its risk, latency, cost, and proof basis; it never overwrites
an explicit selection.

## MOTHER is an optional manager SPECIALIST

MOTHER is a profession under SPECIALIST, not a root or coordinator authority.
Materialize it only when a persistent coordination truth surface across lanes
will save more friction than it costs.

- Purpose: keep dependencies, risks, handoffs, and recommendations coherent.
- Ownership: that concise truth surface and its receipts only.
- Boundaries: observe, synthesize, advise, and escalate; never create or
  reparent tasks, assign owners, amend objectives, lease surfaces, integrate,
  deploy, review, accept, or turn a WATCHDOG alert into action.
- Escalation: return an evidence-backed recommendation or exact blocker to CTRL;
  CTRL decides.

Historical MOTHER titles and config remain readable as this profession. They
never recreate old topology, lease, review, or acceptance authority.

## Specialists, advisors, and temporary help

Before the first affected mutation, add a persistent SPECIALIST only when one
named cross-cutting truth must remain coherent across lanes. The contract names
its profession, stable instance identity, truth surface, invariants, and gate.
ARCHITECT, ENGINEER, DEVELOPER, DESIGNER, RESEARCHER, ANALYST, STRATEGIST, and
MOTHER are examples, not an allowlist. Profession is not singleton; multiple
instances may share it only when stable identities, truth surfaces, and accepting
routes do not overlap.

Task size and task count alone do not justify a persistent SPECIALIST. Neither
do risk labels or profession availability. If a qualifying cross-cutting truth
emerges later, stop the next affected mutation, bind the truth surface and gate,
then resume only the affected work.

Use ADVISOR or EXPERT for one bounded uncertainty delaying accepted proof, never artifact ownership.
Use ASSIST as temporary surge capacity for one bounded result. None of them
receives authority merely because it found an issue.

When a DOER has two or more independent subtasks and child capacity, delegate
worthwhile slices promptly. Do not force delegation when startup, collision,
safety, privacy, or whole-task cost would erase the benefit. The current owner
retains integration and accountability.

## Capacity and dependencies

Measure task startup from host receipts when available: request-to-ID, ID-to-ready,
ready-to-first-material-result, worktree setup, orientation/handoff, and
host-reported usage. Before enough comparable samples exist, use conservative
explicit assumptions and label them; never present estimates as observed usage.
Use a rolling median only after five comparable samples. A required durable
boundary still wins regardless of cost. Otherwise split work only when expected critical-path
savings clearly exceed startup, worktree, coordination, handoff, integration,
and review cost. Keep the bounded slice inside its current owner when it does not.

Parallelize only disjoint lanes that can return integration-ready artifacts.
Explicit dependencies wait on their named stage; overlapping mutation is
serialized by CTRL through an explicit shared-surface receipt. A failure pauses
only its affected surface while safe independent lanes continue.

### Lightweight parallelism graph

The runtime classifies every lane with the same small record: objective, owner,
lane type, mutable surfaces, proof requirements, explicit ordering or proof
dependencies, named exclusive resources, and a host-capacity key/receipt. The
lane type is descriptive and does not create a category-specific queue. Code,
research, architecture, automation, payment, design, QA, and future lane types
follow the same rule: independent records may share a parallel group.

CTRL serializes a candidate only when the graph observes an overlapping mutable
surface, an explicit dependency, a matching destructive/provider/exclusive lock,
or exhausted host capacity for that capacity key. A full capacity key creates a
typed pending/blocked record containing the host observation and the next
release condition. It never silently waits, changes the owner, or lets CTRL do
the worker's substantive work. Unrelated capacity keys continue concurrently.

The single `WORK_LEDGER` identity travels through `REQUEST -> ASSIGNED ->
PROGRESS`, then to `BLOCKED` (with the exact observation and release condition)
or `ACCEPTED` (with proof), and finally `CLOSED`. The older accepted-request
inventory remains compatible as a continuity view; it is not a second progress
authority and does not mint a new identity at assignment or blocking.

Configured task counts, lane widths, and review capacity are ceilings, never
creation targets. Ready immutable handoffs free execution capacity while the
original owner retains correction accountability until acceptance or transfer.

## Ownership, transfer, and materialization

Materialize each justified LEAD, persistent SPECIALIST, DOER, TASK, SUBTASK, and
independent REVIEW as a host task when the host supports it. Materialize ASSIST
and ADVISOR only for their bounded assignment. Never create a role to fill a
tree, and never treat an internal subagent as a durable owner.

Count only a host-confirmed task ID as a live owner. A pending creation receipt
reserves its objective, artifact, mutable surface, and accepting route; do not
create a replacement until it resolves. If a duplicate materializes, stop it
before mutation, transfer unique evidence, and archive it.

Never overlap mutable ownership. The old owner releases, the task-tree receipt
records the transfer, and the new owner acknowledges before mutation. Peer
coordination can exchange immutable handoffs but cannot mutate another owner's
surface or bypass REVIEW.

With role icons enabled, use `🐙CTRL - <objective>` for the root,
`<domain emoji>LEAD - <responsibility>` for lane owners, and
`<role emoji><PROFESSION> - <truth surface>` for specialists, including
`🐝MOTHER - <coordination truth>`. A title is a readability signal, never an
authority token.
