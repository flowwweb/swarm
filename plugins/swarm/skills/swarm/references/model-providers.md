# Model providers and capability routing

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

Third-party models can use shell, web, MCP, apps, or computer use only when the
provider protocol, model tool calling, modalities, and Codex host all support
the path. Being selectable in Codex does not prove those tools work. Run a
bounded read-only probe before consequential routing and update the SWARM catalog
with the observed result.

The packaged catalog keeps `gpt-5.3-codex-spark` on simple shell/web work and
keeps computer-use work on the configured GPT-5.6 models, including Luna. Spark
is text-only during its research preview and is not a large-goal fallback.
