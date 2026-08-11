# Global SWARM settings

SWARM reads `~/.agents/swarm/config.toml` before scheduling or managing a
portfolio. Run `python scripts/rush_config.py show --json` from the skill
directory to resolve built-in defaults plus the user's file.

The loader requires Python 3.11 or newer and otherwise uses only the standard
library. `show --json` writes structured settings to stdout. Parse, schema, and
read failures write a specific diagnostic to stderr and exit with status 2.
`init` is idempotent and never overwrites an existing settings file.

## Precedence

The configuration loader has exactly two file layers: packaged defaults, then
one selected global file (`~/.agents/swarm/config.toml`, with the read-only
legacy `~/.agents/rush/config.toml` fallback when canonical config is absent). Direct user, project, and session instructions govern task
behavior, safety, and authority, but are not loader file-merge layers.

Settings affect new scheduling and management decisions. They do not rewrite an
already-dispatched task contract. Re-read the config before a new scheduling
wave so edits take effect without reinstalling the plugin.

Packaged values are editable defaults, not a complete operating policy. Keep
context-dependent decisions in SWARM's general selection rules and add a setting
only when a user needs that preference to persist across runs. Hard validation
protects schema integrity and fixed SWARM invariants; it should not encode a
catalog of project-specific tactics.

## Fixed invariants

Configuration cannot make an unsafe or hidden coordination path valid:

- Portfolio lanes are user-visible host tasks. In Codex, create Codex tasks with
  thread tools.
- Subagents may work only inside an owning Codex task and never replace a lane.
- The latest direct user instruction controls its task.
- Existing safety, authority, provider, worktree, and proof boundaries remain.
- If a required task tool is unavailable, report the blocker instead of
  substituting a local process or subagent hierarchy.
- CTRL, MOTHER, every LEAD, and every persistent ARCHITECT require an active durable
  goal before scheduling or substantive work. Goal controls are required; this
  invariant is not configurable and goal creation does not expand authority.
- The MOTHER heartbeat is passive when enabled (the default): it reads every active
  descendant, detects stalls from material-change evidence, performs exactly
  one configured same-surface recovery, and then releases or reassigns on an
  unchanged result. `monitoring.heartbeat_enabled = false` is silent; it never
  becomes polling, a queue, daemon, private log, or activity-based progress.

## Settings

| Setting | Meaning | Valid values |
| --- | --- | --- |
| `portfolio.max_active_tasks` | Tasks currently producing, integrating, or reviewing, excluding MOTHER | 1-12 |
| `portfolio.default_parallel_tasks` | Preferred ceiling for an independent wave, never a creation quota | 1-8, not above max |
| `portfolio.reuse_existing_tasks` | Reuse matching live owners | boolean |
| `role_icons.mother` | MOTHER title emoji | trimmed single line, 1-24 chars; default ⚡ |
| `role_icons.lead` | LEAD title emoji | trimmed single line, 1-24 chars |
| `role_icons.review` | REVIEW title emoji | trimmed single line, 1-24 chars |
| `role_icons.fallback` | Generic finite-task emoji when no logical contextual choice exists | trimmed single line, 1-24 chars |
| `role_icons.doer_choices` | Emojis DOERs may choose by actual work | 1-12 unique trimmed single-line strings |
| `execution.usage_profile` | Active relative model/effort policy | high, medium, low; default medium |
| `execution.service_tier` | Optional preferred tier for new tasks when the host exposes it | empty for host default, or advertised tier string; default empty |
| `execution.usage_saver` | Prefer lower-churn coordination for new work without weakening delivery | boolean; default false |
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
| `boost.goal_levels` | Existing hierarchy levels eligible for substantial closeout goals | non-empty unique list of mother, lead, doer, review |
| `boost.spark_model` | Reserve model for simple targeted work | model name; default gpt-5.3-codex-spark |
| `models.<profile>.<role>_model` | Model for MOTHER, LEAD, DOER, TASK, SUBTASK, ASSIST, ADVISOR, ARCHITECT, or REVIEW in a profile | trimmed model name up to 64 chars |
| `models.<profile>.<role>_reasoning` | Reasoning for that role and profile | none, minimal, low, medium, high, xhigh, max, ultra; host/model dependent |
| `model_capabilities.<MODEL>.provider` | Codex provider ID for a model | trimmed name up to 64 chars |
| `model_capabilities.<MODEL>.workloads` | Work classes MOTHER may assign | non-empty unique list of simple, general, large_goal, review |
| `model_capabilities.<MODEL>.tools` | Verified host tools the model may use | up to 32 unique tool names; may be empty |
| `roles.<ROLE>.icon` | Optional icon for a custom contextual leaf role | trimmed single line, 1-24 chars |
| `roles.<ROLE>.model` | Optional model override for a contextual leaf role | trimmed model name up to 64 chars |
| `roles.<ROLE>.reasoning` | Optional reasoning override for a contextual leaf role | supported reasoning value |
| `labels.mother` | Portfolio orchestrator label | trimmed single line, 1-24 chars |
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
| `monitoring.heartbeat_minutes` | Passive MOTHER snapshot cadence for active descendants; mandatory heartbeat remains enabled | 1-120; default 30 |
| `recovery.max_attempts` | One safe same-surface recovery before release | exactly 1; non-disableable |
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

The default title hierarchy is `⚡MOTHER - outcome`, an optional lane owner such
as `🧭API LEAD - payments`, a contextual owner such as `💻DEVELOPER - webhook`,
and `🔎REVIEW - webhook`. Generic DOER and LEAD are authority types, not required
task names: use the concrete job, retaining LEAD unless another familiar title
communicates the same higher ownership. Every title has exactly one literal role
emoji, concatenated directly with its label, and a concrete two-to-five-word
artifact. The label and emoji express the same responsibility. Fewer characters
are better only while the title remains unambiguous. `labels.doer` is only the
fallback; custom labels and emojis never change authority.

## Models and usage

The packaged profiles use Sol/medium for MOTHER, LEAD, ASSIST, ADVISOR,
ARCHITECT, and REVIEW; Luna/xhigh for DOER; and Luna/high for TASK and
SUBTASK. Every named role is resolved from its own configured pair in every
packaged profile. These are customizable defaults, not token quotas, billing
limits, or hard caps. Users may edit every pair and add a `roles.<ROLE>` table
for a custom leaf role; an unlisted custom role requires an explicit override.

SWARM passes model and reasoning when the host task API supports them and permits
saved-config selection. If the host requires a direct request, the resolved
profile remains a preference until the user requests that model in the current
task. The default empty `service_tier` keeps the host's normal behavior. Set it
to `"fast"` as an opt-in preference only when the host exposes and permits that
tier. A host without per-task tier selection keeps its own tier. Existing tasks
are never rewritten by a settings change.

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

MOTHER routes by capability before model preference: the provider/model must be
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
not disable mandatory role goals or the MOTHER heartbeat. When enabled, Boost
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
  requests. Passive heartbeat and terminal/attention observation continue
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
REVIEW owns the cumulative independent verdict; MOTHER alone accepts the full
integrated outcome. A lookup, single edit, one command, or status relay is never
a Boost goal. Hands-off forbids messaging and active polling, but permits passive
heartbeat and terminal/attention waits over launched owners.

SWARM has no account-usage telemetry and does not auto-start Boost at a guessed
threshold. Codex goals support long-running independent work, but Boost is not a
promise to bypass account, service, model, rate, or spend limits. If goal tools
are unavailable or goals are disabled in the host, report that exact blocker.

The functional hierarchy stays MOTHER, optional LEAD, finite ownership, and
acceptance. Rename levels with `labels`, omit LEAD with
`coordination.allow_coordinators = false`, create arbitrary contextual leaf
roles, and control dedicated review tasks with `review.task_enabled`. Turning
off a dedicated REVIEW task never turns off QC.

The role emoji system is always active. Hierarchy roles use their matching
`role_icons` setting. Contextual tasks use `roles.<ROLE>.icon` when present;
otherwise select automatically from `role_icons.doer_choices` by conventional
literal meaning. Prefer a familiar object or action understandable without a
legend, such as a hammer for BUILD or a computer for DEV. Infer other roles from
the same principle rather than a fixed mapping. Avoid decorative, novel, or
merely colorful choices. Keep one emoji per title and reuse the same emoji for
the same contextual role within a portfolio. Use `role_icons.fallback` only
when no choice is clearly logical. Emojis are required but fully customizable.
`🐙 SWARM` is the product mark, not a task-title prefix. The mandatory opening
title starts `CTRL - <project>` with no emoji and does not replace MOTHER's
configurable default `⚡`.

Older configs may still contain `portfolio.title_prefix` or
`role_icons.enabled`. The loader accepts and ignores those two retired settings
so an update does not break scheduling; neither appears in effective settings
or changes title behavior. Remove them when next editing the config.

## Soft lane width

`coordination.preferred_lane_width = 3` is one universal per-span shaping preference,
applied only after delegation is already worthwhile. MOTHER normally keeps
about three direct LEAD lanes. LEADs, finite DOER owners, REVIEW owners, and
consequential planning TASKs use the same preference for their justified
children or internal subtasks.

Three is not a quota, trigger, or hard maximum. Keep four direct children when
that is clearer, use waves when capacity is tighter, and stay flat when another
handoff would add no value. Do not prebuild a three-by-three tree. `portfolio.max_active_tasks`,
`portfolio.default_parallel_tasks`, `review.max_parallel_tasks`, and
`subagents.max_per_task` remain separate scheduling or safety ceilings. With the
packaged defaults, eight is the exceptional internal-subagent ceiling while
three is the normal shape.

## Heartbeat

MOTHER passively snapshots the active task tree every
`monitoring.heartbeat_minutes` and reports one sentence per active descendant,
including children and grandchildren. Each sentence names the task, current
state or material progress, and working duration derived from host timestamps or
an explicitly approximate first-observed time. Heartbeat never messages or wakes
owners, never creates a second ledger, and never counts toward stall detection.
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
