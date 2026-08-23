# Compact task contract

Use CORE + role + these fields. Atomic/simple tasks omit every inapplicable field. A durable task keeps only its exact current decision and proof boundary.

For every user-authorized new SWARM objective, CTRL asks or confirms the goal
and the most efficient safe completion strategy before routing. The typed
intake receipt records both answers and the selected graph profile; a one-shot
prompt may supply the answers, but CTRL still restates them. The graph follows
the invariants in [graph-engineering.md](graph-engineering.md), including one
CTRL root, explicit dependencies, independent parallel lanes, and visible
medium/large task ownership.

For every user-authorized new SWARM objective, the opening user-visible task completes mandatory
Step 0 first: derive a concise specific objective and resolve `role_icons`. Before any title request,
obtain a fresh host-owned custody receipt. The host task API may request the exact
`🐙CTRL - <objective>` title by default (or omit the emoji when `role_icons.enabled = false`).
SWARM never requests or authorizes automatic pinning; every created CTRL surfaces its ID,
directive/title, `pinned: false`, and `placement: placement_unverified`. Only direct host
consumption of an exact current explicit-user request may pin or unpin, and the current host
may append below pinned folders. Otherwise preserve the current user state. If a tool is
unavailable or a receipt fails, state the exact blocker and continue only with truthful internal
CTRL identity. After this Step 0 custody
check, create or continue exactly one matching durable goal before routing work. Its contract
records the chosen topology and which visible task owns each mutable artifact.
Hidden subagents are non-recursive leaf capacity, not a replacement for required
SWARM task ownership. A task that may need recruitment or recursive delegation
routes to a visible owner. A subagent that discovers the need stops and returns
`PROMOTE_TO_VISIBLE_TASK` with the exact remaining deliverable, custody boundary,
and required proof for its parent to route.

If a CTRL is already active, a new CTRL or successor is never an inferred
topology step. Require the actual host task API to consume a current single-use
host-owned user receipt naming the exact operation, source CTRL, target identity,
objective, and scope. The plugin runtime may prepare a typed request but never
consumes or upgrades it to host authority. A CTRL-callable mint method, feed
receipt, naming convention, directly constructed event, signature, or mutated
private attribute carries no host authority.

```text
ROLE — artifact
PURPOSE: objective and acceptance/non-negotiables.
OWNERSHIP: owner, exact mutable surface, canonical artifact/version.
BOUNDARIES: dependencies, proof/claim limits, no hidden scope change.
ESCALATION: accepting route or exact blocker.
CHANGE: ADDITIVE, CORRECTIVE, or REVERSAL; explicitly named scope and accepted behavior preserved.
MODE: CTRL_DIRECT or CTRL_DELEGATED, with the direct-work predicate receipt and typed work kind (`GENERAL`, `DESIGN`, `IMAGEGEN`, or `IMAGE_EDIT`). Only `GENERAL` can pass the CTRL_DIRECT predicate; visual work records `product_experience` or `expressive_art` ownership and binds Designer or Artist respectively.
GOAL: stable goal ID, objective version, measurable milestone, and locally chosen review horizon; optional WATCHDOG binding is separate and names the watched owner plus validated alert route. New-task persistence follows `goals.use_goals`, which defaults true; when it is false the intake and graph remain recorded but the root task does not create or continue a durable goal. LEAD and persistent SPECIALIST ownership goals remain fixed role invariants.
ACCEPTANCE: typed lane kind, exact ArtifactIdentity, deterministic ProofPlan, bound owning LEAD identity, and accepting REVIEW route; CODE has at least one gate and only NON_CODE non-artifact work may use an explicit empty contract.
DELEGATION: exact deliverable, owner ID, portable custody roots, immutable artifact and artifact paths, required proof classes, bounded due event, and maximum readable return size.
TOPOLOGY: structural authority is exactly CTRL, LEAD, or DOER. Freeze one `TopologyMaterializationPlan` before task creation: one CTRL administrator; profession-labelled LEAD/DOER titles; one parent and boundary/artifact per lane; direct LEAD production, bounded DOER delegation, or durable-boundary facts for a nested LEAD; and a span exception receipt when CTRL fanout exceeds the soft preferred width. No fixed depth, arbitrary ratio, or mandatory pass-through.
SUBAGENT RETURN: COMPLETE for the bounded leaf result, or PROMOTE_TO_VISIBLE_TASK with remaining deliverable, custody boundary, proof, and accountable parent. A subagent never recruits or accepts.
RETURN: one bounded readable artifact-bound ACCEPT, REJECT, or BLOCKED receipt with owner-reported evidence, dirty custody, and path/count/byte/hash manifest; final acceptance remains independent.
SKILLS: any agent may request a role skill with exact source/version or digest, purpose, destination scope, and host audit/rollback receipt; installation never transfers authority and defaults task-local.
INCIDENTS: LEAD consultation receipt for matching unresolved `.codex/swarm/incidents.jsonl` records.
```

## Delegated return gate

Task creation, dispatch success, commentary, timeout, silence, empty or
unreadable output, and an in-progress state are activity signals, never return
evidence. Advancement requires one explicit readable `ACCEPT`, `REJECT`, or
`BLOCKED` owner receipt bound to the exact task, owner, artifact, paths, and
declared proof classes. `ACCEPT` may move the artifact only into independent
review when every required proof and parity item is present. `REJECT` names the
first in-scope correction and stays active; `BLOCKED` names the first concrete
blocker and stays unresolved. Neither can advance acceptance.

Every bounded return rechecks the original objective, assigned profession and
structural authority, exact deliverable, non-goals, dirty custody, and next
acceptance gate. A CTRL project pulse contains one state, receipt-backed declared
unit total and completed or accepted units with server-derived percentage or
explicit `Unmeasured`, latest material proof, first blocker, and next action/ETA.
Tool output and exact receipts remain available beneath the pulse; raw logs,
filler, repeated plans, commentary, and unchanged heartbeats are not progress.
Profession does not transfer ownership, and review does not become implementation
or acceptance.

The parity manifest is an owner return claim, not host or user authority. It
must match the declared paths, count, byte total, and file digests and remain
inside exact dirty custody; missing or ambiguous ownership or parity fails
closed. Independent REVIEW still verifies the immutable artifact. Proof classes
are nonpromoting: source, static, local, browser, authenticated, provider,
payment, deployed, device, and human evidence close only their exact class.

An objective amendment increments the version and records authority, reason, requirements delta, new baseline, and prior-miss relevance. A genuinely new project links a distinct successor goal; it never rewrites the prior history.

User-state custody is a binding non-negotiable: user-created, renamed, titled,
pinned, unpinned, archived, and state-changed host tasks remain the source of
truth. The coordination ledger may record only a safe custody digest and receipt,
never raw user text. The console/runtime cannot authorize host task mutation; the
host task API must independently consume a current explicit-user receipt naming the
exact operation, target, and scope. Missing or conflicting custody means no
mutation is permitted: it is a fail-closed blocker, not permission to normalize or
replace the user state.

SWARM runtime never calls or authorizes pin/unpin. Every user-authorized CTRL creation
surfaces the created ID, exact directive/title, `pinned: false`, and
`placement: placement_unverified`. Only the host may consume an exact explicit-user
pin request, and the current host may append the task below pinned folders.
Existing user state is always preserved. The host task API independently consumes
the exact current user request for every pin or unpin mutation; SWARM does not
authorize or request it.

Any substantive lane uses a visible senior Codex task/chat with its own cwd, owner,
and heartbeat. A hidden subagent is bounded sidecar inspection or non-authoritative
review assistance only and cannot recursively delegate. Independent review is
performed by a separate visible owner from the producer, normally a DOER-level task
or a LEAD for a durable review program; it is a function/profession, not a fourth
structural authority.
Each senior lane owes a material checkpoint or exact blocker at its due event;
missing receipt is stall evidence, so reorient the existing owner before any
successor. A permitted successor carries explicit custody/handoff and never silently
duplicates, replaces, renames, or archives the old lane.

A meaningful stable checkpoint for long-lived CTRL or LEAD work records the
exact task identity and state, source SHA/tree/parent, exact dirty custody, proof
manifest and claim limits, exact owned-path manifest digest, dependency-graph
digest, proof-plan digest, blocker, and next bounded action. A clean unblocked
checkpoint produces one deterministic immutable review packet bound to repository,
producer, reviewer task, candidate SHA/tree/parent, content digest, path manifest,
dependency graph, proof plan, proofs, and claim limits. Any changed bound field
invalidates the packet and every receipt derived from it. Commit only coherent
attributable work after proportionate proof. Never automatically stage, reset,
clean, normalize, commit, or absorb unrelated dirty work. Before a successor may
own the lane, it acknowledges the exact immutable checkpoint; this handoff does
not authorize renaming, pinning, archiving, or any other host-task mutation.

With `automation.mode = "standard"`, the checkpoint may produce an exact-path
commit request only when the complete dirty set equals attributable paths inside
the recorded custody boundary. Mixed or ambiguous dirty work fails closed. The
immutable candidate then routes to a separate visible independent review owner;
creation, commentary, activity, timeout, silence, `BLOCKED`, and in-progress
state never authorize integration. `manual` emits no Git or lifecycle request.
Runtime entry points normalize raw config mode and route commit, review,
integration/push, release, and archive planning through the same fail-closed
decisions. Every policy or gate receipt is typed and bound to repository root,
branch/remote, candidate SHA/tree, operation, authority, and freshness; a string
claim or mismatched receipt cannot authorize an action.

Storage inventory, archive, cleanup, relocation, and monitoring use a dedicated
delegable STORAGE LEAD lane. Its contract binds an exact target manifest,
exact-root, active-process, live-log, database, and dirty/current-worktree guards,
recoverable move or copy-verify-remove, post-operation target and free-space
receipts, and independent review. CTRL may only reconcile read-only state or perform
an explicitly authorized narrow host-safety stop; pressure alone is not destructive
authority.

Archive or relocation requires explicit idle, completed, or handed-off state;
proof that the rollout is not under direct user control; no active process, file
handle, or lock; and size stability across bounded observations. Verify the exact
destination by file count, byte count, and hash parity, retain a recoverable
manifest, and only then permit copy-verify-remove. Creation age alone is never
stale or quiescent evidence, and active or growing logs remain protected.

## Durable request ledger

Each accepted user request has one private, atomic repo-local record: safe request/goal/task IDs, accountable owner, derived outcome digest, accepting route, next due event, state, safe evidence/transition receipts, the last published event/message/surface plus feed sequence, and immutable history. Never store raw user text, artifact body/path, credentials, or host identity claims. `OPEN` and `BLOCKED` remain unresolved through interruption, restart, heartbeat, reprioritization, or objective amendment. Only evidence-backed completion, explicit user supersession, or explicit user cancellation is terminal. The ledger is continuity, not task/gate/review authority: reload must revalidate current runtime facts before a composed or archive claim. A fresh runtime derives its feed-sequence floor from the persisted cursor and accepts only a newly published, fully validated later event; it never reconstructs old feed authority.

Use `REQUEST_PENDING` only between durable staging and matching acceptance/activation. It is non-runnable and blocks worker/artifact work, stale/collapse handling, closeout, and archive until accepted or CTRL rolls it back from an exact surfaced blocker. A single record changes per lifecycle call; shared proof can advance multiple same-task requests only through separate calls. CTRL cannot silently delete or overwrite an accepted request.

Integration-ready means immutable artifact identity, required proof state, and an explicit accepting route. `UNVERIFIED` remains open. A composed rendered product needs its composed render comparison when visual work is in scope.

The deterministic ProofPlan binds changed surfaces, declared claims, authority
boundaries, dependency reach, incidents, runtime signals, repository
capabilities, consequence tier, exact commands and environments, gates, reviews, and claim coverage.
Unknown impact broadens proof. Gate receipts bind the plan, gate, artifact,
input closure, environment, authority, timing, attempt history, stability, and
proof class. Stable exact-input evidence may be re-observed and adopted, but it
never transfers review or acceptance authority. A plan revision adopts only
receipts whose gate specification and full binding still match; changed or new
gates reopen. Gate dependencies stop downstream work after an upstream failure
or timeout, so a blocked plan does not spend capacity proving a result it cannot
accept. Every declared claim remains
open until a current receipt of its matching proof class exists. Gate receipts use only `PASS`,
`FAIL`, or `TIMEOUT`; timeout never passes and allows at most one typed
same-state transient retry. Source-semantic review cannot close the lane. A material defect found
after handoff adds one local causal record; minor failures do not. Daily fold may
generalize only distinct repeated or demonstrably generalizable candidates backed
by contrasting regression proof; ineligible candidates remain pending until an
explicit reasoned rejection. The private Git-ignored ledger uses structured safe
evidence references and serialized cross-process updates, never a repo command,
person-specific rule, or credential value.

A SPECIALIST interface is only a current decision/dependency reference. The specialist persists one exact cross-cutting truth surface; it does not acquire a lane. Record the structural role and typed profession namespace separately so profession `specialist` cannot collide with structural SPECIALIST authority. Unknown historical titles remain inert user-owned text and never become profession or authority records. A DOER may use a temporary wildcard ASSIST for a bounded independent subtask, but never for acceptance or authority transfer. Detailed role and recovery rationale is lazy-loaded from the matching reference.

WATCHDOG is not a role or task-contract owner. When explicitly bound, its receipt
records only the goal, watched owner, due evidence digest, one of `CLEAR`,
`ATTENTION`, or `BLOCKER`, and the validated accountable decision owner. It never
records or authorizes a recovery decision.
