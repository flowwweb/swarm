# Global SWARM settings

SWARM reads `~/.agents/swarm/config.toml` before scheduling or managing a
portfolio. Run `python scripts/swarm_config.py show --json` from the skill
directory to resolve built-in defaults plus the user's file.

Run `python scripts/swarm_config.py resolve --role lead --route-tier 3` to
resolve the exact model and reasoning pair for a new assignment after profile,
route, global-bound, custom-role, and Turbo rules.

The loader requires Python 3.11 or newer and otherwise uses only the standard
library. `show --json` writes structured settings to stdout. Parse, schema, and
read failures write a specific diagnostic to stderr and exit with status 2.
`init` is idempotent and never overwrites an existing settings file.

## Precedence

The configuration loader has exactly two file layers: packaged defaults, then
one selected global file (`~/.agents/swarm/config.toml`). Direct user, project, and session instructions govern task
behavior, safety, and authority, but are not loader file-merge layers.

Settings affect new scheduling and management decisions. They do not rewrite an
already-dispatched task contract. Re-read the config before a new scheduling
wave so edits take effect without reinstalling the plugin.

Packaged values are editable defaults, not a complete operating policy. Keep
context-dependent decisions in SWARM's general selection rules and add a setting
only when a user needs that preference to persist across runs. Hard validation
protects schema integrity and fixed SWARM invariants; it should not encode a
catalog of project-specific tactics.

### Operational handling

Load effective settings once for each new scheduling wave with
`scripts/swarm_config.py show --json`, then pass that validated map to
`Swarm.from_config`. Runtime code, the console, and relay adapters must not
invent a second settings source. A missing file uses packaged defaults. An
existing file with TOML, schema, or value errors is a diagnostic: do not guess,
partially apply, or silently repair it. Safe local work may continue, while a
ChatGPT relay falls back to local Codex until the file validates.

Explicit user instructions win over persisted preferences. Persisted model,
provider, service-tier, and reasoning values remain preferences rather than
authority; preserve them exactly when the host supports them and report the
exact host blocker when it does not. A setting change is read by the next
scheduling or relay decision and never rewrites an already-dispatched task
contract.

`execution.usage_saver` only selects lower-churn tactics when the outcome,
proof, review, model, reasoning, and authority boundaries remain unchanged.
`chat_relay.enabled` permits a route but does not force one. Its normal and
challenging model/effort fields select the requested visible ChatGPT profile;
the observed visible selection must match it and include a host receipt or the
relay stays local. The advisory route never gives ChatGPT write, command,
upload, artifact, or acceptance authority. The separate executor settings
permit only the host-reported local MCP tools and scope described in
`chat-relay.md`; they never grant unscoped machine authority or acceptance.

## Fixed invariants

Configuration cannot make an unsafe or hidden coordination path valid:

- Portfolio lanes are user-visible host tasks. In Codex, create Codex tasks with
  thread tools.
- Substantive artifact-producing work delegates to a LEAD-owned lane and bounded
  DOER work whenever qualifying host lane capacity is available. CTRL remains
  the orchestrator for bounded read-only inspection, coordination,
  plan/goal/receipt work, integration, and final composed acceptance; the
  existing `CTRL_DIRECT` safe-work predicate remains a narrow explicit
  exception. Subagents work only inside an owning Codex task and never replace a
  required lane. Disabled or unavailable capacity requires the exact host
  observation and one typed exception with affected gates left `UNVERIFIED`; it
  is not a standing waiver for silent worker execution.
- The packaged medium profile routes new DOER/TASK/SUBTASK assignments to
  `gpt-5.6-luna` at `xhigh`, within declared host capabilities. Explicit user,
  host, and project model or reasoning selections win; an unrequested CTRL
  adjustment records its risk, latency, cost, and proof basis.
- The latest direct user instruction controls its task.
- Existing safety, authority, provider, worktree, and proof boundaries remain.
- If a required task tool is unavailable, report the blocker instead of
  substituting a local process or subagent hierarchy.
- CTRL, every LEAD, and every persistent SPECIALIST—including a materialized MOTHER—require an active durable
  goal before scheduling or substantive work. Goal controls are required; this
  invariant is not configurable and goal creation does not expand authority.
- A LEAD or persistent SPECIALIST may explicitly bind a WATCHDOG to its durable
  goal; CTRL may not be watched. An unbound goal has no watchdog clock, check,
  receipt, or alert. A bound sensor detects material progress, flow, or
  outcome-integrity evidence and only records or routes `CLEAR`, `ATTENTION`, or
  `BLOCKER`. It never recovers, releases, reassigns, polls, queues, or becomes a
  daemon, private log, or activity-based progress system.

## Settings

| Setting | Meaning | Valid values |
| --- | --- | --- |
| `portfolio.max_active_tasks` | Tasks currently producing, integrating, or reviewing | 1-12 |
| `portfolio.default_parallel_tasks` | Preferred ceiling for an independent wave, never a creation quota | 1-8, not above max |
| `portfolio.reuse_existing_tasks` | Reuse matching live owners | boolean |
| `role_icons.enabled` | Include exactly one role-matched emoji in every SWARM task title | boolean; default true |
| `role_icons.ctrl` | CTRL title emoji | trimmed single line, 1-24 chars; default 🐙 |
| `role_icons.lead` | LEAD title emoji | trimmed single line, 1-24 chars |
| `role_icons.review` | REVIEW title emoji | trimmed single line, 1-24 chars |
| `role_icons.fallback` | Generic finite-task emoji when no logical contextual choice exists | trimmed single line, 1-24 chars |
| `role_icons.doer_choices` | Emojis DOERs may choose by actual work | 1-12 unique trimmed single-line strings |
| `execution.usage_profile` | Active relative model/effort policy | high, medium, low; default medium |
| `execution.service_tier` | Optional preferred tier for new tasks when the host exposes it | empty for host default, or advertised tier string; default empty |
| `execution.min_reasoning` | Global reasoning floor applied after every profile, role override, and route adjustment | none, minimal, low, medium, high, xhigh, max, ultra; compatibility-neutral default none |
| `execution.max_reasoning` | Global reasoning ceiling applied after every profile, role override, and route adjustment | none, minimal, low, medium, high, xhigh, max, ultra; compatibility-neutral default ultra; must be at least min |
| `execution.usage_saver` | Prefer lower-churn coordination for new work without weakening delivery | boolean; default false |
| `chat_relay.enabled` | Permit bounded, visible ChatGPT advisory consultations | boolean; default false |
| `chat_relay.provider` | Host-owned visible-browser adapter identifier | safe identifier; default `codex-chatgpt-control` |
| `chat_relay.surface` | User-visible ChatGPT surface for consultations | `chat` only |
| `chat_relay.mode` | Consultation authority mode | `consult` only |
| `chat_relay.routing_mode` | Explicit local/cloud routing preference | `auto`, `always_local`, or `always_cloud`; default `auto` |
| `chat_relay.offload_level` | Breadth of eligible ChatGPT routing | `light`, `balanced`, `high`, or `max`; default `balanced` |
| `chat_relay.default_model` | ChatGPT model requested for normal offloads | `gpt-5.6-luna`, `gpt-5.6-sol`, or `pro`; default `gpt-5.6-luna` |
| `chat_relay.default_effort` | ChatGPT reasoning level requested for normal offloads | supported level; default `xhigh` |
| `chat_relay.challenging_model` | ChatGPT model requested for explicitly challenging offloads | `gpt-5.6-luna`, `gpt-5.6-sol`, or `pro`; default `pro` |
| `chat_relay.challenging_effort` | ChatGPT reasoning level requested for explicitly challenging offloads | supported level; default `pro` |
| `chat_relay.executor_enabled` | Permit the separate host-owned ChatGPT local MCP executor | boolean; default false |
| `chat_relay.executor_write_mode` | Local executor file authority | `read_only` or `workspace`; default `read_only` |
| `chat_relay.executor_command_mode` | Local executor command authority | `none` or `safe`; default `none` |
| `chat_relay.executor_require_confirmation` | Confirm each local executor task before dispatch | boolean; default true |
| `logging.task_event_limit` | Bounded recent task-transition metadata retained in memory; never prompts, responses, artifact bodies, or credentials | 8-256; default 64 |
| `proof.policy_version` | Deterministic proof-planner policy | trimmed identifier; default lean-v1 |
| `proof.impacted_selection` | Select focused impacted gates when dependency reach is known | boolean; default true |
| `proof.receipt_reuse` | Permit exact-key stable gate adoption after runtime re-observation; never acceptance reuse | boolean; default true |
| `proof.gate_timeout_seconds` | Default gate timeout before truthful TIMEOUT | 1-3600; default 120 |
| `proof.browser_freshness_seconds` | Maximum reusable browser-proof age | 0-604800; default 86400 |
| `proof.provider_freshness_seconds` | Maximum reusable provider-proof age | 0-86400; default 3600 |
| `proof.transient_retry_limit` | Same-state retry budget for typed transient infrastructure failure | 0-1; default 1 |
| `turbo.enabled` | Opt into the high usage profile, fast service-tier preference, MAX progress policy, and the highest declared model-supported reasoning within the global bounds | boolean; default false |
| `efficiency.mode` | Resource strategy for useful depth, concurrency, routing, and review; never weakens safety floors | CONSERVE, BALANCED, FAST, MAX; default BALANCED |
| `efficiency.doer_wip_limit` | Maximum active assignments owned by one DOER | 1-8; default 3 |
| `hive.enabled` | Enable compact SWARM institutional-memory records | boolean; default true |
| `hive.cleanup_strategy` | Mechanical lifecycle cleanup | adaptive; default adaptive |
| `hive.retention_strategy` | Compact lesson retention policy | adaptive; default adaptive |
| `hive.worker_strategy` | Keep useful idle workers warm before retirement | warm_when_useful; default warm_when_useful |
| `hive.archive_behavior` | Preserve provenance through archive/purge | provenance; default provenance |
| `boost.enabled` | Make explicit, user-started Boost closeout goals available | boolean; default true |
| `boost.strategies` | Active Boost performance strategies | non-empty unique list of durable_goal, closeout_first, hands_off, spark_simple_work |
| `boost.plan_at_remaining_percent` | Prepare substantial closeout goals | 1-100; default 5 |
| `boost.decide_at_remaining_percent` | Lock goal contracts and final routing | 1-100; default 2 |
| `boost.launch_at_remaining_percent` | Launch or resume closeout goals | 1-100; default 1 |
| `boost.goal_levels` | Existing hierarchy levels eligible for substantial closeout goals | non-empty unique list of lead, doer, review |
| `boost.spark_model` | Reserve model for simple targeted work | model name; default gpt-5.3-codex-spark |
| `models.<profile>.<role>_model` | Model for CTRL, LEAD, DOER, TASK, SUBTASK, ASSIST, ADVISOR, SPECIALIST, legacy ARCHITECT, or REVIEW in a profile | trimmed model name up to 64 chars; defaults request Sol for CTRL, Terra for LEAD, Luna for DOER/TASK/SUBTASK; MOTHER uses SPECIALIST policy |
| `models.<profile>.<role>_reasoning` | Reasoning for that role and profile | none, minimal, low, medium, high, xhigh, max, ultra; host/model dependent |
| `model_capabilities.<MODEL>.provider` | Codex provider ID for a model | trimmed name up to 64 chars |
| `model_capabilities.<MODEL>.workloads` | Work classes an assigning CTRL or LEAD may route | non-empty unique list of simple, general, large_goal, review |
| `model_capabilities.<MODEL>.tools` | Verified host tools the model may use | up to 32 unique tool names; may be empty |
| `model_capabilities.<MODEL>.reasoning` | Ordered reasoning levels verified for the model on the intended host | optional non-empty unique subset of supported reasoning values |
| `roles.<ROLE>.icon` | Optional icon for a specialist or contextual role; `roles.MOTHER.icon` defaults to 🐝 | trimmed single line, 1-24 chars |
| `roles.<ROLE>.model` | Optional model override for a contextual leaf role | trimmed model name up to 64 chars |
| `roles.<ROLE>.reasoning` | Optional reasoning override for a contextual leaf role | supported reasoning value |
| `labels.lead` | Coordinator label | trimmed single line, 1-24 chars |
| `labels.doer` | Fallback DOER label | trimmed single line, 1-24 chars |
| `labels.review` | Independent review label | trimmed single line, 1-24 chars |
| `coordination.allow_coordinators` | Permit justified LEAD tasks | boolean |
| `coordination.coordinator_min_children` | Minimum children for an otherwise-justified LEAD; not a trigger | 2-8 |
| `coordination.preferred_lane_width` | Soft child-lane preference for every owner after delegation is justified | 1-8; default 3; never a quota or hard cutoff |
| `subagents.enabled` | Permit internal task subagents | boolean |
| `subagents.max_per_task` | Concurrent internal subagents per task | 0-8 |
| `subagents.allowed_for` | Permitted bounded work classes | exploration, implementation, testing, review |
| `review.task_enabled` | Make dedicated REVIEW tasks eligible when work warrants them; QC remains mandatory when false | boolean |
| `review.max_parallel_tasks` | Concurrent REVIEW tasks | 1-8 |
| `review.scale_when_queue_reaches` | Ready-artifact queue that adds review capacity | 2-8 |
| `monitoring.heartbeat_minutes` | Fallback cadence for an explicitly bound optional WATCHDOG | 1-120; default 30 |
| `monitoring.default_review_horizon_minutes` | Default event-driven goal review horizon | 1-60; default 30 |
| `monitoring.max_review_horizon_minutes` | Hard ceiling for a locally selected review horizon | 1-60; default 60 |
| `monitoring.small_task_review_horizon_minutes` | Preferred small-task horizon | 1-20; default 15 |
| `coordination.ctrl_direct_horizon_minutes` | Maximum measurable CTRL_DIRECT window | 1-60; default 20 |
| `recovery.max_attempts` | Legacy owner recovery budget; WATCHDOG never consumes it | exactly 1; non-disableable |
| `recovery.stall_after_updates` | Unchanged owner work updates before a lane stalls; heartbeat observations excluded | 1-5 |
| `lifecycle.pin_created_tasks` | Pin new SWARM tasks | boolean |
| `lifecycle.archive_completed_tasks` | Archive terminally accepted finite tasks only when no concrete retention reason remains | boolean; default true |
| `feedback.enabled` | Make the on-demand SWARM feedback workflow available | boolean; default true |
| `feedback.include_diagnostics` | Include the privacy-safe SWARM diagnostic snapshot | boolean; default true |
| `feedback.prompt_on_close` | Offer one optional feedback prompt after an accepted portfolio | boolean; default false |
| `feedback.destination` | Optional issue URL, email, or channel shown before explicit submission | empty, or trimmed single line up to 512 chars |

Unknown tables or keys are errors. If the file is invalid, stop creating new
portfolio tasks, show the exact validation error, and let already-owned work
continue safely. If the file is missing, use built-in defaults.

## Accepted-task archive

When `lifecycle.archive_completed_tasks` is true, archive a finite task only
after terminal acceptance and only when no concrete reason remains to retain its
user-visible surface. Never archive while review or correction is pending, a
user choice or continuation is expected (including an image-generation review
set), a goal, ownership, or handoff remains active, or the state is ambiguous.
Ambiguous tasks remain open until a later bounded stale audit proves archival is
safe; then use the host archive control. The setting creates no queue, daemon,
ledger, polling loop, or telemetry.

The default title hierarchy is `🐙CTRL - <objective>`, an optional advisory
specialist such as `🐝MOTHER - release coordination`, a lane owner such as `🔐LEAD - payments`, a
contextual owner such as `💻DEVELOPER - webhook`, and `🔎REVIEW - webhook`.
Generic DOER is an authority type, not a required task name: use the concrete
job. Keep the lane marker `LEAD` stable, put its domain or responsibility after
the dash, and use a domain-matched icon. With `role_icons.enabled = true`, every
title has exactly one literal role emoji concatenated directly with its label.
The label and emoji express the same responsibility. Fewer characters are
better only while the title remains unambiguous. `labels.doer` is only the
fallback; custom labels and emojis never change authority.

## Models and usage

The packaged low, medium, and high profiles use distinct reasoning defaults.
The high profile requests `max` for every built-in role; the host-observed value
remains authoritative and may be unavailable or different.
For a normal run, route tier 1 selects one step below the role default, tier 2
selects the role default, and tier 3 selects one step above it. SWARM then
applies `execution.min_reasoning` and `execution.max_reasoning` as global clamps.
Those bounds override profile defaults and `roles.<ROLE>.reasoning`; they never
expand a model's declared host-supported reasoning levels. The neutral defaults
preserve existing explicit `none`, `minimal`, and `ultra` settings. When a
model declares supported levels, SWARM selects the nearest permitted value
inside the global range and fails closed if the range and model do not overlap.

Every named role is resolved from its own configured pair in every packaged
profile. These are customizable defaults, not token quotas, billing limits, or
hard caps. Users may edit every pair and add a `roles.<ROLE>` table for a custom
leaf role; an unlisted custom role requires an explicit override.

SWARM passes model and reasoning when the host task API supports them and permits
saved-config selection. If the host requires a direct request, the resolved
profile remains a preference until the user requests that model in the current
task. The default empty `service_tier` keeps the host's normal behavior. Set it
to `"fast"` as an opt-in preference only when the host exposes and permits that
tier. A host without per-task tier selection keeps its own tier. Existing tasks
are never rewritten by a settings change.

## Turbo mode

Turbo is a disabled-by-default composite over the three controls SWARM can
confidently use:

1. **Reasoning envelope:** select the high usage profile and resolve every new
   assignment at the highest declared model-supported level up to
   `execution.max_reasoning` and not below `execution.min_reasoning`.
2. **Fast transport preference:** resolve `execution.service_tier` to `fast`.
3. **Fast progress policy:** resolve `efficiency.mode` to `MAX`, enabling the
   runtime's highest critical-path parallelism and routing bias while retaining
   its standard review floor.

Set `[turbo] enabled = true` to activate it for new scheduling decisions. Turbo
does not rewrite the user's underlying low/medium/high, tier, or efficiency
values, so disabling it restores those values on the next load. Direct user
instructions still win.

Turbo means maximum *configured* reasoning, not guaranteed token consumption.
It cannot promise spend, latency, quota, fast-tier availability, or literal
full-token use. It does not weaken safety, authority, WIP, proof, review,
recovery, bound-WATCHDOG, or acceptance requirements, and it is independent of
Boost and Usage Saver.

## Usage Saver

`execution.usage_saver = true` makes SWARM use the lower-churn option when two
sound tactics preserve the same outcome. It reuses current-wave context and
matching owners, batches compatible read-only discovery and passive task waits,
keeps small or serially dependent work with its existing owner, sends only
material contract changes, and reruns the failed proof plus the smallest
relevant regression set after correction. It does not invent a token target or
claim savings that the host does not report.

Usage Saver never changes the selected model, reasoning, service tier, task
ceilings, or capability routing. It never hides portfolio work in subagents,
cuts scope, skips review or proof, weakens authority, suppresses a real blocker,
or substitutes static evidence for required runtime or live proof. The normal
lane test and configured recovery budget still decide when work should split or
stop. Turning the setting on affects new scheduling and management actions, not
already-dispatched contracts.

`Swarm.from_config` retains the flag in runtime state. When the existing
coordination rules choose canonical deduplication, current-owner context reuse,
or a non-critical spawn refusal, the efficiency ledger records the
`usage_saver:` reason; critical-path, proof, authority, model, and reasoning
requirements remain unchanged.

### Visible ChatGPT advisory relay

The optional `chat_relay` table is a usage-saving consultation seam, not a
provider route or a quota feature. When enabled, SWARM may ask a compatible
visible browser bridge to consult the ChatGPT Chat surface for bounded T0/T1
planning, research, or review. The bridge must expose a signed-in visible
session, its observed configuration, and a host receipt; the user must confirm
each prompt at action time.

`chat_relay.routing_mode = auto` is the recommended setting. It offers only
self-contained advisory work to the visible Chat surface. `always_local`
keeps every task local. `always_cloud` requests cloud routing for eligible
bounded advisory work but never overrides local-boundary, mutation, consequence,
visible-session, or confirmation checks. `chat_relay.offload_level` then gives
Auto four route-breadth stops: `light` is selective, `balanced` is the default
common set, `high` widens to most eligible T0/T1 consultations, and `max`
includes every otherwise-eligible advisory consultation. Local files,
terminals, browser state, writes, tests, and artifacts remain local at every
level.

Relay telemetry is provider-reported only. The local ledger preserves request,
response, thread, asset, latency, and token fields when the bridge returns
them; missing provider usage is shown as unavailable. It does not estimate
tokens and cannot claim savings without an equivalent local baseline.

Normal offloads request GPT-5.6 Luna at Extra High reasoning. Callers may mark
an eligible consultation as challenging to request Pro intelligence. The host's
visible selection and receipt remain authoritative; if the bridge cannot verify
the requested selection, it must fail closed to local Codex.

The relay never sends writes, uploads, commands, or artifact-producing work. It
never handles T2-T4 consequence tiers, owns acceptance, replaces independent
review, or changes the selected Codex model, reasoning, tier, or authority. If
the session, bridge, or confirmation is missing, SWARM falls back to local
Codex. The adapter is expected to use the visible user-directed workflow (for
example, the community `codex-chatgpt-control` pattern), not hidden endpoints,
cookies, private APIs, scraping, account pooling, or quota bypasses. See
[chat-relay.md](chat-relay.md) for the contract and claim limits.

The assigning CTRL or LEAD routes by capability before model preference: the provider/model must be
available, its workload must fit, and every required tool must be exposed by the
host and declared for that model. An unlisted model is unverified. The packaged
catalog keeps `gpt-5.3-codex-spark` on simple shell/web work and declares
computer use for the GPT-5.6 models, including Luna. Read
[model-providers.md](model-providers.md) to connect Kimi, Qwen, or another
Responses-compatible Codex provider and add a capability entry without storing
credentials in SWARM.

## Boost mode

Boost turns the active SWARM outcome into one durable Codex goal per eligible
existing owner with substantial closeout work. Together they cover integration,
remaining outcome-critical work, independent review, proof, and honest closeout
without routine steering.

Set `boost.enabled = false` to disable optional Boost closeout behavior. It does
not disable mandatory role goals or an explicitly bound WATCHDOG. When enabled, Boost
still starts only
after a direct request such as "start Boost mode". SWARM first checks for an
unfinished goal in each eligible task. It continues a matching goal without
recreating it and refuses to replace a different unfinished goal. For each new
goal, SWARM defines one objective and one stopping condition, then supplies the
relevant files, proof commands, checkpoints, non-goals, and authority limits.
It does not add a token budget unless the user explicitly provides one.

The default strategies are all enabled:

- `durable_goal`: use one Codex goal per eligible owner for its verifiable part
  of the Boost objective;
- `closeout_first`: prioritize remaining outcome-critical work, integration,
  review, proof, and closeout over new optional scope;
- `hands_off`: after launch, suppress owner messaging, steering, and status
  requests. Passive bound-WATCHDOG and terminal/attention observation continue
  without waking owners. Interrupt only for a direct user change, required
  approval or safety boundary, or a genuine human-only blocker.
- `spark_simple_work`: route only small, targeted, low-risk work to
  `boost.spark_model` when that model and its separate allowance are available.
  Keep substantial closeout goals on their configured SWARM role models.

Inside an explicitly Boost-authorized run, use real host-reported remaining
usage to glide through three stages. With `durable_goal`, plan substantial
owner-level goals at 5%, lock their outcome, stopping condition, proof, and
routing at 2%, then launch or resume them at 1%. `closeout_first`, `hands_off`,
and `spark_simple_work` act only when present in `boost.strategies`. If telemetry
is unavailable, do not estimate it; ask the user to start Boost or report the
remaining percentage.

When `durable_goal` is enabled, treat configured levels as eligible. Launch only
for existing owners with substantial remaining closeout work; close tiny or
complete owners normally and report them as skipped. Never create empty tasks
to host a goal. A leaf goal owns remaining implementation, tests, proof, and
  handoff; LEAD accepts child handoffs only into its domain and integrates them;
REVIEW owns the cumulative independent verdict; CTRL alone accepts the full
integrated outcome. A lookup, single edit, one command, or status relay is never
a Boost goal. Hands-off forbids messaging and active polling, but permits passive
bound-WATCHDOG and terminal/attention waits over launched owners.

SWARM has no account-usage telemetry and does not auto-start Boost at a guessed
threshold. Codex goals support long-running independent work, but Boost is not a
promise to bypass account, service, model, rate, or spend limits. If goal tools
are unavailable or goals are disabled in the host, report that exact blocker.

The functional hierarchy stays sole-root CTRL, optional LEAD, finite ownership, and
acceptance. Rename levels with `labels`, omit LEAD with
`coordination.allow_coordinators = false`, create arbitrary contextual leaf
roles, and control dedicated review tasks with `review.task_enabled`. Turning
off a dedicated REVIEW task never turns off QC.

The role emoji system is active by default. Set `role_icons.enabled = false`
only to remove emojis from all SWARM task titles; direct user instruction still
wins for the requested task. CTRL uses `role_icons.ctrl`, default `🐙`.
Hierarchy roles use their matching `role_icons` setting. Contextual tasks use `roles.<ROLE>.icon` when present;
otherwise select automatically from `role_icons.doer_choices` by conventional
literal meaning. Prefer a familiar object or action understandable without a
legend, such as a hammer for BUILD or a computer for DEV. Infer other roles from
the same principle rather than a fixed mapping. Avoid decorative, novel, or
merely colorful choices. Keep one emoji per title and reuse the same emoji for
the same contextual role within a portfolio. For a LEAD, choose the domain icon
rather than a generic leadership icon and use `role_icons.lead` only as the
fallback when no domain match is clear. Use `role_icons.fallback` only when no
choice is clearly logical. Enabled emojis are fully customizable.

Older configs may still contain `portfolio.title_prefix`. The loader accepts
and ignores that retired setting so an update does not break scheduling.
`role_icons.enabled` is current boolean configuration and is never ignored.

## Soft lane width

`coordination.preferred_lane_width = 3` is one universal per-span shaping preference,
applied only after delegation is already worthwhile. CTRL normally keeps about
three direct LEAD lanes. LEADs, finite DOER owners, REVIEW owners, and
consequential planning TASKs use the same preference for their justified
children or internal subtasks.

Three is not a quota, trigger, or hard maximum. Keep four direct children when
that is clearer, use waves when capacity is tighter, and stay flat when another
handoff would add no value. Do not prebuild a three-by-three tree. `portfolio.max_active_tasks`,
`portfolio.default_parallel_tasks`, `review.max_parallel_tasks`, and
`subagents.max_per_task` remain separate scheduling or safety ceilings. With the
packaged defaults, eight is the exceptional internal-subagent ceiling while
three is the normal shape.

## Optional WATCHDOG

An accountable LEAD or persistent SPECIALIST may explicitly bind one WATCHDOG
sensor to its durable goal at `monitoring.heartbeat_minutes`; CTRL may not be
watched. Unbound
goals create no clock, check, receipt, or alert. The sensor records only
`CLEAR`, `ATTENTION`, or `BLOCKER`; it never decides, recovers, reassigns,
restructures, reviews, or accepts work. Ordinary alerts return to the watched
owner. Owner-integrity alerts follow the prevalidated non-self route.
See [monitoring.md](monitoring.md) for batching, stale-state, timing, and Boost
`hands_off` behavior.

## Feedback

Users can say "give feedback on SWARM" or "report a SWARM bug" at any time. SWARM
returns a compact portable report and, when enabled, a privacy-safe diagnostic
snapshot. It never gathers telemetry or sends feedback automatically. A
configured destination is contacted only after a direct instruction to submit
the visible packet. Do not store tokens, credentials, or private routing data
in `feedback.destination`. Set `feedback.prompt_on_close = true` to allow one optional
prompt after an accepted portfolio; it remains suppressed during Boost
hands-off execution and is off by default. See [feedback.md](feedback.md).
