# Lab and Factory Flows

A **Lab** is an open operating framework for a focused area of work, like an AI
lab, design lab, or biome lab. It uses SWARM's existing milestone, task, block,
artifact, decision-set, proof, and review contracts. It is not a new role, lifecycle state, backlog,
delegation system, or source of truth.

## When to use one

Use the smallest matching manifest in `../labs/catalog.json` when an area
benefits from iterative or cross-functional work. Keep one known atomic change
on its normal specialist task. A CTRL may name a custom Lab for any focused area
and apply the same thin manifest contract.

The six default Labs are Product, Research, Design, Test, Content and Growth.
Build and Ops are no longer default presets; existing unit identities,
manifests and history stay intact. Use the matching Factory for production,
or name a custom Lab when exploration needs a different focus.

## Shape

Represent every Lab as one normal task under its owning CTRL. CTRL routes the
request to the unit coordinator; the coordinator delegates bounded producer
tasks and returns accepted results to CTRL. The Lab may choose and change its
roles, methods, and internal order as evidence develops. Catalog roles are
suggestions, not a fixed team.

Lab and Factory coordinators may exchange bounded requests and immutable
artifacts directly. The receiving coordinator accepts the request within its
own goal before delegating its own tasks, retaining the owner, scope, evidence
and stopping condition in the existing contracts. Peers cannot mutate another
unit's surface, change its goal or bypass independent review. Route shared
priority decisions, ownership conflicts and new authority to CTRL.

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

Goals are enabled by default for every Lab and Factory using the same
`goals.use_goals` setting and existing goal owner. Bind the unit's own objective
to its coordinator goal and retain its parent outcome goal link. Preserve an explicit
persistence opt-out, while keeping the same bounded contracts.

The parent holds the major outcome. Each producer receives one concrete block
with artifact, exact scope, dependencies, acceptance and stop condition. Split
an unbounded request before assigning it; no producer receives the entire Lab
or software factory as its execution task.

## Open loop

1. **Frame:** state the owned area, intended outcome, proof, and stop condition.
2. **Work:** move in short inspectable cycles and adapt roles or methods from
   evidence.
3. **Review:** compare the strongest result against the goal and required proof.
4. **Promote:** integrate only accepted work, then complete and commit its block.

The Lab may change its internal approach whenever the goal, accepted constraints,
and proof boundary remain intact.

## Software engineering factory

Labs and Factories are first-class work units, separate from structural roles.
Each unit has one native task identity, its own goal, coordinator, bounded task
hierarchy and accepted results. The optional existing task-manifest `work_unit`
metadata records `LAB` or `FACTORY`, the goal and parent links; the confirmed
task ID is the coordinator identity. By default a draft without a goal ID remains
pending until its coordinator creates or binds the verified native goal before
production. An explicit `goals.use_goals=false` leaves the holder goal unbound
while preserving bounded contracts and production-role goal requirements.
Once bound, unit kind,
parent identity and goal identity cannot silently change.

A Factory runs a repeatable production Flow. A Lab explores and improves an
owned area. Both reuse normal tasks, blocks, artifacts, acceptance and Ledger
lifecycle; they do not create a second backlog. CTRL routes a request to the
fitting unit, whose coordinator splits its goal into bounded producer blocks.
The unit holder coordinates; it is never the whole-factory producer task.

The catalog ships six starting Flows: Software, Web App, Game, Integration,
Data and Release Factory. Each coordinator chooses or adapts the Flow to its
own goal, constraints and evidence, then hires only fitting Leads and Doers
for the next bounded work. Suggested professions are not a fixed crew, and
independent review remains a separate owner. Custom units use the same contract.

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
current step; do not add a manager or duplicate state for each nested Flow.

## Completion

A Lab or Factory outcome is complete when selected work is integrated, required
proof passes, and its declared blocks are accepted, completed and committed.
Compose that evidence through existing Ledger blocks, results and proof.
An empty NON_CODE holder acceptance closes only its coordination cycle; it does
not accept producer artifacts or prove the parent goal finished. Display holder
state separately from outcome acceptance, which remains unknown until the
declared work and integrated outcome are proven. Lab-only proof does not prove
the integrated product.

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
