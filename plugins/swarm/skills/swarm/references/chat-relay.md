# Visible ChatGPT advisory relay

SWARM can optionally use the user's visible ChatGPT Chat session for bounded
planning, research, review, testing advice, and explicitly requested provider
image generation. This is a routing seam—not a ChatGPT model provider, an API
proxy, or a way to avoid usage limits.

## Contract

The relay is eligible only when all of these conditions hold:

- `chat_relay.enabled = true`;
- `chat_relay.routing_mode` permits the route (`auto` is the default; `always_local`
  disables cloud routing and `always_cloud` applies only to eligible advisory work);
- the requested purpose is `plan`, `research`, `review`, `testing`, or
  `imagegen`;
- the consequence tier is T0 or T1;
- the request has no write intent and produces no local artifact;
- an `imagegen` request explicitly opts into a provider-owned artifact and does
  not claim local ownership or acceptance;
- a compatible browser bridge reports a visible, signed-in ChatGPT session;
- the bridge reports the actual visible model and reasoning effort;
- the bridge reports the visible surface/configuration and a host receipt; and
- the user confirms the exact prompt immediately before it is sent.

The `chat_relay.routing_mode` setting controls the transport preference:
`auto` applies the offload level, `always_local` keeps eligible consultations
in local Codex, and `always_cloud` sends every otherwise-eligible advisory
consultation through the visible ChatGPT bridge. Local-boundary work remains
local in every mode. With `auto`, `chat_relay.offload_level` controls route
breadth: `light` is selective, `balanced` covers the common bounded
consultation set, `high` widens that set to most eligible T0/T1 work, and `max`
routes every otherwise-eligible task.

Auto is the recommended mode: it sends only self-contained work with
explicitly shared context. Repo files, terminals, browser state, test
execution, writes, uploads, local artifacts, and acceptance carry a local
boundary and remain local in every mode. Testing advice may be relayed, but the
test command and result must be produced locally. An image request may ask
ChatGPT to create a provider-owned asset; SWARM records the provider asset
receipt but does not copy it into the repo, accept it, or treat it as local
proof. Always cloud does not override these boundaries, mutation checks,
consequence tiers, visible-session checks, or user confirmation.

The default policy requests GPT-5.6 Luna at Extra High reasoning. GPT-5.6 Sol
is also supported when it is the visible host selection. An explicitly
challenging eligible consultation requests Pro intelligence. These are visible
host selections, not hidden model aliases. The bridge must report a matching
visible model and effort (known labels such as `GPT-5.6 Luna`, `GPT-5.6 Sol`,
and `Extra High` are
normalized to the stable SWARM names) or the consultation falls back to local
Codex. An unknown or mismatched label is not treated as a match.

The visible response is advisory context. Local SWARM/Codex remains the
execution owner, and the bound LEAD/REVIEW route remains the only acceptance
authority. A missing capability falls back to local Codex instead of blocking
the task.

## Optional local MCP executor

`chat_relay.executor_enabled` is a separate, disabled-by-default path. It is
the only route that may ask ChatGPT to read, edit, or run work in a local
workspace. It does not make the visible browser relay a filesystem bridge.

The executor is eligible only when the caller marks an explicit local
boundary, the four-level offload setting permits the work, and a host-owned
adapter reports a connected bridge, an exact workspace scope, the required
read/write/command/artifact tools, the observed model and reasoning effort,
and a host receipt. User confirmation is required by default.

`executor_write_mode = "read_only"` never permits writes. `workspace` permits
only the host's reported workspace write tools. `executor_command_mode =
"none"` never permits commands; `safe` still depends on the bridge's own
approved command capability. T4 work remains local, and mutation, command, or
artifact work requires `Max` so the user makes that breadth choice explicitly.
The adapter returns a host receipt and transient result; SWARM performs the
tests, review, artifact checks, and final acceptance. A transport or capability
failure falls back to local SWARM.

When repo context is useful, the local side may build a transient context packet
from an explicit tuple of repo-relative UTF-8 file paths. The packet rejects
path traversal, symlink escapes, `.git` and credential/key paths, caps each file
at 32 KiB and the whole packet at 96 KiB, and records a SHA-256 digest for each
file and for the rendered packet. It does not discover files, include the whole
repo, or persist prompt content in SWARM state. Sending that packet remains a
separate visible action requiring confirmation.

## Adapter boundary

The default adapter identifier is `codex-chatgpt-control`. It represents the
community pattern of controlling an already-visible ChatGPT session through a
user-directed browser bridge. The adapter must not use hidden endpoints,
private API calls, cookie or local-storage extraction, UI scraping outside the
visible session, account pooling, programmatic quota extraction, or bypasses of
provider limits.

The adapter must preserve the actual visible model, effort, speed, and surface
as host observations. SWARM must not infer “Pro intelligence,” unlimited usage,
zero cost, or quota savings from a local routing decision. ChatGPT Work and
Codex/agentic usage may have separate or shared host accounting; only the host
can report the current usage and limits.

The runtime exposes a small host boundary: an adapter reports
`ChatRelayCapability`, then receives one rendered prompt through `send_consult`
or, for an explicit `imagegen` request, `send_image`. SWARM calls the selected
method only after routing succeeds; a blocked, unconfirmed, unknown, or
mismatched capability is returned as a local fallback and the adapter is not
called. Image routing additionally requires a provider asset receipt. Every
response carries its own host receipt, observed model and effort, and a typed
transport receipt. The transport receipt preserves provider/client thread,
request, response, asset, model, latency, and usage fields when the bridge
returns them. Missing fields stay empty or `UNAVAILABLE`; SWARM never invents
IDs, latency, or tokens. Text responses remain transient advisory context and
provider images remain unaccepted provider artifacts.

The Python adapter reuses the already-observed visible model and effort instead
of applying a second configuration mutation during send. This avoids a
provider-side UI race: if the visible selection is not the requested profile,
the decision falls back locally before any prompt is submitted.

The canonical runtime entry points are `Swarm.select_chat_relay()` for a
decision and `Swarm.consult_chat_relay()` for the host call. `Swarm.from_config`
loads the validated `chat_relay` policy, so callers do not bypass runtime
authority by constructing an independent policy accidentally.

Successful visible consultations may write a small local
`chat-relay-usage.json` ledger beside the SWARM config. It stores transport
receipts and provider-reported input/output/total token fields when available;
it never stores prompts or responses and retains at most 100 events. When the
provider does not expose usage, the event records the exact unavailable reason.
The Settings view makes no savings claim because this ledger has no equivalent
local baseline. Ledger writes are best effort and must never block or fail a
relay consultation. Legacy estimate logs are discarded rather than displayed.

An optional `CodexChatGPTControlAdapter` is bundled as a lazy Python facade for
the community SDK's documented backend protocol. It is not installed or
started automatically; construction requires explicit capability and exact
prompt-confirmation callbacks. If the package, backend, visible receipt, or
observed configuration is missing, the adapter fails closed.

For a Python caller that must cross from an ordinary local process into a
bridge-hosted Node runtime, SWARM ships
`scripts/chatgpt_http_stdio_relay.mjs`. Set
`CHATGPT_BROWSER_BACKEND_HTTP_URL` to a loopback HTTP endpoint created inside
the authenticated browser-bridge execution, and use the relay as the Python
adapter's backend command. The relay forwards only the documented NDJSON
backend protocol; it does not create a browser session or carry credentials.
Keep the Node backend and its browser runtime alive in the same host execution
for the entire Python call. A normal subprocess without that host still gets a
structured `browser_bridge_unavailable` result and SWARM falls back locally.

## Deliberate non-goals

This feature does not:

- reproduce or depend on an unpublished model name or internal route;
- automate a loophole that suppresses usage accounting;
- grant ChatGPT unscoped repository or machine authority;
- make ChatGPT output a test, deployment, provider, device, or acceptance
  receipt; or
- install a third-party bridge automatically.

Until a compatible bridge is deliberately installed and configured, the
feature stays dormant. See the adapter's own documentation for its runtime
requirements and visible-session safety controls.
