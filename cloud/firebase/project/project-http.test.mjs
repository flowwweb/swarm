import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createServer, request as httpRequest } from "node:http";
import { once } from "node:events";
import { test } from "node:test";
import { createProjectHttp } from "../server/account-http.mjs";

const secret = "s".repeat(43), device = "device-one", workspace = "team-one";
const digest = (value) => createHash("sha256").update(value).digest("hex");
function fixture() {
  const docs = new Map(); let lock = Promise.resolve(), initializations = 0, writes = 0;
  const db = { projectId: "swarm-sync-20261105-fw", doc: (path) => ({ path }), runTransaction(fn) {
    const work = lock.then(async () => {
      const pending = new Map();
      const result = await fn({ get: async ({ path }) => ({ exists: docs.has(path), data: () => structuredClone(docs.get(path)) }), create: ({ path }, value) => pending.set(path, structuredClone(value)), set: ({ path }, value) => pending.set(path, structuredClone(value)) });
      for (const [path, value] of pending) { docs.set(path, value); writes++; }
      return result;
    });
    lock = work.catch(() => {}); return work;
  } };
  const auth = { async verifyIdToken(token, checkRevoked) { assert.equal(checkRevoked, true); if (!["alice", "bob"].includes(token)) throw Object.assign(new Error("fixture-private"), { code: "auth/id-token-revoked" }); return { uid: token }; },
    async getUser(uid) { return { uid, email: uid + "@example.test", emailVerified: true, disabled: false }; } };
  docs.set(`swrmDeviceAccounts/${digest("alice")}/devices/${device}`, { subject: "alice", secretDigest: digest(secret), revoked: false });
  docs.set(`swrmDeviceAccounts/${digest("bob")}/devices/${device}`, { subject: "bob", secretDigest: digest(secret), revoked: false });
  docs.set(`swrmWorkspaces/${workspace}`, { id: workspace, members: { alice: "owner", bob: "viewer" }, billingRevision: 1, billing: { verified: true, revision: 1, plan: "team", status: "active", paymentStatus: "paid", paidSeats: 2, validUntil: Date.now() + 600000 } });
  return { docs, get writes() { return writes; }, get initializations() { return initializations; }, initialize: () => (initializations++, { app: { options: { projectId: "swarm-sync-20261105-fw" } }, getFirestore: () => db, getAuth: () => auth }) };
}
function facade(res) {
  res.status = (v) => (res.statusCode = v, res); res.set = (k, v) => (res.setHeader(k, v), res);
  res.json = (v) => (res.setHeader("Content-Type", "application/json"), res.end(JSON.stringify(v))); res.send = (v) => res.end(v); return res;
}
async function withServer(handler, run) {
  const server = createServer(async (req, res) => { const chunks = []; for await (const c of req) chunks.push(c); req.rawBody = Buffer.concat(chunks); await handler(req, facade(res)); });
  server.listen(0, "127.0.0.1"); await once(server, "listening");
  const send = (body, headers = { "content-type": "application/json", authorization: "Bearer alice" }, method = "POST") => new Promise((resolve, reject) => {
    const req = httpRequest({ host: "127.0.0.1", port: server.address().port, path: "/project", method, headers }, (res) => { const chunks = []; res.on("data", (c) => chunks.push(c)); res.on("end", () => { const body = Buffer.concat(chunks).toString(); resolve({ status: res.statusCode, headers: res.headers, text: body, json: () => JSON.parse(body) }); }); });
    req.on("error", reject); req.end(body);
  });
  try { await run(send); } finally { server.close(); await once(server, "close"); }
}
const common = { deviceId: device, deviceSecret: secret, workspaceId: workspace };

test("real project HTTP preserves authorization, independent ticket value, CAS and replay", async () => {
  const previous = process.env.SWARM_SHARED_SYNC_ENABLED; process.env.SWARM_SHARED_SYNC_ENABLED = "true";
  const f = fixture();
  try { await withServer(createProjectHttp({ initialize: f.initialize }), async (send) => {
    const call = (v, token = "alice") => send(JSON.stringify(v), { "content-type": "application/json", authorization: "Bearer " + token });
    const created = await call({ action: "create", ...common, operationId: "create-1" }); assert.equal(created.status, 200); const projectId = created.json().projectId;
    assert.match(projectId, /^[0-9a-f-]{36}$/); assert.deepEqual((await call({ action: "create", ...common, operationId: "create-1" })).json(), { projectId, replay: true });
    const put = { projectId, deviceId: device, id: "put-1", expectedRevision: 0, kind: "put", value: "unrelated project content" };
    assert.deepEqual((await call({ action: "mutate", ...common, projectId, operation: put })).json(), { revision: 1, replay: false });
    const ticket = { projectId, deviceId: device, id: "ticket-1", expectedRevision: 1, kind: "ticket-put", value: '{"ticket":"stable-42"}' };
    assert.deepEqual((await call({ action: "mutate", ...common, projectId, operation: ticket })).json(), { revision: 2, replay: false });
    assert.deepEqual((await call({ action: "mutate", ...common, projectId, operation: ticket })).json(), { revision: 2, replay: true });
    let read = (await call({ action: "read", ...common, projectId })).json(); assert.equal(read.value, put.value); assert.equal(read.ticketValue, ticket.value); assert.equal(read.id, projectId);
    const stale = { ...ticket, id: "stale", value: "new ticket" };
    const conflict = (await call({ action: "mutate", ...common, projectId, operation: stale })).json(); assert.equal(conflict.conflict.value, ticket.value); assert.equal(conflict.conflict.revision, 2); assert.equal(conflict.replay, false);
    assert.equal((await call({ action: "mutate", ...common, projectId, operation: stale })).json().replay, true);
    assert.equal((await call({ action: "mutate", ...common, projectId, operation: { ...ticket, value: "changed" } })).status, 409);
    const writes = f.writes;
    for (const [payload, token] of [[{ action: "read", ...common, projectId }, "revoked"], [{ action: "read", ...common, projectId }, "bob"], [{ action: "read", ...common, deviceSecret: "x".repeat(43), projectId }, "alice"], [{ action: "read", ...common, deviceId: "wrong", projectId }, "alice"], [{ action: "read", ...common, workspaceId: "wrong-workspace", projectId }, "alice"], [{ action: "read", ...common, projectId: "00000000-0000-4000-8000-000000000000" }, "alice"]]) assert.equal((await call(payload, token)).status, 403);
    const key = `swrmDeviceAccounts/${digest("alice")}/devices/${device}`; f.docs.get(key).revoked = true; assert.equal((await call({ action: "read", ...common, projectId })).status, 403); f.docs.get(key).revoked = false;
    const billing = f.docs.get(`swrmWorkspaces/${workspace}`).billing; billing.paymentStatus = "unpaid"; assert.equal((await call({ action: "read", ...common, projectId })).status, 403); assert.equal(f.writes, writes);
    billing.paymentStatus = "paid"; billing.validUntil = 0; assert.equal((await call({ action: "read", ...common, projectId })).status, 403); assert.equal(f.writes, writes); billing.validUntil = Date.now() + 600000;
    const deletion = { projectId, deviceId: device, id: "delete-1", expectedRevision: 2, kind: "delete" };
    assert.deepEqual((await call({ action: "mutate", ...common, projectId, operation: deletion })).json(), { revision: 3, replay: false });
    assert.deepEqual((await call({ action: "mutate", ...common, projectId, operation: deletion })).json(), { revision: 3, replay: true });
    read = (await call({ action: "read", ...common, projectId })).json(); assert.equal(read.deleted, true); assert.equal(read.value, null); assert.equal(Object.hasOwn(read, "ticketValue"), false);
  }); } finally { if (previous === undefined) delete process.env.SWARM_SHARED_SYNC_ENABLED; else process.env.SWARM_SHARED_SYNC_ENABLED = previous; }
});

test("project HTTP respects project cap, CORS, input checks and safe errors", async () => {
  const previous = process.env.SWARM_SHARED_SYNC_ENABLED; process.env.SWARM_SHARED_SYNC_ENABLED = "true"; const f = fixture();
  try { await withServer(createProjectHttp({ initialize: f.initialize }), async (send) => {
    const body = JSON.stringify({ action: "create", ...common, operationId: "cap" }); const headers = { "content-type": "application/json", authorization: "Bearer alice" };
    let r = await send(Buffer.concat([Buffer.from(body), Buffer.alloc(262144 - Buffer.byteLength(body), 32)]), headers); assert.equal(r.status, 200); const projectId = r.json().projectId;
    const mutate = (value, id) => JSON.stringify({ action: "mutate", ...common, projectId, operation: { projectId, deviceId: device, id, expectedRevision: 0, kind: "ticket-put", value } });
    r = await send(mutate("x".repeat(32000), "value-limit"), headers); assert.equal(r.status, 200);
    const writes = f.writes; r = await send(mutate("x".repeat(32001), "value-overflow"), headers); assert.equal(r.status, 400); assert.equal(f.writes, writes);
    r = await send(Buffer.alloc(262145, 32), headers); assert.equal(r.status, 413);
    r = await send(body, { ...headers, origin: "https://other.example" }); assert.equal(r.status, 403);
    r = await send(body, { ...headers, origin: "https://swarm.botlord.ai" }); assert.equal(r.status, 200); assert.equal(r.headers["access-control-allow-origin"], "https://swarm.botlord.ai");
    r = await send(body, { ...headers, authorization: "Bearer revoked" }); assert.equal(r.status, 403); assert.equal(r.headers["access-control-allow-origin"], undefined);
    r = await send("", { origin: "https://swarm.botlord.ai", "access-control-request-method": "POST", "access-control-request-headers": "authorization, content-type" }, "OPTIONS"); assert.equal(r.status, 204);
    r = await send("", headers, "GET"); assert.equal(r.status, 405);
    r = await send(body, { ...headers, "content-encoding": "gzip" }); assert.equal(r.status, 400);
    r = await send(Buffer.from([0xff]), headers); assert.equal(r.status, 400);
    r = await send("{", headers); assert.equal(r.status, 400);
    r = await send(body, { "content-type": "text/plain", authorization: "Bearer alice" }); assert.equal(r.status, 400);
    r = await send(body, ["Content-Type", "application/json", "Authorization", "Bearer alice", "Authorization", "Bearer bob"]); assert.equal(r.status, 400);
    assert.equal(r.text.includes(secret), false);
  }); } finally { if (previous === undefined) delete process.env.SWARM_SHARED_SYNC_ENABLED; else process.env.SWARM_SHARED_SYNC_ENABLED = previous; }
});

test("actual project Functions export fails closed before provider access", async () => {
  const keys = ["SWARM_SHARED_SYNC_ENABLED", "GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT", "FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST"]; const prev = Object.fromEntries(keys.map((k) => [k, process.env[k]]));
  try {
    delete process.env.SWARM_SHARED_SYNC_ENABLED; const { project } = await import("../index.mjs"); const { getApps } = await import("firebase-admin/app"); const before = getApps().length;
    await withServer(project, async (send) => { const headers = { "content-type": "application/json", authorization: "Bearer synthetic" }; let r = await send('{"action":"read"}', headers); assert.equal(r.status, 503);
      process.env.SWARM_SHARED_SYNC_ENABLED = "true"; process.env.GCLOUD_PROJECT = "swarm-sync-20261105-fw"; delete process.env.GOOGLE_CLOUD_PROJECT; delete process.env.FIREBASE_AUTH_EMULATOR_HOST; delete process.env.FIRESTORE_EMULATOR_HOST;
      r = await send(Buffer.alloc(262145, 32), headers); assert.equal(r.status, 413); process.env.GCLOUD_PROJECT = "wrong"; r = await send('{"action":"read"}', headers); assert.equal(r.status, 503);
    }); assert.equal(getApps().length, before);
  } finally { for (const k of keys) if (prev[k] === undefined) delete process.env[k]; else process.env[k] = prev[k]; }
});
