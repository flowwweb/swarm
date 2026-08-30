# Codex host execution adapters

An execution adapter translates an already-authorized SWARM request into the
Codex host protocol. It never chooses the owner, stores prompt or response
bodies, reviews its own work, accepts an artifact, mutates a host task, or grants
external-provider authority.

## Universal HQ connector

Explicit HQ commands and scoped Auto continuation use one `HQCommandEnvelope`, an injected host authorization verifier, `UniversalHQConnector`, and the existing Ledger CONNECTOR receipts. A single-use `HQAuthorizationReceipt` binds one envelope; a separate `HQAutoGrant` may bind reusable AUTO commands only within one project/root/CTRL/action/expiry scope. Constructing either data record does not authorize it. Fixed actions are AUTO, MANUAL_AGENT, TASK, TOPOLOGY_MATERIALIZE, REPAIR, and LOCAL_HQ. A command is reserved atomically before transport; only `APPENDED` may dispatch, while exact `REPLAY` may reconcile retained COMMAND/ACK facts but never dispatches again.

`CodexAppServerAdapter` receives a host-owned `CodexAppServerTransport`; it has no subprocess or argv launch authority. An injected resolver returns ephemeral `HQDispatchMaterial` containing the real canonical cwd and exact instruction bytes. Their UTF-8 SHA-256 must match the envelope, and a separate injected host root verifier must bind that exact canonical cwd to the authorized root digest, before Ledger reservation or transport. The adapter reuses the same thread/turn wire builders as ordinary Codex execution, sends text as the installed App Server UserInput shape (`type`, `text`, and empty `text_elements`), redacts the material representation, and never persists it.

New-thread MANUAL_AGENT and TOPOLOGY_MATERIALIZE commands call `thread/start` and admit ACKNOWLEDGED only after that response supplies one unambiguous string thread identity and cwd that the injected root verifier binds to the authorized root. They then call `turn/start` with the authorized input and admit RESULT only when the matching response supplies one unambiguous string turn identity for that thread. Existing-thread AUTO and TASK call root-bound `thread/resume` before `turn/start`; REPAIR calls root-bound `thread/resume` before `turn/steer` and accepts completion only when the request-bound thread and returned turn exactly match the envelope targets. App Server cwd is evidence for the injected verifier, not a self-authorizing root receipt. A thread start/resume response is never treated as a completed turn. Missing, non-string, ambiguous, or conflicting response identity or cwd leaves COMMAND or ACKNOWLEDGED as a typed pending lifecycle. Restart calls the injected reconciliation surface by command identity and may append a proven completion only when it returns the exact thread/turn identities plus verifier-bound cwd; it does not recover expired authorization or transient dispatch material and never redispatches an uncertain command.

The adapter's existing `AdapterExecutionPlan` is the disabled/readiness gate. Disabled, unavailable, or non-native required capability states produce COMMAND to UNSUPPORTED with zero App Server requests. App Server is never claimed to return project ID, agent role, or a binding receipt.

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
JSONL protocol. It can translate initialization, thread start/resume, turn
start/steer, and lifecycle events through an injected host-owned transport.
SWARM stores only safe thread/turn/item IDs, status, and an evidence digest;
instruction text exists only at the transport boundary and its UTF-8 SHA-256
must match the authorized digest.

Codex thread and turn operations are native transport capabilities. SWARM owner
routing is enforced before translation. Model instructions are instruction-only.
Independent acceptance and host task title, pin, folder, order, archive, or
other mutation are unsupported. A successful event is activity, not proof or an
acceptance receipt.

The adapter emits wire messages but no process entrypoint. A host-owned launcher
and injected transport must start, supervise, and stop App Server under the
host's sandbox, approval, and credential policy. Enabling the adapter does not
prove the Codex binary, model, provider, service tier, or host task API was
available or used.
