<p align="center">
  <a href="https://flowwweb.com/swarm">
    <img src="skills/swarm/assets/swarm-wordmark.png" alt="SWARM" width="640">
  </a>
</p>

<p align="center">
  <strong>Structured Workflows for Autonomous Role Management</strong>
</p>

<p align="center">
  <a href="https://github.com/flowwweb/swarm/blob/main/LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-11dff3"></a>
  <a href="https://flowwweb.com/swarm"><img alt="Built for Codex" src="https://img.shields.io/badge/built_for-Codex-ff5b45"></a>
  <a href="https://github.com/flowwweb/swarm"><img alt="Open source on GitHub" src="https://img.shields.io/badge/open_source-GitHub-ffffff"></a>
</p>

SWARM is an open-source workflow for Codex.

Install it as a Codex plugin and run a coordinated team of AI agents from one CTRL task. CTRL routes work to clear leads, leads delegate focused lanes, and independent review checks the combined result. The hierarchy gives parallel agents direction, shared state, and a clean route back to you—without turning every project into a polling loop.

[Explore SWARM](https://flowwweb.com/swarm) · [View the repository](https://github.com/flowwweb/swarm)

## One command point. A whole team.

```text
🐙 CTRL — your command point
├── LEAD — product
│   └── DESIGNER — product experience
├── LEAD — engineering
│   └── DEVELOPER — implementation
├── LEAD — quality
│   └── QA ENGINEER — verification
└── REVIEW — independent acceptance
```

SWARM chooses the shallowest structure that can reliably finish the objective. Small work stays small. Parallel work gets explicit owners. A MOTHER appears only when genuinely interdependent lanes need portfolio-level integration and acceptance. Persistent specialists can protect a cross-cutting truth without becoming another management layer. ARCHITECT, ENGINEER, DEVELOPER, DESIGNER, RESEARCHER, ANALYST, and STRATEGIST are ready-made examples—not a limit. Any profession is valid, and multiple specialists may share a profession when their owned truth surfaces differ.

The result is a swarm you can steer from one place:

- **One visible control stream.** Decisions, blockers, evidence, and acceptance come back to CTRL; routine chatter stays quiet.
- **Parallel work without duplicate ownership.** Every lane has a bounded artifact, mutable surface, and accepting route.
- **Hierarchy that earns its place.** Roles appear for real dependencies and collapse when they stop helping.
- **Coherent results.** Leads integrate their lanes and REVIEW verifies the composed outcome before it is accepted.
- **Recovery without retry theatre.** Durable goals, bounded wakeups, and evidence-driven correction keep stalled work honest.

## Install

Add the Flowwweb marketplace to Codex:

```text
codex plugin marketplace add flowwweb/swarm --ref main
```

Run `/plugins`, open the **Flowwweb** marketplace, and install **SWARM**. Start a new Codex task so the plugin loads into fresh context.

Then ask Codex to use it:

```text
Use SWARM to ship the next release of this project.
```

That task becomes `🐙CTRL - <objective>`: the single place where you direct the objective and review what the swarm returns.

## Update

```text
codex plugin marketplace upgrade flowwweb
codex plugin add swarm@flowwweb
```

Start a new Codex task after reinstalling so it loads the updated plugin.

## Console

SWARM includes an optional loopback-only console for inspecting hierarchy and validated local settings. Python 3.11 or newer is required; the console uses only the Python standard library.

```text
python skills/swarm/scripts/swarm_console.py --open
```

Docker is optional:

```text
python console/docker.py up
```

The console is an observability surface, not the authority for task state.

## Develop

```text
python -m unittest discover -s skills/swarm/tests -p "test_*.py"
python -m unittest discover -s console/tests -p "test_*.py"
node --test console/tests/test_console_ui.mjs
```

The browser test requires Playwright. See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and the [MIT License](LICENSE).

## Release verification

Build from a clean, committed checkout. The archive is reproducible and assembled
from one captured Git commit/tree snapshot: it records the plugin version, commit,
tree, and a SHA-256 manifest for every shipped product file. Write the archive
outside the repository so the clean-source check remains meaningful.

```text
python scripts/build_package.py --output ../swarm.zip --verify-repeat
python skills/swarm/scripts/verify_plugin_install.py <installed-plugin-root> --package ../swarm.zip
python skills/swarm/scripts/verify_plugin_install.py <installed-plugin-root> --source .
```

The builder writes `swarm.zip.sha256` beside the archive; package verification
requires that exact sidecar. The verifier checks the whole shipped surface—plugin
manifest, skills, console and Docker files, and public documentation/security
files. Installed parity ignores only host Git metadata, generated `__pycache__`
contents, and generated package metadata; logs, loose bytecode, state, build output,
and dependency directories fail verification.
