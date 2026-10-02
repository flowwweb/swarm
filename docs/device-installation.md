# Install SWARM on another device

SWARM 0.4.8+codex.20261002 uses the same tracked source and generated Codex plugin. The plugin icon is the existing approved orange mascot, with exact 64px and 512px assets. No artwork was regenerated.

Use the same release ref on each device. Until this release is merged to main, use `codex/swarm-device-release-20261002`:

```text
codex plugin marketplace add flowwweb/swarm --ref codex/swarm-device-release-20261002
codex plugin add swarm@flowwweb
```

For an existing Flowwweb marketplace, refresh its configured ref, then reinstall:

```text
codex plugin marketplace upgrade flowwweb
codex plugin add swarm@flowwweb
```

An existing marketplace pinned to another ref keeps that ref. Check `codex plugin marketplace list`; update its registration to the intended release ref before refreshing. Start a new Codex chat after installing. An already-running chat keeps its loaded instructions.

The release contains no device-specific absolute paths, credentials, global SWARM config, or private benchmark session reports. Each device uses its own Codex login and `~/.agents/swarm/config.toml`. Installing the plugin does not transfer local chats, worktrees, services, project briefs or credentials.

The Python HQ and measurement commands require Python 3.11 or later. Codex owns native task tools and model availability. Platform code paths have local fixture coverage; installation and execution on a second physical device must be verified there.

## Benchmark model lock and measurement

GPT-6.1 Sol capabilities are declared in the existing model registry and config template. Explicit user-selected models remain authoritative. Normal profile defaults are preserved.

For the comparison only, set `SWARM_CONFIG_PATH` to the absolute path of the installed `skills/swarm/assets/swarm-benchmark.toml`. It disables Usage Saver, Jev selection, Spark and Chat relay; all configured roles and routing tiers use GPT-6.1 Sol Xhigh. Also select that exact model and effort through the host for each controller, worker and internal reviewer. Configuration is a request, not execution proof.

Use the installed `skills/swarm/scripts/swarm_usage.py`:

```text
python swarm_usage.py report ROOT.jsonl WORKER.jsonl REVIEWER.jsonl --after 2026-10-02T00:00:00Z --output usage.json
```

Replace the paths and timestamp with the exact run roster and start boundary. Supply every participant once, including retries and failed attempts; reconcile the roster against host creation evidence. Reports retain per-thread and per-model input, cached input, cache-write, output, reasoning and total tokens. Reasoning is already included in output. Mixed or incorrect models/efforts produce a failed model-lock result and nonzero exit.

Price is a conditional Standard-tier API-equivalent estimate using the linked official model rates, not subscription billing. Per-request long-context pricing is applied only when request counts reconcile with cumulative deltas. Unknown models, incomplete records, resets, or nonzero cache-write accounting that has not been reconciled retain unknown prices. Unknown service tier, regional premiums and external tool charges remain explicit limitations.

Read-only snapshots do not prove final closure or participant completeness. Keep common external judging separate from build costs. No background collector, additional database or scheduler is installed.

## Release scope

This release reconciles committed maturity routing/Jev changes with main's security and font removals, the naming correction, visual-review and development-checkpoint doctrine, the Auto timeout fix, and console lifecycle/backend fixes. New measurement and model-capability fixes are included.

The dirty HQ checkout's separate visual redesign remains with its existing owner. It was inventoried and preserved; its unreconciled UI edits are not silently installed as part of this release. Packaging and local tests do not establish acceptance of every HQ screen or live topology enforcement.

Official references: [plugin packaging and local marketplaces](https://developers.openai.com/plugins/build/plugins), [listing icons](https://developers.openai.com/plugins/deploy/submission), [GPT-6.1 Sol pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol).
