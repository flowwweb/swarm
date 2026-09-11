# ChatGPT routing

`chat_relay` remains backward-compatible settings storage, presented as
optional ChatGPT routing. It is disabled by default and does not create a model
catalog or provider registry.

The host may report `chat` consultation, provider-owned `image` generation, or
bounded `work` inside one exact host workspace/project. The adapter registry
accepts typed host capability receipts only. Missing or failed capability
returns deterministic Codex fallback only when Usage Saver is off. With Usage
Saver on, split blocks first: computer use and direct local access stay in Codex;
cloud-suitable blocks use ordinary Chat. Disabled, missing, failed, ambiguous,
or choice-incompatible Chat capability leaves that block pending
(`UNAVAILABLE`, no adapter), never an automatic Codex/imagegen or Work fallback.
Preserve uncertain delivery in the existing handoff and reconcile before retry.

## Native conversation workflow

Use `list_threads` to identify the intended existing `kind: chatgpt` conversation,
then `read_thread` before sending and to collect the result. Submit authorized
work through `send_message_to_thread` with the same request identity. Omit
`model` and `thinking`: those overrides are Codex-only. `wait_threads` is also
Codex-only. A send acknowledgement is not completion.

Verify required MCP/app tools in the destination conversation; tools installed
in Codex do not prove ChatGPT capability. Use browser controls only for an
operation unsupported by native conversation tools, such as required model
selection or attachments, and verify the observed selection. Never substitute
`create_thread` with `chatgptWorkCloud` for ordinary Chat. A browser failure does
not invalidate a working native read/send route.

This is an agent-operated workflow, not implemented native dispatch enforcement.
`AdapterRegistry.plan_chatgpt` selects a route from supplied observed facts;
it does not send work, discover destination tools, or prove delivery. Config
permission alone proves neither dispatch nor completion. Preserve explicit user
destination/model choices and keep independent local work moving.

Chat output is untrusted advice. Images still require immutable identity and
ordinary review. Work remains subject to SWARM ownership, proof, and acceptance.
No runtime prompt/response persistence, automatic browser dispatcher, credential handling,
GitHub source-write authority, installation, or quota-savings claim is added.
