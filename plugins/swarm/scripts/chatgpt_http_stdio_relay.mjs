#!/usr/bin/env node

/**
 * Forward the documented codex-chatgpt-control backend NDJSON protocol from a
 * local stdio client to a bridge-hosted loopback HTTP server.
 *
 * This process does not authenticate to ChatGPT, inspect cookies, or call
 * provider endpoints. The HTTP server must be deliberately hosted by the
 * authenticated Chrome/bridge runtime; this relay only carries the public
 * backend protocol across the local process boundary.
 */

import { createInterface } from "node:readline";

const FRAME_LIMIT_BYTES = 8 * 1024 * 1024;
const RESPONSE_SCHEMA = "chatgpt.browser_control.backend_response.v1";

function parseArgs(argv) {
  const index = argv.indexOf("--url");
  if (index >= 0 && typeof argv[index + 1] === "string") return argv[index + 1];
  return process.env.CHATGPT_BROWSER_BACKEND_HTTP_URL || "";
}

function requestIdFromLine(line) {
  try {
    const value = JSON.parse(line);
    return typeof value?.requestId === "string" ? value.requestId : undefined;
  } catch {
    return undefined;
  }
}

function errorFrame(requestId, code, message) {
  return JSON.stringify({
    schemaVersion: RESPONSE_SCHEMA,
    ...(requestId === undefined ? {} : { requestId }),
    ok: false,
    error: { code, message, recoverable: true },
  });
}

function backendUrl(value) {
  if (!value) throw new Error("CHATGPT_BROWSER_BACKEND_HTTP_URL or --url is required");
  const parsed = new URL(value);
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("backend relay URL must use http or https");
  }
  return parsed;
}

async function forward(line, url) {
  const requestId = requestIdFromLine(line);
  if (Buffer.byteLength(line, "utf8") > FRAME_LIMIT_BYTES) {
    return errorFrame(requestId, "relay_frame_too_large", "Backend request frame exceeds the relay limit.");
  }
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/x-ndjson" },
      body: `${line}\n`,
    });
    const text = await response.text();
    if (Buffer.byteLength(text, "utf8") > FRAME_LIMIT_BYTES) {
      return errorFrame(requestId, "relay_frame_too_large", "Backend response frame exceeds the relay limit.");
    }
    const frames = text.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    if (!response.ok || frames.length === 0) {
      return errorFrame(requestId, "relay_http_error", `Bridge-hosted backend returned HTTP ${response.status}.`);
    }
    return frames.join("\n");
  } catch {
    return errorFrame(requestId, "relay_unavailable", "Bridge-hosted backend could not be reached.");
  }
}

let url;
try {
  url = backendUrl(parseArgs(process.argv.slice(2)));
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 2;
}

if (url !== undefined) {
  const input = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of input) {
    if (!line.trim()) continue;
    process.stdout.write(`${await forward(line, url)}\n`);
  }
}
