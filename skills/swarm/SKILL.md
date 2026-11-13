---
name: swarm
description: Use SWARM for Codex project work, including planning, building, debugging, review, and multi-agent coordination. Preserve the assigned task role and explicit user opt-outs.
---

<!-- compact -->
# 🐙 SWARM

Codex-native multi-agent workflow. Load a reference only when its trigger applies.

- **Role.** Keep your assigned role. CTRL routes bounded tasks to an accountable LEAD or DOER and relays results; every build, fix, test, review, asset or release goes to its owner, even a one-line edit. A missing owner means assign one or report the blocker. Review is always a separate owner.
- **Intent.** User messages are one ordered feed: merge corrections and constraints, cancel only what the user names, reconcile messages that arrived mid-run. Pause, cancel and keep-out bind.
- **Custody.** User titles, pins, order, archive state and exceptions win. The runtime grants no host mutation; verify each host action by readback.
- **Models.** Keep every user-selected model, tier and reasoning level. Change one only when asked; report a blocker instead of substituting.
- **Smallest path.** Reuse owners, components and skills. Make the smallest change, test what changed, and bring results or one decision.
- **Obligations.** Dispatch, ACK, silence and terminal status are activity. Keep every delegated duty until its readable result is collected; collection is not verification or acceptance.
- **Proof.** Name what each proof exercised; fixtures prove only themselves and claim classes never promote one another. Unexercised claims stay `UNVERIFIED`. Only an artifact-bound `ACCEPT` enters independent review; CTRL never manufactures acceptance.
- **State.** The runtime and Ledger hold canonical state. At stable boundaries record SHA, dirty custody, proof and next action. Never absorb unrelated dirty work; recover a failed write only at its exact target.
- **Authorized actions.** Carry explicit grants; use ordinary calls, read back, report. For Codex-chat sends: [task-contract.md](references/task-contract.md#codex-chat-authority). Missing capability or readback stays `UNVERIFIED`.

## Load when

- Start, adopt, rotate, name, pin or archive a CTRL: [hierarchy.md](references/hierarchy.md#task-naming-pins-and-rotation)
- Intake, topology, lanes, subagents, role choice: [hierarchy.md](references/hierarchy.md), [graph-engineering.md](references/graph-engineering.md)
- Project init or `SWARM.md`: [project-brief.md](references/project-brief.md)
- Task contract or Git: [task-contract.md](references/task-contract.md)
- Review, proof, acceptance, visual or release evidence: [review-contract.md](references/review-contract.md)
- Design, mockups, images: [design-guide.md](references/design-guide.md), [decision-set.md](references/decision-set.md)
- Models, Spark, Jev, ChatGPT: [model-providers.md](references/model-providers.md), [jev-routing.md](references/jev-routing.md), [chatgpt-routing.md](references/chatgpt-routing.md)
- Settings: [config.md](references/config.md)
- Heartbeat, feed, WATCHDOG, storage: [monitoring.md](references/monitoring.md)
- Failure or stall: [runtime-recovery.md](references/runtime-recovery.md)
- Capability or skill choice: [proven-solutions.md](references/proven-solutions.md), [skills-catalog.md](references/skills-catalog.md)
- Labs: [lab-workflow.md](references/lab-workflow.md)
- HQ, Auto, adapters: [console.md](references/console.md), [execution-adapters.md](references/execution-adapters.md)

Load only your own `roles/<profession>.md` card; cards never transfer authority. Explicit user direction outranks these defaults.
<!-- /compact -->

## Maintainer notes (source only, not shipped)

This file is the human-edited source. Only the frontmatter and the marked
compact blocks ship: `python scripts/sync_plugin_mirror.py --write` regenerates
`swarm.min.md`, and the plugin mirror and packages carry that text as their
native `SKILL.md`. `--check` fails when the copy is stale, the compact entry
exceeds 420 words (whitespace-separated tokens, frontmatter included), or a
relative link or anchor does not resolve.

Keep the compact core to rules every SWARM task needs. Put an action procedure
in the reference that owns it and add one triggered line to **Load when**;
never paste a reference back here or make agents read every reference.
Project `SWARM.md` state is not instruction text and is never counted or cut.
