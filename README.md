# RUSH

**Agents need command.** RUSH gives Codex a visible operating structure for complex work: one accountable outcome owner, a few worthwhile parallel tasks, and independent review before acceptance.

RUSH is a Codex plugin with an optional loopback-only console. Current version: `0.1.0+codex.20260809183508`.

## Install

Add the Flowwweb marketplace to Codex CLI:

```text
codex plugin marketplace add flowwweb/rush --ref main
```

Run `/plugins`, open the **Flowwweb** marketplace, and install **RUSH**. Start a new session so Codex loads the skill.

## Update

Refresh the marketplace and reinstall RUSH:

```text
codex plugin marketplace upgrade flowwweb
codex plugin add rush@flowwweb
```

Start a new session after reinstalling. Release versions use one `+codex.<cachebuster>` suffix so Codex can distinguish installed builds.

## What it owns

- User-visible MOTHER, LEAD, TASK, ASSIST, and REVIEW ownership contracts.
- Config-aware model and capability routing without silent defaults.
- Passive task heartbeats, bounded recovery, and evidence-matched acceptance.
- A local settings and hierarchy console that binds to loopback by default.

## Console

The console and configuration tools require Python 3.11 or newer and use only the Python standard library.

```text
python skills/rush/scripts/rush_console.py
```

Docker is optional. Run `python console/docker.py` to launch the console with explicit Codex and RUSH data paths.

## Develop

```text
python -m unittest discover -s skills/rush/tests -p "test_*.py"
python -m unittest discover -s console/tests -p "test_console.py"
node --test console/tests/test_console_ui.mjs
```

The browser test requires Playwright. See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and the [MIT License](LICENSE).
