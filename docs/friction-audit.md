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
