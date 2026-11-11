import assert from "node:assert/strict";
import { test } from "node:test";
import { createAuthFlow } from "./auth.mjs";
import { createServer } from "node:http";
import { once } from "node:events";
import { createAccountHttp } from "../server/account-http.mjs";

const config = { projectId: "swarm-sync-20261105-fw", appId: "1:765846931749:web:0cc27254c87721b613b2cc", authDomain: "swarm-sync-20261105-fw.firebaseapp.com", apiKey: "synthetic-public" };
const tick = () => new Promise((resolve) => setImmediate(resolve));

test("sets persistence first, restores a session and only signs in on user action", async () => {
  const events = [], states = [], calls = []; let observer, popups = 0;
  const user = { async getIdToken() { return "synthetic-token"; } };
  const authSdk = { browserLocalPersistence: {}, getAuth() { events.push("auth"); return {}; }, async setPersistence() { events.push("persistence"); }, onAuthStateChanged(_auth, cb) { events.push("observer"); observer = cb; cb(user); }, async signInWithPopup() { popups++; }, GoogleAuthProvider: class {} };
  const fetcher = async (path, options) => { calls.push({ path, options }); return path === "/api/config" ? Response.json(config) : Response.json({ subject: "server-user", email: "test@example.test", created: false }); };
  const flow = createAuthFlow({ appSdk: { initializeApp() { events.push("app"); return {}; } }, authSdk, fetcher, render: (state) => states.push(state) });
  await flow.start(); await tick(); assert.deepEqual(events, ["app", "auth", "persistence", "observer"]); assert.equal(states.at(-1), "signed-in"); assert.equal(popups, 0);
  assert.equal(calls[1].path, "/api/account"); assert.deepEqual(JSON.parse(calls[1].options.body), { action: "bootstrap" }); assert.equal(calls[1].options.redirect, "error");
  await flow.signIn(); assert.equal(popups, 1); observer(null); assert.equal(states.at(-1), "signed-out");
  const restarted = createAuthFlow({ appSdk: { initializeApp: () => ({}) }, authSdk, fetcher, render: (state) => states.push(state) }); await restarted.start(); await tick(); assert.equal(states.at(-1), "signed-in"); assert.equal(popups, 1);
});

test("browser bootstrap composes with the actual account adapter origin policy", async () => {
  const prior = process.env.SWARM_SHARED_SYNC_ENABLED; process.env.SWARM_SHARED_SYNC_ENABLED = "true";
  const records = new Map();
  const db = { projectId: config.projectId, doc: (path) => ({ path }), async runTransaction(fn) { return fn({ async get(ref) { return { exists: records.has(ref.path), data: () => records.get(ref.path) }; }, create(ref, value) { records.set(ref.path, value); } }); } };
  const auth = { async verifyIdToken(token) { if (token !== "synthetic-token") throw Object.assign(new Error(), { code: "auth/invalid-id-token" }); return { uid: "synthetic-user" }; }, async getUser(uid) { return { uid, email: "test@example.test", emailVerified: true, disabled: false }; } };
  const handler = createAccountHttp({ initialize: () => ({ app: { options: { projectId: config.projectId } }, getFirestore: () => db, getAuth: () => auth }) });
  const server = createServer(async (req, res) => { const chunks = []; for await (const chunk of req) chunks.push(chunk); req.rawBody = Buffer.concat(chunks); res.status = (n) => (res.statusCode = n, res); res.set = (k, v) => (res.setHeader(k, v), res); res.json = (v) => (res.setHeader("Content-Type", "application/json"), res.end(JSON.stringify(v))); res.send = (v) => res.end(v); await handler(req, res); });
  server.listen(0, "127.0.0.1"); await once(server, "listening");
  try {
    for (const [origin, expected] of [["https://swarm.botlord.ai", "signed-in"], ["https://evil.example", "unavailable"], [null, "signed-in"]]) {
      const states = [], sdk = { browserLocalPersistence: {}, getAuth: () => ({}), setPersistence: async () => {}, onAuthStateChanged(_auth, cb) { cb({ getIdToken: async () => "synthetic-token" }); }, GoogleAuthProvider: class {}, signInWithPopup: async () => {} };
      const fetcher = (path, options) => path === "/api/config" ? Promise.resolve(Response.json(config)) : fetch(`http://127.0.0.1:${server.address().port}/account`, { ...options, headers: { ...options.headers, ...(origin ? { Origin: origin } : {}) } });
      const flow = createAuthFlow({ appSdk: { initializeApp: () => ({}) }, authSdk: sdk, fetcher, render: (s) => states.push(s) }); await flow.start();
      for (let i = 0; i < 50 && states.at(-1) === "loading"; i++) await new Promise((resolve) => setTimeout(resolve, 10));
      assert.equal(states.at(-1), expected);
    }
  } finally { server.close(); await once(server, "close"); if (prior === undefined) delete process.env.SWARM_SHARED_SYNC_ENABLED; else process.env.SWARM_SHARED_SYNC_ENABLED = prior; }
});

test("missing configuration, rejected token, and stale session fail closed", async () => {
  const states = []; let callback, complete;
  const authSdk = { browserLocalPersistence: {}, getAuth: () => ({}), setPersistence: async () => {}, onAuthStateChanged(_a, cb) { callback = cb; }, signInWithPopup: async () => {}, GoogleAuthProvider: class {} };
  const flow = createAuthFlow({ appSdk: { initializeApp: () => ({}) }, authSdk, fetcher: async (path) => path === "/api/config" ? Response.json(config) : new Promise((resolve) => { complete = resolve; }), render: (s) => states.push(s) });
  await flow.start(); callback({ getIdToken: async () => "synthetic" }); await tick(); callback(null); complete(Response.json({ subject: "u", email: "e", created: false })); await tick(); assert.equal(states.at(-1), "signed-out");
  const failed = createAuthFlow({ appSdk: { initializeApp() { throw new Error("must not initialize"); } }, authSdk, fetcher: async () => new Response("", { status: 503 }), render: (s) => states.push(s) });
  await failed.start(); assert.equal(states.at(-1), "unavailable");
});

test("persistence and token errors cannot start background sign-in or bootstrap", async () => {
  for (const failure of ["persistence", "token"]) {
    let observer = 0, bootstrap = 0, popup = 0;
    const states = [];
    const authSdk = { browserLocalPersistence: {}, getAuth: () => ({}), async setPersistence() { if (failure === "persistence") throw new Error("synthetic-private"); }, onAuthStateChanged(_auth, cb) { observer++; cb({ async getIdToken() { throw new Error("synthetic-private"); } }); }, async signInWithPopup() { popup++; }, GoogleAuthProvider: class {} };
    const flow = createAuthFlow({ appSdk: { initializeApp: () => ({}) }, authSdk, fetcher: async (url) => { if (url !== "/api/config") bootstrap++; return Response.json(config); }, render: (state) => states.push(state) });
    await flow.start(); await tick();
    assert.equal(states.at(-1), "unavailable"); assert.equal(observer, failure === "persistence" ? 0 : 1); assert.equal(bootstrap, 0); assert.equal(popup, 0);
  }
});

test("click after failed persistence or observer setup never opens a popup", async () => {
  for (const failure of ["persistence", "observer-throw", "observer-error"]) {
    let popups = 0, observes = 0, bootstrap = 0;
    const states = [];
    const authSdk = { browserLocalPersistence: {}, getAuth: () => ({}), async setPersistence() { if (failure === "persistence") throw new Error("synthetic"); }, onAuthStateChanged(_auth, _next, error) { observes++; if (failure === "observer-throw") throw new Error("synthetic"); error(); }, async signInWithPopup() { popups++; }, GoogleAuthProvider: class {} };
    const flow = createAuthFlow({ appSdk: { initializeApp: () => ({}) }, authSdk, fetcher: async (url) => { if (url !== "/api/config") bootstrap++; return Response.json(config); }, render: (state, ready) => states.push({ state, ready }) });
    await flow.start(); await flow.signIn();
    assert.equal(popups, 0); assert.equal(bootstrap, 0); assert.equal(observes, failure === "persistence" ? 0 : 1); assert.deepEqual(states.at(-1), { state: "unavailable", ready: false });
  }
});
