---
name: swarm
description: Compact SWARM coordination doctrine for directing coordinated coding agents from one control task.
---

# 🐙 SWARM

## START

User action has custody precedence. User-created, renamed, titled, pinned, unpinned,
archived, and state-changed host tasks always win; SWARM, CTRL, and LEAD never
undo, normalize, overwrite, revert, rebase, rename, pin, unpin, archive, or
change them by inference. The coordination/runtime request ledger may retain a
safe custody digest and state receipt without raw user text, but the console has
no host-task mutation authority. A rename, pin/archive, title, or state mutation
requires the host task API to independently consume a current host-owned
explicit-user receipt naming the exact operation, target, and scope. If that
receipt or custody verification is absent or conflicts, no mutation is permitted:
fail closed, surface the conflict, and wait.

**Step 0, never defer:** For an unassigned user-facing task explicitly told by the user to use SWARM, derive a concise specific objective and resolve `role_icons`. Before any title or pin request, obtain a fresh host-owned receipt proving SWARM custody and confirming that no user-created, renamed, titled, pinned, unpinned, archived, or state-changed task state is present. Only then may the host task API request the exact `🐙CTRL - <objective>` title (or `CTRL - <objective>` when `role_icons.enabled = false`) and pin; verify both receipts. Otherwise preserve the current user state and continue only with truthful internal CTRL identity. If either host control is unavailable or fails, state the exact blocker and never claim the UI changed. A task assigned by an existing CTRL keeps its assigned role. A CTRL cannot create, fork, promote, replace, rename, recover-as-new, or link a successor CTRL unless the user explicitly requests that exact operation. The plugin may prepare a typed single-use request bound to source CTRL, target identity, objective, and scope, but code running in its interpreter cannot authorize the host action. The actual Codex task API must independently consume a host-owned user receipt; without that host enforcement the request is non-authoritative and no new CTRL may be created. Adjacent work stays inside the current CTRL or returns to the user.

After the Step 0 custody check—whether it produced an eligible SWARM receipt or preserved existing user state—invoke the sibling `scripts/swarm_console.py --start` once. It obeys `console.open_on_start`, reuses the local server and an already-open portal tab, and opens the portal in the default browser only when needed. A launcher or browser failure is advisory and never blocks SWARM work.

After the Step 0 custody check, always ask and capture both intake answers before routing: **What is the goal for this task?** and **What is the most efficient safe way to complete it?** A one-shot user prompt may already contain the answers; CTRL must still restate the goal and proposed efficiency strategy so the two fields are inspectable before it proceeds. Then inspect or create exactly one matching durable goal when `goals.use_goals = true` (the default), and record its objective, canonical artifact/mutable surface, owners, dependencies, accepting route, proof, and claim limits. When `goals.use_goals = false`, retain the same intake and graph receipt but do not create or continue a durable goal; the setting is an explicit persistence choice, not permission to skip intake. Reuse only when objective, surface, and accepting route match; a pending creation receipt reserves that identity. Stop a disproved duplicate before mutation and archive it after resolution. For goal ownership, title rules, duplicate prevention, visible-lane economics, delegation exceptions, role selection, and topology, load [hierarchy.md](references/hierarchy.md).

Immediately after that receipt—and before topology or work—use `swarm_contract.py request` to `list` then `audit` the exact repository and reconcile every unresolved request. A missing store returns empty/unattached without writing; enable continuity only with an explicit absolute repo root before consequential request work. Intake stages non-runnable `REQUEST_PENDING`, publishes its reserved-ID `DECISION`, calls live `register`, verifies the digest, then activates. Serialized bridge calls are read-only. New input may reprioritize but never replace open work. Persist each typed event cursor and digest; after restart, a new current event must exceed its persisted feed-sequence floor without replaying old feed objects. Audit again before closeout/archive; any unresolved, orphaned, invalid, or provisional record blocks the claim. Missing/corrupt receipts are `UNVERIFIED`, never an empty ledger.

Before the first mutable handoff, select the smallest graph that satisfies the captured objective, efficiency strategy, ownership, dependencies, resumption, integration, and acceptance evidence. Follow [graph-engineering.md](references/graph-engineering.md): one CTRL root, explicit artifact-owning lanes, parallelize only independent work, serialize shared-surface gates, and keep every edge explainable by a dependency or acceptance reason. A game objective selects the registered `game_studio` graph: game-studio lead, design, engineering, art, audio, playtest/QA, and release agents with production dependencies; medium and large lanes are visible Codex tasks, while lane-local bounded work may use subagents. Do not flatten a domain graph into a single undifferentiated worker list.

Use the shallowest structure that can finish the accepted objective. `CTRL_DIRECT` is only one low-risk atomic outcome on one mutable surface, no cross-lane dependency, and measurable completion inside the configured horizon; otherwise use `CTRL_DELEGATED` and a LEAD. Materialize a visible task lane whenever work needs durable ownership or resumable ownership, independent progress or review, a separate mutable surface/artifact, worktree isolation, interruption-safe resumption, or separate acceptance/handoff; economics never overrides that boundary. Use a subagent only as short bounded capacity inside an existing lane: small-to-medium one-surface work may use it when measured task overhead does not clearly repay itself. The subagent returns evidence to its accountable owner and never substitutes for a qualifying durable task. A capacity-forced degraded subagent records the exact host failure, owner, immutable checkpoint, resumption marker, and `UNVERIFIED` gates; it cannot own, hand off, review, or accept the lane. Non-atomic delegated authority is always `CTRL -> LEAD -> DOER`. Record only the typed exceptions in the hierarchy contract. Internal-helper or read-only-tool approval gates are failed capacity: cancel the attempt, record the host gate, and continue direct bounded owner work without asking the user. This never grants external, provider, destructive, or user-reserved authority.

For the root CTRL, bounded `GENERAL` work may still use a `NORMAL_SUBAGENT`
when it is genuinely small, one-surface, low-risk, and the measured economics
favor it. Medium or large work must open a visible Codex task so it can gain
lanes and its own subagent capacity. `DESIGN`, `IMAGEGEN`, and `IMAGE_EDIT`
always open a visible `DESIGNER` task; do not label an internal subagent as a
Designer to avoid that boundary. If the required task cannot be created,
surface the exact blocker or an explicitly degraded unverified route—never
silently generate the visual artifact in a subagent.

Preserve every explicit user-selected model, provider, service tier, and reasoning level exactly across CTRL and all assignments. SWARM may recommend a change but never applies one unless the user explicitly asks SWARM to choose or change it; if the host cannot honor the selection, report the exact blocker instead of substituting. Only when the user delegates that choice may SWARM resolve it from the active profile, route tier, and execution bounds. Treat fast-tier and turbo settings as host-dependent preferences, never proof or a safety exception. Load [model-providers.md](references/model-providers.md) when selecting or probing a model/provider.

Spark is a separate, opt-in lane for extremely low-risk small work. It is
disabled by default and may handle only read-only inspection, narrow search or
inventory, deterministic formatting, typo/copy/documentation edits, or a
focused local check with an obvious result. Keep source logic, APIs,
dependencies, schemas/data, auth, payments, security, secrets, provider or
deployment actions, destructive commands, computer-use/image work, visual
acceptance, and ambiguous multi-file changes on the configured role model.
Require the `simple` workload and shell-only access; a task outside that boundary
must fail closed rather than being squeezed into Spark. Use
`boost.spark_reasoning` (default `xhigh`) only after `boost.spark_enabled` and
the `spark_simple_work` strategy are both active. The setting changes routing
preference, never ownership, review, acceptance, or release authority. A
successful response is not proof of Spark execution: count Spark usage only
when the host returns the actual Spark model and a matching host receipt.

## CTRL OPERATOR BOUNDARY

Any substantive lane—product implementation, storage recovery, deploy preparation,
provider integration, design system, test/review ownership, or work with multiple
checkpoints or delegation—must be a visible senior Codex task/chat with its own
cwd, owner, and heartbeat. A hidden or short-lived subagent is only a bounded
sidecar inspection or independent review; it cannot be the sole owner or bottleneck.
The parent CTRL keeps unrelated senior lanes moving in parallel and integrates only
exact receipts. Each senior lane owes a material checkpoint or exact blocker at its
due event; a missing due receipt is stall evidence, so reorient the existing owner
first. A successor is permitted only when the user-authorized topology allows it and
must carry an explicit custody/handoff; never silently duplicate, replace, rename,
archive, or alter the old lane or user state.

Only genuinely small, single-surface, low-risk `GENERAL` inspection or review may
remain eligible for a bounded sidecar subagent; that exception never grants lane
ownership, handoff, heartbeat, acceptance, or host mutation authority.

CTRL is the operator/orchestrator, not the producer. Keep the small-work
exception: `CTRL_DIRECT` is valid for one low-risk, atomic `GENERAL` outcome
when measured coordination overhead costs more than the work. That exception
covers bounded copy, documentation, formatting, read-only inspection, or a
focused local check; it does not let CTRL choose visual taste, generate a
mockup, run image generation, own a production artifact, or silently become a
LEAD/DOER.

Design, mockup, image-generation, and image-editing work defaults to
`CTRL_DELEGATED` and a `DESIGNER` assignment, even when the request is small.
The designer owns the candidate artifact and visual proof; CTRL routes the
work, surfaces the decision set, waits at the user's approval boundary, and
composes the accepted result. If the required designer lane cannot be
materialized, keep the work blocked or explicitly degraded with open gates;
never fall back to CTRL production work.

Every agent may request a role skill when it would materially improve its lane.
The request names the exact skill, source/version or digest, purpose, scope,
and rollback/audit receipt. The host owns the actual install; the installed
skill cannot grant a model, tool, browser, provider, destructive, review, or
acceptance authority. Task-local scope is the default, and persistent/global
installation needs its own explicit host/user authorization. A designer may
therefore use an approved image-generation skill without turning CTRL into the
designer.

Skill reuse is a SWARM first principle. At intake and planning, identify whether
an approved existing skill materially improves the task before inventing a
workflow. Use `find-skills` as the default discovery mechanism when a capability
is missing or specialized. Prefer installed or bundled reviewed skills; inherit
only the smallest role- and task-relevant set; and record source, ref or digest,
approval, scope, and assignment receipt. Task-local inheritance is the default.
Never silently install or update a skill. External or unreviewed skills fail
closed. Skills cannot expand model, tool, browser, provider, destructive, review,
or acceptance authority. User and project settings override globals, duplicate
skills are not injected, and version checks are metadata-only until the host
explicitly authorizes the operation.

Storage inventory, archive, cleanup, relocation, and monitoring form a delegable
dedicated `STORAGE LEAD` lane. CTRL keeps unrelated project lanes open and owns
topology, ownership, proof, blockers, and acceptance only. CTRL storage work is
limited to read-only reconciliation or an explicitly authorized, narrowly bounded
host-safety stop; long-running copy, move, or delete work is always delegated.
The STORAGE LEAD uses an exact target manifest, exact-root and active-process,
live-log, database, and dirty/current-worktree guards, then performs a recoverable
move or copy-verify-remove and returns target and free-space receipts for independent
review. Storage pressure alone never authorizes destructive inference.

## CORE

Keep the runtime—not prompts—as the canonical state, ownership, artifact identity, and acceptance authority. Before mutation, establish an evidence-backed execution brief: user outcome and context, canonical state, binding invariants/non-goals, dependencies/risks, approach, and proof. Preserve project conventions unless bounded inspection proves greenfield; escalate material ambiguity, conflict, inaccessible authority, or missing evidence. Explicit user direction outranks SWARM defaults. Make reversible, evidence-backed choices inside the owner’s authority; ask only the smallest decision that changes intent, canonical truth, scope, cost, risk, or the reserved approval boundary.

Treat failed, timed-out, or non-atomic writes as untrusted. Verify the exact target and intended diff scope, preserve pre-existing work, recover only the damaged target from a verified baseline/backup, reapply smaller patches, and revalidate—never broadly roll back a shared surface.

Every durable CTRL, LEAD, and persistent SPECIALIST has one goal with objective, stopping condition, authority boundary, and proof. MOTHER is available only as an optional manager-style SPECIALIST with an advisory truth surface; it never becomes a second root or authority. `UNVERIFIED` is an open acceptance failure. Every artifact-producing lane declares its typed lane kind, immutable `ArtifactIdentity`, bound LEAD identity, deterministic `ProofPlan`, and independent `ACCEPTANCE` route. The planner selects the minimum proof from changed surfaces, claims, authority, dependency reach, incident matches, runtime signals, and repository capabilities; unknown input broadens proof. T0 atomic work uses focused contracts, T1 ordinary code adds impacted proof, T2 adds browser proof only for affected or claimed browser/visual surfaces, T3 provider/security/data work adds plan review and authority proof, and T4 release work replaces impacted proof with broad package/parity proof and composed acceptance. Only non-artifact `NON_CODE` work may use an explicit empty contract. Stable exact-input gate receipts may be re-observed and adopted as execution evidence only when plan, command, gate spec, environment, freshness, proof class, claim, and artifact still match; they never carry acceptance authority. Provider, deployed, device, and human claims remain `UNVERIFIED` unless an isolated host verifier records a typed observation with exact plan/spec/artifact/environment bindings, evidence digest, and bounded freshness; in-process commands, signatures, and caller-created receipts cannot close them. T0 independence cannot be disabled by caller assertion. The bound LEAD integrates and records exact-artifact gate results as `PASS`, `FAIL`, or `TIMEOUT`; a timeout never passes and permits at most one typed transient retry. Missing, failed, timed-out, wrong-artifact, uncovered-claim, or source-only receipts stay open; CTRL may surface but never manufacture acceptance. Load [task-contract.md](references/task-contract.md) to record the contract and [review-contract.md](references/review-contract.md) for all acceptance, incident, proof, review, and claim-limit rules.

Classify proof by the authority and transport actually exercised. Mocks, interception, fixtures, or an in-memory substitute prove only that substitute; name it and leave each unexercised boundary `UNVERIFIED`. For a visual claim, inspect the exact final frame: real primary substrate and relevant user context must be visible. A correct overlay cannot rescue a blank, fallback, mocked, placeholder, or failed substrate; relevant console/page/network failures remain findings. Load the review contract before accepting visual, browser, provider, deployed, device, security, consequential, or release work.

For design or taste-led generation, honor the user’s approval boundary: a clear direction authorizes generation; a reserved choice requires candidates and a wait. Classify supplied references as loose inspiration or binding. Bind self-review to the exact delivered artifact, not previews or transformation receipts. Use [design-guide.md](references/design-guide.md) and the review contract for binding-reference fidelity, real-content rendering, accessibility, and design review. Do not promote a reviewer’s preference, a candidate, silence, or “best available” judgment into approval.

Review and correction must be materially worthwhile. Outside design, require a concrete consequence and observable improvement that outweighs the work; do not turn preference or theoretical purity into backlog. Stop once outcome, proof, and risk threshold pass. Design may refine granular craft within the accepted direction, never unrelated scope. Correct doctrine at its lowest existing governing layer, consolidate rather than add incident clauses, and regression-test contrasting outcomes. Load the review contract for the full significance, escaped-defect, and independent-review procedure.

For a material capability choice, load [proven-solutions.md](references/proven-solutions.md): prefer an existing fitting, authorized primitive or workflow when its outcome benefit exceeds total cost; otherwise build the smallest native path. Never make discovery, installation, or external contact a prerequisite without authority.

WATCHDOG is an optional alert-only sensor bound to an accountable LEAD or persistent SPECIALIST goal, never CTRL, a role, or a worker. At the due event or a material failure signal it checks milestone/deadline/goal progress, flow integrity, and outcome integrity. It emits only `CLEAR`, `ATTENTION`, or `BLOCKER`; it never chooses or applies a correction. Load [monitoring.md](references/monitoring.md) for binding, evidence, alert routing, and the lean owner-heard post-alert review.

In hands-off mode, an active durable goal continues without routine prompting or topology churn. Model/task messages and ordinary usage evidence do not interrupt it. Pause only for explicit user direction, a material immutable handoff/review, the stopping condition, or a genuine human-authority, safety, destructive, or required-gate blocker. A usage limit selects the next viable lower-overhead structure at a safe boundary and becomes `BLOCKER` only when no permitted route can progress.

## ROLE

Every role contract states only PURPOSE, OWNERSHIP, BOUNDARIES, and ESCALATION. CTRL is the sole root and owns intake, durable objective ledger, topology, shared-surface coordination, final composed acceptance, and the human route. LEAD owns one mutable lane, integration, gates, and lane completion. DOER owns one bounded artifact. A persistent SPECIALIST owns one named cross-cutting truth surface and gate; MOTHER is one optional advisory SPECIALIST profession. EXPERT is bounded advice without artifact ownership; independent REVIEW verifies the frozen plan and the frozen completed artifact. WATCHDOG is a scoped sensor, not a role. No prompt transfers authority between roles.

`roles/` filenames are the default profession registry; an assigned named profession loads its matching lowercase card when present. The card refines perspective only and never transfers role authority; explicit user direction still wins.

Name roles so responsibility and artifact are unambiguous: use exactly one configured role icon unless disabled; name DOERs by their real job, lane owners as `<domain emoji>LEAD - <responsibility>`, specialists as `<role emoji><PROFESSION> - <truth surface>`, and other roles as `<role emoji><ROLE> - <artifact>`. Load the hierarchy reference for specialist trigger, free professions, ASSIST/ADVISOR, exact authority, task materialization, and detailed naming.

## TASK

Give an atomic task only CORE, role, objective, acceptance/non-negotiables, owner, dependencies, mutable surface, canonical artifact/version, proof limits, and accepting route/blocker. Record the role, surface, boundaries, proof, accepting route, goal, and acceptance contract before work. Reject mutation outside that recorded lane until the current owner releases or transfers it. Use [task-contract.md](references/task-contract.md); do not paste history, a crew handbook, or runtime-enforced laws.

## EVENT

CTRL is the human review feed, not a management log. At the next safe boundary, surface each new material screenshot, generated result, mockup, comparison, excerpt, or proof that can help the user judge or steer; caption it with what it shows and its claim limit. Record each material result as surfaced once with a receipt or withheld with the exact defect, duplication, or authority reason. Paths, worker finals, manifests, and folders are provenance—not delivery—and an undisposed material result blocks acceptance, archive, and phase advance.

Immediately after a screenshot, browser capture, recording, ImageGen result, mockup, or preview produces a local file, its owning lane must run `python skills/swarm/scripts/swarm_proof.py <path> --evidence-id <stable-id> --task-id <host-task-id> --kind <kind> --caption <caption>`. This deterministic receipt copies the file into the bounded content-addressed evidence store; the console discovers it on the next observation without reading task messages or invoking a model. Registration means available for review, never surfaced or accepted. CTRL still embeds the decisive artifact conversation-natively and records the external surface receipt before changing its runtime disposition.

Every CTRL heartbeat begins by checking the material-evidence ledger for new screenshots, ImageGen results, mockups, comparisons, and test or browser proof. Pending material evidence is the heartbeat's first reminder: surface it inline at the next safe message boundary or record the exact objective reason it is withheld before sending ordinary progress prose. An unchanged heartbeat stays silent only when no new material proof is due.

Render decisive proof inside the CTRL feed response itself. Use conversation-native image, audio, generated-image, or visualization content so the user can inspect it at a glance without opening a path; tool previews, local-path Markdown, file links, and commentary that disappears behind the final response do not count as surfaced proof. Keep links only as provenance or fallback. For a visual set, embed the smallest representative gallery or contact sheet that proves the claim, caption each state, and bind the gallery to the artifact identity and claim limit. If the host cannot render the content inline, report that exact delivery blocker and provide the best clickable fallback, but leave the result unsurfaced and acceptance open.

When material previews form one decision set, surface each promptly and also provide one consolidated decision gallery that embeds every candidate with a concise label and known defect. A representative subset is allowed only for a genuinely large set the user did not ask to see in full, with the complete inventory and exact omissions. Links or an inventory alone cannot accept a decision set. Load [review-contract.md](references/review-contract.md) for visual evidence and [monitoring.md](references/monitoring.md) for feed receipts and correction behavior.

Emit only a material result, inspectable proof, steerable decision, exact blocker with recovery, acceptance verdict, release state, or direct answer to a topology question. Lead with the user outcome, then the smallest decisive inline proof, then remaining risk and next material checkpoint only when non-empty. Never lead with task activity, role inventory, commands, paths, or a tool run; never use fixed word/count/keyword caps. For visual/browser work, a fresh representative capture is required unless capture is exactly blocked; for nonvisual work, show a compact excerpt, table, or before/after proof.

Before a finite portfolio, lane, review, migration, audit, or one-off task ends, its accepting owner inventories every visible task it created or superseded. Keep only work with a concrete active goal, dependency, correction, handoff, user choice, or continuation. For SWARM-created state whose current custody is independently verified, the host task API may release ownership/leases, make it terminal, unpin, or archive only with the matching receipt, and must verify that receipt. User-created, renamed, titled, pinned, unpinned, archived, or state-changed tasks remain untouched absent an exact host-owned explicit-user receipt naming that mutation. No unconditional unpin/archive is permitted. Archive failure is an exact CTRL blocker, never a silently completed task. Archive a finite CTRL after its final handoff only under the same custody guard.
