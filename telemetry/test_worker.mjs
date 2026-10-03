import assert from "node:assert/strict";
import test from "node:test";
import worker, {valid} from "./worker.mjs";

const event = () => ({event_id: "a".repeat(32), installation_id: "b".repeat(32), session_id: "c".repeat(32), at: Math.floor(Date.now()/1000), kind: "activation", version: "0.4.11+codex.20261002", os: "Windows", model: "gpt-6.1-sol", effort: "xhigh", coverage: "baseline"});
const request = (events, extra = {}) => new Request("https://flowwweb.com/api/swarm/telemetry", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({schema_version: 1, events, ...extra})});

test("strict schema rejects content, broken accounting and excess batch sizes", async () => {
  assert.equal(valid(event()), true);
  const start = {...event(),kind:"turn_start"};
  delete start.coverage;
  assert.equal(valid(start),true);
  assert.equal(valid({...event(),kind:"subagent_end",duration_ms:1000}),true);
  assert.equal(valid({...event(),kind:"turn_end",duration_ms:null}),true);
  for (const change of [{prompt: "secret"}, {model: "private-custom-name"}, {at: 0}, {installation_id: "hostname"}, {coverage: "compliant"}]) assert.equal(valid({...event(), ...change}), false);
  const usage = {...event(), kind: "usage", tokens: {input_tokens: 100, cached_input_tokens: 50, cache_write_input_tokens: 0, output_tokens: 10, reasoning_output_tokens: 5, total_tokens: 110}, cost_microusd: 205};
  delete usage.coverage;
  assert.equal(valid(usage), true);
  assert.equal(valid({...usage, tokens: {...usage.tokens, total_tokens: 109}}), false);
  for (const req of [request([event()], {prompt:"secret"}), request(Array(33).fill(event())), request([])]) assert.equal((await worker.fetch(req, {})).status, 400);
  const oversized = new Request("https://flowwweb.com/api/swarm/telemetry", {method: "POST", headers:{"Content-Type":"application/json"}, body:" ".repeat(32769)});
  assert.equal((await worker.fetch(oversized, {})).status, 413);
});

test("acknowledges only durable inserts, limits ingress and exposes no fleet reads", async () => {
  const stored = new Map();
  const db = {prepare: () => ({bind: (...values) => values}), batch: async rows => rows.forEach(row => stored.set(row[0] + row[1], row))};
  const env = {DB: db, LIMITER: {limit: async () => ({success:true})}};
  for (let i=0; i<2; i++) {
    const response = await worker.fetch(request([event()]), env);
    assert.equal(response.status, 200);
    assert.deepEqual((await response.json()).accepted, [event().event_id]);
  }
  assert.equal(stored.size, 1);
  assert.equal((await worker.fetch(request([event()]), {...env, LIMITER:{limit: async()=>({success:false})}})).status,429);
  assert.equal((await worker.fetch(request([event()]), {...env, DB:{...db, batch:async()=>{throw Error("disk");}}})).status,503);
  assert.deepEqual(await (await worker.fetch(new Request("https://flowwweb.com/api/swarm/telemetry"), env)).json(), {service:"swarm-telemetry",schema_version:1});
  assert.equal((await worker.fetch(new Request("https://flowwweb.com/api/swarm/telemetry/admin"), env)).status,404);
  let cutoff;
  await worker.scheduled({}, {DB:{prepare:()=>({bind:value=>({run:async()=>{cutoff=value;}})})}});
  assert.ok(Math.abs(cutoff - (Math.floor(Date.now()/1000)-90*86400)) < 2);
});
