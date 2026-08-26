# Codex host model and execution boundaries

An explicit user choice of Codex model, service tier, or reasoning level is an
assignment constraint, not a preference. Preserve it exactly for CTRL and every
child assignment. SWARM may explain a mismatch or recommend an alternative,
but must not silently lower, raise, replace, or reinterpret the choice. If the
Codex host cannot honor it, return the exact blocker. SWARM chooses these
settings only when the user explicitly delegates that choice.

SWARM keeps two concerns separate:

1. The Codex host selects and serves a supported model.
2. SWARM records the host-provided capability and execution receipt.

SWARM never stores credentials in its settings file. The host owns model
authentication and execution. A `provider` label in a capability receipt is
descriptive metadata, not a writable SWARM execution authority.

## Codex host capability boundary

The Codex host is the only supported model-execution surface. SWARM can record
the exact model, host capability label, reasoning, requested service tier, and
host-served receipt when those are exposed. It does not configure, install, or
claim compatibility with another agent host. A missing or stale host receipt
leaves actual execution `UNVERIFIED`.

Model and tool capability is host-owned. Being named in a configuration file
does not prove that the Codex host served it or that a tool path worked. Use a
bounded read-only host receipt before consequential routing and keep each
unobserved capability `UNVERIFIED`.

Execution transport is the Codex host boundary. Load
[execution-adapters.md](execution-adapters.md) for the source/static contract.
An adapter receipt does not grant SWARM ownership, review, acceptance,
host-task mutation, or external-provider authority. External-provider proof is
still a distinct evidence class for real service boundaries, not model-host
execution.

The packaged catalog keeps `gpt-5.3-codex-spark` on simple shell-only work and
keeps computer-use work on the configured GPT-5.6 models, including Luna. Spark
is text-only during its research preview and is not a large-goal fallback. Its
separate small-work toggle is off by default; even when enabled, it is limited
to the allowlist in [config.md](config.md#spark-small-work-policy).
