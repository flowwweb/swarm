# Install SWARM on another device

SWARM 0.4.14+codex.20261004 uses the same tracked source and generated Codex plugin. The plugin icon is the existing approved orange mascot, with exact 64px and 512px assets. No artwork was regenerated.

Version 0.4.14 names CTRLs with a project-matching emoji instead of a global
octopus default. Explicit user choices and existing title custody take precedence.

Version 0.4.13 keeps console configuration parsing bounded for long malformed
escaped strings and hardens generated JavaScript literals in the vendored Jev
bundle. The original Jev revision, disabled retries and external import boundary
are retained; the bundle is rebuilt from source with reproducibility checks.

Install the current public release from the default branch on each device:

```text
codex plugin marketplace add flowwweb/swarm
codex plugin add swarm@flowwweb
```

For pre-release testing only, explicitly add `--ref codex/swarm-device-release-20261002`. That branch stays pinned until its registration is changed.

For an existing Flowwweb marketplace, refresh its configured ref, then reinstall:

```text
codex plugin marketplace upgrade flowwweb
codex plugin add swarm@flowwweb
```

An existing marketplace pinned to another ref keeps that ref. Check `codex plugin marketplace list`; update its registration to the intended release ref before refreshing. Start a new Codex chat after installing. An already-running chat keeps its loaded instructions.

The release contains no device-specific absolute paths, credentials, global SWARM config, or private benchmark session reports. Each device uses its own Codex login and `~/.agents/swarm/config.toml`. Installing the plugin does not transfer local chats, worktrees, services, project briefs or credentials.

Version 0.4.11 adds opt-in [product telemetry](product-telemetry.md) to the Flowwweb
beacon at `https://telemetry.flowwweb.com/api/swarm/telemetry`. Enable **Share SWARM
usage with Flowwweb** in onboarding or Settings on each installation. Consent
defaults to off; native hook trust remains required. Delivery runs automatically
after consent, including bounded offline retries. Installation alone does not
prove hook execution, agent compliance, or telemetry from another device.

The Python HQ and measurement commands require Python 3.11 or later. Codex owns native task tools and model availability. Platform code paths have local fixture coverage; installation and execution on a second physical device must be verified there.

## Activate the workflow for tasks

Installing a skill makes it discoverable; Codex otherwise decides whether to load it from its description. SWARM now bundles native `SessionStart` and `SubagentStart` hooks that explicitly direct each task to the installed canonical workflow. The startup hook also covers resume, clear and compaction. The same small pointer is emitted at each boundary; the workflow stays in one skill file.

After installation, open `/hooks` in Codex CLI, review the SWARM hooks and trust their exact definitions. Codex skips untrusted plugin hooks, even when the plugin is enabled. Repeat the review when a hook definition changes. The hook prints an instruction pointing to the shipped skill and appends a bounded activation receipt to the existing `~/.agents/swarm/mcp-telemetry.jsonl` stream. It creates no chats, services or model calls. Each device needs a working `python3` command on macOS/Linux or `python` on Windows.

Until the hooks are trusted, explicitly invoke `$swarm` in the task. An existing running turn does not gain a newly installed hook retroactively. Verify a resumed or fresh task reads the installed `skills/swarm/SKILL.md` before project work. Hook delivery proves activation instructions; following the workflow, delegation, independent review and completion still require task evidence. Loading SWARM preserves assigned roles and explicit user opt-outs.

If marketplace registration already exists, inspect `codex plugin marketplace list` and `codex plugin list --marketplace flowwweb --json` before changing its source. Refreshing preserves its current ref; it does not switch a registration from another source or branch. Preserve other installed plugins and report an unresolved registration instead of claiming the new release was installed.

Official behavior: [skill activation](https://developers.openai.com/codex/skills), [hook trust and startup context](https://learn.chatgpt.com/docs/hooks).

## Inspect activation telemetry

`swarm_status` now includes a `device` projection: host name, running package version and the last 50 activation receipts within the last 64 KiB of the existing telemetry stream. Each receipt binds the emitted startup pointer to the hook event, hashed session identity, package version and skill SHA-256. Prompts, responses and raw session IDs are excluded. A telemetry write failure reports a fixed diagnostic on stderr while preserving the startup instructions.

`OBSERVED_HOOK_OUTPUT` means the hook emitted its context. Host delivery, reading the skill and following the workflow still need task evidence. `NO_ACTIVATION_RECEIPTS` does not mean a task ignored SWARM: an older package, an untrusted hook or an inactive hook may produce no record. Activation receipts are local to the connected device. The separate `device.product_telemetry` projection reports consent, beacon, pending count and delivery acknowledgement for central product telemetry. Flowwweb maintainers read consenting installations centrally through `python telemetry/manage.py summary --days 7` with authenticated Cloudflare access. An advertised connector tool returning `Unknown tool` is a connector registration failure, not proof of absent telemetry or failed project work.

## Check the installation

Run the bundled smoke check from the installed plugin directory:

```text
python scripts/smoke_plugin.py
```

Or run the source copy against an installed package with `--plugin-root <absolute-plugin-directory>`. A successful run exits zero and prints `status: PASS`. It validates shipped metadata and icon paths, resolves the benchmark model, serves HQ files over loopback, and checks server reuse plus task-specific browser claims across restart. It uses temporary synthetic host metadata; it does not change your chats or settings, open Chrome, or call a model.

Chrome startup preserves the exact current task ID and looks for the standard Windows, macOS and Linux Google Chrome executable locations. macOS and Linux discovery have fixture coverage; run the smoke check and verify Chrome startup on each physical device.

If a fresh Codex run can read the installed skill but its Python tool returns a Windows sandbox launch error, treat that as host execution failure. Run the check directly with a working Python 3.11+ interpreter and preserve the exact host error. Installing another SWARM copy does not repair the host sandbox.

## Benchmark model lock and measurement

GPT-6.1 Sol capabilities are declared in the existing model registry and config template. Explicit user-selected models remain authoritative. Normal profile defaults are preserved.

For the comparison only, set `SWARM_CONFIG_PATH` to the absolute path of the installed `skills/swarm/assets/swarm-benchmark.toml`. It disables Usage Saver, Jev selection, Spark and Chat relay; all configured roles and routing tiers use GPT-6.1 Sol Xhigh. Also select that exact model and effort through the host for each controller, worker and internal reviewer. Configuration is a request, not execution proof.

Use the installed `skills/swarm/scripts/swarm_usage.py`:

```text
python swarm_usage.py report ROOT.jsonl WORKER.jsonl REVIEWER.jsonl --after 2026-10-02T00:00:00Z --output usage.json
```

Replace the paths and timestamp with the exact run roster and start boundary. Supply every participant once, including retries and failed attempts; reconcile the roster against host creation evidence. Reports retain per-thread and per-model input, cached input, cache-write, output, reasoning and total tokens. Reasoning is already included in output. Mixed or incorrect models/efforts produce a failed model-lock result and nonzero exit.

Price is a conditional Standard-tier API-equivalent estimate using the linked official model rates, not subscription billing. Per-request long-context pricing is applied only when request counts reconcile with cumulative deltas. Unknown models, incomplete records, resets, or nonzero cache-write accounting that has not been reconciled retain unknown prices. Unknown service tier, regional premiums and external tool charges remain explicit limitations.

Read-only benchmark snapshots do not prove final closure or participant completeness. Keep common external judging separate from build costs. The benchmark reporting command installs no collector, database or scheduler. Separately, consented product telemetry uses background hooks, a bounded local outbox and the Flowwweb beacon; it does not replace exact benchmark roster accounting.

## Release scope

This release adds guarded Git commit and push preparation plus six starting
Factory Flows: Software, Web App, Game, Integration, Data and Release. Each
coordinator receives the selected Flow, chooses or adapts it to its own goal,
and delegates bounded work to fitting Leads and Doers with separate independent
review. CTRL stays the switchboard operator. Six Lab starting points remain:
Product, Research, Design, Test, Content and Growth. Build and Ops are retired
only from the default catalog; their existing unit identities, manifests and
history remain intact. Custom Labs and Factories remain available.

Source, package and installation checks do not establish native hook trust,
fresh-task adherence or behavior on another device.

Official references: [plugin packaging and local marketplaces](https://developers.openai.com/plugins/build/plugins), [listing icons](https://developers.openai.com/plugins/deploy/submission), [GPT-6.1 Sol pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol).
