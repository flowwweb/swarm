# SWARM repository instructions

This file applies only inside this repository. SWARM-created agents receive
universal behavior from `skills/swarm/SKILL.md` and its runtime contracts; this
file is not composed into their project instructions.

## Orient

- Start with `git status --short --branch`; preserve unrelated dirty paths.
- Read `SWARM.md` for intent, milestones, owners and claim limits.
- Read `skills/swarm/SKILL.md` before changing SWARM behavior or contracts, then
  only the references its load table names for your change.
- `CONTRIBUTING.md` lists the complete pre-PR check set.

## Canonical source and generated mirror

- Root product files and `skills/swarm/` are canonical. `plugins/swarm/` is
  generated: never hand-edit it.
- After canonical changes run `python scripts/sync_plugin_mirror.py --write`,
  inspect the generated diff, then `python scripts/sync_plugin_mirror.py --check`.
  The check caps this file and the generated SWARM entry at 420 words each;
  put task-specific rules in the owning reference instead.
- Mirror or package parity proves bytes only, not host activation or execution.

## Existing owners

Extend the applicable owner. Do not add a parallel policy schema, role loader,
Ledger, store, service, queue, retry path, connector or dependency.

- Progress, request, task-identity and role-manifest contracts:
  `skills/swarm/runtime/progress_events.py`.
- Host launch adaptation and the execution journal:
  `skills/swarm/runtime/execution_adapters.py`.
- Skill discovery: `console/skills_catalog.py`.
- Console read projections: `console/server.py`; they do not own runtime truth.

Stay out of console UI, listeners, packages, providers and deployment unless the
task explicitly owns that surface.

## Focused checks

- Role cards: `python -m unittest discover -s skills/swarm/tests -p "test_role_cards.py"`
- Runtime ledger: `python -m unittest discover -s skills/swarm/tests -p "test_progress_ledger_contract.py"`
- Launch adapters: `python -m unittest discover -s skills/swarm/tests -p "test_execution_adapters.py"`
- Console backend: `python -m unittest discover -s console/tests -p "test_console.py"`
- Fast repository tier: `python scripts/run_test_tier.py fast`

Report failures, timeouts and skipped gates as they are. One proof class never
stands in for source, runtime, browser, provider, deployment, device or human
proof.

## Commits and pushes

- Before every commit or push, review the current diff and outgoing commit range;
  `@ponytail-review` is optional unless the task requires it.
- Address each finding or retain it with a reason, and complete the required checks.
- Run the exact current-diff receipt command printed by Ponytail Commit Guard.
- Never bypass, disable or retry around the guard. Recheck the staged diff after hooks.
