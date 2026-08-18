import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import assert from "node:assert/strict";

const script = join(dirname(fileURLToPath(import.meta.url)), "chatgpt_http_stdio_relay.mjs");
const server = createServer(async (request, response) => {
  let body = "";
  for await (const chunk of request) body += chunk;
  const value = JSON.parse(body);
  response.setHeader("content-type", "application/x-ndjson");
  response.end(JSON.stringify({
    schemaVersion: "chatgpt.browser_control.backend_response.v1",
    requestId: value.requestId,
    ok: true,
    result: { echoedCommand: value.command },
  }));
});
server.listen(0, "127.0.0.1");
await once(server, "listening");
const { port } = server.address();

const child = spawn(process.execPath, [script], {
  stdio: ["pipe", "pipe", "pipe"],
  env: { ...process.env, CHATGPT_BROWSER_BACKEND_HTTP_URL: `http://127.0.0.1:${port}` },
});
let stdout = "";
let stderr = "";
child.stdout.on("data", (chunk) => { stdout += chunk; });
child.stderr.on("data", (chunk) => { stderr += chunk; });
child.stdin.end(JSON.stringify({
  schemaVersion: "chatgpt.browser_control.backend_request.v1",
  requestId: "relay-test-1",
  command: "backend.health",
  payload: {},
}) + "\n");
const [result] = await once(child, "close");
server.close();
assert.equal(result, 0, stderr);
const frame = JSON.parse(stdout.trim());
assert.equal(frame.ok, true);
assert.equal(frame.requestId, "relay-test-1");
assert.equal(frame.result.echoedCommand, "backend.health");
console.log("chatgpt_http_stdio_relay: PASS");
