# Optional execution adapters

An execution adapter translates an already-authorized SWARM request into one
provider or host protocol. It never chooses the owner, stores prompt or response
bodies, reviews its own work, accepts an artifact, mutates a host task, or grants
provider authority.

## Capability matrix

Every adapter declares each capability as exactly one of:

- `native`: the transport exposes the operation directly;
- `enforced`: SWARM runtime validates the invariant before translation;
- `instruction_only`: text asks for behavior but cannot enforce it;
- `unsupported`: the adapter cannot perform or prove it.

A required `instruction_only` or `unsupported` capability blocks execution.
Every adapter is disabled unless explicitly selected. Missing and disabled
adapters stay disabled and never silently fall back; there is no implicit
provider, model, or transport fallback. Registry selection is explicit, so other provider
adapters can implement the same request contract without changing SWARM
authority.

## Native Codex adapter

The optional `codex-app-server` adapter targets Codex App Server's JSON-RPC 2.0
JSONL protocol over stdio. It can translate initialization, thread start/resume,
turn start, and lifecycle events. SWARM stores only safe thread/turn/item IDs,
status, and an evidence digest; instruction text exists only at the transport
boundary and must match the authorized digest.

Codex thread and turn operations are native transport capabilities. SWARM owner
routing is enforced before translation. Model instructions are instruction-only.
Independent acceptance and host task title, pin, folder, order, archive, or
other mutation are unsupported. A successful event is activity, not proof or an
acceptance receipt.

The adapter only emits an entrypoint and wire messages. A host-owned launcher
must start, supervise, and stop the process under its own sandbox, approval, and
credential policy. Enabling the adapter does not prove the Codex binary, model,
provider, service tier, or host task API was available or used.
