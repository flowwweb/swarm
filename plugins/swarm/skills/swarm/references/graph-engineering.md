# Graph engineering

SWARM graphs are executable ownership and dependency plans, not decorative
role lists. CTRL selects one before the first mutable handoff and records the
goal, efficiency strategy, profile, owners, dependencies, accepting route, and
proof boundary.

## Invariants

- One `CTRL` root owns intake, graph selection, shared-surface coordination,
  and final composed acceptance.
- Every non-root node has one accountable owner, one bounded purpose, and an
  explicit dependency or handoff reason.
- Parallel lanes must be independent in mutable surface, artifact, and
  acceptance. Shared-surface work is serialized behind its dependency gate.
- A downstream node cannot accept upstream work merely because it was created;
  it consumes the upstream artifact and current proof receipt.
- Medium and large work becomes visible Codex task lanes. Subagents are
  short-lived capacity inside an existing lane and never replace durable
  ownership, handoff, review, or acceptance.
- Use the most efficient and smallest graph that can complete the objective
  durably, reliably, and confidently. More agents are not evidence of a better
  graph.
- Recompute only when objective, ownership, dependency, integration, or
  acceptance facts materially change. User direction remains the highest
  constraint.

The runtime also projects a tiny dependency/artifact graph from the same
records. It contains only TASK and content-addressed ARTIFACT nodes plus
`waits_for` and `accepts_artifact` edges. It is not a second scheduler, role
roster, or persistence system. Use its deterministic digest in the immutable
review packet so a real dependency or artifact change invalidates proof while
unrelated hierarchy metadata does not.

## Registered profiles

`general` is the default shallow profile. CTRL appoints a LEAD for a durable
boundary; that LEAD may produce directly, recruit a DOER for a bounded artifact,
or recruit another LEAD when the subordinate boundary needs independent durable
ownership, heartbeat, integration/review surface, worktree isolation, cross-lane
dependency, or its own team. Hidden subagents remain non-recursive leaves. There
is no fixed depth, roster, or mandatory pass-through.

`game_studio` is selected when the objective or declared domain is a game,
gameplay, engine, Unity, Unreal, Godot, or playtest project. Its production
flow is:

```text
CTRL
  -> MANAGER LEAD
       -> DESIGNER DOER   ┐
       -> DEV DOER        ├─ independent production lanes
       -> ARTIST DOER     │
       -> PRODUCER DOER   ┘
            -> TESTER DOER / playtest
                 -> OPERATOR DOER
```

The game-studio lead owns the integrated plan. Design owns the player contract
and rules; engineering owns deterministic runtime and integration; art owns
visual production; the Producer owns sound and music; the independent Tester
verifies the integrated player contract; the Operator owns packaging and
publication checks.
These are conventional production dependencies encoded as a SWARM profile,
not a claim that every project needs every lane. A smaller game task can
choose a narrower explicit scope; a one-shot game-project prompt uses the full
profile so independent lanes can proceed without flattening their ownership.

The profile is optimized for AI agents by making handoffs typed and bounded:
each lane returns its artifact and proof to the game-studio lead, QA consumes
the integrated set, and release is blocked until QA's acceptance evidence is
current.
