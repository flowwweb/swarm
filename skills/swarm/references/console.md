# SWARM Console

SWARM Console is the local command surface for global settings, project swarms,
hierarchy, and host-reported task analytics. It borrows the useful local-service
shape of codex-lb without adding account pooling, an API proxy, credentials, or a
second task ledger.

The always-visible Usage Saver switch writes the single
`execution.usage_saver` preference through the same validated settings API. The
nearby `Save Codex usage with ChatGPT` switch controls `chat_relay.enabled` and
uses the description `Offload planning, coding, testing, and review to ChatGPT
to make your Codex usage go further.` Usage Saver is off by default and does not
change model routing, scope, proof, review, capability, or authority. The
ChatGPT switch is also off by default and enables only bounded, user-confirmed
advisory consultations; it does not grant ChatGPT execution or acceptance
authority.

Directly below that switch, Settings shows the local ChatGPT usage log: routed
task count, consultation count, recent metadata-only entries, and an estimated
Codex-token total. It reads one local JSON file and does not query Codex usage,
call a model, or start a refresh loop. `Clear log` removes that file through the
authenticated loopback console action.

The console switch changes only the relay's opt-in flag. It must preserve the
validated `chat_relay.default_*` and `chat_relay.challenging_*` profile fields;
those fields remain config-level settings, not UI guesses. After any settings
change, new scheduling waves reload the effective config, while already-
dispatched tasks keep their original contract. If validation fails, show the
diagnostic and leave the source file unchanged.

The Graph view's Usage panel is derived in the browser from the existing cached
`/api/overview` snapshot. It shows cumulative host-reported thread tokens,
observed tasks, active tasks, and model mix for the selected scope. It adds no
usage endpoint, database query, timer, model call, relay call, billing data, or
quota request.

## Launch

Run the dependency-free local server from the plugin root:

```powershell
python skills/swarm/scripts/swarm_console.py --open
```

The default address is `http://127.0.0.1:4788`. Override `--port`, `--codex-home`,
or `--config` only when needed.

The console is a portable Python 3.11+ process for Windows and macOS. Use
`python` on Windows and `python3` on macOS. The browser shell is also a PWA:
Safari can add it to an iPhone or iPad Home Screen when the console is reached
over a trusted LAN or hosted HTTPS address. The PWA caches only the static shell;
`/api/*` remains live and is never cached.

Docker is optional. The launcher supplies explicit cross-platform host paths:

```powershell
python console/docker.py up
```

Add `--detach` for background mode; run `python console/docker.py down` to stop.
Direct Compose use must set `SWARM_CODEX_HOME` and `SWARM_CONFIG_HOME` explicitly.

Compose publishes only `127.0.0.1:4788` and mounts both Codex metadata and the
SWARM config directory read-only. Docker is therefore an inspection surface;
use the native loopback launcher for validated settings writes. Do not expose
the container port to a LAN or public host.

## iPhone or iPad access

Run the native server on the Windows or macOS host with the explicit network
bind:

```text
# Windows
python skills/swarm/scripts/swarm_console.py --host 0.0.0.0

# macOS
python3 skills/swarm/scripts/swarm_console.py --host 0.0.0.0
```

Open `http://<host-lan-ip>:4788` in Safari and choose **Add to Home Screen**.
Network clients are read-only by design: they receive no local token and cannot
write settings. Keep the bind on a trusted network and return to the default
loopback mode when remote access is not needed.

## Authority and privacy

- The console derives hierarchy from Codex task spawn edges and short
  SWARM-formatted task titles. It does not create, accept, steer, or archive tasks.
- It reads only the state database columns needed for hierarchy, timestamps,
  model, effort, project grouping, and cumulative thread-token counts. It does
  not read message bodies, previews, rollouts, credentials, or the logs database.
- Project IDs sent to the browser are one-way hashes of local authorities; raw
  working directories and repository origins remain server-side.
- `Recent` means a task was updated within two configured heartbeat windows. It
  does not prove that a model is executing.
- Token totals are host-reported cumulative thread tokens. They are not billing,
  rate-limit, quota, or remaining-usage telemetry.
- Native-loopback config writes are same-origin, token-gated, allowlisted,
  atomically replaced, and accepted only after the existing SWARM validator
  passes. One prior config backup is retained beside the live file. Docker is
  explicitly read-only because container peers are not loopback authority.
- Feedback destinations are redacted and cannot be edited in the console.

## Visual contract

Keep the interface distinctive, calm, and operational: dark navy depth,
cold-light surfaces, restrained electric signals, readable hierarchy, and motion
that communicates active structure. Respect `prefers-reduced-motion`. Never add
generic dashboard filler, decorative charts without a decision, or activity
claims stronger than the host evidence.
