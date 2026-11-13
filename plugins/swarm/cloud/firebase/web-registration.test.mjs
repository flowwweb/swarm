import assert from "node:assert/strict";
import { test } from "node:test";
import { matchesSwarmWebRegistration, resolveSwarmWebRegistration } from "./web-registration.mjs";

const registration = { projectId: "swarm-sync-20261105-fw", appId: "1:765846931749:web:0cc27254c87721b613b2cc", authDomain: "swarm-sync-20261105-fw.firebaseapp.com", apiKey: "public-test-key" };

test("only the trusted SWARM registration and matching client configuration pass", () => {
  assert.equal(matchesSwarmWebRegistration(registration, { ...registration }), true);
  for (const key of ["projectId", "appId", "authDomain", "apiKey"]) {
    assert.equal(matchesSwarmWebRegistration(registration, { ...registration, [key]: "wrong" }), false);
  }
  for (const key of ["projectId", "appId", "authDomain"]) assert.equal(matchesSwarmWebRegistration({ ...registration, [key]: "wrong" }, { ...registration, [key]: "wrong" }), false);
  assert.equal(matchesSwarmWebRegistration({ ...registration, apiKey: "" }, { ...registration, apiKey: "" }), false);
  assert.equal(matchesSwarmWebRegistration(null, registration), false);
});

test("server resolver validates trusted registration and suppresses failures", async () => {
  let calls = 0;
  const app = { options: { projectId: registration.projectId, credential: { async getAccessToken() { return { access_token: "synthetic-only" }; } } } };
  const fetcher = async (url, options) => { calls++; assert.equal(url, `https://firebase.googleapis.com/v1beta1/projects/-/webApps/${registration.appId}/config`); assert.equal(options.redirect, "error"); return new Response(JSON.stringify({ ...registration, ignored: "not returned" })); };
  assert.deepEqual(await resolveSwarmWebRegistration(app, registration, fetcher), registration);
  for (const key of ["projectId", "appId", "authDomain", "apiKey"]) await assert.rejects(resolveSwarmWebRegistration(app, { ...registration, [key]: "wrong" }, fetcher), { message: "UNAVAILABLE" });
  const before = calls;
  await assert.rejects(resolveSwarmWebRegistration({ options: { ...app.options, projectId: "wrong" } }, registration, fetcher), { message: "UNAVAILABLE" });
  assert.equal(calls, before);
  for (const bad of [() => { throw new Error("synthetic-secret"); }, async () => new Response("x".repeat(65537)), async () => new Response("not json"), async () => new Response("", { status: 403 })]) {
    await assert.rejects(resolveSwarmWebRegistration(app, registration, bad), { message: "UNAVAILABLE" });
  }
});
