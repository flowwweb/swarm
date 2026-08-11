# 🐙 SWARM

**System for Workload Allocation, Routing & Management.**

SWARM distils RUSH's practical safeguards into seven clear responsibilities: CTRL receives every new objective, holds its durable goal, and chooses the initial topology; MOTHER orchestrates; ARCHITECT owns technical truth; LEAD owns a workstream; DOER executes; EXPERT advises without taking ownership; REVIEW independently verifies.

A new SWARM task starts with mandatory Step 0: set and verify the title `CTRL - <project> - <detailed descriptor>` with no emoji, then pin and verify the task. Project is mandatory; the descriptor may be omitted only when none is useful. If task-management tools are unavailable or a receipt fails, report the exact blocker and continue only with truthful internal CTRL identity. Only after Step 0 does CTRL inspect or create the durable controller goal and materialize the smallest useful topology.

The runtime owns mechanical safeguards: canonical-state ownership, a preferred 3×3 execution cell, worker replacement, named waiting/deadlock detection, version staleness, leases, bounded changed recovery, compressed CTRL events, and completion gates. The console is an observability projection, never canonical authority.

## RUSH migration

Public history is preserved by migrating `flowwweb/rush` to `flowwweb/swarm`; legacy RUSH configuration, title, command, and console seams remain readable during the transition. New documentation and metadata use SWARM.

## Develop

```text
python -m unittest discover -s skills/swarm/tests -p "test_*.py"
python -m unittest discover -s console/tests -p "test_console.py"
node --test console/tests/test_console_ui.mjs
```

The browser test requires Playwright. This local checkout is not published or installed by these commands.
