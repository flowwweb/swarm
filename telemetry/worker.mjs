// Public ingestion only. Fleet reads use the authenticated Cloudflare D1 API.
const PATH = "/api/swarm/telemetry";
const HEX = /^[a-f0-9]{32}$/;
const MODELS = new Set(["gpt-6.1-sol", "gpt-6-sol", "gpt-6-astra", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.5", "gpt-5.3-codex-spark", "other", "unknown"]);
const EFFORTS = new Set(["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra", "unknown"]);
const KINDS = new Set(["activation", "subagent_start", "subagent_end", "turn_start", "turn_end", "tool", "usage"]);
const FIELDS = ["input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"];
const BASE = ["event_id", "installation_id", "session_id", "at", "kind", "version", "os", "model", "effort"];
const boundedInt = (value, max) => Number.isSafeInteger(value) && value >= 0 && value <= max;
const exact = (value, keys) => value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

export function valid(event, now = Math.floor(Date.now() / 1000)) {
  const extras = event?.kind === "usage" ? ["tokens", "cost_microusd"] : event?.kind === "tool" ? ["tool", "success"] : ["turn_end", "subagent_end"].includes(event?.kind) ? ["coverage", "duration_ms"] : event?.kind === "activation" ? ["coverage"] : [];
  if (!exact(event, [...BASE, ...extras]) || !KINDS.has(event.kind)) return false;
  if (![event.event_id, event.installation_id, event.session_id].every(value => typeof value === "string" && HEX.test(value))) return false;
  if (!boundedInt(event.at, now + 300) || event.at < now - 7 * 86400 || !/^\d+\.\d+\.\d+\+codex\.\d{8}$/.test(event.version)) return false;
  if (!["Windows", "Darwin", "Linux", "other"].includes(event.os) || !MODELS.has(event.model) || !EFFORTS.has(event.effort)) return false;
  if (extras.includes("coverage") && !["baseline", "observed", "partial", "reset", "unavailable"].includes(event.coverage)) return false;
  if (["turn_end", "subagent_end"].includes(event.kind) && event.duration_ms !== null && !boundedInt(event.duration_ms, 86400000)) return false;
  if (event.kind === "tool" && (!["shell", "edit", "delegation", "swarm_read", "other"].includes(event.tool) || ![true, false, null].includes(event.success))) return false;
  if (event.kind === "usage") {
    const t = event.tokens;
    if (!exact(t, FIELDS) || !FIELDS.every(key => boundedInt(t[key], 1e9))) return false;
    if (t.input_tokens + t.output_tokens !== t.total_tokens || t.cached_input_tokens > t.input_tokens || t.reasoning_output_tokens > t.output_tokens) return false;
    if (event.cost_microusd !== null && !boundedInt(event.cost_microusd, 1e10)) return false;
  }
  return true;
}

const reply = (status, value) => Response.json(value, { status, headers: { "Cache-Control": "no-store" } });

export default {
  async fetch(request, env) {
    if (new URL(request.url).pathname !== PATH) return reply(404, {error: "not_found"});
    if (request.method === "GET") return reply(200, {service: "swarm-telemetry", schema_version: 1});
    if (request.method !== "POST") return reply(405, {error: "method_not_allowed"});
    if (request.headers.get("content-type")?.split(";")[0] !== "application/json") return reply(415, {error: "json_required"});
    if (Number(request.headers.get("content-length")) > 32768) return reply(413, {error: "too_large"});
    const reader = request.body?.getReader();
    if (!reader) return reply(400, {error: "invalid_batch"});
    let size = 0;
    const chunks = [];
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 32768) { await reader.cancel(); return reply(413, {error: "too_large"}); }
      chunks.push(value);
    }
    let batch;
    try {
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {bytes.set(chunk, offset); offset += chunk.byteLength;}
      batch = JSON.parse(new TextDecoder("utf-8", {fatal: true}).decode(bytes));
    } catch { return reply(400, {error: "invalid_batch"}); }
    if (!exact(batch, ["schema_version", "events"]) || batch.schema_version !== 1 || !Array.isArray(batch.events) || !batch.events.length || batch.events.length > 32 || !batch.events.every(event => valid(event))) return reply(400, {error: "invalid_batch"});
    const installation = batch.events[0].installation_id;
    if (batch.events.some(event => event.installation_id !== installation)) return reply(400, {error: "mixed_installations"});
    // IP is used transiently for abuse limiting, never stored with product events.
    for (const key of ["ip:" + (request.headers.get("CF-Connecting-IP") || "unknown"), "install:" + installation]) {
      if (!(await env.LIMITER.limit({key})).success) return reply(429, {error: "rate_limited"});
    }
    try {
      const insert = env.DB.prepare("INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?, ?, ?)");
      await env.DB.batch(batch.events.map(event => insert.bind(installation, event.event_id, event.kind, event.at, Math.floor(Date.now() / 1000), event.version, JSON.stringify(event))));
      return reply(200, {accepted: batch.events.map(event => event.event_id)});
    } catch { return reply(503, {error: "storage_unavailable"}); }
  },
  async scheduled(_event, env) {
    await env.DB.prepare("DELETE FROM events WHERE received_at < ?").bind(Math.floor(Date.now() / 1000) - 90 * 86400).run();
  }
};
