# RUSH hierarchy and finite roles

Read this reference when shaping a portfolio, creating user-visible tasks,
selecting ASSIST, naming roles, or transferring ownership.

## Choose the smallest useful shape

- Use MOTHER -> LEAD -> TASK as the normal shape when a domain needs repeated
  decisions, child boundaries, or integration.
- Keep a small flat portfolio as MOTHER -> TASK when its artifacts are clearly
  independent and do not need repeated domain coordination.
- Add STEP MOTHER only when several LEAD domains need a bounded segment owner
  and that extra handoff reduces MOTHER's integration load.
- Never build a complete tree from configured counts or role availability. The
  lane test decides every task.
- Creating MOTHER, STEP MOTHER, LEAD, TASK, ASSIST, or REVIEW never requires a
  goal. Create goals only after a direct user request or an explicitly
  authorized Boost run.

## Authority

| Function | Owns | Stops when |
| --- | --- | --- |
| MOTHER | Outcome, planning, priority, collisions, capacity, integration, final acceptance | Outcome is accepted or an exact blocker is handed back |
| STEP MOTHER | Repeated decisions and LEAD integration inside one bounded segment | Its LEAD wave is integrated and handed to MOTHER |
| LEAD | Repeated decisions, TASK boundaries, child acceptance, and domain integration | Its domain is integrated and handed to its parent |
| TASK | One inspectable artifact, adjacent implementation, tests, proof, correction, and handoff | Its parent accepts, transfers, or receives an exact blocker |
| ASSIST | One immediate non-overlapping bottleneck for one accepting owner | It returns one handoff and stops |
| REVIEW | Independent verdict, failed-proof reruns, and claim limits | It returns APPROVE, CORRECT, or BLOCKED |

MOTHER's planning pass is not a standing task or role. STEP MOTHER and LEAD do
not give final portfolio acceptance. TASK and ASSIST never self-accept. REVIEW
does not mutate unless MOTHER explicitly transfers one narrow correction after
the prior owner releases it.

## Use ASSIST narrowly

ASSIST is a contextual finite TASK label, not a hierarchy level, configuration
setting, permanent helper, or alternate owner. Use it only for one immediate
bottleneck that can advance without overlapping the acceptor's mutable surface.
MOTHER, STEP MOTHER, and LEAD normally create it. Any owner may request one
through its accepting parent; the parent decides whether the lane test passes.

Allow at most one active ASSIST per accepting owner. It counts under normal
active-task capacity. It cannot create children, use internal subagents, or own
a durable goal. It returns one inspectable handoff, then stops. Use an internal
subagent instead when the work is tiny and stays on the owner's same surface.

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

## Materialize user-visible ownership

In Codex, create STEP MOTHER, LEAD, TASK, ASSIST, and REVIEW with the host task
primitive. Internal subagents never replace portfolio lanes. Grant child-task
authority explicitly and only for a bounded named set that passes the same lane
test.

Give every title exactly one role emoji with no separator before the label.
Use configured hierarchy icons for MOTHER, STEP MOTHER, LEAD, and REVIEW. For a
finite contextual role, prefer its configured override or choose a literal,
familiar icon from `role_icons.task_choices`; use the fallback only when no
clear metaphor fits. Format hierarchy titles as `⚡MOTHER - outcome`,
`🗂️STEP MOTHER - segment`, and `🧭LEAD - domain`; format finite titles as
`<icon>ROLE - artifact`, using a familiar role word and short concrete artifact.

Count only a host-confirmed task ID as a task, owner, or capacity allocation.
Preserve exact title/ID, artifact, mutable surface or external authority, owner
state, dependency, and accepting route in one task-tree receipt. Update it only
for material creation, transfer, blocker, ready handoff, acceptance, or release.
Never overlap mutable ownership: the old owner must release, the receipt records
the transfer, and the new owner acknowledges before mutation.
