import assert from "node:assert/strict";
import { createServer, request as httpRequest } from "node:http";
import { once } from "node:events";
import { test } from "node:test";
import { createAccountHttp } from "./account-http.mjs";

function responseFacade(res) {
  res.status = (code) => (res.statusCode = code, res);
  res.set = (key, value) => (res.setHeader(key, value), res);
  res.json = (value) => (res.setHeader("Content-Type", "application/json"), res.end(JSON.stringify(value)));
  res.send = (value) => res.end(value);
  return res;
}

async function serverFor(handler, run) {
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    req.rawBody = Buffer.concat(chunks);
    await handler(req, responseFacade(res));
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const port = server.address().port;
  const send = (body, headers = {}, method = "POST") => new Promise((resolve, reject) => {
    const r = httpRequest({ host: "127.0.0.1", port, method, path: "/account", headers }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks).toString() }));
    });
    r.on("error", reject);
    r.end(body);
  });
  try { await run(send); } finally { server.close(); await once(server, "close"); }
}

function fixture() {
  const docs = new Map();
  let lock = Promise.resolve(), initialized = 0;
  const db = { projectId: "swarm-sync-20261105-fw", doc: (path) => ({ path }), runTransaction(fn) {
    const work = lock.then(async () => {
      const pending = new Map();
      const result = await fn({ get: async ({ path }) => ({ exists: docs.has(path), data: () => structuredClone(docs.get(path)) }), create: ({ path }, value) => pending.set(path, structuredClone(value)), set: ({ path }, value) => pending.set(path, structuredClone(value)) });
      for (const [path, value] of pending) docs.set(path, value);
      return result;
    });
    lock = work.catch(() => {}); return work;
  } };
  const auth = { async verifyIdToken(token, checkRevoked) {
    assert.equal(checkRevoked, true);
    if (!["alice", "bob", "disabled", "mismatch", "old"].includes(token)) throw Object.assign(new Error("private fixture error"), { code: "auth/id-token-revoked" });
    return { uid: token === "old" ? "alice" : token, auth_time: Math.floor(Date.now() / 1000) - (token === "old" ? 301 : 1) };
  }, async getUser(uid) { return { uid: uid === "mismatch" ? "other" : uid, disabled: uid === "disabled", emailVerified: true, email: uid + "@example.test" }; } };
  return { docs, db, get initialized() { return initialized; }, initialize: () => (initialized++, { app: { options: { projectId: "swarm-sync-20261105-fw" } }, getFirestore: () => db, getAuth: () => auth }) };
}

test("real loopback HTTP composes existing factory and preserves identity, scope and replay", async () => {
  const previous = process.env.SWARM_SHARED_SYNC_ENABLED; process.env.SWARM_SHARED_SYNC_ENABLED = "true";
  const f = fixture(), json = { "content-type": "application/json", authorization: "Bearer alice" };
  const encode = (value) => JSON.stringify(value);
  try {
    await serverFor(createAccountHttp({ initialize: f.initialize }), async (send) => {
      let r = await send(encode({ action: "bootstrap" }), json); assert.equal(r.status, 200); assert.equal(JSON.parse(r.body).subject, "alice"); assert.equal(r.headers["cache-control"], "no-store");
      const count = f.docs.size;
      for (const token of ["revoked", "disabled", "mismatch"]) { r = await send(encode({ action: "bootstrap" }), { ...json, authorization: "Bearer " + token }); assert.equal(r.status, 401); }
      r = await send(encode({ action: "bootstrap", subject: "bob" }), json); assert.equal(r.status, 400); assert.equal(f.docs.size, count);
      r = await send(encode({ action: "enroll", operationId: "O".repeat(22) }), { ...json, authorization: "Bearer old" }); assert.equal(r.status, 403);
      const issued = JSON.parse((await send(encode({ action: "enroll", operationId: "O".repeat(22) }), json)).body);
      assert.equal(issued.status, "ISSUED");
      const replay = JSON.parse((await send(encode({ action: "enroll", operationId: "O".repeat(22) }), json)).body);
      assert.deepEqual(replay, { deviceId: issued.deviceId, status: "DELIVERY_UNCONFIRMED" });
      assert.equal(JSON.stringify([...f.docs.values()]).includes(issued.deviceSecret), false);
      r = await send(encode({ action: "revoke", deviceId: issued.deviceId }), json); assert.equal(r.status, 200);
      r = await send(encode({ action: "enroll", operationId: "O".repeat(22) }), json); assert.equal(r.status, 401);
    });
  } finally { if (previous === undefined) delete process.env.SWARM_SHARED_SYNC_ENABLED; else process.env.SWARM_SHARED_SYNC_ENABLED = previous; }
});

test("origin, request bounds and errors fail closed without logging fixture secrets", async () => {
  const previous = process.env.SWARM_SHARED_SYNC_ENABLED; process.env.SWARM_SHARED_SYNC_ENABLED = "true";
  const f = fixture(), json = { "content-type": "application/json", authorization: "Bearer alice" };
  try { await serverFor(createAccountHttp({ initialize: f.initialize }), async (send) => {
    const boot = JSON.stringify({ action: "bootstrap" });
    let r = await send(boot, { ...json, origin: "https://evil.example" }); assert.equal(r.status, 403); assert.equal(f.initialized, 0);
    r = await send(boot, { ...json, origin: "https://swarm.botlord.ai" }); assert.equal(r.status, 200); assert.equal(r.headers["access-control-allow-origin"], "https://swarm.botlord.ai");
    r = await send(boot, { ...json, authorization: "Bearer revoked" }); assert.equal(r.status, 401); assert.equal(r.headers["access-control-allow-origin"], undefined);
    r = await send("", { origin: "https://swarm.botlord.ai", "access-control-request-method": "POST", "access-control-request-headers": "authorization, content-type" }, "OPTIONS"); assert.equal(r.status, 204);
    r = await send("", json, "GET"); assert.equal(r.status, 405);
    r = await send(boot, { ...json, "content-encoding": "gzip" }); assert.equal(r.status, 400);
    r = await send(Buffer.alloc(16385, 32), json); assert.equal(r.status, 413);
    r = await send(Buffer.concat([Buffer.from(boot), Buffer.alloc(16384 - Buffer.byteLength(boot), 32)]), json); assert.equal(r.status, 200);
    r = await send(Buffer.from([0xff]), json); assert.equal(r.status, 400);
    r = await send("{", json); assert.equal(r.status, 400);
    r = await send(boot, { "content-type": "text/plain", authorization: "Bearer alice" }); assert.equal(r.status, 400);
    r = await send(boot, { "content-type": "application/json" }); assert.equal(r.status, 401);
    r = await send(boot, ["Content-Type", "application/json", "Authorization", "Bearer alice", "Authorization", "Bearer bob"]); assert.equal(r.status, 400);
  }); } finally { if (previous === undefined) delete process.env.SWARM_SHARED_SYNC_ENABLED; else process.env.SWARM_SHARED_SYNC_ENABLED = previous; }
});

test("disabled and invalid server initialization never expose errors", async () => {
  const previous = process.env.SWARM_SHARED_SYNC_ENABLED;
  const boot = JSON.stringify({ action: "bootstrap" }), headers = { "content-type": "application/json", authorization: "Bearer alice" };
  try {
    delete process.env.SWARM_SHARED_SYNC_ENABLED;
    await serverFor(createAccountHttp({ initialize: () => { throw new Error("fixture-secret"); } }), async (send) => { const r = await send(boot, headers); assert.equal(r.status, 503); assert.equal(r.body.includes("fixture-secret"), false); });
    process.env.SWARM_SHARED_SYNC_ENABLED = "true";
    for (const initialize of [() => { throw new Error("fixture-secret"); }, () => ({ app: { options: { projectId: "wrong" } }, getAuth() {}, getFirestore() {} }), () => ({ app: { options: { projectId: "swarm-sync-20261105-fw" } }, getAuth() {}, getFirestore: () => ({ projectId: "wrong" }) })]) {
      await serverFor(createAccountHttp({ initialize }), async (send) => { const r = await send(boot, headers); assert.equal(r.status, 503); assert.equal(r.body, '{"error":"UNAVAILABLE"}'); });
    }
    for (const key of ["FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST"]) {
      const before = process.env[key]; process.env[key] = "127.0.0.1:9999";
      try { await serverFor(createAccountHttp({ initialize: fixture().initialize }), async (send) => { const r = await send(boot, headers); assert.equal(r.status, 503); }); }
      finally { if (before === undefined) delete process.env[key]; else process.env[key] = before; }
    }
  } finally { if (previous === undefined) delete process.env.SWARM_SHARED_SYNC_ENABLED; else process.env.SWARM_SHARED_SYNC_ENABLED = previous; }
});

test("actual Functions SDK export returns disabled without creating an Admin app", async () => {
  const previous = process.env.SWARM_SHARED_SYNC_ENABLED;
  delete process.env.SWARM_SHARED_SYNC_ENABLED;
  try {
    const { getApps } = await import("firebase-admin/app");
    const { account } = await import("../index.mjs");
    const before = getApps().length;
    await serverFor(account, async (send) => {
      const r = await send(JSON.stringify({ action: "bootstrap" }), { "content-type": "application/json", authorization: "Bearer synthetic" });
      assert.equal(r.status, 503);
      assert.equal(r.body, '{"error":"UNAVAILABLE"}');
    });
    assert.equal(getApps().length, before);
  } finally { if (previous === undefined) delete process.env.SWARM_SHARED_SYNC_ENABLED; else process.env.SWARM_SHARED_SYNC_ENABLED = previous; }
});

test("actual Functions SDK export rejects wrong project and emulator overrides before Admin initialization", async () => {
  const keys = ["SWARM_SHARED_SYNC_ENABLED", "GCLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT", "FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST"];
  const previous = Object.fromEntries(keys.map((key) => [key, process.env[key]]));
  try {
    process.env.SWARM_SHARED_SYNC_ENABLED = "true";
    delete process.env.GOOGLE_CLOUD_PROJECT;
    delete process.env.FIREBASE_AUTH_EMULATOR_HOST;
    delete process.env.FIRESTORE_EMULATOR_HOST;
    const { getApps } = await import("firebase-admin/app");
    const { account } = await import("../index.mjs");
    const before = getApps().length;
    await serverFor(account, async (send) => {
      const headers = { "content-type": "application/json", authorization: "Bearer synthetic" };
      const body = JSON.stringify({ action: "bootstrap" });
      for (const [project, override] of [["wrong", null], ["swarm-sync-20261105-fw", "FIREBASE_AUTH_EMULATOR_HOST"], ["swarm-sync-20261105-fw", "FIRESTORE_EMULATOR_HOST"]]) {
        process.env.GCLOUD_PROJECT = project;
        if (override) process.env[override] = "127.0.0.1:9999";
        const r = await send(body, headers); assert.equal(r.status, 503); assert.equal(r.body, '{"error":"UNAVAILABLE"}');
        if (override) delete process.env[override];
      }
    });
    assert.equal(getApps().length, before);
  } finally { for (const key of keys) if (previous[key] === undefined) delete process.env[key]; else process.env[key] = previous[key]; }
});
