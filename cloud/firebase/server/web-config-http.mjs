import { resolveSwarmWebRegistration } from "../web-registration.mjs";

// Server-owned adapters are never selected by the HTTP request.
export function createWebConfigHttp({ initialize, enabled = () => process.env.SWARM_SHARED_SYNC_ENABLED === "true", fetcher = fetch }) {
  return async (req, res) => {
    const reply = (status, body) => res.status(status).set("Cache-Control", "no-store").json(body);
    try {
      const origins = req.rawHeaders.filter((_, i) => i % 2 === 0 && req.rawHeaders[i].toLowerCase() === "origin");
      if (origins.length > 1 || (req.headers.origin && req.headers.origin !== "https://swarm.botlord.ai")) return reply(403, { error: "FORBIDDEN" });
      if (!enabled()) return reply(503, { error: "UNAVAILABLE" });
      if (req.method !== "GET") return reply(405, { error: "METHOD_NOT_ALLOWED" });
      const { app } = await initialize();
      const configured = { projectId: "swarm-sync-20261105-fw", appId: "1:765846931749:web:0cc27254c87721b613b2cc", authDomain: "swarm-sync-20261105-fw.firebaseapp.com", apiKey: process.env.SWARM_WEB_API_KEY };
      return reply(200, await resolveSwarmWebRegistration(app, configured, fetcher));
    } catch {
      return reply(503, { error: "UNAVAILABLE" });
    }
  };
}
