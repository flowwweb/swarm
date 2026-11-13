import assert from "node:assert/strict";
import { test } from "node:test";
import { createSwarmAccountHandler } from "./account-factory.mjs";

test("new project is required and emulator or disabled states fail before creating adapters", () => {
  const previous = { ...process.env };
  let adapterCalls = 0;
  const make = (projectId) => createSwarmAccountHandler({ app: { options: { projectId } }, getAuth: () => { adapterCalls++; return {}; }, getFirestore: () => { adapterCalls++; return { projectId: "swarm-sync-20261105-fw" }; } });
  try {
    delete process.env.SWARM_SHARED_SYNC_ENABLED;
    assert.throws(() => make("swarm-sync-20261105-fw"), /SWARM_FIREBASE_PROJECT_UNVERIFIED/);
    process.env.SWARM_SHARED_SYNC_ENABLED = "true";
    assert.throws(() => make("flow-4289"), /SWARM_FIREBASE_PROJECT_UNVERIFIED/);
    for (const key of ["FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST"]) {
      process.env[key] = "127.0.0.1:9999";
      assert.throws(() => make("swarm-sync-20261105-fw"), /SWARM_FIREBASE_PROJECT_UNVERIFIED/);
      delete process.env[key];
    }
    assert.equal(adapterCalls, 0);
    const options = { app: { options: { projectId: "swarm-sync-20261105-fw" } }, getAuth: () => { throw new Error("unexpected auth"); } };
    for (const getFirestore of [() => ({ projectId: "flow-4289" }), () => null, () => ({}), () => ({ get projectId() { throw new Error("private"); } })]) {
      assert.throws(() => createSwarmAccountHandler({ ...options, getFirestore }), /^Error: SWARM_FIREBASE_PROJECT_UNVERIFIED$/);
    }
    assert.equal(typeof make("swarm-sync-20261105-fw"), "function");
    assert.equal(adapterCalls, 2);
  } finally {
    for (const key of ["SWARM_SHARED_SYNC_ENABLED", "FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST"]) {
      if (previous[key] === undefined) delete process.env[key]; else process.env[key] = previous[key];
    }
  }
});

test("account and device handler rejects wrong identities and issues a secret once", async () => {
  const before = process.env.SWARM_SHARED_SYNC_ENABLED;
  process.env.SWARM_SHARED_SYNC_ENABLED = "true";
  const docs = new Map();
  let lock = Promise.resolve();
  const db = {
    projectId: "swarm-sync-20261105-fw",
    doc: (path) => ({ path }),
    runTransaction(fn) {
      const work = lock.then(async () => {
        const pending = new Map();
        const tx = {
          get: async ({ path }) => ({ exists: docs.has(path), data: () => structuredClone(docs.get(path)) }),
          create: ({ path }, value) => pending.set(path, structuredClone(value)),
          set: ({ path }, value) => pending.set(path, structuredClone(value)),
        };
        const result = await fn(tx);
        for (const [path, value] of pending) docs.set(path, value);
        return result;
      });
      lock = work.catch(() => {});
      return work;
    },
  };
  const auth = {
    async verifyIdToken(token, checkRevoked) {
      assert.equal(checkRevoked, true);
      if (token === "revoked") throw Object.assign(new Error("revoked"), { code: "auth/id-token-revoked" });
      if (!["alice", "bob", "old", "unverified", "disabled", "mismatch"].includes(token)) throw Object.assign(new Error("invalid"), { code: "auth/invalid-id-token" });
      return { uid: token === "old" ? "alice" : token, auth_time: Math.floor(Date.now() / 1000) - (token === "old" ? 301 : 1) };
    },
    async getUser(uid) { return { uid: uid === "mismatch" ? "other" : uid, disabled: uid === "disabled", emailVerified: uid !== "unverified", email: `${uid}@example.test` }; },
  };
  try {
    const handler = createSwarmAccountHandler({ app: { options: { projectId: "swarm-sync-20261105-fw" } }, getAuth: () => auth, getFirestore: () => db });
    const send = (token, body) => handler(new Request("https://example.test/account", { method: "POST", headers: { "content-type": "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(body) }));
    assert.equal((await send(null, { action: "bootstrap" })).status, 401);
    for (const token of ["invalid", "revoked", "disabled", "mismatch"]) {
      const rejected = await send(token, { action: "bootstrap" });
      assert.equal(rejected.status, 401);
      assert.deepEqual(await rejected.json(), { error: "UNAUTHORIZED" });
    }
    assert.equal((await handler(new Request("https://example.test/account", { method: "POST", headers: { authorization: "Bearer alice", "content-type": "text/plain" }, body: '{}' }))).status, 400);
    assert.equal((await send("unverified", { action: "bootstrap" })).status, 401);
    assert.equal((await send("alice", { action: "bootstrap", extra: true })).status, 400);
    assert.equal((await send("alice", { action: "bootstrap", subject: "bob" })).status, 400);
    assert.equal(docs.size, 0, "rejected identity and caller-supplied subject must not create an account");
    const bootstrap = await send("alice", { action: "bootstrap" });
    assert.equal(bootstrap.status, 200);
    assert.equal(bootstrap.headers.get("cache-control"), "no-store");
    assert.deepEqual(await bootstrap.json(), { subject: "alice", email: "alice@example.test", created: true });
    assert.deepEqual(await (await send("alice", { action: "bootstrap" })).json(), { subject: "alice", email: "alice@example.test", created: false });
    assert.equal((await send("bob", { action: "bootstrap" })).status, 200);
    const operationId = "O".repeat(22);
    assert.equal((await send("old", { action: "enroll", operationId })).status, 403);
    const [first, second] = await Promise.all([send("alice", { action: "enroll", operationId }), send("alice", { action: "enroll", operationId })]);
    const issued = await first.json(), replay = await second.json();
    assert.equal(first.headers.get("cache-control"), "no-store");
    assert.equal(issued.status, "ISSUED");
    assert.match(issued.deviceSecret, /^[A-Za-z0-9_-]{43}$/u);
    assert.deepEqual(replay, { deviceId: issued.deviceId, status: "DELIVERY_UNCONFIRMED" });
    assert.equal(JSON.stringify([...docs.values()]).includes(issued.deviceSecret), false);
    const bobFirst = await send("bob", { action: "enroll", operationId });
    assert.equal(bobFirst.status, 200);
    const bobIssued = await bobFirst.json();
    assert.equal(bobIssued.status, "ISSUED");
    assert.notEqual(bobIssued.deviceId, issued.deviceId);
    assert.deepEqual(await (await send("bob", { action: "enroll", operationId })).json(), { deviceId: bobIssued.deviceId, status: "DELIVERY_UNCONFIRMED" });
    assert.equal((await send("bob", { action: "revoke", deviceId: issued.deviceId })).status, 401);
    assert.equal((await send("alice", { action: "revoke", deviceId: issued.deviceId, extra: true })).status, 400);
    assert.equal((await send("alice", { action: "revoke", deviceId: issued.deviceId })).status, 200);
    assert.equal((await send("alice", { action: "enroll", operationId })).status, 401);
  } finally {
    if (before === undefined) delete process.env.SWARM_SHARED_SYNC_ENABLED; else process.env.SWARM_SHARED_SYNC_ENABLED = before;
  }
});
