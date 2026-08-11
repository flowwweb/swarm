---
name: swarm
description: Coordinate complex work with the shallowest reliable structure, explicit authority, canonical state, bounded recovery, and independent review.
---

# SWARM

System for Workload Allocation, Routing & Management.

Use the shallowest structure that can finish reliably. `CTRL → DOER` is enough for atomic work. Add MOTHER only when orchestration, state, or lifecycle earns its cost. Add a LEAD for a real workstream; add ARCHITECT and multiple LEADs only for real system design or independent workstreams. Evaluate scope, architecture impact, independent tasks, dependencies, uncertainty, blast radius, specialisation, useful parallelism, and coordination overhead. Collapse idle capacity after work narrows.

CTRL speaks with people and never invents technical decisions. MOTHER alone changes topology. ARCHITECT owns architecture and contract versions. LEAD owns one workstream. DOER executes. EXPERT advises without transferring ownership. REVIEW independently verifies and never approves work it authored.

Canonical state, not conversation history, holds tasks, owners, versions, artifacts, blockers, findings, leases, and lifecycle. WAITING names a dependency; cycles emit deadlock. Workers are replaceable; retirement archives useful state. Retries are bounded and materially changed. A stale task cannot silently proceed. Completion requires independent review, integration, and any required architecture checkpoint.

MOTHER, every LEAD, and every persistent ARCHITECT continue one durable goal with an objective, stopping condition, authority boundary, and required proof. Keep an end-to-end requirement ledger in the task-tree receipt; `UNVERIFIED` is an open acceptance failure. The MOTHER heartbeat is passive: it observes material change, uses one same-surface recovery, then releases an unchanged lane with its exact blocker and unblock condition.

LEAD integrates and inspects each whole lane result before it reaches independent REVIEW. A conflicting unfinished goal is escalated rather than replaced. An atomic route may skip the LEAD, but never independent acceptance where review is required.

The legacy phrase “zerg rush” means starting only disjoint, integration-ready work; it never overrides adaptive depth, ownership, or the coordination-cost test.

RUSH configuration and state remain readable only as migration compatibility. New user-facing output says SWARM. Prefer one broad runtime invariant over incident-specific prompt rules. Treat the console as a CTRL/observability projection, never a second authority.

Workspace hygiene is mechanical: classify completed work as NONE, LOW, HIGH, or PINNED review value; archive NONE after verification, retain LOW/HIGH for configured windows, and exempt PINNED items. Archive stale work as `ARCHIVED_STALE` with reason, replacement/version provenance, and promoted operational knowledge. Archive is never delete. Global configuration is schema-validated with packaged defaults → one selected global config; direct task instructions are not file-merge layers. Retention, lanes, WIP, heartbeat, review, telemetry, and CTRL policy are configurable, while single MOTHER, independent review, bounded recovery, and canonical-state continuity are not.

HIVE is a compact logical namespace for durable SWARM lessons that have no better authoritative home. Current canonical state and repository/project truth outrank HIVE; archive/history is lower. Keep only concise decisions, constraints, meaningful failed approaches, or continuation facts, reference existing durable truth instead of copying it, and hydrate only relevant current records inside the context budget. HIVE never becomes a product-memory prescription: ARCHITECT remains free to design target-product memory from its own requirements. Workers may stay WARM while their compact context has near-term value; retirement flushes zero or a few unique lessons before ownership transfer.
