# SWARM hierarchy and specialist roles

## Profession registry and authority boundary

The built-in profession registry is exactly, in lifecycle display order:

- Direction: Manager (`manager`), Strategist (`strategist`).
- Discovery: Researcher (`researcher`), Analyst (`analyst`), Specialist
  (`specialist`), Inventor (`inventor`).
- Creation: Architect (`architect`), Designer (`designer`), Artist (`artist`),
  Writer (`writer`), Dev (`developer`), Producer (`producer`).
- Assurance: Tester (`tester`), Critic (`critic`), Security (`security`),
  Auditor (`auditor`), Legal (`legal`), Reviewer (`reviewer`).
- Delivery: Operator (`operator`), Marketer (`marketer`), Support (`support`).
- Foundation: Accountant (`accountant`), Recruiter (`recruiter`), Educator
  (`educator`).

Profession and authority are orthogonal. A profession selects perspective and
skills; only assignment as CTRL, LEAD, DOER, independent REVIEW, or ADVISOR
grants the corresponding authority. Architect, Dev, Security, Specialist, and
any other profession may be assigned LEAD or DOER. Profession labels never grant
recruitment, mutation, review, or acceptance authority. WATCHDOG remains a
sensor. Specialist requires a named domain and truth surface; it is not the
structural SPECIALIST role field.

Only proven persisted aliases resolve compatibly, without renaming user-owned
task titles: product, project, and planning management to Manager; data and
financial analysis to Analyst; content, social, sales, and brand strategy to
Strategist; Security Engineer to Security; Support Specialist to Support; and
Dev to `developer`. Unknown labels remain unregistered custom text and cannot
materialize a profession or grant authority.

Architect owns system shape, ADRs, and interfaces; Dev owns working software;
Security owns threat resistance and controls. Designer owns usability,
interaction, and design systems; Artist owns expressive media and craft.
Manager owns priorities, resources, and organization; Producer owns one
production from brief through assembled delivery. Inventor owns novel mechanism
or method exploration, prior-art checks, feasibility prototypes, failure modes,
and handoff—not strategy, production implementation, or acceptance.

Read this reference when shaping topology, selecting an owner, creating a
user-visible task, adding a SPECIALIST, or transferring ownership.

## Intake before graph selection

CTRL begins every new task by asking or confirming two answers: the desired
goal and the most efficient safe way to complete it. A one-shot prompt may
provide both; CTRL still records the concise goal and proposed strategy before
selecting topology. The graph is chosen from objective, domain, ownership,
dependencies, resumption, integration, acceptance, and the strategy—not from
an arbitrary number of agents. Load [graph-engineering.md](graph-engineering.md)
for the graph invariants and registered domain profiles.

Steer, do not overcorrect: classify every new instruction as `ADDITIVE`,
`CORRECTIVE`, or `REVERSAL` and
bind it to the explicitly named scope. The receipt also names the compatible
accepted behavior that remains preserved. `ADDITIVE` extends that behavior;
`CORRECTIVE` makes the smallest coherent adjustment that closes the finding;
`REVERSAL` replaces only the explicitly reversed behavior. Every class preserves
unaffected topology, dirty custody, proof boundaries, accepted artifacts, and
unrelated lanes. A local correction never implies the opposite blanket rule.

## One root, the shallowest useful shape

CTRL is the sole root and final composed authority. Use `CTRL_DIRECT` only for
one low-risk atomic outcome on one mutable surface with no cross-lane dependency
and measurable completion inside the direct-work horizon. Otherwise CTRL hires
a LEAD. A LEAD may hire DOERs for separable work that shortens accepted proof.

### CTRL is an operator, not a producer

The direct-work clause remains intentional: small, low-risk, atomic `GENERAL`
work may stay with CTRL when measured task overhead costs more than the
delegation. It is not permission for CTRL to become the producer. `DESIGN`,
`IMAGEGEN`, mockup generation, image editing, and taste-led visual work are
always routed as `CTRL_DELEGATED`. Product experience, interaction, UI mockups,
and design-system work bind a visible Designer lane; expressive illustration,
concept art, visual assets, motion, 3D, photography, sound, and other media
craft bind a visible Artist lane. They do not qualify for `CTRL_DIRECT` merely
because they touch one surface or finish quickly. If the required visual lane
is unavailable, preserve the blocker rather than falling back to CTRL.

CTRL may route, inspect read-only state, resolve user decisions, surface
candidate galleries, integrate accepted handoffs, and perform the narrow
general small-work exception. If CTRL has started producing a mockup, image,
visual direction, or other delegated artifact, stop at the next safe boundary,
record the routing error, and transfer the exact surface to the Designer,
Artist, or accountable LEAD; do not finish it in CTRL.

Any agent may request a skill that improves its role. Skill installation is a
bounded host action: the request binds the requester, exact skill source and
version/digest, purpose, destination scope, and audit/rollback receipt. The
default is task-local; persistent or global installation requires explicit
host/user authorization. Skills improve execution but never transfer model,
tool, browser, provider, destructive, review, or acceptance authority. This
lets Designer or Artist load an approved image-generation skill while keeping
CTRL's operator boundary intact.

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

For root CTRL, small bounded `GENERAL` work may use an internal subagent when
it has one surface, low risk, no durable boundary, and measured economics that
favor the shortcut. Medium or large work opens a visible Codex task with
`CTRL -> LEAD -> DOER` so the lane can own its own subagents. `DESIGN`,
`IMAGEGEN`, mockups, and image edits always open a visible Designer or Artist
task according to the typed visual ownership; `CTRL -> SUBAGENT` is not a
substitute for that visual lane, even when a role label names the profession.
If the required task cannot be materialized, record the
exact capability blocker or degraded `UNVERIFIED` route; do not silently
generate the visual artifact in a subagent.

Use this routing order:

1. Keep one atomic outcome with the current owner when coordination costs more.
2. Open a visible task lane when a durable boundary above applies.
3. Add a subagent only for bounded small `GENERAL` capacity within the current
   owner or an already-open lane; never for visual artifact production.

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
For a game objective, use the registered game-studio graph and materialize its
independent design, engineering, art, and audio lanes before the integrated
playtest/QA and release gates. Medium and large lanes are visible Codex tasks;
subagents are only bounded capacity inside those lanes.

Every durable CTRL, LEAD, and persistent SPECIALIST has one active goal with an
objective, stopping condition, authority boundary, and required proof. Finite
DOER, TASK, SUBTASK, ASSIST, ADVISOR, and REVIEW work does not automatically own
a goal. Goal ownership never grants topology, mutation, review, or acceptance
authority.

## User-state custody and substantive lanes

User-created, renamed, titled, pinned, unpinned, archived, and state-changed host
tasks always win. SWARM, CTRL, and LEAD cannot undo, normalize, overwrite, revert,
rebase, rename, pin, unpin, archive, or change that state by inference. A safe
custody digest may be retained without raw user text, but only the host task API
can independently consume an explicit-user receipt naming the exact mutation,
target, and scope. Missing or conflicting custody means no mutation is permitted;
it fails closed and waits.

A fresh host-observed direct-user turn for one specific CTRL opens a scoped
user-activity keep-out for that CTRL and its subordinate owners. During the
window the Master or portfolio CTRL must not send conflicting or duplicate
directives, enqueue follow-ups, wake those owners, or interrupt their work.
Read-only portfolio observation and unaffected CTRL lanes continue. The keep-out
ends when that user-directed turn completes or the user explicitly hands
coordination back. Silence, age, stale presence, or inferred activity cannot
open or indefinitely extend it; user actions always win.

Product implementation, storage recovery, deploy preparation, provider integration,
design-system work, test/review ownership, and any lane with a separate mutable
surface or artifact, durable/resumable ownership, independent progress or review,
worktree isolation, a cross-lane dependency, user-visible delivery, or multiple
checkpoints/delegation are substantive: they require a visible senior Codex
task/chat with its own cwd, owner, and heartbeat. Hidden or short-lived subagents
are only bounded sidecar inspection or independent review; they cannot own, accept,
hand off, or maintain a lane heartbeat. The parent CTRL keeps unrelated senior
lanes moving in parallel and integrates only exact receipts. A missing due material
checkpoint is stall evidence; reorient the existing owner first, and open a
successor only when user-authorized topology permits it with explicit custody and
handoff.

At each meaningful stable boundary, long-lived CTRL and LEAD work emits an
immutable checkpoint with exact task identity and state, source SHA/tree/parent,
dirty custody, proof manifest and claim limits, blocker, and next bounded action.
Only coherent attributable work may be committed after proportionate proof;
never automatically stage, reset, clean, commit, normalize, or absorb unrelated
dirty work. A handoff is effective only after the successor acknowledges that
exact checkpoint. Shrink or archive the old rollout only through the guarded
lifecycle in [monitoring.md](monitoring.md).

Storage inventory, archive, cleanup, relocation, and monitoring are a dedicated
delegable STORAGE LEAD lane. It owns a bounded exact target manifest, exact-root,
active-process, live-log, database, and dirty/current-worktree guards, recoverable
move or copy-verify-remove, post-operation target/free-space receipts, and
independent review. CTRL retains topology, ownership, proof, blockers, and
acceptance; storage pressure alone never authorizes destructive inference.

## Authority

CTRL owns the durable accepted-request inventory and human route; a LEAD owns each delegated request's live task and evidence transitions. Stored history never restores authority after restart. WATCHDOG may alert an eligible bound owner about a valid request, while orphaned records return only to CTRL's completion audit and never manufacture a sensor identity or correction.

| Function | Owns | Does not own |
| --- | --- | --- |
| CTRL | Intake, objective ledger, topology, authorized user-visible task materialization, shared-surface coordination, final composed acceptance, human route, narrow general atomic work | Another CTRL without exact user authorization, LEAD/DOER/Designer/Artist implementation or artifact production, or independent REVIEW |
| LEAD | One lane, decomposition, integration, incident consultation, exact-artifact gates, correction loop, lane completion, authorized deploy and rollback | Other lanes or final portfolio acceptance |
| DOER | One bounded workstream and its artifact handoff | Self-acceptance or topology |
| TASK / SUBTASK | One bounded artifact or execution unit | Parent ownership or acceptance |
| ASSIST | One temporary bounded assignment | Persistent ownership, integration, review, acceptance, or further authority |
| SPECIALIST | One persistent named truth surface, its invariants, evidence, and advisory gate | Scheduling, ownership transfer, mutation, integration, deploy, review, or acceptance |
| ADVISOR / EXPERT | One focused answer with evidence | Artifact ownership or authority |
| REVIEW | Independent verdict on the frozen plan or frozen completed artifact | Implementation, self-correction, deploy, or final composed acceptance |

CTRL may complete direct work only through its declared direct-work contract,
and only when the work kind is `GENERAL`.
LEAD alone completes a LEAD-owned lane after independent exact-artifact review.
CTRL composes accepted lanes; it cannot impersonate LEAD or REVIEW.

## Specialists, advisors, and temporary help

Before the first affected mutation, add a persistent SPECIALIST only when one
named cross-cutting truth must remain coherent across lanes. The contract names
its profession, stable instance identity, truth surface, invariants, and gate.
The 24 registered profession cards are the allowlisted perspectives; profession
is not singleton, and multiple instances may share one only when stable
identities, truth surfaces, and accepting routes do not overlap. A profession
assignment never changes the structural SPECIALIST authority field.

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
`<role emoji><PROFESSION> - <truth surface>` for specialists. A title is a
readability signal, never an authority token; unregistered historical titles
remain user-owned text and are never normalized into a profession.
