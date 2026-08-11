# SWARM Console

SWARM Console is the local command surface for global settings, project swarms,
hierarchy, and host-reported task analytics. It borrows the useful local-service
shape of codex-lb without adding account pooling, an API proxy, credentials, or a
second task ledger.

The always-visible Usage Saver switch writes the single
`execution.usage_saver` preference through the same validated settings API. It
is off by default, applies to new SWARM actions, and does not change model routing,
scope, proof, review, capability, or authority.

## Launch

Run the dependency-free local server from the plugin root:

```powershell
python skills/swarm/scripts/rush_console.py --open
```

The default address is `http://127.0.0.1:4788`. Override `--port`, `--codex-home`,
or `--config` only when needed.

Docker is optional. The launcher supplies explicit cross-platform host paths:

```powershell
python console/docker.py up
```

Add `--detach` for background mode; run `python console/docker.py down` to stop.
Direct Compose use must set `SWARM_CODEX_HOME` and `SWARM_CONFIG_HOME` explicitly; the
legacy `RUSH_CODEX_HOME` and `RUSH_CONFIG_HOME` names remain compatibility aliases.

Compose publishes only `127.0.0.1:4788`, mounts Codex metadata read-only, and
mounts the SWARM config directory for validated settings writes. Do not expose the
container port to a LAN or public host.

## Authority and privacy

- The console derives hierarchy from Codex task spawn edges and short
  legacy RUSH-formatted task titles. It does not create, accept, steer, or archive tasks.
- It reads only the state database columns needed for hierarchy, timestamps,
  model, effort, project grouping, and cumulative thread-token counts. It does
  not read message bodies, previews, rollouts, credentials, or the logs database.
- Project IDs sent to the browser are one-way hashes of local authorities; raw
  working directories and repository origins remain server-side.
- `Recent` means a task was updated within two configured heartbeat windows. It
  does not prove that a model is executing.
- Token totals are host-reported cumulative thread tokens. They are not billing,
  rate-limit, quota, or remaining-usage telemetry.
- Config writes are same-origin, token-gated, allowlisted, atomically replaced,
  and accepted only after the existing SWARM validator passes. One prior config
  backup is retained beside the live file.
- Feedback destinations are redacted and cannot be edited in the console.

## Visual contract

Keep the interface distinctive, calm, and operational: dark navy depth,
cold-light surfaces, restrained electric signals, readable hierarchy, and motion
that communicates active structure. Respect `prefers-reduced-motion`. Never add
generic dashboard filler, decorative charts without a decision, or activity
claims stronger than the host evidence.
