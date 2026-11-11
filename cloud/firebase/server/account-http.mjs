import { createSwarmAccountHandler } from "./account-factory.mjs";
import { createSwarmProjectHandler } from "../project/project-factory.mjs";

const originAllowed = "https://swarm.botlord.ai";
// Dependencies are owned by the server, never selected from a request.
function createHttp({ initialize, enabled = () => process.env.SWARM_SHARED_SYNC_ENABLED === "true" }, createHandler, maxBody) {
  return async (req, res) => {
    const finish = (status, error) => res.status(status).set("Cache-Control", "no-store").json({ error });
    try {
      const counts = {};
      for (let i = 0; i < req.rawHeaders.length; i += 2) {
        const key = req.rawHeaders[i].toLowerCase();
        counts[key] = (counts[key] ?? 0) + 1;
      }
      if (["origin", "authorization", "content-type", "content-encoding", "content-length"].some((key) => counts[key] > 1)) return finish(400, "INVALID_REQUEST");
      const origin = req.headers.origin;
      if (origin !== undefined && origin !== originAllowed) return finish(403, "FORBIDDEN");
      if (origin === originAllowed) res.set("Access-Control-Allow-Origin", originAllowed).set("Vary", "Origin");
      if (!enabled()) return finish(503, "UNAVAILABLE");
      if (req.method === "OPTIONS" && origin === originAllowed) {
        if (req.headers["access-control-request-method"] !== "POST" || !/^(?:authorization|content-type)(?:\s*,\s*(?:authorization|content-type))*$/i.test(req.headers["access-control-request-headers"] ?? "")) return finish(400, "INVALID_REQUEST");
        return res.status(204).set("Cache-Control", "no-store").set("Access-Control-Allow-Methods", "POST").set("Access-Control-Allow-Headers", "Authorization, Content-Type").end();
      }
      if (req.method !== "POST") return finish(405, "METHOD_NOT_ALLOWED");
      if (req.headers["content-encoding"] && req.headers["content-encoding"].toLowerCase() !== "identity") return finish(400, "INVALID_REQUEST");
      if (!Buffer.isBuffer(req.rawBody) || req.rawBody.length === 0) return finish(400, "INVALID_REQUEST");
      if (req.rawBody.length > maxBody) return finish(413, "INVALID_REQUEST");
      if (req.headers["content-length"] !== undefined && (!/^\d+$/.test(req.headers["content-length"]) || Number(req.headers["content-length"]) !== req.rawBody.length)) return finish(400, "INVALID_REQUEST");
      const handler = createHandler(await initialize());
      const headers = new Headers();
      for (const key of ["authorization", "content-type"]) if (typeof req.headers[key] === "string") headers.set(key, req.headers[key]);
      const response = await handler(new Request("https://internal.invalid/account", { method: "POST", headers, body: req.rawBody }));
      res.status(response.status).set("Cache-Control", "no-store").set("Content-Type", "application/json");
      return res.send(Buffer.from(await response.arrayBuffer()));
    } catch {
      return finish(503, "UNAVAILABLE");
    }
  };
}

export function createAccountHttp(options) { return createHttp(options, createSwarmAccountHandler, 16384); }
export function createProjectHttp(options) { return createHttp(options, createSwarmProjectHandler, 262144); }
