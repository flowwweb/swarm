# Model providers and capability routing

## User choice is binding

An explicit user choice of model, provider, service tier, or reasoning level is
an assignment constraint, not a preference. Preserve it exactly for CTRL and
every child assignment. SWARM may explain a mismatch or recommend an
alternative, but must not silently lower, raise, replace, or reinterpret the
choice. If the host cannot honor it, return the exact blocker. SWARM chooses
these settings only when the user explicitly delegates that choice.

SWARM keeps two concerns separate:

1. Codex connects to and authenticates a model provider.
2. SWARM records what each configured model may own.

Never place API keys in the SWARM settings file. Use an environment variable or
the provider authentication mechanism supported by Codex.

## Connect a provider to Codex

Codex supports custom `model_providers` and named profiles in
`~/.codex/config.toml`. Use the exact model ID, Responses-compatible base URL,
and authentication variable from the provider's current documentation:

```toml
[model_providers.<provider-id>]
name = "<Provider name>"
base_url = "<Responses-compatible base URL>"
env_key = "<API key environment variable>"
wire_api = "responses"

[profiles.<profile-id>]
model = "<provider model ID>"
model_provider = "<provider-id>"
```

Use this shape for providers serving Kimi, Qwen, or another model; do not guess
their endpoint, model ID, or environment variable. Codex no longer supports the
legacy `wire_api = "chat"` provider path. Start a new Codex task after changing
provider or model configuration.

A SWARM task can select a custom provider or profile only when the host task API
exposes that control. Otherwise activate the Codex profile before starting the
SWARM portfolio and report that the provider cannot be changed per task.

## Declare the model to SWARM

Add the same exact model ID to `~/.agents/swarm/config.toml`:

```toml
[model_capabilities."<provider model ID>"]
provider = "<provider-id>"
workloads = ["simple", "general"]
tools = ["shell", "web"]
```

Valid workloads are `simple`, `general`, `large_goal`, and `review`. Tool names
are host capability names such as `shell`, `web`, `computer_use`, and
`image_input`. Use an empty tools list for a text-only model with no verified
tool calling. Add only capabilities proven on the intended Codex client and
provider path.

## Route by capability

The assigning CTRL or LEAD applies three gates before model preference or cost:

1. the provider and model are available on this host;
2. the declared workload includes the lane's work class;
3. every required tool is both host-exposed and declared for that model.

If any gate fails, choose another configured model or return the exact blocker.
Do not silently drop computer use, image inspection, review, tests, or proof to
fit a cheaper model.

For every task and subagent, record the requested model, provider, reasoning,
service tier, selection source, and exact host model receipt when the host
provides one. Fast mode changes only the request service tier: request `fast` or
`priority`, and treat the response's `service_tier` as the served-tier evidence
(`fast` may be reported as `priority`). Record `requested_fast_mode`,
`requested_service_tier`, nullable `actual_service_tier`, and the bound host
response receipt separately. A request receipt proves only what SWARM asked the host to run.
Actual model execution remains `UNVERIFIED` unless host metadata identifies it;
never infer Luna execution from the configured default or successful helper
completion. Likewise, never report Fast mode active from config, task
creation, latency, or success alone. The current visible-task host API exposes no
service-tier request or confirmation field, so those assignments stay schedulable
with Fast mode `UNAVAILABLE` until that host capability and receipt exist.

Third-party models can use shell, web, MCP, apps, or computer use only when the
provider protocol, model tool calling, modalities, and Codex host all support
the path. Being selectable in Codex does not prove those tools work. Run a
bounded read-only probe before consequential routing and update the SWARM catalog
with the observed result.

Execution transport is a separate optional layer. Load
[execution-adapters.md](execution-adapters.md) before enabling one. Every adapter
publishes a capability matrix using only `native`, `enforced`,
`instruction_only`, or `unsupported`; selection is explicit and a missing or
disabled adapter never triggers provider fallback. Adapter events and success
do not grant SWARM ownership, review, acceptance, host-task mutation, or provider
authority.

The packaged catalog keeps `gpt-5.3-codex-spark` on simple shell-only work and
keeps computer-use work on the configured GPT-5.6 models, including Luna. Spark
is text-only during its research preview and is not a large-goal fallback. Its
separate small-work toggle is off by default; even when enabled, it is limited
to the allowlist in [config.md](config.md#spark-small-work-policy).
