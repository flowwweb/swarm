# SWARM product telemetry

Opt in with **Share SWARM usage with Flowwweb** during onboarding or in Settings.
The same setting is `telemetry.enabled = true` in the `[telemetry]` config table.
It defaults to false. Hook trust and telemetry consent are separate choices.

Consenting installations automatically send bounded events to
`https://telemetry.flowwweb.com/api/swarm/telemetry`: plugin activation and
version, operating-system family, coarse tool categories and observed failures,
delegation starts/stops, turn duration, observed model/reasoning settings, token
categories and conditional Standard API cost estimates. Unknown or unsupported
prices remain null. This does not expose the user's bill or subscription usage.

No prompts, responses, source code, file paths, hostname, account details,
credentials or raw session IDs are sent. A random installation ID and keyed
session hashes group activity. Turning telemetry off clears queued events,
local identifiers and usage cursors on the next hook. Existing central events
expire after 90 days. Opting in starts a usage baseline; it does not upload
previous conversation usage.

The local SQLite outbox holds at most 1,000 events for seven days. Background
hooks retry failed delivery with backoff; engineering work continues. The beacon
validates an exact schema, rejects excess fields, limits request size and rate,
and deduplicates event IDs. It offers no public fleet reads. Delivery state and
pending count appear in `swarm_status` under `device.product_telemetry`.

Flowwweb maintainers query through authenticated Cloudflare D1 access:

```text
python telemetry/manage.py summary --days 7
```

These are client-reported observations from consenting installations, not an
attested census. Hook activity does not prove SWARM compliance, successful work,
or satisfaction. Transcript accounting is bounded and may be partial if the
host format changes, a child start was not observed, counters reset, records
are oversized, or hooks are unavailable. Estimated prices are supported only
for explicitly priced models and reconciled request deltas.
Live delivery and deduplication checks do not establish throughput for thousands
of installations; storage and request limits remain those of the Cloudflare
Worker and its single D1 database.
