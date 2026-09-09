<p align="center">
  <a href="https://flowwweb.com/swarm">
    <img src="skills/swarm/assets/swarm-wordmark.png" alt="SWARM" width="560">
  </a>
</p>

<p align="center">
  <strong>One objective. Clear ownership. A coordinated Codex team.</strong>
</p>

<p align="center">
  <a href="https://github.com/flowwweb/swarm/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-11dff3"></a>
  <a href="https://flowwweb.com/swarm"><img alt="Built for Codex" src="https://img.shields.io/badge/built_for-Codex-ff5b45"></a>
  <a href="https://github.com/flowwweb/swarm"><img alt="Open source on GitHub" src="https://img.shields.io/badge/open_source-GitHub-ffffff"></a>
</p>

SWARM is an open-source Codex plugin for work that benefits from more than one agent. You direct a single CTRL task. CTRL divides the objective into clear lanes, LEADs own the outcome of each lane, and DOERs complete focused work inside them.

The hierarchy keeps parallel work understandable: one place to steer, one owner for every lane, and one integrated result to review.

[Explore SWARM](https://flowwweb.com/swarm) · [View the repository](https://github.com/flowwweb/swarm)

## How the hierarchy works

SWARM starts with the smallest graph that can finish the objective. There is
one control point. LEAD and DOER tasks appear only when durable ownership or a
bounded artifact warrants a visible lane; the dashed routes stay inside the
current accountable task.

```mermaid
%%{init: {"theme":"base","themeVariables":{"lineColor":"#36aeca"},"flowchart":{"nodeSpacing":34,"rankSpacing":74,"curve":"basis","padding":20}}}%%
flowchart TB
  C("🐙<br/>CTRL<br/>Objective, routing, integration")
  C -->|durable outcome boundary| L("🧭<br/>PROFESSION LEAD<br/>Owns one lane")
  L -->|bounded artifact when useful| D("🛠️<br/>PROFESSION DOER<br/>Owns one artifact")
  C -.->|one low-risk atomic GENERAL outcome| X("CTRL_DIRECT<br/>No separate lane")
  C -.->|bounded GENERAL inspection or check| S("SUBAGENT<br/>No durable ownership")

  classDef ctrl fill:#fff1ed,stroke:#ff5b45,color:#172033,stroke-width:3px;
  classDef lead fill:#e9fbff,stroke:#0ea5c6,color:#172033,stroke-width:2px;
  classDef doer fill:#ffffff,stroke:#78cddd,color:#172033,stroke-width:1px;
  classDef internal fill:#f8fafc,stroke:#94a3b8,color:#172033,stroke-width:1px,stroke-dasharray:4 3;
  class C ctrl;
  class L lead;
  class D doer;
  class X,S internal;
  linkStyle default stroke:#36aeca,stroke-width:1.5px;
```

The branches are choices, not a roster to pre-create. Every visible lane says
both what expertise it brings and whether it is a LEAD or DOER; bare structural
titles are rejected before creation.

- **CTRL** is the sole control point. It owns the objective, chooses the graph,
  resolves shared-surface decisions, and returns the combined result.
- **LEAD** appears when an outcome needs durable ownership, integration,
  resumption, or its own acceptance route.
- **DOER** appears when a bounded artifact benefits from an explicit producer.
- **CTRL_DIRECT** is limited to one low-risk atomic `GENERAL` outcome on one
  mutable surface with no external side effect.
- **Bounded subagents** may handle small `GENERAL` inspection, search,
  formatting, or a focused check inside their accountable owner. They never own
  a durable lane, review, handoff, or acceptance.

The Codex host owns model, service-tier, and reasoning selection. SWARM reports
host-observed values when that metadata is available; a configured preference
or diagram label is never proof of execution.

## Small work stays small

SWARM does not turn every request into a fleet.

- A small or medium assignment on one surface can stay inside the current task and use bounded subagents.
- A large, parallel, resumable, isolated, or independently accepted outcome earns a visible task lane.
- A task lane can use its own subagents when that reduces overhead without hiding ownership.
- Small `CTRL_DIRECT` work remains available for one low-risk atomic general outcome; design, mockup, and image-generation work goes to a DESIGNER lane even when it is small.
- Usage limits constrain the available route; they do not decide the structure when normal capacity is available.

This keeps quick work quick while giving larger objectives durable lanes that can progress in parallel.

## Intake and domain graphs

At the start of every new task, CTRL captures two answers: the goal and the
most efficient safe way to reach it. Durable goal persistence is on by default
and can be disabled with `goals.use_goals = false`; disabling persistence does
not disable intake, graph selection, ownership, or proof.

CTRL then selects the most efficient and smallest graph that can complete the
objective durably, reliably, and confidently. Game projects use
the registered game-studio flow: design, engineering, art, and audio can run
as independent production lanes, followed by integrated playtest/QA and
release gates. The graph is an ownership and dependency contract, not a flat
agent roster. See [graph engineering](skills/swarm/references/graph-engineering.md)
for the invariants and profile.

Every agent may request an approved role skill with an exact source/version or
digest and task-local scope by default. The host owns installation and audit;
skills improve execution but never grant authority or turn CTRL into a producer.

## Project Workspace views

A project may expose one digest-bound Project Workspace from its root
`SWARM.md` brief and `swarm.project_views` manifest. The registered renderers
are `canvas`, `table`, `timeline`, `gallery`, `compare`, and `document`.

| Current view | Renderer | Mode |
| --- | --- | --- |
| Master plan | `document` | `blocks` |
| Roadmap | `timeline` | `milestones` |
| Flowchart | `canvas` | `network` |
| Screens | `gallery` | `grid` |
| Map | `canvas` | `network` |

`table` and `compare` are registered but are not bound by the current project
manifest. Board, Kanban, and calendar are not registered renderers. An unknown
renderer or mode, an unsupported source, or a digest mismatch fails closed; it
does not become executable UI or replace the last accepted read-only
projection.

Project-view manifests and plan files are snapshot metadata. Live task state,
progress, ownership, blockers, proof, and acceptance remain authoritative only
in the existing Ledger and accepted event projections. Reusing a registered
renderer is a manifest-only change when its existing source contract fits. A
new renderer, parser, or dependency is a reviewed source slice with its own
tests and proof—not a manifest shortcut.

## Universal HQ command connector

The source runtime contains a typed universal HQ command connector for already
authorized Codex host actions. One immutable command envelope binds project,
root, CTRL where required, target, payload digest, Ledger revision, expiry, and
idempotency. The injected host verifier and host-owned App Server transport must
validate the command before dispatch; exact replay reconciles retained command
receipts without redispatching.

The connector starts no process, stores no prompt or response body, grants no
progress or acceptance, and does not make a host task title or project claim.
`LOCAL_HQ` produces a digest-bound plan without calling Codex transport. Console
wiring and end-to-end or live availability are not established by this source
contract. See [execution adapters](skills/swarm/references/execution-adapters.md)
for the accepted boundary.

## What you get back

- **A quiet control stream.** CTRL surfaces decisions, blockers, proof, and completed outcomes—not routine agent chatter.
- **Visible ownership.** Every lane has a named outcome, an accountable LEAD, and bounded work beneath it.
- **Focused proof.** SWARM selects the smallest sufficient checks for the changed surface and expands them when risk or uncertainty requires it.
- **Independent acceptance.** Work is not complete because an agent says it is; the required evidence and review must close.
- **Human authority.** A swarm has one CTRL. Creating or replacing another CTRL requires an explicit user request.

## Install in Codex

Add the Flowwweb marketplace:

```text
codex plugin marketplace add flowwweb/swarm --ref main
```

Run `/plugins`, open **Flowwweb**, install **SWARM**, and start a new Codex task so the plugin loads into fresh context.

Then ask Codex to use it:

```text
Use SWARM to ship the next release of this project.
```

That task becomes `🐙 <objective>`: the one place where you direct the work and review what the swarm returns.

To update an existing installation:

```text
codex plugin marketplace upgrade flowwweb
codex plugin add swarm@flowwweb
```

Start a new task after reinstalling.

## Configure SWARM

SWARM uses one global TOML file: `~/.agents/swarm/config.toml`. Initialize it
from the maintained current-schema template, edit only the settings you need,
then validate the complete result:

```text
python skills/swarm/scripts/swarm_config.py init
python skills/swarm/scripts/swarm_config.py validate
python skills/swarm/scripts/swarm_config.py show
```

The generated template and the
[configuration reference](skills/swarm/references/config.md) are the schema
authority; a README excerpt is not. Changes apply at the next safe scheduling
boundary, and a plugin update takes effect in a new task. Config never overrides
an explicit user choice or grants task, Git, release, provider, or user-state
authority. Fast or automation preferences become active only when the relevant
host/runtime receipt confirms them.

## Local console

SWARM includes an optional loopback-only console for seeing the live hierarchy, task state, requested and observed models, reasoning levels, lightweight logs, evidence, and blockers.

```text
python skills/swarm/scripts/swarm_console.py --start
```

Python 3.11 or newer is required. Docker is optional:

```text
python console/docker.py up
```

The console shows what SWARM knows; it does not invent host activity or passing proof. Settings writes are validated and loopback-only in both native and Docker modes. Docker keeps Codex task metadata read-only, writes only the bounded SWARM proof directory, and stores console history in its named volume.

## Codex-native scope

SWARM is a Codex plugin and workflow: Codex is the only agent host whose task,
tool, model, and execution behavior this repository describes or routes. The
`plugins/swarm` tree is the generated Codex marketplace mirror of the canonical
`skills/swarm` source. SWARM does not ship, install, or claim compatibility with
Claude Code, Anthropic, Gemini, Copilot, Cursor, OpenCode, or another agent host.

The word `provider` may still appear in proof contracts for a real external
service boundary such as authentication, payments, deployment, or browser
evidence. That proof category is not a model-host adapter and does not create a
second execution authority. Host installation, activation, task behavior, and
served-tier claims require their own direct receipts.

## Reference

- [Hierarchy and role contracts](skills/swarm/references/hierarchy.md)
- [Configuration and model profiles](skills/swarm/references/config.md)
- [Review and acceptance](skills/swarm/references/review-contract.md)
- [Console guide](skills/swarm/references/console.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [MIT License](LICENSE)
