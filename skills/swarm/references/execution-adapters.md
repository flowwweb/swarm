# Codex host execution adapters

An execution adapter translates an already-authorized SWARM request into the
Codex host protocol. It never chooses the owner, stores prompt or response
bodies, reviews its own work, accepts an artifact, mutates a host task, or grants
external-provider authority.

## Universal HQ connector

Explicit HQ commands and scoped Auto continuation use one `HQCommandEnvelope`, one host-injected authorization receipt, `UniversalHQConnector`, and the existing Ledger CONNECTOR receipts. Fixed actions are AUTO, MANUAL_AGENT, TASK, TOPOLOGY_MATERIALIZE, REPAIR, and LOCAL_HQ. A command is reserved atomically before transport; only `APPENDED` may dispatch, while exact `REPLAY` never dispatches again.

`CodexAppServerAdapter` receives a host-owned `CodexAppServerTransport`; it has no subprocess or argv launch authority. It uses only capabilities the host exposes and retains returned thread/turn identities plus the observed root digest. App Server is never claimed to return project ID, agent role, or a binding receipt.

Localhost migration replaces private `CodexStdioBridge` Auto dispatch and routes manual-agent, task, topology, and repair commands through this envelope. Explicit HQ submission is single-use user authorization; a current scoped Auto grant is the only reusable authorization. Explicit commands no longer depend on unavailable `host_threads.agent_role` or host project fields. Structural Current Work observation remains read-only. LOCAL_HQ bypasses Codex transport and returns a digest-bound plan for later localhost execution and acknowledgement. Console wiring remains a separate owner/path slice.

## Capability matrix

Every adapter declares each capability as exactly one of:

- `native`: the transport exposes the operation directly;
- `enforced`: SWARM runtime validates the invariant before translation;
- `instruction_only`: text asks for behavior but cannot enforce it;
- `unsupported`: the adapter cannot perform or prove it.

A required `instruction_only` or `unsupported` capability blocks execution.
Every adapter is disabled unless explicitly selected. Missing and disabled
adapters stay disabled and never silently fall back; there is no implicit model
or transport fallback. Registry selection is explicit, and the Codex host remains
the only supported execution authority.

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
