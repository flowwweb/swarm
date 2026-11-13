import assert from "node:assert/strict";
import { test } from "node:test";
import { createWebConfigHttp } from "./web-config-http.mjs";

const config = { projectId: "swarm-sync-20261105-fw", appId: "1:765846931749:web:0cc27254c87721b613b2cc", authDomain: "swarm-sync-20261105-fw.firebaseapp.com", apiKey: "synthetic-public" };
const request = (origin) => ({ method: "GET", rawHeaders: origin ? ["Origin", origin] : [], headers: origin ? { origin } : {} });
function response() { return { statusCode: 0, headers: {}, status(n) { this.statusCode = n; return this; }, set(k, v) { this.headers[k] = v; return this; }, json(v) { this.body = v; return this; } }; }
test("config endpoint is disabled-first, project-bound and origin-restricted", async () => {
  const previous = process.env.SWARM_WEB_API_KEY; process.env.SWARM_WEB_API_KEY = config.apiKey; let calls = 0;
  const app = { options: { projectId: config.projectId, credential: { async getAccessToken() { return { access_token: "synthetic-token" }; } } } };
  const initialize = () => (calls++, { app });
  try {
    let res = response(); await createWebConfigHttp({ initialize, enabled: () => false })(request(), res); assert.equal(res.statusCode, 503); assert.equal(calls, 0);
    const handle = createWebConfigHttp({ initialize, enabled: () => true, fetcher: async () => Response.json(config) });
    res = response(); await handle(request("https://evil.example"), res); assert.equal(res.statusCode, 403); assert.equal(calls, 0);
    res = response(); await handle(request("https://swarm.botlord.ai"), res); assert.equal(res.statusCode, 200); assert.deepEqual(res.body, config); assert.equal(res.headers["Cache-Control"], "no-store");
    res = response(); await createWebConfigHttp({ initialize: () => { throw new Error("synthetic-secret"); }, enabled: () => true })(request(), res); assert.equal(res.statusCode, 503); assert.deepEqual(res.body, { error: "UNAVAILABLE" });
  } finally { if (previous === undefined) delete process.env.SWARM_WEB_API_KEY; else process.env.SWARM_WEB_API_KEY = previous; }
});
