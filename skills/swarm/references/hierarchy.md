# SWARM hierarchy and specialist roles

Read this reference when shaping a portfolio, creating user-visible tasks,
selecting ASSIST, naming roles, or transferring ownership.

## Choose the smallest useful shape

- Use CTRL_DIRECT only for one low-risk atomic outcome on one mutable surface,
  with no cross-lane dependency and measurable completion inside the configured
  direct-work horizon. Otherwise CTRL hires a LEAD. LEAD may build a cohesive
  domain seam and hires DOERs for separable work that shortens accepted proof.
- Visible tasks are durable topology. Subagents are bounded capacity within an
  existing owner and never become topology; unavailable visible capacity uses
  the typed capacity exception rather than a fabricated owner.

- Every `CTRL_DELEGATED` and non-CTRL SWARM task delegates at least one bounded
  outcome-critical slice to a subagent before substantive execution by default.
  The owner retains integration and acceptance. Only unavailable capacity, a
  host gate on internal helper creation or a read-only internal tool, an
  inseparable mutable-authority collision, a safety or privacy boundary, or
  delegation cost at least as large as the whole bounded task permits a typed,
  exactly reasoned exception. An internal approval gate is failed capacity, not
  a user decision: abandon the helper attempt immediately, record unavailable
  subagent capacity, and continue the bounded owner work directly. For a
  read-only internal tool, record the same immediate fallback as a host-gate
  exception. Never ask the user to approve either internal mechanism. External
  or provider actions, destructive actions, and user-reserved choices retain
  their normal approval gates.
- Create MOTHER only when multiple distinct owner lanes have real cross-lane
  dependencies and integration, portfolio acceptance is required, and CTRL
  cannot cheaply own that integration and acceptance.
- Artifact or variant count, related branding, shared keywords, and configured
  role capacity never establish a portfolio.
- Never build a complete tree from configured counts or role availability. The
  lane test decides every task.
- CTRL, MOTHER, every LEAD, and every persistent SPECIALIST require an active durable
  goal before scheduling, resuming, or substantive work. Inspect first, create
  when none is unfinished, continue a matching goal, and reconcile or escalate
  a conflicting unfinished goal without replacement. The goal states objective,
  stopping condition, authority boundary, and proof required. Missing host goal
  controls are an exact blocker, not permission to proceed. Finite DOER, TASK,
  SUBTASK, ASSIST, ADVISOR, and REVIEW work does not automatically require a
  goal; temporary ASSIST never owns one.

## Authority

The unassigned user-facing task explicitly told to use SWARM is CTRL. As
mandatory Step 0, CTRL derives a concise specific objective, uses the host task-title
tool to set `🐙CTRL - <objective>` by default, pins the
task, and verifies both receipts. Only `role_icons.enabled = false` or direct
user instruction removes the emoji. Complete Step 0 before durable-goal inspection,
topology, research, any other tool work, or substantive commentary. If a tool is
unavailable or a receipt fails, state the exact blocker and continue only with
truthful internal CTRL identity, never a claim that the UI changed. CTRL then
inspects or creates the matching durable goal, inventories live tasks and
pending creation receipts, and records the objective ledger. Hidden subagents do
not count as user-visible ownership. CTRL owns topology until the portfolio predicate creates
MOTHER; MOTHER then alone owns execution-topology changes and portfolio
acceptance while CTRL remains the human-facing control route.

| Function | Owns | Stops when |
| --- | --- | --- |
| CTRL | Intake classification, durable objective goal and ledger, initial topology, user-visible task materialization, human-facing routing; refuses portfolio claims without lane acceptance receipts | Outcome is accepted or an exact blocker is handed back |
| MOTHER | WORKER lanes, capacity, ownership, checkpoints, escalations, outcome lock, composed portfolio acceptance, shared release-surface leases | Outcome is accepted or an exact blocker is handed back |
| LEAD | Deployable-lane decomposition, bound-identity incident consultation, DOER integration SHA, exact-artifact gate ledger, independent ACCEPTANCE REVIEW routing, correction loop, lane completion, provider/deploy/rollback control, production proof | Its accepted lane receipt is handed to MOTHER |
| DOER | One bounded workstream as developer, designer, researcher, or operator; coordinates TASK artifacts, proof, and handoff | LEAD accepts, transfers, or receives an exact blocker |
| TASK | One bounded artifact inside a DOER workstream | Its DOER accepts, transfers, or receives an exact blocker |
| SUBTASK | One smaller bounded execution unit inside a TASK | Its TASK receives output or an exact blocker |
| ASSIST | Temporary wildcard capacity hired by MOTHER, SPECIALIST, LEAD, or DOER for one bounded assignment | It returns artifact/evidence and exits |
| SPECIALIST | One persistent, named professional perspective and its exact cross-cutting truth surface, invariants, and gate | It returns concise decisions or blockers; no worker/deploy authority |
| ADVISOR | One focused question/problem recommendation with evidence | It returns to its requester then exits; no authority |
| REVIEW | Independent SOURCE_SEMANTICS or ACCEPTANCE verdict, exact-artifact receipt verification, failed-proof reruns, and claim limits | It returns APPROVE, CORRECT, or BLOCKED |

MOTHER's planning pass is not a standing task or role. LEAD does
not give final portfolio acceptance. DOER and ASSIST never self-accept. REVIEW
does not mutate unless MOTHER explicitly transfers one narrow correction after
the prior owner releases it.

MOTHER orchestrates; it does not become an untracked implementation or deploy
lane. Give substantive implementation, asset generation, task-level proof, and
even a tiny integration or collision seam to a named DOER, TASK, or ASSIST. A
LEAD owns a justified deployable lane end-to-end:
decomposes DOER work, integrates an immutable SHA, routes independent REVIEW, receives corrections, accepts
the lane, and controls provider/deploy/rollback/production proof.

## Use ASSIST as temporary surge capacity

ASSIST is temporary surge/wildcard capacity hireable by MOTHER, SPECIALIST, LEAD,
or DOER, not a lesser helper or another authority layer. Its customizable default is
gpt-5.6-sol/medium. It may perform any bounded developer, design, research,
operations, proof, diagnostic, or execution slice when the hiring owner needs
parallel capacity, hits a material issue, is clogged, or misses an explicit
checkpoint/deadline. ASSIST returns artifact/evidence to the hiring owner and
exits. The hiring owner retains its own final authority: MOTHER orchestration decisions,
SPECIALIST truth-surface coherence, LEAD lane acceptance/deploy, and DOER artifact
accountability never transfer. REVIEW remains separately named and independent.

When a DOER has two or more independent SUBTASKs and child capacity, delegate
ASSISTs promptly; otherwise state the concrete dependency or collision reason.
Do not force pointless ASSISTs. An ASSIST cannot independently review,
self-accept, integrate, mutate providers, deploy, or create further authority.
It may be spawned as a child or reassigned from
available capacity, but never becomes permanent ownership or task sprawl.

A SPECIALIST is a free professional role. ARCHITECT, ENGINEER, DEVELOPER,
DESIGNER, RESEARCHER, ANALYST, and STRATEGIST are built-in examples, not an
allowlist. Its task contract names the exact truth surface, invariants, and gate
it owns. Multiple specialists may use the same profession concurrently when
those owned surfaces or accepting routes differ. A SPECIALIST is not a WORKER
scheduler, reviewer, integrator, provider mutator, or deployer. LEAD owns one
delivery lane and coordinates with the relevant SPECIALIST for cross-lane
impacts. ADVISOR is ephemeral: spawn it on
demand for one focused question/problem, receive recommendation/evidence, then
exit. It has no ownership, build, review, integration, provider, or deploy
authority.

DOERs, TASKs, and ASSISTs coordinate routine artifact dependencies and immutable
handoffs directly. LEAD is the lane outcome owner, not a message router; it gets
compact state/receipt updates. Escalate to LEAD only for scope/authority changes,
ownership collisions, missed commitments, unresolved decisions, or
integration/deploy impact. Escalate to MOTHER only for cross-lane capacity,
priority, collisions, or shared deploy leases. Peer coordination cannot mutate
another owner's files or bypass required independent REVIEW.

## Apply the lane and capacity tests

Create a user-visible lane only when it produces an inspectable artifact, can
advance now without shared mutable ownership, contains enough adjacent work to
justify startup and handoff, and has no existing owner that already fits it.
Keep lookups, single small edits, status relays, and other tiny same-surface work
inside the owner.

Measure task-start overhead when the host exposes exact data. Record
request-to-task-ID, task-ID-to-ready, ready-to-first-material-artifact-or-proof,
worktree setup, and host-reported token usage; never estimate missing token usage.
Keep same-directory or projectless startup, worktree provisioning, and
owner orientation or handoff as distinct classes. Use rolling medians only
after at least five comparable samples; before then use a conservative
qualitative threshold. Create a visible portfolio task only when evidence-backed expected critical-path savings exceed
measured startup plus orientation, handoff, and
integration or review cost. Otherwise keep the slice with its current owner.
This threshold never waives default internal-subagent delegation.
Set recovery and proof windows from observed cold-start or setup latency plus
the actual readiness condition, never from a generic budget shorter than
initialization. A timeout proves only that the chosen window elapsed; it does not prove service failure.

Treat configured parallel counts, coordinator minimums, lane width, and review
capacity as ceilings or shaping preferences, never creation targets. Count a
non-MOTHER task as active only while producing, integrating, or reviewing. A
ready immutable handoff frees capacity but retains correction accountability
until acceptance, transfer, or exact blocker.

Fast parallelism is a critical-path tactic, not a task quota. Start all and only
disjoint lanes that can return integration-ready artifacts; each LEAD integrates
its lane continuously while MOTHER keeps the remaining portfolio critical path
visible in the existing receipt. Never parallelize overlapping mutation, duplicate investigation, or
status collection. A collision or failure pauses only its affected surface when
the other lanes remain safe.

Multiple LEADs may concurrently prepare or deploy only to disjoint provider
targets and mutable surfaces. A shared provider, project, environment, channel,
or release target requires an explicit MOTHER-managed lease naming holder,
target, scope, acquisition, release condition, and waiting lane unblock. MOTHER
serializes only that shared mutation; it does not take over the deployment.

## Materialize user-visible ownership

In Codex, materialize every persistent SPECIALIST and every justified LEAD, DOER, TASK,
SUBTASK, and REVIEW as a host agent with the declared owner, artifact, and
accepting route. Materialize ASSIST and ADVISOR only for their bounded temporary
assignment; they return evidence and exit. Do not create any role merely to
complete a tree, and internal subagents never replace a required portfolio lane.
Grant child-task authority explicitly and only for a bounded named set that
passes the same lane test.

Before CTRL routes work or MOTHER schedules it, and before a LEAD or persistent SPECIALIST starts
or resumes substantive work, its owner must inspect or continue the matching
host goal. Goal creation does not grant extra file, provider, deploy, review, or
acceptance authority; completion is valid only at the stated stopping condition.

With `role_icons.enabled = true`, the opening title uses
`🐙CTRL - <objective>` by default and every SWARM task
title has exactly one role-matched emoji with no separator before the label.
`role_icons.ctrl` configures CTRL and defaults to `🐙`; `🐝` is MOTHER's
default task icon. Disable all title emojis only with
`role_icons.enabled = false` or direct user instruction.
Generic role types do not dictate task names: name a DOER by its concrete job,
such as DEVELOPER, DESIGNER, or RESEARCHER. Name a lane owner
`<domain-matched emoji>LEAD - <domain or responsibility>`: keep `LEAD` stable,
put the distinguishing responsibility after the dash, and choose the icon from
the domain rather than a generic leadership symbol. Name a specialist
`<role-matched emoji><PROFESSION> - <owned truth surface>`; never title it
SPECIALIST, and distinguish concurrent specialists through their owned surface,
not artificial profession variants. Other roles use
`<role-matched emoji><ROLE> - <specific artifact>`. The label,
icon, and concrete artifact should form the shortest unambiguous responsibility
receipt; use the fallback icon only when no clear metaphor fits.

Count only a host-confirmed task ID as a live task, owner, or capacity allocation.
A pending `clientThreadId` is still a creation reservation for its objective,
artifact, mutable surface, and accepting route; do not create a replacement
while it is unresolved. Search both live tasks and pending reservations before
every creation. If a duplicate materializes, stop it before mutation, transfer
any unique receipt to the sole owner, and archive the duplicate.
Preserve exact title/ID, artifact, mutable surface or external authority, owner
state, dependency, accepting route, composed acceptance surface, and required
proof state in one task-tree receipt. Update it only
for material creation, transfer, blocker, ready handoff, acceptance, or release.
Never overlap mutable ownership: the old owner must release, the receipt records
the transfer, and the new owner acknowledges before mutation.
