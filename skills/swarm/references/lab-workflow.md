# Lab workflow

A **Lab** is an open operating framework for a focused area of work, like an AI
lab, design lab, or biome lab. It uses SWARM's existing milestone, task, block,
artifact, decision-set, proof, and review contracts. It is not a new role, lifecycle state, backlog,
delegation system, or source of truth.

## When to use one

Use the smallest matching manifest in `../labs/catalog.json` when an area
benefits from iterative or cross-functional work. Keep one known atomic change
on its normal specialist task. A CTRL may name a custom Lab for any focused area
and apply the same thin manifest contract.

## Shape

Represent every Lab as one normal task under its owning CTRL. The CTRL handles
all delegation. The Lab may choose and change its roles, methods, and internal
order as evidence develops. Catalog roles are suggestions, not a fixed team.

Keep the manifest thin:

- the owned area or question;
- the intended outcome and proof;
- the stopping condition; and
- any fixed constraint the Lab must preserve.

Blocks are portions of the Lab task. A group of Lab tasks may share a milestone.
Use the existing quarter-step block scale:

| Value | Evidence |
| --- | --- |
| `.25` | Work started |
| `.5` | Handed to review |
| `.75` | Review accepted |
| `1` | Completed and committed |

A failed review leaves the block below `.75`, records the correction, and
returns it to the Lab's next short cycle.

## Open loop

1. **Frame:** state the owned area, intended outcome, proof, and stop condition.
2. **Work:** move in short inspectable cycles and adapt roles or methods from
   evidence.
3. **Review:** compare the strongest result against the goal and required proof.
4. **Promote:** integrate only accepted work, then complete and commit its block.

The Lab may change its internal approach whenever the goal, accepted constraints,
and proof boundary remain intact.

## Software engineering factory

A factory is a reusable workflow called by a Lab, not another role or backlog.
The Lab owns the outcome; its existing CTRL routes bounded work to existing
owners using normal tasks, blocks, artifacts, and acceptance.

1. **Frame and reproduce:** choose a testable slice and capture the baseline
   using [before/after proof](review-contract.md#capture-comparable-before-and-after-proof).
2. **Build:** resume the matching owner and checkout; isolate only when mutable
   work would conflict. Reuse the repo's architecture and route model effort to
   the challenge through existing routing rules.
3. **Prove and repair:** exercise the changed behavior, compare the result to
   the baseline, and repair failures with focused checks. Bind proof to the
   actual candidate and runtime, not a sibling checkout or stale server.
4. **Review and integrate:** use existing independent review and risk-based
   checks; resolve actionable findings and preserve release authority. Stop
   for a concrete blocker rather than chasing a numeric reviewer score.
   Verify the integrated outcome and hand settled worktrees to normal cleanup.

Other factories, such as design, may replace the work steps while retaining
the same ownership and proof contract. Load only the skills needed by the
current step; do not add a manager or duplicate state for each nested workflow.

## Completion

A Lab is complete when its task outcome is accepted, selected work is integrated,
the required proof passes, and its blocks are completed and committed. Lab-only
proof does not prove the integrated product.

## SWARM improvement Labs

The shared frozen corpus and three current improvement Labs live in
`../labs/labs.json`. Validate the matrix with:

```text
python skills/swarm/scripts/swarm_labs.py validate
```

Record actual candidate runs in a separate results JSON and compare them with
`swarm_labs.py report <results.json>`. Each run requires evidence. Token savings
remain `UNKNOWN` until the same scenario has measured Codex-token receipts for
both its baseline and candidate; ChatGPT tokens remain separate from Codex quota.
