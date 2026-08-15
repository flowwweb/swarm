# Read-only runtime recovery

Read this reference when the SWARM config loader or another required read-only
internal helper fails before it can return its normal receipt.

## Require an exact runtime receipt

Use the requested runtime when it is allowed. On Windows, a tooling permission
failure may justify one already-authorized, non-elevated runtime for the same
read-only script and arguments. Require an exact current-host receipt for that
runtime, such as an authorized bundled workspace dependency path or a successful
non-mutating capability check. Do not infer authorization from a provider login,
an unrelated command, an older task, or the runtime merely existing on disk.

Tooling permission and provider authentication are separate boundaries. A
blocked executable does not prove a provider is logged out, unhealthy, or
unauthorized. A provider session does not prove permission to launch a local
runtime. State only the receipt actually observed.

If the host requests user approval for that read-only internal helper or tool,
abandon or cancel it immediately, record a typed host-gate exception, and
continue already-owned bounded work that does not depend on the missing receipt.
Never ask the user to approve an internal helper. This recovery does not waive
approval for external or provider actions, destructive actions, or decisions
reserved to the user.

## Use one same-purpose fallback

Retry once with the authorized runtime, without elevation and without changing
the script, config path, arguments, read-only purpose, provider state, or safety
boundary. Do not cycle through interpreters, shells, browsers, credentials, or
providers. If the fallback works, report which runtime executed without
claiming broader approval or provider access.

## Contain only the affected actions

If the loader still fails, report the exact tooling or environment error and
pause new scheduling plus actions whose correctness depends on unresolved
config. Already-owned safe work, proof, review, and handoffs that do not require
new config resolution continue. Do not apply silent defaults, interrupt proven
unaffected owners, or generalize the loader failure into an account or provider
failure.
