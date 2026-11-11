import test from "node:test";
import assert from "node:assert/strict";
import { createSwarmProjectHandler } from "./project-factory.mjs";

test("project factory binds the dedicated project and rejects emulator overrides before adapters", async () => {
  const prior = { ...process.env };
  const called = [];
  const options = { app: { options: { projectId: "swarm-sync-20261105-fw" } }, getAuth: () => (called.push("auth"), {}), getFirestore: () => (called.push("db"), { projectId: "swarm-sync-20261105-fw" }) };
  try {
    delete process.env.FIREBASE_AUTH_EMULATOR_HOST;
    delete process.env.FIRESTORE_EMULATOR_HOST;
    delete process.env.SWARM_SHARED_SYNC_ENABLED;
    assert.throws(() => createSwarmProjectHandler(options), /SWARM_FIREBASE_PROJECT_UNVERIFIED/);
    process.env.SWARM_SHARED_SYNC_ENABLED = "true";
    assert.throws(() => createSwarmProjectHandler({ ...options, app: { options: { projectId: "flow-4289" } } }), /SWARM_FIREBASE_PROJECT_UNVERIFIED/);
    process.env.FIREBASE_AUTH_EMULATOR_HOST = "127.0.0.1:19099";
    assert.throws(() => createSwarmProjectHandler(options), /SWARM_FIREBASE_PROJECT_UNVERIFIED/);
    delete process.env.FIREBASE_AUTH_EMULATOR_HOST;
    process.env.FIRESTORE_EMULATOR_HOST = "127.0.0.1:19081";
    assert.throws(() => createSwarmProjectHandler(options), /SWARM_FIREBASE_PROJECT_UNVERIFIED/);
    assert.deepEqual(called, []);
    delete process.env.FIRESTORE_EMULATOR_HOST;
    assert.throws(() => createSwarmProjectHandler({ ...options, getFirestore: () => ({ projectId: "flow-4289" }) }), /SWARM_FIREBASE_PROJECT_UNVERIFIED/);
    assert.throws(() => createSwarmProjectHandler({ ...options, getFirestore: () => ({ get projectId() { throw new Error("private adapter error"); } }) }), /^Error: SWARM_FIREBASE_PROJECT_UNVERIFIED$/);
    assert.deepEqual(called, []);
    const handle = createSwarmProjectHandler(options);
    assert.deepEqual(called, ["db", "auth"]);
    assert.equal((await handle(new Request("http://localhost/project", { method:"POST" }))).status, 401);
  } finally {
    for (const key of ["SWARM_SHARED_SYNC_ENABLED", "FIREBASE_AUTH_EMULATOR_HOST", "FIRESTORE_EMULATOR_HOST"]) {
      if (prior[key] === undefined) delete process.env[key]; else process.env[key] = prior[key];
    }
  }
});
