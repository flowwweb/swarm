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

Treat user messages as one ordered intent feed, not isolated commands or an
unconditional last-message-wins register. Reconcile every newly observed message
against the active objective and prior unsuperseded instructions, classifying it
as a continuation, clarification, added constraint, correction, approval,
status question, cancellation, or replacement. Merge continuations,
clarifications, constraints, corrections, and approvals into the active request;
replace or cancel prior scope only when the user actually says to do so or the
new instruction directly conflicts. A burst of messages is one logical turn:
preserve every compatible instruction and apply explicit corrections before
accepting, stopping, waiting, or routing further work. A tool run or owner turn
does not consume messages invisibly; after it returns, reconcile all unseen user
messages before judging the output. Never require the user to repeat a message
that arrived while work was running.

SWARM runtime never calls or authorizes pin/unpin. Every user-authorized CTRL creation
must surface the created task ID, exact directive/title, `pinned: false`, and
`placement: placement_unverified` immediately. Only the host may consume an exact
explicit-user pin request; the current host may append it below pinned folders.
The required future host placement capability remains a host concern, not runtime authority.
LEAD, DOER, REVIEW, WATCHDOG, storage, sidecar, and nested CTRL tasks default to
unpinned. Only direct host consumption of an exact current explicit-user request
may pin or unpin; the current host may append below pinned folders. Existing user
state is always preserved, and SWARM never requests or authorizes pin/unpin.

**Step 0, never defer:** For an unassigned user-facing task explicitly told by the user to use SWARM, derive a concise specific objective and resolve `role_icons`. Before any title request, obtain a fresh host-owned custody receipt. SWARM runtime never calls or authorizes pin or unpin; every created CTRL is surfaced with `pinned: false` and `placement: placement_unverified`. Only the host may consume an exact explicit-user pin request, and current placement may remain below pinned folders. Otherwise preserve the current user state and continue only with truthful internal CTRL identity. If either host control is unavailable or fails, state the exact blocker and never claim the UI changed. A task assigned by an existing CTRL keeps its assigned role. A CTRL cannot create, fork, promote, replace, rename, recover-as-new, or link a successor CTRL unless the user explicitly requests that exact operation. The plugin may prepare a typed single-use request bound to source CTRL, target identity, objective, and scope, but code running in its interpreter cannot authorize the host action. The actual Codex task API must independently consume a host-owned user receipt; without that host enforcement the request is non-authoritative and no new CTRL may be created. Adjacent work stays inside the current CTRL or returns to the user.

After the Step 0 custody check—whether it produced an eligible SWARM receipt or preserved existing user state—invoke the sibling `scripts/swarm_console.py --start` once. It obeys `console.open_on_start`, reuses the local server and an already-open portal tab, and opens the portal in the default browser only when needed. A launcher or browser failure is advisory and never blocks SWARM work.

After the Step 0 custody check, always ask and capture both intake answers before routing: **What is the goal for this task?** and **What is the most efficient safe way to complete it?** A one-shot user prompt may already contain the answers; CTRL must still restate the goal and proposed efficiency strategy so the two fields are inspectable before it proceeds. Then inspect or create exactly one matching durable goal when `goals.use_goals = true` (the default), and record its objective, canonical artifact/mutable surface, owners, dependencies, accepting route, proof, and claim limits. When `goals.use_goals = false`, retain the same intake and graph receipt but do not create or continue a durable goal; the setting is an explicit persistence choice, not permission to skip intake. Reuse only when objective, surface, and accepting route match; a pending creation receipt reserves that identity. Stop a disproved duplicate before mutation and archive it after resolution. For goal ownership, title rules, duplicate prevention, visible-lane economics, delegation exceptions, role selection, and topology, load [hierarchy.md](references/hierarchy.md).

Steer, do not overcorrect: classify each fresh instruction as `ADDITIVE`,
`CORRECTIVE`, or `REVERSAL`, bind
it to the explicitly named scope, and record which accepted behavior remains.
Extend compatible behavior, correct only the finding, or reverse only what the
user explicitly reversed; preserve unaffected topology, dirty custody, proof
boundaries, accepted artifacts, and lanes. Never turn a local correction into a
blanket opposite rule. A fresh host-observed direct-user turn for a specific CTRL
also creates a scoped keep-out: Master must not send conflicting or duplicate
directives, enqueue follow-ups, wake that CTRL's subordinate owners, or interrupt
the turn. Unaffected lanes and read-only portfolio heartbeat continue. Release
the keep-out only when the turn completes or the user explicitly hands coordination
back; silence, age, stale state, or inference cannot extend it indefinitely.

Immediately after that receipt—and before topology or work—use `swarm_contract.py request` to `list` then `audit` the exact repository and reconcile every unresolved request. A missing store returns empty/unattached without writing; enable continuity only with an explicit absolute repo root before consequential request work. Intake stages non-runnable `REQUEST_PENDING`, publishes its reserved-ID `DECISION`, calls live `register`, verifies the digest, then activates. Serialized bridge calls are read-only. New input accumulates or reprioritizes by default; only an explicit scoped cancellation or replacement supersedes matching open work, and unrelated open work remains preserved. Persist each typed event cursor and digest; after restart, a new current event must exceed its persisted feed-sequence floor without replaying old feed objects. Audit again before closeout/archive; any unresolved, orphaned, invalid, or provisional record blocks the claim. Missing/corrupt receipts are `UNVERIFIED`, never an empty ledger.

Before the first mutable handoff, select the smallest graph that satisfies the captured objective, efficiency strategy, ownership, dependencies, resumption, integration, and acceptance evidence. Follow [graph-engineering.md](references/graph-engineering.md): one CTRL root, explicit artifact-owning lanes, parallelize only independent work, serialize shared-surface gates, and keep every edge explainable by a dependency or acceptance reason. A game objective selects the registered `game_studio` graph: game-studio lead, design, engineering, art, audio, playtest/QA, and release agents with production dependencies; medium and large lanes are visible Codex tasks, while lane-local bounded work may use subagents. Do not flatten a domain graph into a single undifferentiated worker list.

Use the shallowest structure that can finish the accepted objective. `CTRL_DIRECT`
is limited to exactly one low-risk atomic outcome using `GENERAL` work on one mutable
surface: read-only inspection, one focused check, or a bounded copy,
documentation, or formatting edit with no external side effect, cross-file
behavior, dependency, handoff, or separate acceptance receipt. Otherwise use
`CTRL_DELEGATED`. Multi-file or multi-surface work, runtime/API/auth/data,
provider/deployment/device state, visual work, multiple proof gates, or
independent review MUST open a visible senior Codex task/chat before CTRL does
substantive work. That lane has its own cwd, owner, heartbeat, mutable surface,
and accepting route. Structural authority is exactly `CTRL`, `LEAD`, and
`DOER`, but it is not fixed depth: a LEAD may produce directly, recruit a DOER
for a bounded artifact, or recruit a nested LEAD when a subordinate boundary
needs independent durable ownership, heartbeat, integration/review surface,
worktree isolation, cross-lane dependency, or its own team. No pass-through,
headcount, depth, or approval ceremony is mandatory. Independent review uses a
separate visible owner from the producer and never becomes a structural tier.

Only genuinely small, single-surface, low-risk `GENERAL` work remains eligible
for `NORMAL_SUBAGENT` when measured task economics favor it. The subagent stays
inside its accountable owner and cannot own, hand off, review, or accept a
durable lane. A capacity-forced degraded subagent records the exact host
failure, immutable checkpoint, resumption marker, and `UNVERIFIED` gates. If a
required visible task cannot be created, surface the exact blocker or a typed
degraded route; never silently expand CTRL or subagent authority. `DESIGN`,
`IMAGEGEN`, and `IMAGE_EDIT` always open a visible visual task. Product/UI
experience, interaction, mockup, and design-system work binds Designer;
expressive illustration, concept art, media, motion, 3D, photography, or sound
binds Artist. Profession changes perspective and craft, never authority.

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

Materialize a visible task lane whenever durable ownership or interruption-safe
resumption is required. Use a subagent only as short bounded capacity inside an existing lane: it remains eligible only for genuinely small, single-surface,
low-risk `GENERAL` inspection or review and never substitutes for a qualifying durable task. It never gains lane ownership, handoff, heartbeat, acceptance, or
host mutation authority. Hidden subagents are non-recursive leaves: routing facts
that may need recruitment or recursive delegation require a visible owner. If a
leaf discovers that need, it stops and returns `PROMOTE_TO_VISIBLE_TASK` with the
remaining deliverable, custody boundary, and required proof; the parent reuses
or creates the visible owner. Internal-helper or read-only-tool approval gates are failed capacity: cancel the attempt, record the host gate, and continue inside
the same accountable boundary without asking the user. That fallback never grants external, provider, destructive, or user-reserved authority.

CTRL is the operator/orchestrator, not the producer. Keep the small-work
exception: `CTRL_DIRECT` is valid for one low-risk, atomic `GENERAL` outcome
when measured coordination overhead costs more than the work. That exception
covers bounded copy, documentation, formatting, read-only inspection, or a
focused local check; it does not let CTRL choose visual taste, generate a
mockup, run image generation, own a production artifact, or silently become a
LEAD/DOER.

The active-owner and no-duplicate guards protect user custody and topology; they
are not execution gates. In particular, they prevent a parent/master CTRL, peer
CTRL, or unsolicited replacement lane from hijacking a user-active CTRL or its
owned surface. They do not prevent the current owning CTRL from continuing
already-authorized work through its existing owner, sending a clarification,
inspecting completed output, or reorienting that same owner after a concrete
defect or missed receipt. `active` status alone is neither progress nor a
blocker and must never cause wait-only behavior. Direct user instruction may
reorient the existing owner within the same lane immediately; create a successor
or duplicate only when the user-authorized topology explicitly permits it.

Design, mockup, image-generation, and image-editing work defaults to
`CTRL_DELEGATED` and a typed visual ownership assignment, even when the request
is small. Designer owns product experience, interaction, hierarchy, and design
systems; Artist owns expressive media and craft. The assigned visual profession
owns the candidate artifact and visual proof; CTRL routes the work, surfaces
the decision set, waits at the user's approval boundary, and composes the
accepted result. If the required visual lane cannot be
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
review. It reclaims only exact stale or rebuildable residue incrementally and never
touches active or growing logs, current sessions, databases, dirty product work, or
live-process-referenced paths. Resource pressure is command-scoped, not a project
freeze: above the exact critical safety floor, keep source/review moving through
small durable checkpoints and serialize only predictably large build, export,
browser, Docker, install, device, or provider jobs. Verify `O:\` before using it
for large sequential artifacts, immutable evidence, archives, installers, or
release bundles; keep active worktrees, databases, dependency trees, and
random-I/O-heavy caches local. A recovery target such as 10 GiB is not itself a
freeze gate. Load [monitoring.md](references/monitoring.md) for the full resource,
archive, and copy-verification gates.

## CORE

Keep the runtime—not prompts—as the canonical state, ownership, artifact identity, and acceptance authority. Before mutation, establish an evidence-backed execution brief: user outcome and context, canonical state, binding invariants/non-goals, dependencies/risks, approach, and proof. Preserve project conventions unless bounded inspection proves greenfield; escalate material ambiguity, conflict, inaccessible authority, or missing evidence. Explicit user direction outranks SWARM defaults. Make reversible, evidence-backed choices inside the owner’s authority; ask only the smallest decision that changes intent, canonical truth, scope, cost, risk, or the reserved approval boundary.

Treat failed, timed-out, or non-atomic writes as untrusted. Verify the exact target and intended diff scope, preserve pre-existing work, recover only the damaged target from a verified baseline/backup, reapply smaller patches, and revalidate—never broadly roll back a shared surface.

At every meaningful stable boundary, long-lived CTRL and LEAD work records exact
task identity/state, source SHA/tree/parent, dirty custody, proof manifest and
claim limits, blocker, and next bounded action. Commit only coherent attributable
work after proportionate proof; never automatically stage, reset, clean, normalize,
commit, or absorb unrelated dirty work. A successor must acknowledge that exact
immutable checkpoint before handoff. Archive or relocation additionally requires
quiescent, process-free, handle/lock-free, size-stable state and exact destination
file-count, byte-count, and hash parity with a recoverable manifest. Creation age
alone is never stale evidence; active or growing logs remain protected.

`automation.mode = "standard"` may turn that evidence into bounded requests:
exact owned commit, separate visible independent review, history-preserving
integration after fetch and readable `ACCEPT`, repository-defined release with
rollback, and a host-consumed archive request. Mixed dirty work, silence,
in-progress state, `BLOCKED`, unreviewed divergence, open task gates, user
custody, or missing host custody blocks advancement. The runtime never emits
force-push, rebase, reset, or host archive authority; `archive_unverified` stays
visible until the host confirms it. `manual` emits none of these requests.
The production runtime normalizes raw mode before every decision and accepts
only typed, fresh receipts bound to repository root/identity, branch/remote,
candidate SHA/tree, operation, authority, and any fetched remote head. Unbound
strings and mismatched receipts never authorize Git, release, or archive work.

Every durable CTRL, LEAD, and persistent SPECIALIST has one goal with objective, stopping condition, authority boundary, and proof. Profession is a separate typed perspective selected from the 24-card registry; unknown historical titles remain inert user-owned text and never become routable authority. `UNVERIFIED` is an open acceptance failure. Every artifact-producing lane declares its typed lane kind, immutable `ArtifactIdentity`, bound LEAD identity, deterministic `ProofPlan`, and independent `ACCEPTANCE` route. The planner selects the minimum proof from changed surfaces, claims, authority, dependency reach, incident matches, runtime signals, and repository capabilities; unknown input broadens proof. T0 atomic work uses focused contracts, T1 ordinary code adds impacted proof, T2 adds browser proof only for affected or claimed browser/visual surfaces, T3 provider/security/data work adds plan review and authority proof, and T4 release work replaces impacted proof with broad package/parity proof and composed acceptance. Only non-artifact `NON_CODE` work may use an explicit empty contract. Stable exact-input gate receipts may be re-observed and adopted as execution evidence only when plan, command, gate spec, environment, freshness, proof class, claim, and artifact still match; they never carry acceptance authority. Provider, deployed, device, and human claims remain `UNVERIFIED` unless an isolated host verifier records a typed observation with exact plan/spec/artifact/environment bindings, evidence digest, and bounded freshness; in-process commands, signatures, and caller-created receipts cannot close them. T0 independence cannot be disabled by caller assertion. The bound LEAD integrates and records exact-artifact gate results as `PASS`, `FAIL`, or `TIMEOUT`; a timeout never passes and permits at most one typed transient retry. Missing, failed, timed-out, wrong-artifact, uncovered-claim, or source-only receipts stay open; CTRL may surface but never manufacture acceptance. Load [task-contract.md](references/task-contract.md) to record the contract and [review-contract.md](references/review-contract.md) for all acceptance, incident, proof, review, and claim-limit rules.

Every delegated task also declares its exact deliverable, accountable owner,
portable custody boundary, immutable artifact and path manifest, required proof
classes, due event, and maximum readable return size. Creation, dispatch,
commentary, timeout, silence, unreadable or empty output, and `IN_PROGRESS` are
activity only. They cannot advance review or completion. The owner returns one
typed, artifact-bound `ACCEPT`, `REJECT`, or `BLOCKED` receipt; only a complete
`ACCEPT` may enter independent review, and `BLOCKED` remains open. Source,
static, local, browser, authenticated, provider, payment, deployed, device, and
human claims stay separate and never promote one another.

Classify proof by the authority and transport actually exercised. Mocks, interception, fixtures, or an in-memory substitute prove only that substitute; name it and leave each unexercised boundary `UNVERIFIED`. For a visual claim, inspect the exact final frame: real primary substrate and relevant user context must be visible. A correct overlay cannot rescue a blank, fallback, mocked, placeholder, or failed substrate; relevant console/page/network failures remain findings. Load the review contract before accepting visual, browser, provider, deployed, device, security, consequential, or release work.

For design or taste-led generation, honor the user’s approval boundary: a clear direction authorizes generation; a reserved choice requires candidates and a wait. Classify supplied references as loose inspiration or binding. Bind self-review to the exact delivered artifact, not previews or transformation receipts. Use [design-guide.md](references/design-guide.md) and the review contract for binding-reference fidelity, real-content rendering, accessibility, and design review. Do not promote a reviewer’s preference, a candidate, silence, or “best available” judgment into approval.

Review and correction must be materially worthwhile. Outside design, require a concrete consequence and observable improvement that outweighs the work. Block only material user impact, correctness, safety, regression, maintainability, reference fidelity, or an explicit acceptance failure; cosmetic preference is an optional note and never another loop unless the user requested that polish. Choose the smallest durable solution: reuse, delete, or consolidate before adding abstractions, roles, process, tests, or dependencies. Classify each instruction or failure in its named scope, fix it locally, preserve accepted product character and useful capability, and regression-check the adjacent behavior at risk instead of inferring an opposite blanket rule. Design may refine granular craft within the accepted direction, never unrelated scope; use [design-guide.md](references/design-guide.md). If the same material finding repeats without a new receipt, stop the method, reorient the same owner once with temporary higher reasoning inside the accepted model authority and a root-cause question, then use the existing accountable parent or an independent reviewer if it still fails—never a new CTRL. Correct doctrine at its lowest existing governing layer and consolidate rather than add incident clauses. Confidence never permits fabricated proof, weakened security, or custody bypass. Load the review contract for the full significance, visual-proof, escaped-defect, and independent-review procedure.

For a material capability choice, load [proven-solutions.md](references/proven-solutions.md): prefer an existing fitting, authorized primitive or workflow when its outcome benefit exceeds total cost; otherwise build the smallest native path. Never make discovery, installation, or external contact a prerequisite without authority.

WATCHDOG is an optional alert-only sensor bound to an accountable LEAD or persistent SPECIALIST goal, never CTRL, a role, or a worker. At the due event or a material failure signal it checks milestone/deadline/goal progress, flow integrity, and outcome integrity. It emits only `CLEAR`, `ATTENTION`, or `BLOCKER`; it never chooses or applies a correction. Load [monitoring.md](references/monitoring.md) for binding, evidence, alert routing, and the lean owner-heard post-alert review.

In hands-off mode, an active durable goal continues without routine prompting or topology churn. Model/task messages and ordinary usage evidence do not interrupt it. Pause only for explicit user direction, a material immutable handoff/review, the stopping condition, or a genuine human-authority, safety, destructive, or required-gate blocker. A usage limit selects the next viable lower-overhead structure at a safe boundary and becomes `BLOCKER` only when no permitted route can progress.

## ROLE

Every role contract states only PURPOSE, OWNERSHIP, BOUNDARIES, and ESCALATION. CTRL is the sole root and owns intake, durable objective ledger, topology, shared-surface coordination, final composed acceptance, and the human route. LEAD owns one mutable lane, integration, gates, and lane completion. DOER owns one bounded artifact. A persistent SPECIALIST owns one named cross-cutting truth surface and gate; the profession `specialist` is stored separately from the structural SPECIALIST role. EXPERT is bounded advice without artifact ownership; independent REVIEW verifies the frozen plan and the frozen completed artifact. WATCHDOG is a scoped sensor, not a role. No prompt transfers authority between roles.

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

Emit only a material result, defensible progress change, inspectable proof, steerable decision, exact blocker with recovery, acceptance verdict, release state, or direct answer to a topology question. Lead with the user outcome, then the smallest decisive inline proof, then remaining risk and next material checkpoint only when non-empty. Never lead with task activity, role inventory, commands, paths, or a tool run, and never impose fixed word, count, or keyword caps. The default pulse is one compact human-readable card or paragraph per project: project/CTRL, state, receipt-backed progress percentage and basis or `Unmeasured`, latest material proof, first blocker, and next action/ETA. Keep exact machine receipts underneath for audit; do not dump raw logs, tool chatter, repeated plans, self-narration, or unchanged heartbeats into the human feed. For visual work, surface the highest-signal screenshot or artifact inline first and a compact gallery for every remaining requested surface, with explicit omissions and claim limits; links, filenames, source diffs, and prose are not visual proof. A fresh representative capture is required unless capture is exactly blocked; for nonvisual work, show a compact excerpt, table, or before/after proof. Prefer one readable `ACCEPT`, `REJECT`, or `BLOCKED` receipt over conversational back-and-forth. In progress is not done; source/static/local is not browser/deployed/human; `BLOCKED` is not accepted. Every return remains bound to the original objective, current profession and authority, owned deliverable, non-goals, and next acceptance gate.
