# Lean SWARM Reset Architecture

Architecture spec version: 1.1
Status: corrected candidate; documentation only
Candidate basis: canonical SWARM source at 0ff1cf1a4be69ca832a417e6051a288e926347c6, tree c0a6a2bd4734dceeb5bf00c185f9dd20482e9968, parent d956e5e1c4dba9de06543e7b424aba003888183d
Corrected input payload: 65fb9981bbeeb4ddebe44243c5c98761186dc75e81cb93cd0fcc4293c9a7f5b5
Scope: lean execution-kernel architecture; no implementation, schema migration, runtime activation, localhost mutation, or UI change

## Purpose and evidence boundary

SWARM is the lightest reliable Codex-native multi-agent harness: one CTRL directs lazy role work through one durable material ledger, one atomic handoff protocol, proof-aware acceptance, and an alert-only recovery/watchdog surface. Localhost is a richer read/projection control surface, not part of the hot prompt or execution-kernel budget.

Observed source seams, read-only:

| Existing authority or primitive | Current path and symbol | Observation | Corrected contract |
| --- | --- | --- | --- |
| Material lifecycle ledger | skills/swarm/runtime/progress_events.py, current compatibility class `ProgressLedger` (`append`, `replay`, `project`, `project_topology`) | Append-only material events, replay, topology projection, dedupe/conflict handling, and canonical projection digests already exist. The current implementation also writes a disposable projection during append/replay. | Keep one append-only Ledger. Rename or alias the compatibility class during migration without creating another public authority. Accepted lifecycle transitions are ledger events. Replay and projections are derived views; a later implementation slice must not introduce another mutable transition authority. |
| Request transport/state | skills/swarm/runtime/request_ledger.py, RequestStore.read/peek/_mutate_validated/with_current | The request file is locked and CAS-checked, but it is still a mutable request-state surface. core.py also translates request records and can write request transitions. | Retain RequestStore as an inbox and acknowledgement journal only. It may persist envelope receipt, dedupe identity, and append acknowledgement; it may not assert accepted lifecycle state. |
| Recovery and control path | skills/swarm/runtime/core.py, RetryTopologyLedger, resolve_control_path_failure, recover, heartbeat | Typed retry, recovery, user-control, custody, and blocking primitives exist, including terminal release fields. | Consolidate one state decision at this throat. USER_PAUSED and KEEP_OUT preserve open custody; BLOCKED requires retained exhaustion evidence, not a caller flag or one failed route. |
| Configuration | skills/swarm/scripts/swarm_config.py and skills/swarm/assets/swarm-config.toml | The loader already has one canonical Fast-mode boolean and derived host-tier receipts, but no settled single lifetime setting is present in the inspected asset. | Add only continuity.task_lifetime_hours in its own later config slice; remove competing lifetime thresholds during migration. |
| Control surface | console/server.py and console/static/* | Server and UI expose projections and receipts; browser/runtime acceptance is a separate gate. | Keep localhost as a projection and control surface with its own maintainability budget. It never becomes a second lifecycle ledger. |
| Role library | skills/swarm/runtime/progress_events.py role manifest helpers and the existing profession cards | The source validates the exact 24 built-ins and supports assignment/version bindings. | Keep 24 lazy role cards and skills. Materialize only the selected ready wave; do not preload or create role owners for headcount. |

The supplied prior payload is treated as an input binding, not as a locally recovered file. This candidate corrects the four stated findings without claiming that the prior draft was independently read from disk.

## Frozen system boundary

| Area | Decision | Preserved value and deletion boundary |
| --- | --- | --- |
| One CTRL | KEEP | One visible accountable control task owns objective, custody, routing, and acceptance coordination. |
| 24 professions and skills | KEEP, lazy | The library remains available; only a selected role card is injected when a ready artifact requires it. |
| Ledger | KEEP and make canonical | It is the only authority that accepts lifecycle/material transitions and proof-bearing outcome facts. |
| Offered -> acknowledged -> admitted handoff | KEEP | Each handoff is one immutable lineage-bound transaction; duplicate replay returns the original receipt. |
| Outcome and proof acceptance | KEEP | Commentary, activity, task presence, or a plan cannot raise accepted progress or complete a task. |
| Watchdog | KEEP, alert-only | It derives attention from ledger/request evidence and due events; it cannot assign, mutate, recover, or invent completion. |
| Configuration | KEEP, simplify | One canonical loader and one exposed lifetime setting; host-derived model/service receipts remain audit output, never competing inputs. |
| Localhost | KEEP as separate projection/product | It may have richer screens, diagnostics, and projections, but no second mutable state, scheduler, or arbitrary hot-path prompt budget. |
| Duplicate state/workflow authorities | SIMPLIFY/REMOVE | Request state, progress state, ad hoc task fields, and activity engines may not independently accept the same transition. Migrate reads, then delete competing writes. |
| Activity-weighted progress | REMOVE from completion | Keep liveness/attention telemetry only. Accepted progress is proof-weighted from factual material events. |
| Repeated unchanged retries | REMOVE/CONSOLIDATE | One retry ledger records the stable signature; unchanged action, target, outcome, and blocker trigger one bounded reassessment and a different route or exact blocker. |
| HIVE, Boost, Turbo, Spark overlap | SIMPLIFY/REMOVE from kernel | Preserve host-supported model capability receipts and explicit Fast-mode semantics. Remove overlapping scheduler/provider/model catalogs from the hot doctrine unless a distinct host receipt requires them. |
| Mandatory bridge/scheduler path | MOVE OUT / optional adapter | A bridge may deliver an inbox envelope, but it cannot be required for local ledger continuity or become a second state machine. |
| Hardcoded model catalog | REMOVE | Use host-derived capability/served-tier receipts. Do not infer provider, model, or tier from labels or configuration echoes. |
| Kanban, visualization, report/history weight | MOVE TO LOCALHOST | These are projections and decision aids, not prompt primitives or progress authority. |
| New scheduler, database, service, poller, or watchdog role | REMOVE | The smallest kernel reuses existing ledger, request inbox, due-event wake, and recovery seams. |

## Corrected lifecycle and custody state machine

The hot-path lifecycle states are:

INTAKE -> OFFERED -> ACKNOWLEDGED -> ADMITTED -> RUNNING -> RESULT_PENDING -> REVIEW_PENDING -> COMPLETE

Recovery and custody guards are nonterminal branches from any open state:

RUNNING or RESULT_PENDING -> RETRYING
RUNNING or RESULT_PENDING -> WAITING
RUNNING or RESULT_PENDING -> USER_PAUSED
RUNNING or RESULT_PENDING -> KEEP_OUT
RUNNING or RESULT_PENDING -> NEEDS_AUTHORITY
RUNNING or RESULT_PENDING -> STALLED

A valid outcome/proof receipt returns an open task to RESULT_PENDING or REVIEW_PENDING; only an independent accepted proof transition permits COMPLETE. An invalid, empty, timeout, 400, missing-thread, stale-cursor, or transport result is evidence of failure or uncertainty, never progress.

USER_PAUSED means the objective remains open and custody is retained until an explicit user resume/cancel/supersession receipt. KEEP_OUT means direct user control remains authoritative; peers cannot route, interrupt, wake, or block that lane. Neither state releases custody, consumes the objective, or becomes terminal merely because time passes.

BLOCKED is terminal only when the retained evidence bundle proves all of the following:

1. The same immutable task, owner, artifact, cause, and affected edge remain implicated across at least three distinct consecutive goal-turn receipts.
2. Every permitted safe route is explicitly listed and exhausted, with route receipts or a durable reason each route is unavailable.
3. No safe same-owner route, existing authorized handoff, or disjoint ready continuation is currently available.
4. One exact external or user state change, release condition, and responsible authority are named.
5. The validation passed before the blocked decision was retained, and duplicate goal-turn receipts do not increment exhaustion.

A failed observation is UNVERIFIED/RETRYING first. Unknown attribution remains UNVERIFIED. Historical BLOCKED receipts are immutable facts and are never rewritten to make the new rule appear retroactive.

## Canonical ledger versus request inbox

Ledger is the only accepted lifecycle authority. Its input event is validated for immutable project, CTRL, task, owner, artifact, scope, causal parent, proof, and custody identity before any append. Event identity and semantic dedupe identity are retained. Exact duplicate replay is a no-op returning the original cursor/digest. A conflicting event ID or dedupe key is retained as visible conflict or rejected according to the existing event class; it never overwrites accepted history.

RequestStore is transport inbox only:

1. Receive one bounded envelope with request identity, source, target, payload digest, and transport receipt.
2. Persist the envelope and inbox sequence under its existing lock/CAS.
3. Ask Ledger to validate and append the corresponding typed event.
4. Persist one acknowledgement containing request identity, event identity, event digest, and ledger cursor only after the append result is durable.
5. Return the original acknowledgement for an exact replay. A different payload under the same request identity fails closed.
6. The request state never changes lifecycle state directly; the ledger projection is the only accepted current state.

Crash-order contracts:

| Failure point | Required recovery |
| --- | --- |
| Crash before inbox append | No request or lifecycle effect exists. Replay the same request identity once; do not infer that work started. |
| Inbox append before ledger append | The durable inbox envelope is pending. Reconcile by exact request identity and payload digest, then attempt one bounded ledger append. |
| Ledger append before acknowledgement | Replay finds the event by identity/digest and returns its original cursor; write exactly one acknowledgement. No duplicate transition. |
| Acknowledgement before projection refresh | The append log is authoritative. Replay reconstructs the projection from the log; projection lag cannot erase the event or create a second event. |
| Duplicate request or acknowledgement | Same identity and digest return the retained receipt. A different digest is a visible conflict and fails closed. |
| Corrupt, orphaned, private, or oversized envelope | Retain a typed rejection/unknown receipt without mutating accepted state. Do not fabricate a missing artifact or completion. |
| Handoff or restart | Reconcile the inbox and ledger by request/event digest, then rebuild derived views. Custody and proof bindings survive; empty reader output does not clear them. |

Acceptance tests to implement in the later source slice:

- ledger is the sole transition writer;
- request inbox cannot set COMPLETE or BLOCKED;
- append-before-ack replay is exactly once;
- crash-before-append remains open and retryable;
- conflicting request/event digest is visible and non-mutating;
- replay and projection are deterministic after restart;
- USER_PAUSED and KEEP_OUT remain open;
- one failure cannot produce BLOCKED;
- three distinct goal-turn impasses plus exhausted routes can produce BLOCKED;
- duplicate goal-turn receipts do not increase exhaustion;
- independent proof is required before COMPLETE.

## One lifetime setting and continuity contract

Canonical config:

[continuity]
task_lifetime_hours = 24

Allowed range is an integer from 1 through 720 inclusive. The value is the only writable task-lifetime threshold. Elapsed time, active intervals, generation, packet age, and continuity state are derived read-only projections.

Deterministic migration precedence:

1. A valid explicit continuity.task_lifetime_hours wins.
2. If absent, a valid legacy ctrl_checkpoint_after_minutes value is converted by ceiling division to hours.
3. If that is absent, a valid legacy ctrl_prepare_after_minutes value is converted by ceiling division.
4. If no legacy value exists, use 24.
5. If an explicit value is invalid, inverted with any still-present legacy pair, or the legacy values conflict, fail validation visibly; never silently choose a competing timer. A successful migration writes one continuity value and records the source fields in a migration receipt, then removes their writable authority.

The elapsed basis is the durable sum of validated active orchestration intervals for the current CTRL generation, starting at the host activation receipt. Explicit user-paused intervals and intervals with no runnable authorized work contribute zero. Retry, compaction, reconnect, narration, and reader refresh do not reset elapsed time. A restart closes the prior interval at its last trustworthy host receipt and opens a new interval only after a fresh host receipt; it does not reset the accumulated high-water. A wall-clock regression or negative interval is retained as CLOCK_UNCERTAIN, does not lower the high-water, and requires a fresh receipt before more elapsed time is admitted.

At the threshold, the next stable boundary must durably checkpoint the current atomic step and prepare the handoff packet. No new mutable wave is admitted once the boundary is checkpoint-required, while already-running independent lanes may finish. A continuity packet binds source CTRL/task/goal, project brief generation/digest, request sequence/digest, progress cursor/digest, retry snapshot, owner/custody map, artifact/proof matrix, open requests, next action, limits, trigger, checkpoint, and packet digest. Any material change invalidates it. The receiver must have explicit host-owned user authority, revalidate current state, acknowledge the exact packet digest, and verify title then pin before intake. The source remains pinned until that acknowledgement and pin verification. No packet mints authority, links a successor, transfers acceptance, or overrides USER_PAUSED/KEEP_OUT.

This architecture intentionally uses one lifetime threshold rather than separate prepare/checkpoint timers. PREPARE and CHECKPOINT_REQUIRED are derived boundary states from the same value and current atomic-step safety, not additional writable settings.

## Measurable hot-path budgets

These are testable acceptance budgets for the plugin/in-context harness. They do not cap localhost screens, server maintainability, or projections.

| Budget | Exact measurement and surface | Target and over-budget behavior |
| --- | --- | --- |
| Instruction envelope | UTF-8 byte length of the rendered hot prompt: selected SKILL sections, one selected role card, task contract, current recovery suffix, and referenced receipt identifiers; excludes repository files and localhost code | At most 24,576 bytes. Before dispatch, compact/refer to canonical files or split the task; never silently truncate or spend a model call narrating the overflow. |
| Token accounting | Host receipt fields input_tokens and output_tokens for the same dispatch generation; tokenizer name/version is recorded when present | No token estimate is accepted. Missing fields are UNKNOWN. A token budget warning is visible but cannot raise progress or alter model/provider/tier automatically. |
| Material event | UTF-8 byte length of one canonical JSONL ProgressMaterialEvent after canonical serialization | At most 16,384 bytes, with a target median below 2,048 bytes and p95 below 4,096 bytes for the bounded fixture. Reject before append; never truncate. |
| Schema shape | Schema version, exact field allowlist, and count of serialized keys in each hot event/envelope | No unversioned event; no unknown keys; maximum 40 top-level event keys and 16 nested handoff fields. Fail closed before mutation. |
| Runtime state vocabulary | Count of the named hot-path lifecycle states in the state enum; custody guards are counted, not hidden | At most 14 states. New states require a replacement/deletion decision and contract update, not incidental growth. |
| Writable authorities | Count of surfaces that can write accepted lifecycle state | Exactly one: Ledger. RequestStore may write inbox/ack transport facts; config may write settings; neither can accept lifecycle state. |
| Lifetime settings | Count of writable keys under continuity | Exactly one: task_lifetime_hours. Legacy keys are migration inputs only and are removed from effective config. |
| Model calls | Calls attributable to one admitted attempt, and calls with reason progress/replay/ack | At most one task-execution call per admitted attempt; zero calls solely for progress, replay, acknowledgement, watchdog, or narration. |
| Polling | Timer wake frequency in the plugin/runtime path | Zero high-frequency polling. Use append notifications and bounded due-event wakes. |
| Conceptual primitives | Count of distinct hot-path concepts named by the schema: CTRL, role card, ledger event, inbox request, handoff, proof receipt, watchdog attention, continuity checkpoint | At most eight primitives. Localhost visualizations and history/report concepts are projections, not kernel concepts. |

Budget measurements are emitted as receipts bound to source SHA, generation, event digest, and operation. A missing metric is UNKNOWN, not zero. A budget failure blocks only the affected dispatch or append and leaves custody open; it does not create a new owner, change model/provider/tier, erase proof, or turn into product BLOCKED.

Contrasting acceptance contracts:

- a prompt just under and just over 24,576 UTF-8 bytes;
- multibyte UTF-8 text measured by bytes rather than character count;
- absent token receipt remains UNKNOWN;
- 16,384-byte event accepted and 16,385-byte event rejected before append;
- unknown schema key rejected before mutation;
- one duplicate replay does not add a model call or event;
- a progress heartbeat with no material event records no progress;
- high-frequency polling configuration is rejected or moved to localhost;
- a new role card is loaded on demand without materializing all 24 roles;
- localhost content is excluded from hot-path budget accounting.

## Smallest migration and deletion slices

1. Documentation candidate (this artifact only). Freeze the boundary and acceptance contracts. No runtime behavior changes.
2. Ledger throat. Add the lifecycle transition validator and append/ack receipts at Ledger; make replay/project pure derived reconstruction. Preserve old event bytes and read compatibility.
3. Request bridge. Convert RequestStore writes to envelope and acknowledgement facts; remove direct lifecycle writes from request helpers after a migration receipt proves equivalent replay.
4. Lifetime config. Add task_lifetime_hours with the precedence above, migrate and remove legacy timer writers, and persist active interval/high-water receipts.
5. Recovery consolidation. Route all retry, control-path failure, and heartbeat decisions through the one retained retry/continuity snapshot. Delete repeated unchanged retry paths and caller-supplied BLOCKED/keep-out/exhaustion assertions.
6. Handoff continuity. Add the immutable packet and receiver acknowledgement to the existing request/progress/proof ledgers; do not add a store, scheduler, successor creator, or pin authority.
7. Kernel slimming. Remove overlapping HIVE/Boost/Turbo/Spark orchestration, hardcoded model catalogs, mandatory bridge paths, and plugin-side Kanban/visual/report/history weight only after source references and compatibility readers are mapped.
8. Localhost projection. Preserve richer screens and diagnostics as read-only projections over ledger/request receipts. It is a separate product slice and must not be bundled into the plugin hot path.

Each slice must be one reviewed clean commit with a source SHA/tree, exact paths, proof receipt, independent acceptance, and a rollback point. The dirty UI custody currently present at console/static/app.js, console/static/index.html, and console/static/styles.css is unrelated and excluded from this candidate.

## Rollback and compatibility

This documentation candidate rolls back by reverting only its exact docs commit; it does not touch UI custody. Future source slices must be additive at first: retain old event readers, import legacy request envelopes into the inbox, and write a migration receipt before deleting a competing writer. A failed migration leaves the old accepted log and custody intact and marks the new route UNVERIFIED. Never reset, force-rewrite, rebase, or rewrite accepted ledger history. Localhost can continue projecting the old schema while the new derived view is validated, but it cannot author a second truth.

## Review request and claim limits

Requested accepting route: Security owner 01a02dbf-cc38-7df0-a8f1-82a7d909b36c plus one existing independent reviewer route already attached to this CTRL; the existing independent-review task 01a02240-41f5-7f30-aac9-358b4e8d2813 is the preferred read-only route. No new owner, task, lane, or worktree is requested by this artifact.

This candidate proves only a repo-owned architecture document and its exact source-bound observations. It does not prove runtime implementation, migration, config loading, persistence durability, host receipts, model/tier service, localhost, browser/accessibility, package/install/cache, deployment, security acceptance, or user/human acceptance. It does not include the three dirty UI files. The supplied prior payload hash is a correction binding, not an independent acceptance receipt.
