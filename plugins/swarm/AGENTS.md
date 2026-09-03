# SWARM repository instructions

This file applies only inside this repository. SWARM-created agents receive
universal behavior from `skills/swarm/SKILL.md` and its runtime contracts; this
repository file is not composed into their project instructions.

## Orient

- Read `SWARM.md` for current intent, milestones, owners, and claim limits.
- Read `skills/swarm/SKILL.md` before changing SWARM behavior or contracts.
- Follow `CONTRIBUTING.md` for the complete pre-PR check set.
- Start with `git status --short --branch`; preserve unrelated dirty paths.

## Canonical source and generated mirror

- Root product files and `skills/swarm/` are canonical.
- `plugins/swarm/` is generated. Never hand-edit it.
- After canonical changes, run `python scripts/sync_plugin_mirror.py --write`,
  inspect the generated diff, then run `python scripts/sync_plugin_mirror.py --check`.
- Mirror or package parity proves bytes only, not host activation or execution.

## Existing owners

- Durable progress, request, task-identity, and role-manifest contracts live in
  `skills/swarm/runtime/progress_events.py`.
- Host launch adaptation lives in `skills/swarm/runtime/execution_adapters.py`.
- Skill discovery lives in `console/skills_catalog.py`.
- Console read projections live in `console/server.py`; they do not own runtime truth.
- Extend the applicable owner. Do not add a parallel policy schema, role loader,
  Ledger, store, service, queue, retry path, connector, or dependency.
- Do not expand into console UI, listeners, packages, providers, or deployment
  unless the task explicitly owns that surface.

## Focused checks

- Role cards: `python -m unittest discover -s skills/swarm/tests -p "test_role_cards.py"`
- Runtime ledger: `python -m unittest discover -s skills/swarm/tests -p "test_progress_ledger_contract.py"`
- Launch adapters: `python -m unittest discover -s skills/swarm/tests -p "test_execution_adapters.py"`
- Console backend: `python -m unittest discover -s console/tests -p "test_console.py"`
- Fast repository tier: `python scripts/run_test_tier.py fast`
- Report failures, timeouts, and skipped gates without promoting one proof class
  into source, runtime, browser, provider, deployment, device, or human proof.

## Commits and pushes

- Before every commit or push, run `@ponytail-review` on the current diff.
- Address each finding or explicitly retain it with a reason.
- Run the exact current-diff receipt command printed by Ponytail Commit Guard.
- Never bypass, disable, or retry around the guard. Recheck the staged diff after hooks.
