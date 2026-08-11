# SWARM friction audit

| FRICTION | CAUSE | IMPACT | CHANGE | REMOVED | RISK | VALIDATION |
| --- | --- | --- | --- | --- | --- | --- |
| P0 heartbeat traffic was prose-only | no canonical state classifier or MOTHER wake latch | actionable stalled work could remain invisible | `heartbeat()` emits one MOTHER-only `MOTHER_WAKE`, latches unchanged stalls, and re-arms on progress | no daemon, queue, role, or ledger | false wake during WAITING/review/terminal work | runtime truth-table probes |
| P1 adaptive work could require an unearned coordinator | topology guidance was not mechanically connected to runtime ownership | small work carried unnecessary coordination cost | retain atomic/simple route selection and collapse; authority remains explicit | no hierarchy manufacture | accidental authority bypass | proportional-depth and unauthorized-role tests |
| P1 archive could hide continuing work | grooming only saw state/pin/dependent conditions | active goal, handoff, correction, choice, or ambiguity could archive | one fail-closed `archive_eligible()` predicate | duplicated prose-only checks | hidden active work | safe/unsafe archive probes |
| P1 contention could still spawn | decision omitted contention while reason claimed refusal | colliding work could fan out | contention joins `should_spawn` guard | contradictory branch | surface collision | contention returns false |
| P2 dependency/reuse/dedup ambiguity | no completion wake; boolean dedup had reverse semantics | manual wake and confusing reuse choices | completion wakes direct waiters; `DedupDecision` is explicit; duplicate worker IDs reject | polling and ambiguous boolean | premature wake or overwrite | WAITING, dedup, duplicate-ID tests |
| P2 Scope Discipline | discovery could expand work implicitly | finish line drift | explicit doctrine/eval preserves only material invariant findings | speculative follow-on work | explicit requirement narrowed | eval 71 |

Implemented commits: `9ee8d85` heartbeat/archive/contention/dependency baseline; `f8afc0a` adaptive direct paths and WARM reuse; `edd6749` configured heartbeat behavior; `0271fb4` SWARM-first configuration fallback; `eccb957` artifact/HIVE/archive authority; this correction consolidates the remaining review findings. P3/no-change console projection and optimizer concerns remain untouched.

## A. Instruction Architecture

`CORE`: shallowest sufficient route, objective-bound scope, ownership, canonical
runtime state, independent creation/review, reuse, quiet healthy execution, and
accepted stop. `ROLE`: only PURPOSE, OWNERSHIP, BOUNDARIES, ESCALATION. `TASK`:
objective, acceptance/non-negotiables, owner, dependencies, mutable surface,
relevant canonical artifact/version, proof limits, accepting route/blocker.
`EVENT`: load only for stall/heartbeat, architecture/version conflict, high-risk
review failure, provider/browser/Docker/security/release, HIVE retirement, or
feedback.

## B. Removed Friction

MERGED heartbeat classification into runtime; MOVED lane/WIP, identity/dedup,
self-review, state/dependency/archive/retry, and config validation to runtime;
MOVED history/rationale to references; LAZY-LOADED exceptional guidance;
SIMPLIFIED routine CTRL output to attention, blocker, handoff, acceptance, and
release only. The always-loaded `skills/swarm/SKILL.md` is 28 lines; detailed
references remain maintainership/event material.

## C. Preserved Safeguards

Authority/state guards prevent unauthorized mutation; typed identity prevents
duplicate artifacts; independent review prevents self-approval; version and
dependency state prevent stale or premature work; heartbeat/retry surfaces a
real stalled owner once; archive/HIVE limits preserve continuity without active
workspace clutter; config, Docker, browser, security, and legacy migration
guards preserve safe local/public compatibility.
