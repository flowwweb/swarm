// This handler is disconnected; adapters are server-owned, not supplied by a request.
export function createAccountApi({ accountService, deviceService }) {
  return async function handle(request) {
    const headers = { "Cache-Control": "no-store" };
    if (request.method !== "POST") return Response.json({ error: "METHOD_NOT_ALLOWED" }, { status: 405, headers });
    const match = /^Bearer ([^\s]+)$/.exec(request.headers.get("authorization") ?? "");
    if (!match) return Response.json({ error: "UNAUTHORIZED" }, { status: 401, headers });
    if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(request.headers.get("content-type") ?? "") || !request.body) return Response.json({ error: "INVALID_REQUEST" }, { status: 400, headers });
    try {
      const reader = request.body.getReader();
      const decoder = new TextDecoder("utf-8", { fatal: true });
      let size = 0;
      let body = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 16384) { await reader.cancel(); return Response.json({ error: "INVALID_REQUEST" }, { status: 400, headers }); }
        body += decoder.decode(value, { stream: true });
      }
      body += decoder.decode();
      const input = JSON.parse(body);
      if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("INVALID_REQUEST");
      let result;
      if (input.action === "bootstrap") {
        if (Object.keys(input).length !== 1) throw new Error("INVALID_REQUEST");
        result = await accountService.bootstrap(match[1]);
      }
      else if (input.action === "enroll") {
        if (Object.keys(input).some((key) => !["action", "operationId"].includes(key))) throw new Error("INVALID_REQUEST");
        result = await deviceService.enroll(match[1], input.operationId);
      }
      else if (input.action === "revoke") {
        if (Object.keys(input).length !== 2 || !Object.hasOwn(input, "deviceId")) throw new Error("INVALID_REQUEST");
        result = await deviceService.revoke(match[1], input.deviceId);
      }
      else if (input.action === "listDevices") {
        if (Object.keys(input).some((key) => !["action", "cursor"].includes(key))) throw new Error("INVALID_REQUEST");
        result = await deviceService.list(match[1], input.cursor);
      }
      else throw new Error("INVALID_REQUEST");
      return Response.json(result, { status: 200, headers });
    } catch (error) {
      const code = error instanceof Error ? error.message : "";
      if (code === "FORBIDDEN") return Response.json({ error: "UNAUTHORIZED" }, { status: 401, headers });
      if (code === "REAUTH_REQUIRED") return Response.json({ error: "REAUTH_REQUIRED" }, { status: 403, headers });
      if (["INVALID_REQUEST", "DEVICE_ID_REUSED"].includes(code) || error instanceof SyntaxError || error instanceof TypeError) {
        return Response.json({ error: "INVALID_REQUEST" }, { status: 400, headers });
      }
      return Response.json({ error: "UNAVAILABLE" }, { status: 503, headers });
    }
  };
}
