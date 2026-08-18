# Visible ChatGPT advisory relay

SWARM can optionally use the user's visible ChatGPT Chat session for a narrow
consultation before local execution. This is a routing seam for planning,
research, and review—not a ChatGPT model provider, an API proxy, or a way to
avoid usage limits.

## Contract

The relay is eligible only when all of these conditions hold:

- `chat_relay.enabled = true`;
- the requested purpose is `plan`, `research`, or `review`;
- the consequence tier is T0 or T1;
- the request has no write intent and produces no artifact;
- a compatible browser bridge reports a visible, signed-in ChatGPT session;
- the bridge reports the actual visible model and reasoning effort;
- the bridge reports the visible surface/configuration and a host receipt; and
- the user confirms the exact prompt immediately before it is sent.

The `chat_relay.offload_level` setting controls route breadth: `light` is
selective, `balanced` covers the common bounded consultation set, `high`
widens that set to most eligible T0/T1 work, and `max` routes every otherwise
eligible advisory task. Local-boundary work remains local at every level.

The default policy requests GPT-5.6 Luna at Extra High reasoning. An explicitly
challenging eligible consultation requests Pro intelligence. These are visible
host selections, not hidden model aliases. The bridge must report a matching
visible model and effort (known labels such as `GPT-5.6 Luna`/`Extra High` are
normalized to the stable SWARM names) or the consultation falls back to local
Codex. An unknown or mismatched label is not treated as a match.

The visible response is advisory context. Local SWARM/Codex remains the
execution owner, and the bound LEAD/REVIEW route remains the only acceptance
authority. A missing capability falls back to local Codex instead of blocking
the task.

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
`ChatRelayCapability`, then receives one rendered advisory prompt through
`send_consult`. SWARM calls that method only after routing succeeds; a blocked,
unconfirmed, unknown, or mismatched capability is returned as a local fallback
and the adapter is not called. The response must carry its own host receipt and
observed model and effort, and remains transient advisory text rather than a
SWARM acceptance receipt.

The canonical runtime entry points are `Swarm.select_chat_relay()` for a
decision and `Swarm.consult_chat_relay()` for the host call. `Swarm.from_config`
loads the validated `chat_relay` policy, so callers do not bypass runtime
authority by constructing an independent policy accidentally.

Successful visible consultations may write a small local
`chat-relay-usage.json` ledger beside the SWARM config. It stores only the
timestamp, optional task identity, purpose, visible model/effort, and a rough
token estimate; it never stores prompts or responses and retains at most 100
events. The estimate is `ceil(relay prompt bytes / 4) + ceil(ChatGPT reply
bytes / 4)`. This is an avoided-Codex-work estimate for the Settings view, not
billing, quota, or remaining-usage telemetry. Ledger writes are best effort and
must never block or fail a relay consultation.

An optional `CodexChatGPTControlAdapter` is bundled as a lazy Python facade for
the community SDK's documented backend protocol. It is not installed or
started automatically; construction requires explicit capability and exact
prompt-confirmation callbacks. If the package, backend, visible receipt, or
observed configuration is missing, the adapter fails closed.

## Deliberate non-goals

This feature does not:

- reproduce or depend on an unpublished model name or internal route;
- automate a loophole that suppresses usage accounting;
- turn ChatGPT into a hidden SWARM worker with repo-write authority;
- make ChatGPT output a test, deployment, provider, device, or acceptance
  receipt; or
- install a third-party bridge automatically.

Until a compatible bridge is deliberately installed and configured, the
feature stays dormant. See the adapter's own documentation for its runtime
requirements and visible-session safety controls.
