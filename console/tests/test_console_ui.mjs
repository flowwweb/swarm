import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const testsRoot = path.dirname(fileURLToPath(import.meta.url));
const consoleRoot = path.resolve(testsRoot, "..");
const staticRoot = path.join(consoleRoot, "static");
const fixture = JSON.parse(fs.readFileSync(path.join(testsRoot, "fixtures", "console-ui.json"), "utf8"));
const css = fs.readFileSync(path.join(staticRoot, "styles.css"), "utf8");
const app = fs.readFileSync(path.join(staticRoot, "app.js"), "utf8");
const indexHtml = fs.readFileSync(path.join(staticRoot, "index.html"), "utf8");
const documentHtml = indexHtml
  .replace("<head>", '<head><base href="http://swarm.test/">');

for (const label of ["Current work", "Recent images", "Tokens · 24h", "Completed", "Dashboard", "Where changes apply", "Manage", "Advanced settings"]) {
  assert.match(indexHtml + app, new RegExp(label));
}
assert.match(app, /\/api\/usage-history\?/);
assert.match(app, /hours: "24"/);
assert.match(app, /source\.status === 'no_data'/);
assert.match(app, /Partial coverage/);
assert.match(app, /Complete coverage/);
assert.match(app, /source\.coverage\?\.observed_threads/);
assert.match(indexHtml, /id="usage-range"/);
assert.match(indexHtml, /id="overview-monitoring-health-state"/);
assert.match(indexHtml, /id="view-dashboard"/);
assert.match(indexHtml, /id="tab-dashboard"/);
assert.match(app, /function renderOverviewHealth\(nodes\)/);
assert.match(app, /function renderDashboard\(\)/);
assert.match(app, /function routeView\(\)/);
assert.match(app, /\["overview", "dashboard", "hierarchy", "kanban", "diagnostics", "settings"\]/);
assert.match(app, /renderOverviewProjectCards\(nodes\)/);
assert.match(app, /function authoritativeProgress\(projectId, ctrlId = ""\)/);
assert.match(app, /function progressPresentation\(summary\)/);
assert.match(app, /if \(ctrlId\) return summaries\.controllers\?\.\[ctrlId\] \?\? null/);
assert.match(app, /if \(projectId\) return summaries\.projects\?\.\[projectId\] \?\? null/);
assert.match(app, /validPercent == null \? "Unmeasured"/);
assert.match(app, /freshness\.state === "fresh" \? "Fresh" : freshness\.state === "stale" \? "Stale" : "Unmeasured"/);
assert.doesNotMatch(app, /completed \/ total/);
assert.doesNotMatch(app, /progress_basis\?\.percent|progress_percent/);
assert.match(app, /function hasCurrentWorkScopeContract\(\)/);
assert.match(app, /function currentWorkProjects\(\)/);
assert.match(app, /function currentWorkControllers\(\)/);
assert.match(app, /function currentWorkScopeUnavailable\(\)/);
assert.match(app, /function historicalProjects\(\)/);
assert.match(app, /function historicalControllers\(\)/);
assert.match(app, /project\.visibility === "visible" && project\.archived === false && project\.project_eligibility === "swarm_ctrl"/);
assert.match(app, /controller\.visibility === "visible" && controller\.archived === false && allowedControllerProjects\.get\(controller\.id\) === controller\.project_id/);
assert.match(app, /project\.ctrl_ids\.includes\(ctrl\.id\)/);
assert.doesNotMatch(app, /function activeControllers\(\)/);
assert.doesNotMatch(app, /function hasCurrentOverviewWork\(card\)/);
assert.match(app, /Current Work needs host-reported CTRL classification/);
assert.equal((app.match(/Current Work needs host-reported CTRL classification/g) || []).length, 1);
assert.match(app, /expectedControllerIds\.some\(\(ctrlId\) => !resolvedControllerIds\.has\(ctrlId\)\)/);
assert.match(app, /if \(currentWorkScopeUnavailable\(\)\) return \[\]/);
assert.match(app, /cards\.filter\(\(card\) => card\.nodes\.length\)/);
assert.match(app, /scopedCards\.slice\(0, 5\)/);
assert.match(app, /class="overview-more"/);
assert.match(app, /No classified Current Work is available/);
const currentWorkProjectsSource = app.slice(app.indexOf("function currentWorkProjects"), app.indexOf("function currentWorkControllers"));
const currentWorkControllersSource = app.slice(app.indexOf("function currentWorkControllers"), app.indexOf("function publicLabel"));
const projectGroupsSource = app.slice(app.indexOf("function projectGroups"), app.indexOf("function scopeLabel"));
const overviewCardsSource = app.slice(app.indexOf("function overviewCards"), app.indexOf("function latestReceipt"));
assert.doesNotMatch(currentWorkProjectsSource, /project\.status|active_ctrl/);
assert.doesNotMatch(currentWorkControllersSource, /controller\.status/);
assert.match(projectGroupsSource, /historicalProjects\(\)|historicalControllers\(\)/);
assert.doesNotMatch(projectGroupsSource, /currentWorkProjects\(\)|currentWorkControllers\(\)/);
assert.doesNotMatch(overviewCardsSource, /node\.role|node\.title/);
assert.equal(fixture.overview.progress.controllers.ctrl.progress.percent, 80);
assert.equal(fixture.overview.progress.controllers.ctrl.progress.source, "material_receipts");
assert.equal(fixture.overview.navigation.projects[0].project_eligibility, "swarm_ctrl");
assert.match(css, /\.overview-project-card/);
assert.match(indexHtml, /id="task-table"/);
assert.match(indexHtml, /id="proof-feed"/);
assert.match(indexHtml, /id="burn-chart"/);
assert.match(indexHtml, /id="overview-diagnostics-heading"/);
assert.match(app, /renderMetrics\(nodes\);\s*renderTable\(nodes\);\s*renderProof\(nodes\);\s*renderBurnRate\(\);\s*renderOverviewDiagnostics\(\);/);
assert.doesNotMatch(app, /renderDashboardMonitoringCards/);
assert.match(app, /Needs attention/);
assert.match(app, /function attentionStatus\(node\)/);
assert.match(app, /\[node\?\.status, node\?\.eta\?\.status\]/);
assert.match(app, /tasks\.find\(needsAttention\)/);
assert.match(app, /const stalled = needsAttention\(current\)/);
assert.match(app, /project_id: state\.projectId/);
assert.match(app, /ctrl_id: state\.ctrlId/);
assert.match(app, /setInterval\(reportPresence, 60_000\)/);
assert.match(app, /async function refreshMonitoring/);
assert.match(app, /renderDashboard\(\);\s*renderHierarchy\(\);/);
assert.match(app, /api\("\/api\/overview", \{ timeoutMs: 15_000 \}\)/);
assert.match(indexHtml, /id="data-status-title">Connecting</);
assert.match(indexHtml, /id="data-status-note">Waiting for data</);
assert.doesNotMatch(indexHtml, /Projects are up to date|<strong>Connected<\/strong>/);
assert.match(app, /setDataStatus\("current", state\.overview\?\.generated_at\)/);
assert.match(app, /setDataStatus\(state\.overview \? "stale" : "unavailable"/);
assert.match(app, /Project data request timed out/);
assert.match(app, /data-overview-subagents/);
assert.match(app, /#overview-evidence-gallery/);
assert.match(indexHtml, /id="evidence-lightbox"/);
assert.match(indexHtml, /id="evidence-lightbox-thumbnails"/);
assert.match(indexHtml, /Close evidence gallery/);
assert.match(indexHtml, /This image could not be loaded/);
assert.match(app, /function renderEvidenceLightbox\(\)/);
assert.match(app, /function openEvidenceLightbox\(index, trigger\)/);
assert.match(app, /data-evidence-open/);
assert.match(app, /data-evidence-thumbnail/);
assert.match(app, /data-evidence-more/);
assert.match(app, /dialog\.showModal\(\)/);
assert.match(app, /ArrowLeft/);
assert.match(app, /ArrowRight/);
assert.match(app, /const previews = images\.slice\(0, limit\)/);
assert.match(app, /const remaining = Math\.max\(0, images\.length - previews\.length\)/);
assert.doesNotMatch(app, /figcaption/);
assert.match(css, /\.evidence-lightbox/);
assert.match(css, /\.proof-tile/);
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
assert.match(app, /settingToggle\('execution\.fast_mode'/);
assert.doesNotMatch(app, /execution\.service_tier/);
assert.doesNotMatch(app, /ctrl-service-tier/);
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
assert.match(app, /\.replace\(\/\\blocalhost\\b\/gi, "console"\)/);
for (const forbidden of ["hidden usage", "developer instructions", "prompts", "tools", "credentials"]) {
  assert.equal((indexHtml + app).toLowerCase().includes(forbidden), false, `forbidden copy: ${forbidden}`);
}

if (process.argv.includes("--source-only")) {
  console.log("SWARM console source UI contract passed");
  process.exit(0);
}

const { chromium } = require("playwright");

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
    { id: "arc-ctrl", role: "ctrl", artifact: "Review release notes", project_id: "project:arc", project: "Arc", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["arc-ctrl"] },
    { id: "arc-task", role: "doer", role_label: "TASK", artifact: "Verify changelog", project_id: "project:arc", project: "Arc", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["arc-ctrl"] },
    { id: "atlas-ctrl", role: "ctrl", artifact: "Prepare customer brief", project_id: "project:atlas", project: "Atlas", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["atlas-ctrl"] },
    { id: "atlas-task", role: "doer", role_label: "TASK", artifact: "Summarize account status", project_id: "project:atlas", project: "Atlas", status: "active", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["atlas-ctrl"] },
    { id: "idle-ctrl", role: "ctrl", artifact: "Await customer decision", project_id: "project:idle", project: "Idle project", status: "idle", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["idle-ctrl"] },
    { id: "idle-task", role: "doer", role_label: "TASK", artifact: "Prepare decision options", project_id: "project:idle", project: "Idle project", status: "idle", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["idle-ctrl"] },
    { id: "stalled-ctrl", role: "ctrl", artifact: "Resolve dependency", project_id: "project:stalled", project: "Stalled project", status: "stalled", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["stalled-ctrl"] },
    { id: "stalled-task", role: "doer", role_label: "TASK", artifact: "Trace dependency", project_id: "project:stalled", project: "Stalled project", status: "stalled", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["stalled-ctrl"] },
    { id: "archived-ctrl", role: "ctrl", artifact: "Archived release", project_id: "project:archived", project: "Archived project", status: "quiet", updated_at: "2026-08-09T00:00:00Z", controller_ids: ["archived-ctrl"] },
  );
  overview.projects.push({ id: "project:branch", name: "Flowwweb", nodes: 2, tokens: 0, active: 2 });
  overview.projects.push({ id: "project:arc", name: "Arc", nodes: 2, tokens: 0, active: 2 });
  overview.projects.push({ id: "project:atlas", name: "Atlas", nodes: 2, tokens: 0, active: 2 });
  overview.projects.push({ id: "project:idle", name: "Idle project", nodes: 2, tokens: 0, active: 0 });
  overview.projects.push({ id: "project:stalled", name: "Stalled project", nodes: 2, tokens: 0, active: 0 });
  overview.projects.push({ id: "project:archived", name: "Archived project", nodes: 1, tokens: 0, active: 0 });
  overview.projects.push({ id: "project:waiting", name: "Unassigned planning", nodes: 0, tokens: 0, active: 0 });
  overview.projects.push({ id: "project:browser", name: "https-mail-google-com-mail-u", nodes: 0, tokens: 0, active: 1 });
  overview.navigation.projects[0].ctrl_ids.push("nested-ctrl");
  overview.navigation.projects.push(
    { id: "project:branch", name: "Flowwweb", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["branch-ctrl"], active_ctrl_id: "branch-ctrl", active_ctrl: true },
    { id: "project:arc", name: "Arc", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["arc-ctrl"], active_ctrl_id: "arc-ctrl", active_ctrl: true },
    { id: "project:atlas", name: "Atlas", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["atlas-ctrl"], active_ctrl_id: "atlas-ctrl", active_ctrl: true },
    { id: "project:idle", name: "Idle project", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["idle-ctrl"], active_ctrl_id: null, active_ctrl: false },
    { id: "project:stalled", name: "Stalled project", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["stalled-ctrl"], active_ctrl_id: null, active_ctrl: false },
    { id: "project:archived", name: "Archived project", archived: true, visibility: "archived", project_eligibility: "swarm_ctrl", ctrl_ids: ["archived-ctrl"], active_ctrl_id: null, active_ctrl: false },
    { id: "project:waiting", name: "Unassigned planning", archived: false, visibility: "visible", project_eligibility: "no_ctrl", ctrl_ids: [], active_ctrl_id: null, active_ctrl: false }
  );
  overview.navigation.controllers.push(
    { id: "nested-ctrl", project_id: "project:fixture", status: "active", archived: false, visibility: "visible" },
    { id: "branch-ctrl", project_id: "project:branch", status: "active", archived: false, visibility: "visible" },
    { id: "arc-ctrl", project_id: "project:arc", status: "active", archived: false, visibility: "visible" },
    { id: "atlas-ctrl", project_id: "project:atlas", status: "active", archived: false, visibility: "visible" },
    { id: "idle-ctrl", project_id: "project:idle", status: "idle", archived: false, visibility: "visible" },
    { id: "stalled-ctrl", project_id: "project:stalled", status: "stalled", archived: false, visibility: "visible" },
    { id: "archived-ctrl", project_id: "project:archived", status: "quiet", archived: true, visibility: "archived" }
  );
  for (const id of ["nested-ctrl", "branch-ctrl", "arc-ctrl", "atlas-ctrl", "idle-ctrl", "stalled-ctrl"]) {
    overview.progress.controllers[id] = { progress: null, freshness: { state: "unavailable", observed_at_ms: null } };
  }
  return overview;
}

function imageProofFixture(count) {
  return {
    ok: true,
    items: Array.from({ length: count }, (_, index) => ({
      task_id: "ctrl",
      evidence_id: "fixture-image-" + String(index + 1),
      digest: String(index + 1).padStart(64, "0"),
      media_type: "image/png",
      caption: "Evidence image " + String(index + 1),
    })),
  };
}

async function mount(page, overview, overrides = {}) {
  const runtimeErrors = [];
  const requests = [];
  const proofFeed = overrides.proofFeed || fixture.proofFeed;
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
    if (url.pathname === "/api/proof-feed") return route.fulfill(response(proofFeed));
    if (url.pathname === "/api/usage-history") return route.fulfill(response(fixture.usageHistory));
    if (url.pathname === "/api/presence") return route.fulfill(response({ ok: true, proof_sequence: proofFeed.sequence || 0 }));
    if (url.pathname === "/api/config") return route.fulfill(response(fixture.config));
    if (url.pathname === "/api/diagnostics") return route.fulfill(response(fixture.diagnostics));
    if (url.pathname === "/api/diagnostics/history") return route.fulfill(response(fixture.diagnosticHistory));
    if (url.pathname === "/api/health/settings") return route.fulfill(response(fixture.healthSettings));
    if (url.pathname === "/api/storage") return route.fulfill(response(fixture.storage));
    if (url.pathname === "/api/ctrl-settings") return route.fulfill(response(fixture.ctrlSettings));
    if (url.pathname.startsWith("/api/proof-media/")) return route.fulfill({ status: 200, contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="100"><rect width="160" height="100" fill="#0f1726"/></svg>' });
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
  assert.equal(await page.locator('[role="tab"]').count(), 6);
  assert.equal(await page.getByRole("button", { name: "All projects" }).count(), 1);
  assert.equal(await page.getByRole("button", { name: "Flowwweb" }).count(), 1);
  assert.equal(await page.getByRole("button", { name: "Idle project" }).count(), 1);
  assert.equal(await page.getByRole("button", { name: "Stalled project" }).count(), 1);
  assert.equal(await page.getByRole("button", { name: "Unassigned planning" }).count(), 1);
  assert.equal(await page.getByRole("button", { name: "Archived project" }).count(), 1);
  assert.equal(await page.locator("#overview-project-cards > .overview-project-card").count(), 5);
  assert.equal(await page.locator("#overview-project-cards > .overview-more").count(), 1);
  assert.doesNotMatch(await page.locator("#overview-project-cards").textContent(), /Unassigned planning/);
  assert.doesNotMatch(await page.locator("#overview-project-cards").textContent(), /Archived project/);
  assert.match(await page.locator("#overview-project-cards").textContent(), /Idle project/);
  assert.match(await page.locator("#overview-project-cards").textContent(), /Stalled project/);
  assert.match(await page.locator("#overview-project-cards").textContent(), /80%/);
  assert.match(await page.locator("#overview-project-cards").textContent(), /Fresh/);
  assert.equal(await page.getByRole("button", { name: /https-mail/i }).count(), 0);
  assert.equal(await page.getByText("Current work").count(), 1);
  assert.equal(await page.locator("#usage-total").textContent(), "1K");
  assert.equal(await page.locator("#overview-monitoring-health-state").textContent(), "Needs attention");
  assert.match(await page.locator("#overview-monitoring-health-note").textContent(), /1 visible lane needs attention/);
  assert.match(await page.locator("#overview-project-cards").textContent(), /Blocker\s*Visual polish/);
  assert.equal(await page.locator("#overview-evidence-gallery img").count(), 1);
  assert.equal(await page.locator('[data-overview-subagents="ctrl"]').count(), 1);
  assert.equal(await page.locator('[data-overview-subagents="ctrl"]').evaluate((element) => element.hasAttribute("open")), false);
  await page.getByRole("button", { name: "Unassigned planning" }).click();
  assert.equal(await page.locator("#scope-context strong").textContent(), "Unassigned planning");
  assert.equal(await page.locator("#overview-project-cards > .overview-project-card").count(), 0);
  assert.match(await page.locator("#overview-project-cards").textContent(), /No classified Current Work is available/);
  await page.getByRole("button", { name: "All projects" }).click();
  await page.getByRole("tab", { name: "Dashboard" }).click();
  assert.equal(await page.locator("#view-title").textContent(), "Dashboard");
  assert.match(page.url(), /#dashboard$/);
  assert.match(await page.locator("#task-table").textContent(), /Resolve customer export/);
  assert.equal(await page.locator("#task-table [data-subagent-parent]").count(), 1);
  assert.equal(await page.locator("#proof-feed").count(), 1);
  assert.equal(await page.locator("#overview-diagnostics-heading").textContent(), "Diagnostics");
  await page.evaluate(() => { location.hash = "#graph"; });
  await page.waitForTimeout(20);
  assert.equal(await page.locator("#view-title").textContent(), "Overview");
  assert.match(page.url(), /#overview$/);
  await page.getByRole("tab", { name: "Hierarchy" }).click();
  assert.match(await page.locator("#hierarchy-list").textContent(), /1 subagent/);
  assert.match(await page.locator("#hierarchy-list").textContent(), /Paused attention/);
  assert.ok(requests.some((request) => request.includes("/api/config")));

  await page.getByRole("button", { name: /^swarm\b/i }).click();
  assert.equal(await page.locator('[data-ctrl-id="nested-ctrl"]').count(), 1);
  await page.locator('[data-ctrl-id="nested-ctrl"]').click();
  assert.equal(await page.locator("#scope-context strong").textContent(), "Evidence review");
  assert.match(await page.locator("#overview-project-cards").textContent(), /Review screenshots|Evidence review/);
  assert.ok(requests.some((request) => request.includes("/api/usage-history?project_id=project%3Afixture&ctrl_id=nested-ctrl&hours=24")));

  await page.getByRole("button", { name: "Flowwweb" }).click();
  assert.equal(await page.locator("#scope-context strong").textContent(), "Ship integrations");

  await page.locator("#tab-diagnostics").focus();
  await page.keyboard.press("ArrowUp");
  assert.equal(await page.locator(":focus").getAttribute("id"), "tab-kanban");
  await page.keyboard.press("End");
  assert.equal(await page.locator(":focus").getAttribute("id"), "tab-settings");
  assert.equal(await page.locator("#view-title").textContent(), "Settings");
  await page.getByRole("tab", { name: "Diagnostics" }).click();
  assert.match(await page.locator("#view-diagnostics").textContent(), /Keep this device healthy/);
  assert.equal(await page.locator("#scope-context strong").textContent(), "Ship integrations");
  await page.getByRole("tab", { name: "Hierarchy" }).click();
  assert.match(await page.locator("#hierarchy-list").textContent(), /Confirm webhooks/);
  await page.getByRole("tab", { name: "Kanban" }).click();
  assert.match(await page.locator("#kanban-board").textContent(), /In progress/);
  assert.match(await page.locator(".kanban-column").nth(1).textContent(), /Confirm webhooks/);
  await page.getByRole("tab", { name: "Settings" }).click();
  assert.match(await page.locator("#settings-grid").textContent(), /Clear history/);
  assert.equal(await page.locator("#settings-scope").inputValue(), "ctrl|branch-ctrl");
  assert.match(await page.locator("#settings-scope").textContent(), /Unassigned planning/);
  assert.match(await page.locator("#settings-scope").textContent(), /Archived project/);
  assert.match(await page.locator("#settings-grid").textContent(), /Manage skills/);

  const unclassifiedPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
  const unclassifiedOverview = structuredClone(fixture.overview);
  unclassifiedOverview.navigation.controllers = [];
  const unclassified = await mount(unclassifiedPage, unclassifiedOverview);
  assert.equal(await unclassifiedPage.locator("#overview-project-cards > .overview-project-card").count(), 0);
  assert.match(await unclassifiedPage.locator("#overview-project-cards").textContent(), /needs host-reported CTRL classification/);
  assert.doesNotMatch(await unclassifiedPage.locator("#overview-project-cards").textContent(), /0%/);
  assert.deepEqual(unclassified.runtimeErrors, []);
  await unclassifiedPage.close();

  const manyPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
  const many = await mount(manyPage, fixture.overview, { proofFeed: imageProofFixture(12) });
  assert.equal(await manyPage.locator("#overview-evidence-gallery .evidence-gallery-item").count(), 4);
  assert.equal(await manyPage.locator('[data-evidence-more="8"]').count(), 1);
  assert.equal(await manyPage.locator('[data-evidence-more="8"]').textContent(), "+8 more");
  await manyPage.getByRole("button", { name: /Open 8 more images; 12 images/ }).click();
  assert.equal(await manyPage.locator("#evidence-lightbox[open]").count(), 1);
  assert.equal(await manyPage.locator("#evidence-lightbox-thumbnails button").count(), 12);
  await manyPage.keyboard.press("ArrowRight");
  assert.equal(await manyPage.locator('[data-evidence-thumbnail="5"]').getAttribute("aria-current"), "true");
  await manyPage.locator('[data-evidence-thumbnail="11"]').click();
  assert.equal(await manyPage.locator('[data-evidence-thumbnail="11"]').getAttribute("aria-current"), "true");
  await manyPage.getByRole("button", { name: "Close evidence gallery" }).click();
  assert.equal(await manyPage.locator("#evidence-lightbox[open]").count(), 0);
  await manyPage.getByRole("tab", { name: "Dashboard" }).click();
  await manyPage.locator("#proof-feed .proof-tile").first().click();
  assert.equal(await manyPage.locator("#evidence-lightbox-thumbnails button").count(), 12);
  await manyPage.getByRole("button", { name: "Close evidence gallery" }).click();
  assert.deepEqual(many.runtimeErrors, []);
  await manyPage.close();

  const onePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
  const one = await mount(onePage, fixture.overview, { proofFeed: imageProofFixture(1) });
  assert.equal(await onePage.locator("#overview-evidence-gallery .evidence-gallery-item").count(), 1);
  assert.equal(await onePage.locator("[data-evidence-more]").count(), 0);
  await onePage.locator("#overview-evidence-gallery .evidence-gallery-item").click();
  assert.equal(await onePage.locator("#evidence-lightbox-thumbnails button").count(), 1);
  assert.equal(await onePage.locator("#evidence-lightbox-previous").isDisabled(), true);
  assert.equal(await onePage.locator("#evidence-lightbox-next").isDisabled(), true);
  await onePage.locator("#evidence-lightbox-image").dispatchEvent("error");
  assert.equal(await onePage.locator("#evidence-lightbox-failed").isVisible(), true);
  await onePage.keyboard.press("Escape");
  assert.equal(await onePage.locator("#evidence-lightbox[open]").count(), 0);
  assert.deepEqual(one.runtimeErrors, []);
  await onePage.close();

  const emptyPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
  const empty = await mount(emptyPage, fixture.overview, { proofFeed: imageProofFixture(0) });
  assert.equal(await emptyPage.locator("#overview-evidence-gallery .evidence-gallery-item").count(), 0);
  assert.equal(await emptyPage.locator("[data-evidence-more]").count(), 0);
  assert.match(await emptyPage.locator("#overview-evidence-gallery").textContent(), /Images appear here when they are received/);
  assert.match(await emptyPage.locator("#proof-feed").textContent(), /No image proof yet/);
  assert.deepEqual(empty.runtimeErrors, []);
  await emptyPage.close();

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
