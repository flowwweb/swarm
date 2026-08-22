import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const testsRoot = path.dirname(fileURLToPath(import.meta.url));
const consoleRoot = path.resolve(testsRoot, "..");
const staticRoot = path.join(consoleRoot, "static");
const fixture = JSON.parse(fs.readFileSync(path.join(testsRoot, "fixtures", "console-ui.json"), "utf8"));
const css = fs.readFileSync(path.join(staticRoot, "styles.css"), "utf8");
const app = fs.readFileSync(path.join(staticRoot, "app.js"), "utf8");
const indexHtml = fs.readFileSync(path.join(staticRoot, "index.html"), "utf8");
const documentHtml = indexHtml
  .replace("<head>", '<head><base href="http://swarm.test/">');

for (const label of ["Current work", "Recent images", "Tokens · 24h", "Completed", "Where changes apply", "Manage skills", "Advanced settings"]) {
  assert.match(indexHtml + app, new RegExp(label));
}
assert.match(app, /\/api\/usage-history\?/);
assert.match(app, /hours: "24"/);
assert.match(app, /source\.status === 'no_data'/);
assert.match(app, /Partial coverage/);
assert.match(app, /Complete coverage/);
assert.match(app, /source\.coverage\?\.observed_threads/);
assert.match(indexHtml, /id="usage-range"/);
assert.match(indexHtml, /id="overview-health-state"/);
assert.match(app, /function renderOverviewHealth\(nodes\)/);
assert.match(app, /Needs attention/);
assert.match(app, /function attentionStatus\(node\)/);
assert.match(app, /\[node\?\.status, node\?\.eta\?\.status\]/);
assert.match(app, /tasks\.find\(needsAttention\)/);
assert.match(app, /const stalled = needsAttention\(current\)/);
assert.match(app, /project_id: state\.projectId/);
assert.match(app, /ctrl_id: state\.ctrlId/);
assert.match(app, /setInterval\(reportPresence, 60_000\)/);
assert.match(app, /async function refreshMonitoring/);
assert.doesNotMatch(app, /15_000/);
assert.match(app, /data-overview-subagents/);
assert.match(app, /subagentDescendants\(card\.ctrlId, tree\)/);
assert.match(app, /params\.set\("project_id", state\.projectId\)/);
assert.doesNotMatch(app, /params\.set\("task_id", state\.ctrlId\)/);
assert.match(app, /\["blocked", "at_risk", "stalled", "critical"\]/);
assert.match(app, /const nodes = scopedNodes\(\)\.filter\(\(node\) => !isSubagent\(node\)\);/);
assert.doesNotMatch(app, /Number\(project\.active_threads \?\? project\.active\) > 0/);
assert.match(app, /function configEditable\(key\)/);
assert.match(app, /id="settings-scope"/);
assert.match(app, /Custom settings/);
assert.match(app, /Inherits global defaults/);
assert.match(app, /settingToggle\('execution\.usage_saver'/);
assert.match(app, /settingToggle\('console\.open_on_start'/);
assert.match(app, /settingToggle\('role_icons\.enabled'/);
assert.match(app, /settingSelect\('boost\.spark_reasoning'/);
assert.match(app, /function forecastSummary\(node\)/);
assert.match(app, /baseline_eta_end_ms/);
assert.match(app, /delta_from_baseline_ms/);
assert.match(app, /last_material_heartbeat_at_ms/);
assert.match(app, /skillsError/);
assert.match(app, /Try again to refresh this scope/);
assert.match(app, /refreshSkills\(\)\]\)\.then\(renderAllViews\)/);
assert.match(app, /latest\.freshness \|\| state\.diagnostics\?\.freshness/);
assert.match(app, /availability\.unavailable/);
assert.match(app, /No independent metrics available/);
assert.doesNotMatch(app, /\["Health", humanize\(latest\.health_state/);
for (const forbidden of ["localhost", "hidden usage", "developer instructions", "prompts", "tools", "credentials"]) {
  assert.equal((indexHtml + app).toLowerCase().includes(forbidden), false, `forbidden copy: ${forbidden}`);
}

function response(body) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

function scopedFixture() {
  const overview = structuredClone(fixture.overview);
  overview.nodes.push(
    { id: "nested-ctrl", role: "ctrl", artifact: "Evidence review", project_id: "project:fixture", project: "swarm", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["nested-ctrl"] },
    { id: "nested-task", role: "doer", role_label: "TASK", artifact: "Review screenshots", project_id: "project:fixture", project: "swarm", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["nested-ctrl"] },
    { id: "branch-ctrl", role: "ctrl", artifact: "Ship integrations", project_id: "project:branch", project: "Flowwweb", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["branch-ctrl"] },
    { id: "branch-task", role: "doer", role_label: "TASK", artifact: "Confirm webhooks", project_id: "project:branch", project: "Flowwweb", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["branch-ctrl"] },
    { id: "standalone-ctrl", role: "ctrl", artifact: "Resolve customer export", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["standalone-ctrl"] },
    { id: "standalone-task", role: "doer", role_label: "TASK", artifact: "Inspect export evidence", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["standalone-ctrl"] },
  );
  overview.projects.push({ id: "project:branch", name: "Flowwweb", nodes: 2, tokens: 0, active: 2 });
  overview.projects.push({ id: "project:waiting", name: "Unassigned planning", nodes: 0, tokens: 0, active: 0 });
  overview.projects.push({ id: "project:browser", name: "https-mail-google-com-mail-u", nodes: 0, tokens: 0, active: 1 });
  return overview;
}

async function mount(page, overview) {
  const runtimeErrors = [];
  const requests = [];
  page.on("console", (message) => { if (message.type() === "error") runtimeErrors.push(message.text()); });
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  await page.route("http://swarm.test/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push(url.pathname + url.search);
    if (url.pathname === "/") return route.fulfill({ status: 200, contentType: "text/html", body: documentHtml });
    if (url.pathname === "/styles.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
    if (url.pathname === "/app.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: app });
    if (url.pathname === "/api/bootstrap") return route.fulfill(response(fixture.bootstrap));
    if (url.pathname === "/api/overview") return route.fulfill(response(overview));
    if (url.pathname === "/api/proof-feed") return route.fulfill(response(fixture.proofFeed));
    if (url.pathname === "/api/usage-history") return route.fulfill(response(fixture.usageHistory));
    if (url.pathname === "/api/presence") return route.fulfill(response({ ok: true, proof_sequence: fixture.proofFeed.sequence || 0 }));
    if (url.pathname === "/api/config") return route.fulfill(response(fixture.config));
    if (url.pathname === "/api/diagnostics") return route.fulfill(response(fixture.diagnostics));
    if (url.pathname === "/api/diagnostics/history") return route.fulfill(response(fixture.diagnosticHistory));
    if (url.pathname === "/api/health/settings") return route.fulfill(response(fixture.healthSettings));
    if (url.pathname === "/api/storage") return route.fulfill(response(fixture.storage));
    if (url.pathname === "/api/ctrl-settings") return route.fulfill(response(fixture.ctrlSettings));
    if (url.pathname === "/assets/swarm-wordmark.png") return route.fulfill({ status: 204 });
    if (url.pathname === "/swarm-favicon.svg") return route.fulfill({ status: 204 });
    return route.abort();
  });
  await page.goto("http://swarm.test/", { waitUntil: "domcontentloaded" });
  try {
    await page.locator("#overview-content").waitFor({ state: "visible" });
  } catch (error) {
    const message = await page.locator("#error-message").textContent().catch(() => "");
    throw new Error(`${error.message}; console=${runtimeErrors.join(" | ")}; surface=${message}`);
  }
  return { runtimeErrors, requests };
}

const browserCandidates = [
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
].filter(Boolean);
const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const { runtimeErrors, requests } = await mount(page, scopedFixture());

  assert.equal(await page.locator("#view-title").textContent(), "Overview");
  assert.equal(await page.locator('[role="tab"]').count(), 5);
  assert.equal(await page.getByRole("button", { name: "All projects" }).count(), 1);
  assert.equal(await page.getByRole("button", { name: "Flowwweb" }).count(), 1);
  assert.equal(await page.getByRole("button", { name: "Unassigned planning" }).count(), 1);
  assert.match(await page.locator("#monitoring-cards").textContent(), /Unassigned planning/);
  assert.equal(await page.getByRole("button", { name: /https-mail/i }).count(), 0);
  assert.equal(await page.getByText("Current work").count(), 1);
  assert.equal(await page.locator("#usage-total").textContent(), "1K");
  assert.equal(await page.locator("#overview-health-state").textContent(), "Needs attention");
  assert.match(await page.locator("#overview-health-note").textContent(), /1 visible lane needs attention/);
  assert.match(await page.locator("#monitoring-cards").textContent(), /First blocker\s*Visual polish/);
  assert.equal(await page.locator('[data-overview-subagents="ctrl"]').count(), 1);
  assert.equal(await page.locator('[data-overview-subagents="ctrl"]').evaluate((element) => element.hasAttribute("open")), false);
  await page.getByRole("tab", { name: "Hierarchy" }).click();
  assert.match(await page.locator("#hierarchy-list").textContent(), /1 subagent/);
  assert.match(await page.locator("#hierarchy-list").textContent(), /Paused attention/);
  assert.ok(requests.some((request) => request.includes("/api/config")));

  await page.getByRole("button", { name: /^swarm\b/i }).click();
  assert.equal(await page.locator('[data-ctrl-id="nested-ctrl"]').count(), 1);
  await page.locator('[data-ctrl-id="nested-ctrl"]').click();
  assert.equal(await page.locator("#scope-context strong").textContent(), "Evidence review");
  assert.match(await page.locator("#monitoring-cards").textContent(), /Review screenshots|Evidence review/);
  assert.ok(requests.some((request) => request.includes("/api/usage-history?project_id=project%3Afixture&ctrl_id=nested-ctrl&hours=24")));

  await page.getByRole("button", { name: "Flowwweb" }).click();
  assert.equal(await page.locator("#scope-context strong").textContent(), "Ship integrations");
  await page.getByRole("button", { name: "Resolve customer export" }).click();
  assert.equal(await page.locator("#scope-context strong").textContent(), "Resolve customer export");

  await page.locator("#tab-diagnostics").focus();
  await page.keyboard.press("ArrowUp");
  assert.equal(await page.locator(":focus").getAttribute("id"), "tab-kanban");
  await page.keyboard.press("End");
  assert.equal(await page.locator(":focus").getAttribute("id"), "tab-settings");
  assert.equal(await page.locator("#view-title").textContent(), "Settings");
  await page.getByRole("tab", { name: "Diagnostics" }).click();
  assert.match(await page.locator("#view-diagnostics").textContent(), /Keep this device healthy/);
  assert.equal(await page.locator("#scope-context strong").textContent(), "Resolve customer export");
  await page.getByRole("tab", { name: "Hierarchy" }).click();
  assert.match(await page.locator("#hierarchy-list").textContent(), /Inspect export evidence/);
  await page.getByRole("tab", { name: "Kanban" }).click();
  assert.match(await page.locator("#kanban-board").textContent(), /In progress/);
  assert.match(await page.locator(".kanban-column").nth(1).textContent(), /Inspect export evidence/);
  await page.getByRole("tab", { name: "Settings" }).click();
  assert.match(await page.locator("#settings-grid").textContent(), /Clear history/);
  assert.equal(await page.locator("#settings-scope").inputValue(), "global");
  assert.match(await page.locator("#settings-grid").textContent(), /Manage skills/);

  for (const viewport of [{ width: 390, height: 844 }, { width: 834, height: 1112 }, { width: 1440, height: 1000 }]) {
    await page.setViewportSize(viewport);
    await page.locator("#tab-overview").evaluate((element) => element.click());
    const overflow = await page.locator("[data-qc-scope]").evaluate((element) => element.scrollWidth > element.clientWidth + 1);
    assert.equal(overflow, false, `horizontal overflow at ${viewport.width}px`);
  }
  assert.deepEqual(runtimeErrors, []);
  console.log("SWARM console Overview UI tests passed");
} finally {
  await browser.close();
}
