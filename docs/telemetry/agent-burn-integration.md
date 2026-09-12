# Agent Burn ideas in SWARM

SWARM reviewed `Melvynx/agent-burn` at commit `9da8df5102778df778288245c9e9fa4453ed722f` on 2026-09-13. The useful design is deliberately small: retain local quota readings, preserve historical snapshots, show measured versus projected usage, expose the token mix by task or model, and keep unknown values unknown when a provider did not return a reading.

## What SWARM already does

| Agent Burn idea | SWARM surface | State |
| --- | --- | --- |
| Local-only readings | `GET /api/usage-history` and the persisted token sample store | Implemented |
| Historical quota / burn history | Usage view ranges (`1d`, `1w`, `1m`) and measured rate history | Implemented |
| Current-cycle forecast | Remaining percentage, measured burn rate, and estimated exhaustion time | Implemented when the account and rate samples are current |
| Per-task breakdown | Usage modal's By task table and task rate graph | Implemented when task samples exist |
| Missing readings are not fabricated | `UNKNOWN` / `STALE` states and coverage notes | Implemented |
| Subscription-value comparison | Cost estimator / plan-rate inputs | Not claimed until a plan and provider rate are configured |

The dashboard now uses host-observed project task counts and active counts when an accepted completion receipt is missing. It labels that state as observed activity and keeps completion percentage unavailable; this avoids the empty-table/dash failure without inventing progress.

## Smallest importable contract

Keep one local telemetry record per observation:

```text
sampled_at, source, scope, task_id, model, input_tokens, output_tokens,
cached_tokens, total_tokens, remaining_percent, reset_at, receipt_state
```

Aggregate only adjacent, measured intervals. Gaps stay gaps. Forecast exhaustion only when the account reading is current, the rate is positive, and the estimate lands before reset. Cost remains `UNKNOWN` until a user-configured plan or provider rate is available.

This is intentionally a mapping onto SWARM's existing `token_samples`, `usage-history`, burn-rate, and task-usage paths rather than a second telemetry database. Agent Burn's subscription-value reporting is a useful future adapter, not a reason to duplicate local history.

## Verification boundary

The local usage history and task breakdown can be verified from the SWARM console API. Provider relay savings still require a successful ChatGPT native-tool receipt with provider, model, task id, and token accounting; a setting being enabled is not evidence of delivery.
