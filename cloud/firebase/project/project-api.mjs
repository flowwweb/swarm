// Disconnected handler: service and its authentication adapters are server-owned.
export function createProjectApi({ projectService }) {
  return async function handle(request) {
    const headers = { "Cache-Control": "no-store" };
    const reply = (body, status) => Response.json(body, { status, headers });
    if (request.method !== "POST") return reply({ error: "METHOD_NOT_ALLOWED" }, 405);
    const token = /^Bearer ([^\s]+)$/.exec(request.headers.get("authorization") ?? "")?.[1];
    if (!token) return reply({ error: "UNAUTHORIZED" }, 401);
    if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(request.headers.get("content-type") ?? "") || !request.body) return reply({ error: "INVALID_REQUEST" }, 400);
    try {
      const reader = request.body.getReader();
      const decoder = new TextDecoder("utf-8", { fatal: true });
      let body = "", bytes = 0;
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        bytes += value.byteLength;
        if (bytes > 262144) { await reader.cancel(); return reply({ error: "INVALID_REQUEST" }, 400); }
        body += decoder.decode(value, { stream: true });
      }
      const input = JSON.parse(body + decoder.decode());
      if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("INVALID_REQUEST");
      const common = ["action", "deviceId", "deviceSecret", "workspaceId"];
      const actionFields = { create: ["operationId"], read: ["projectId"], mutate: ["projectId", "operation"], readMembers: ["projectId"], setMember: ["projectId", "subject", "role", "expectedRevision"] };
      if (!Object.hasOwn(actionFields, input.action)) throw new Error("INVALID_REQUEST");
      const fields = [...common, ...actionFields[input.action]];
      if (Object.keys(input).length !== fields.length || fields.some((key) => !Object.hasOwn(input, key))) throw new Error("INVALID_REQUEST");
      const args = [token, input.deviceId, input.deviceSecret, input.workspaceId];
      let result;
      if (input.action === "create") result = await projectService.create(...args, input.operationId);
      else if (input.action === "read") result = await projectService.read(...args, input.projectId);
      else if (input.action === "readMembers") result = await projectService.readMembers(...args, input.projectId);
      else if (input.action === "setMember") result = await projectService.setMember(...args, input.projectId, input.subject, input.role, input.expectedRevision);
      else {
        const op = input.operation;
        if (!op || typeof op !== "object" || Array.isArray(op)) throw new Error("INVALID_REQUEST");
        const opFields = ["projectId", "deviceId", "id", "expectedRevision", "kind", ...(["put", "ticket-put"].includes(op.kind) ? ["value"] : [])];
        if (Object.keys(op).length !== opFields.length || opFields.some((key) => !Object.hasOwn(op, key))) throw new Error("INVALID_REQUEST");
        result = await projectService.mutate(...args, input.projectId, op);
      }
      return reply(result, 200);
    } catch (error) {
      const code = error instanceof Error ? error.message : "";
      if (code === "FORBIDDEN") return reply({ error: "FORBIDDEN" }, 403);
      if (["INVALID_REQUEST", "INVALID_OPERATION"].includes(code) || error instanceof SyntaxError || error instanceof TypeError) return reply({ error: "INVALID_REQUEST" }, 400);
      if (["OPERATION_ID_REUSED", "PROJECT_CAPACITY_REACHED", "LAST_OWNER", "PROJECT_DELETED"].includes(code)) return reply({ error: code }, 409);
      return reply({ error: "UNAVAILABLE" }, 503);
    }
  };
}
