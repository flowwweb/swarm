---
name: rush
description: Use RUSH to organize complex work into user-visible host task hierarchies, including Codex tasks in Codex, while preserving the requested outcome, parallelizing independent artifact lanes, coordinating dependencies, and requiring independent QC before MOTHER acceptance. Trigger for multi-part development, product, research, provider, or release workflows, and when task sprawl, bottlenecks, churn, overengineering, idle agents, or weak review are slowing delivery.
---

# RUSH

Reach the requested outcome faster by preparing the whole finish line, running
independent work together, and rejecting coordination that costs more than it
saves. Organization is useful only when it increases artifact throughput.

## Load settings

Before each scheduling wave, run `python scripts/rush_config.py show --json`
from this skill directory and follow [config.md](references/config.md). On a
read-only runtime or tooling failure, follow
[runtime-recovery.md](references/runtime-recovery.md): use one authorized,
non-elevated same-purpose fallback, pause only new config-dependent actions, and
let already-owned safe work continue. Never use silent defaults.

When asked to manage local settings, hierarchy, or analytics, read [console.md](references/console.md) and launch RUSH Console.

## Guide outcomes, not every move

Express context-dependent behavior as a preferred outcome, a small selection principle, and a clear stop condition. Let MOTHER and each owner choose the shortest sound tactic for the actual project. Treat examples, role names, icons, lane shapes, and packaged values as defaults, not hidden allowlists. Default visual, design, and image-generation work to distinctive, context-specific outcomes. Generic templates and filler fail review unless the user asks for restraint; distinctive means intentional and fitting, not maximal. When target-device visual direction materially guides implementation, prefer an independently inspectable ImageGen mockup lane that passes the normal lane test. Multiple requested concepts, selection language, or approval-oriented framing means return the review set for user choice before treating a direction as approved; explicit user workflow and provided designs always outrank this default.

Use hard rules only where flexibility would weaken safety, authority, ownership, the user-visible hierarchy, non-negotiable scope, or proof. Add configuration only for a preference users need to keep across runs. When a repeated choice drifts, improve the general rule or default at its existing authority instead of accumulating case-specific instructions and exceptions.

## Take feedback without slowing delivery

When the user says to give feedback on RUSH, report a RUSH bug, or suggest a
RUSH improvement, read [feedback.md](references/feedback.md). If
`feedback.enabled` is false, report that the workflow is disabled. Otherwise
return one compact feedback packet, using the privacy-safe diagnostic command
when `feedback.include_diagnostics` is true. Feedback never becomes a portfolio
lane, never blocks acceptance, and is never submitted automatically.

If `feedback.destination` is configured, state that it is available but contact
it only after a direct instruction to submit the specific packet. Do not print
credentials or private routing data embedded in a destination. If
`feedback.prompt_on_close` is true, offer at most one optional feedback sentence
after an accepted portfolio. Do not prompt during Boost hands-off execution or
after a failed or blocked outcome. The default is no prompt.

## Resolve execution policy

Select `execution.usage_profile`, then use that profile's MOTHER, LEAD, TASK,
or REVIEW model and reasoning pair for each new user-visible task. STEP MOTHER
inherits MOTHER execution policy. Contextual roles inherit TASK unless
`roles.<ROLE>` overrides their icon, model, or reasoning. Internal subagents
inherit their owning task unless a direct instruction says otherwise.

Before assigning a lane, match its workload and required tools against
`model_capabilities`. MOTHER must not route computer use, image input, review,
or a large goal to a model that does not declare that capability. Both the host
tool and the selected model must support it. Treat an unlisted model as
unverified, run a bounded capability probe when safe, and otherwise keep it away
from capability-critical work. Read [model-providers.md](references/model-providers.md)
when configuring or routing a custom provider model.

For provider or consequential work, generic tool support is not surface access.
Make the first material action a non-mutating receipt from the exact required
provider, account, browser profile, connector, or session. Name the observed
surface without exposing credentials, and permit mutation only after it passes.

Pass model and reasoning overrides only when the host task primitive exposes
them and its policy permits saved-config selection. If the host requires a
direct model request, omit the override unless the user made one in the current
task; still report the resolved preference and actual host behavior. When
`execution.service_tier` is non-empty, request it only if the host exposes and
permits per-task tier selection. An empty value keeps the host default. If a
host cannot apply the configured tier, continue useful work and do not claim it
was applied. If a host rejects a configured model or reasoning pair, report the
exact error instead of silently substituting another model. Settings affect new
tasks, not already-running tasks. High, medium, and low are relative
model/effort policies, not token quotas or billing caps.
Provider selection follows the same rule: use the configured Codex provider or
profile only when the host can bind it, and never claim a custom provider was
used from a model name alone.

## Preserve the outcome

Write one compact **outcome contract** from the user's request and current
product authority:

- target outcome and first useful artifact;
- non-negotiable capabilities and must-haves;
- explicit non-goals and authority limits;
- acceptance evidence and claim limits.

Do not invent either requirements or scope cuts. A task may own a narrow
artifact, but the portfolio must preserve the full outcome. If the user asks
for production readiness, checkout, payments, deployment, data, or another
consequential capability, do not disable or omit it and call the smaller result
successful. Missing authority or proof is a blocker to report, not permission
to redefine success. Ask only when an unresolved choice would materially change
the product or outcome.

## Run the shortest useful loop

Use one control loop unless a host or project boundary blocks it:

1. load settings and inspect existing tasks;
2. write the outcome contract and map the finish line;
3. keep tiny work in MOTHER and select the fewest worthwhile owners;
4. create tasks, dispatch their contracts, and show the task-tree receipt;
5. wait for artifacts or material blockers, integrate ready work, then review;
6. accept only proven work, release ownership, and close honestly.

Do not turn the loop into a separate planning artifact, status ledger, or
ceremonial phase. The user should be able to see who owns what, what can run
now, and where acceptance returns after the first scheduling wave.

## Save usage without shrinking delivery

When `execution.usage_saver` is true, choose the lower-churn tactic whenever two
sound options preserve the same outcome. Reuse current-wave context and matching
owners, batch compatible read-only discovery and passive waits, keep small or
serially dependent work with its owner, send only material contract changes,
and use focused reruns after a failed proof. Do not claim estimated savings.

Usage Saver is a coordination tie-breaker, never a scope or quality mode. It
must not change models, reasoning, service tier, capability routing, task
ceilings, user-visible ownership, authority, required proof, or independent
review. It must not guess quota state, hide lanes in subagents, or suppress a
real blocker. When false, apply the normal RUSH rules without this preference.

## Map the finish line

MOTHER is the planner. Identify the smallest complete set of artifacts needed
for the outcome:

1. critical-path product or decision work;
2. prerequisites and integration boundaries;
3. readiness work that can start now, such as tests, fixtures, content,
   provider setup, rollback, release evidence, or review preparation;
4. final acceptance owner and proof.

Start independent readiness work early. Do not wait for the main build to
finish before discovering that its tests, content, payment path, provider
receipt, deployment gate, or review surface are missing. Do not create an idle
task merely to reserve future work.

Follow [hierarchy.md](references/hierarchy.md) for role authority, normal
MOTHER-to-LEAD domain shaping, small flat portfolios, ASSIST, capacity, task
naming, receipts, and transfers. The MOTHER planning pass remains internal;
create a planning task only when its result is itself a consequential,
inspectable artifact.

## Dispatch only when it is faster

Use four quick weights, not a scoring system or ledger: outcome value,
independence, ownership clarity, and coordination cost. Create a lane only when
the first three are strong enough to beat its startup, steering, and handoff.

Use MOTHER -> LEAD -> TASK as the normal shape for a domain with repeated
decisions or integration. Keep small portfolios flat with direct TASKs when no
domain coordinator earns its handoff, and add STEP MOTHER only for justified
multi-LEAD grouping. Never generate a tree from configured counts.

Keep tiny same-surface work inside the owner or a bounded internal subagent. Use
ASSIST only for one immediate non-overlapping bottleneck that warrants a visible
finite handoff; it is not a level or setting. Follow
[hierarchy.md](references/hierarchy.md) for the lane test and full ASSIST
contract. Creating any coordinator or finite task never requires a goal; goals
require a direct user instruction or explicit Boost authorization.

## Make the hierarchy user-visible

RUSH portfolio roles are user-visible host tasks, not internal subagents. In
Codex, "task", "thread", and "chat" are the same user-controlled surface. Keep
the current task as MOTHER, reuse matching owners, create every justified role
through the host task primitive, dispatch [task-contract.md](references/task-contract.md),
and show one compact task-tree receipt. Follow
[hierarchy.md](references/hierarchy.md) for shaping, ASSIST, titles, capacity,
child authority, host-confirmed IDs, and ownership transfers.

Follow created tasks with passive [monitoring.md](references/monitoring.md) and
steer only material contract changes. Internal subagents may help inside an
owner when settings allow, but never become portfolio lanes or cross-task
authority.

Before declaring user-visible task tools unavailable, perform one bounded host
discovery for create, read/wait, and message primitives. Report each capability:
missing create stops new lanes, while available read/wait/message tools continue
existing handoffs. Preserve known task IDs and never replace missing task
primitives with subagents, files, plans, or local processes.

## Keep work flowing

MOTHER owns priority, collision decisions, integration, and final acceptance;
outside the compact heartbeat it does not relay routine status. Owners
communicate direct dependencies to the affected owner and return only artifacts,
behavior changes, proof, decisions, or new blockers.

### Monitor without steering

At each heartbeat, MOTHER passively reads active descendants, including children
and grandchildren, then returns one sentence per task with state, progress, and
duration. Follow [monitoring.md](references/monitoring.md): never steer; Boost
`hands_off` still observes; stall counts ignore it.

Integrate coherent handoffs as dependencies become ready rather than saving one
large merge for the end. Start newly unblocked work immediately within capacity.
Use STEP MOTHER or LEAD only while repeated child decisions or bounded
integration would otherwise burden its parent; remove it when that wave is
accepted. STEP MOTHER accepts LEAD handoffs only into its named segment, LEAD
accepts TASK handoffs only into its named domain, and MOTHER alone accepts the
portfolio.

Count a non-MOTHER task as active only while it is producing, integrating, or
reviewing. A TASK that emits an immutable ready handoff stops active work and
frees its capacity slot, but retains mutable ownership and correction
accountability until acceptance, explicit transfer, or exact blocker. REVIEW
may then use the freed slot. Silence and routine polls are not progress updates.

A lane stalls after the configured number of updates without material change.
Use the bounded recovery budget to remove a handoff, shrink to the true first
artifact, or try one safe same-surface fallback. Then return the exact blocker
and release ownership. Never disguise a stall with planning, polling,
checkpoints, or repeated narration.

If a named accepting route cannot receive a terminal handoff, attempt delivery
once and take one bounded liveness snapshot. Then return the unchanged immutable
artifact/revision, proof, and blocker to the nearest live ancestor, or to the
user when none is live, and release ownership. Never self-accept. Carry the
immediate successor artifact and its unblock condition in the predecessor's
existing stop/handoff so an uncreated dependency cannot disappear.

Treat an account, usage, host, model, or task-setup failure before artifact work
as a possible portfolio-level fault. Once the same boundary is known or likely
to affect sibling tasks, stop creating or retrying them, preserve the task IDs,
and report one exact blocker. If a recent failure or explicit warning makes a
new wave uncertain, start one representative task as a canary and fan out only
after its first material artifact-producing action succeeds or it otherwise
proves the suspect boundary. Do not add canary delay to a healthy host. If the
fault appears after some siblings are already producing material work, stop
pending creation and retries but do not interrupt proven unaffected owners.

If task creation returns only a provisioning handle, follow the provisioning
receipt in [task-contract.md](references/task-contract.md). A handle is
diagnostic setup evidence, not delegation, a live owner, or a duplicate guard.
After one bounded setup observation, retry once through a real user-visible host
task surface and fan out only after it yields a real task ID that starts material
work. MOTHER may perform immediate safety containment while setup is unresolved,
but all non-emergency artifact work remains delegated; do not absorb it into
MOTHER or hidden work.

When a direct user change alters the outcome, MOTHER sends one concise contract
delta to affected owners and REVIEW: changed must-haves, boundaries, acceptance,
and obsolete work. Preserve compatible artifacts, stop or reassign only work
invalidated by the change, and reschedule the smallest new gap. Do not restart
the portfolio or let an older task contract outrank the user. A portfolio-level
change received in a child task must be escalated to MOTHER before affected
mutation.

## Review before acceptance

Name the QC boundary while planning, but start review only when an inspectable
artifact exists. Use a user-visible REVIEW task for multi-lane, cross-owner, or
consequential work when `review.task_enabled` is true. When it is false, keep
independent QC inside an owning or MOTHER task; it does not disable review.
For one cohesive low-risk change, keep QC inside the owning
task with a bounded independent reviewer/subagent when available; do not create
a portfolio lane whose overhead exceeds the change. Scale review tasks only
across genuinely separate surfaces or queued artifacts; one acceptance owner
resolves their findings.

REVIEW follows [review-contract.md](references/review-contract.md) and judges the
cumulative artifact from the user's outcome, not the builder's explanation. In
order, check:

1. scope fidelity and non-negotiables;
2. domain, permission, data, security, and consequential authority;
3. credible failures, recovery, and continuity;
4. reuse, subtraction, maintainability, and common shortcuts;
5. rendered behavior, accessibility, responsiveness, and performance when
   relevant;
6. tests, observability, evidence, and claim limits.

The review response is the human review surface. Embed the highest-signal proof
directly in it: reference/candidate or before/after screenshots when visual
output is in scope, compact tables for repeated comparisons or matrices, and
short excerpts for source, logs, contracts, or receipts. Caption each item with
the observed state and proof class. Links and evidence folders are supplemental,
not substitutes. When capture is blocked, state the exact blocker and embed the
best available lower-class evidence without implying that it proves rendering
or live behavior. Show representative coverage and name material omissions when
the full evidence set is too large. Call fixtures structurally valid only; call
behavior passed only after the corresponding eval or workflow executes.

Treat standards as evidence, not automatic verdicts. When an artifact conflicts
with a contextual guideline rather than a safety, authority, legal, or explicit
product invariant, determine whether the defect is in the artifact, the rule,
or an unresolved product choice. Present the viable options, their user benefit,
risk, consistency cost, and evidence, then recommend one without disguising
judgment as fact. A material unresolved choice may still block acceptance; the
review must not prescribe one implementation when narrowing or replacing the
rule is plausibly better.

When the user says a review or correction is based on the wrong premise, stop
propagating its fix list. Retract the mistaken premise explicitly, reconstruct
the outcome from the latest user statement and product authority, and separate
the invariant player or user contract from mode-, variant-, preset-, or
environment-specific contracts. Preserve compatible findings, withdraw findings
that depended on the false premise, and send one concise contract delta to every
affected owner and reviewer before mutation resumes. Distill the incident into
the narrowest reusable selection rule at the existing authority; never turn one
project correction into a feature, a global product opinion, or a case-specific
exception catalog.

P0-P2 findings block acceptance. Fix bounded P3 only when the benefit is clear
and the correction creates no churn. REVIEW is verdict-only by default. If
MOTHER explicitly transfers one narrow correction to REVIEW after the prior
owner releases it, REVIEW returns CORRECT rather than approving its edit; a
different independent reviewer or context validates the correction before
MOTHER acceptance. After one correction round, rerun the exact failed proof and
the smallest relevant regression set. An unchanged second verdict returns the
blocker; it does not start an endless review loop.

## Subtract before adding

Prefer existing product, platform, repository, and workflow primitives. Add a
dependency, abstraction, configuration switch, task layer, persistent surface,
or compatibility path only for an explicit requirement, a current repeated
contract, or a necessary safety boundary. Hypothetical reuse is not a consumer.

Review the combined result, not only each lane. Remove duplicate authority,
unused variants, superseded paths, scaffolding, defensive copy, and proof
machinery that no longer has a job. Optimize total cognitive and operational
load, not raw line count; preserve explicit domain, security, accessibility,
audit, observability, and recovery invariants.

## Accept and close

When `lifecycle.archive_completed_tasks` is true, archive a finite task only
after terminal acceptance and only when no concrete retention reason remains.
Keep it open while review or correction is pending, user choice or continuation
is expected (including an image-generation review set), a goal, ownership, or
handoff remains active, or its state is ambiguous. Leave ambiguity open until a
later bounded stale audit proves archival safe, then use the host archive
control. Do not create a queue, daemon, ledger, polling loop, or telemetry for
this lifecycle rule.

### Use Boost for durable closeout

When `boost.enabled` is true and the user directly authorizes Boost for the run,
apply the configured `boost.strategies`. Do not treat the default setting alone
as permission to create goals. Once authorized, use real host-reported remaining
usage or a user-reported percentage; never estimate quota state.

Advance every newly crossed stage in order, even if the first observation is
already below more than one threshold. Apply only actions whose strategy is
configured:

1. At `plan_at_remaining_percent`, `durable_goal` prepares one substantial goal
   per eligible existing `goal_levels` owner with substantial closeout work,
   while `closeout_first` reprioritizes required closeout work.
2. At `decide_at_remaining_percent`, `durable_goal` freezes each objective,
   stopping condition, authority boundary, capability routing, dependencies,
   and proof loop.
3. At `launch_at_remaining_percent`, `durable_goal` creates or continues those
   goals and `hands_off` suppresses owner messaging and steering while the
   passive heartbeat continues.

When `durable_goal` is configured, MOTHER sends the stage and frozen contract to
each eligible existing user-visible owner with the host task messaging
primitive. Each owner creates or continues the goal in its own task under the user's
portfolio-wide Boost authorization; MOTHER cannot create a child task's goal
from the root. If task messaging or goal controls are unavailable, report the
exact level that could not launch. When `hands_off` is configured, do not message
owners or actively poll them after launch. MOTHER may maintain passive bounded
`wait_threads` aggregation for heartbeat, terminal, and attention events;
commentary does not trigger steering.

Do not create empty MOTHER, STEP MOTHER, LEAD, TASK, or REVIEW tasks only to host a goal. A
leaf goal bundles its remaining implementation, tests, proof, and handoff; STEP
MOTHER accepts LEAD handoffs only into its segment; LEAD accepts child handoffs
only into its bounded domain and integrates them; REVIEW
owns the cumulative independent verdict and failed-proof reruns; MOTHER alone
owns integrated portfolio acceptance. A lookup, one edit, one command, status
relay, or isolated tiny task is not large enough for Boost. Close tiny or
complete eligible owners normally and report them as skipped, not failed.

When `durable_goal` is configured, inspect the current goal before creating one.
If none is unfinished, create the Boost goal. If an unfinished goal already
matches this outcome and stopping condition, continue it without calling goal
creation again. If another goal is unfinished, report the conflict and do not
replace it. Define one objective and one verifiable stopping condition; include
the relevant sources, non-goals, authority limits, proof loop, and checkpoints.
Do not set a token budget unless the user explicitly supplies one.

When `closeout_first` is configured, prioritize integration, remaining
outcome-critical work, independent review, exact failed-proof reruns, regression
proof, and honest closeout. Boost may continue existing tasks or create a
genuinely necessary lane, but it must not manufacture work, broaden authority,
or trade the requested outcome for a tidy finish. Mark a durable goal complete
only after its stopping condition is proven.

Apply each configured strategy literally:

- `durable_goal`: give each eligible existing level owner with substantial
  remaining closeout work one Codex closeout goal;
- `closeout_first`: finish required work, integration, review, and proof before
  optional additions;
- `hands_off`: once launched, do not message, steer, interrupt, or request
  updates. Let the goal run independently; passive heartbeat and
  terminal/attention aggregation may observe it without waking on commentary.
  Intervene only for a direct user change, required approval or safety boundary,
  or a genuine human-only blocker.
- `spark_simple_work`: use `boost.spark_model` only for simple, targeted work
  when the model, its separate allowance, and required tools are available.
  Never move a large closeout goal, computer-use work, or independent review to
  Spark merely to consume another limit.

Codex goals support long-running independent work; Boost does not promise to
bypass account, service, model, rate, or spend limits. On Codex plans that
explicitly report active-turn continuation after a usage limit, that continuation
remains subject to host fair-use limits and has no guaranteed duration. If usage
telemetry or goal controls are unavailable, report that exact blocker and the
setting needed when known.

MOTHER accepts only the integrated outcome after required review and proof.
Child completion means ready for acceptance, never self-acceptance or production
readiness.

Close with the achieved outcome, artifacts and changed surfaces, exact proof,
review verdict, unresolved P0-P2 issues, claim limits, accepting owner, and
released ownership. Never turn a timeout, task count, commit, CI result, or
local screenshot into a stronger claim than it proves.
