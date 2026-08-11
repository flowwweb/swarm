# SWARM hierarchy and finite roles

Read this reference when shaping a portfolio, creating user-visible tasks,
selecting ASSIST, naming roles, or transferring ownership.

## Choose the smallest useful shape

- Use MOTHER -> LEAD -> DOER as the normal shape when a domain needs repeated
  decisions, child boundaries, or integration.
- Keep a small flat portfolio as MOTHER -> DOER when its artifacts are clearly
  independent and do not need repeated domain coordination.
- Never build a complete tree from configured counts or role availability. The
  lane test decides every task.
- MOTHER, every LEAD, and every persistent ARCHITECT require an active durable
  goal before scheduling, resuming, or substantive work. Inspect first, create
  when none is unfinished, continue a matching goal, and reconcile or escalate
  a conflicting unfinished goal without replacement. The goal states objective,
  stopping condition, authority boundary, and proof required. Missing host goal
  controls are an exact blocker, not permission to proceed. Finite DOER, TASK,
  SUBTASK, ASSIST, ADVISOR, and REVIEW work does not automatically require a
  goal; temporary ASSIST never owns one.

## Authority

| Function | Owns | Stops when |
| --- | --- | --- |
| MOTHER | WORKER lanes, capacity, ownership, checkpoints, escalations, outcome lock, composed portfolio acceptance, shared release-surface leases | Outcome is accepted or an exact blocker is handed back |
| LEAD | Deployable-lane decomposition, DOER integration SHA, independent REVIEW routing, correction loop, lane acceptance, provider/deploy/rollback control, production proof | Its accepted lane receipt is handed to MOTHER |
| DOER | One bounded workstream as developer, designer, researcher, or operator; coordinates TASK artifacts, proof, and handoff | LEAD accepts, transfers, or receives an exact blocker |
| TASK | One bounded artifact inside a DOER workstream | Its DOER accepts, transfers, or receives an exact blocker |
| SUBTASK | One smaller bounded execution unit inside a TASK | Its TASK receives output or an exact blocker |
| ASSIST | Temporary wildcard capacity hired by MOTHER, ARCHITECT, LEAD, or DOER for one bounded assignment | It returns artifact/evidence and exits |
| ARCHITECT | Persistent system map, cross-lane dependencies, interface contracts/invariants, integration order, architectural decisions | It returns concise dependency/decision interfaces; no worker/deploy authority |
| ADVISOR | One focused question/problem recommendation with evidence | It returns to its requester then exits; no authority |
| REVIEW | Independent verdict, failed-proof reruns, and claim limits | It returns APPROVE, CORRECT, or BLOCKED |

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

ASSIST is temporary surge/wildcard capacity hireable by MOTHER, ARCHITECT, LEAD,
or DOER, not a lesser helper or another authority layer. Its customizable default is
gpt-5.6-sol/medium. It may perform any bounded developer, design, research,
operations, proof, diagnostic, or execution slice when the hiring owner needs
parallel capacity, hits a material issue, is clogged, or misses an explicit
checkpoint/deadline. ASSIST returns artifact/evidence to the hiring owner and
exits. The hiring owner retains its own final authority: MOTHER orchestration decisions,
ARCHITECT system coherence, LEAD lane acceptance/deploy, and DOER artifact
accountability never transfer. REVIEW remains separately named and independent.

When a DOER has two or more independent SUBTASKs and child capacity, delegate
ASSISTs promptly; otherwise state the concrete dependency or collision reason.
Do not force pointless ASSISTs. An ASSIST cannot independently review,
self-accept, integrate, mutate providers, deploy, or create further authority.
It may be spawned as a child or reassigned from
available capacity, but never becomes permanent ownership or task sprawl.

ARCHITECT is the persistent system-coherence counterpart: it owns the system map,
cross-lane dependencies, interface contracts/invariants, integration order, and
architectural decisions. It is not a builder, WORKER scheduler, reviewer,
integrator, provider mutator, or deployer. LEAD owns one delivery lane and
coordinates with ARCHITECT for system impacts. ADVISOR is ephemeral: spawn it on
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

In Codex, materialize persistent ARCHITECT and every justified LEAD, DOER, TASK,
SUBTASK, and REVIEW as a host agent with the declared owner, artifact, and
accepting route. Materialize ASSIST and ADVISOR only for their bounded temporary
assignment; they return evidence and exit. Do not create any role merely to
complete a tree, and internal subagents never replace a required portfolio lane.
Grant child-task authority explicitly and only for a bounded named set that
passes the same lane test.

Before MOTHER schedules work, and before a LEAD or persistent ARCHITECT starts
or resumes substantive work, its owner must inspect or continue the matching
host goal. Goal creation does not grant extra file, provider, deploy, review, or
acceptance authority; completion is valid only at the stated stopping condition.

Give every title exactly one role emoji with no separator before the label.
Generic role types do not dictate task names: name a DOER by its concrete job,
such as DEVELOPER, DESIGNER, or RESEARCHER. Name a lane owner `<DOMAIN> LEAD`
unless a clearer familiar title communicates the same higher ownership. Choose
one literal icon for that job, then format `<icon>ROLE - artifact`. The label,
icon, and concrete artifact should form the shortest unambiguous responsibility
receipt; use the fallback icon only when no clear metaphor fits.

Count only a host-confirmed task ID as a task, owner, or capacity allocation.
Preserve exact title/ID, artifact, mutable surface or external authority, owner
state, dependency, accepting route, composed acceptance surface, and required
proof state in one task-tree receipt. Update it only
for material creation, transfer, blocker, ready handoff, acceptance, or release.
Never overlap mutable ownership: the old owner must release, the receipt records
the transfer, and the new owner acknowledges before mutation.
