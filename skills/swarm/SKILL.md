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
