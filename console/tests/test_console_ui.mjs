import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const testsRoot = path.dirname(fileURLToPath(import.meta.url));
const consoleRoot = path.resolve(testsRoot, "..");
const repositoryRoot = path.resolve(consoleRoot, "..");
const staticRoot = path.join(consoleRoot, "static");
const pluginConsoleRoot = path.join(repositoryRoot, "plugins", "swarm", "console");
const pluginStaticRoot = path.join(pluginConsoleRoot, "static");
const fixture = JSON.parse(fs.readFileSync(path.join(testsRoot, "fixtures", "console-ui.json"), "utf8"));
const css = fs.readFileSync(path.join(staticRoot, "styles.css"), "utf8");
const app = fs.readFileSync(path.join(staticRoot, "app.js"), "utf8");
const indexHtml = fs.readFileSync(path.join(staticRoot, "index.html"), "utf8");
const pluginCss = fs.readFileSync(path.join(pluginStaticRoot, "styles.css"), "utf8");
const pluginApp = fs.readFileSync(path.join(pluginStaticRoot, "app.js"), "utf8");
const pluginIndexHtml = fs.readFileSync(path.join(pluginStaticRoot, "index.html"), "utf8");
const server = fs.readFileSync(path.join(consoleRoot, "server.py"), "utf8");
const pluginServer = fs.readFileSync(path.join(pluginConsoleRoot, "server.py"), "utf8");
const offlineAsset = fs.readFileSync(path.join(staticRoot, "swarm-offline-disconnected.png"));
const pluginOfflineAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-offline-disconnected.png"));
const wordmarkAsset = fs.readFileSync(path.join(repositoryRoot, "skills", "swarm", "assets", "swarm-wordmark.png"));
const documentHtml = indexHtml
  .replace("<head>", '<head><base href="http://swarm.test/">');

const offlineAssetDigest = crypto.createHash("sha256").update(offlineAsset).digest("hex");
assert.equal(offlineAssetDigest, "4677c1da5af8c79a2db5dfbaf7dd87a060dbd9dca888a8c3f6d800d990aab4fe");
assert.deepEqual(pluginOfflineAsset, offlineAsset);
assert.equal(pluginCss, css);
assert.equal(pluginApp, app);
assert.equal(pluginIndexHtml, indexHtml);
assert.equal(pluginServer, server);
assert.match(server, /"\/assets\/swarm-offline-disconnected\.png": \("swarm-offline-disconnected\.png", "image\/png"\)/);
assert.match(indexHtml, /id="connection-state" hidden role="status" aria-live="assertive" aria-atomic="true" aria-labelledby="connection-state-title"/);
assert.match(indexHtml, /src="\/assets\/swarm-offline-disconnected\.png" width="1536" height="1024"/);
assert.match(indexHtml, /<h1 id="connection-state-title">Connection lost<\/h1><p>Your work is safe\. SWARM will reconnect when the console is available\.<\/p>/);
assert.doesNotMatch(indexHtml, /Local console unavailable|Reconnect, then try again|connection-retry|Retry connection/);
assert.match(app, /if \(error instanceof TypeError\) throw connectionFailure/);
assert.match(app, /const CONNECTION_RETRY_DELAYS_MS = \[1_000, 3_000, 10_000, 30_000\]/);
assert.match(app, /shell\.hidden = true;[\s\S]*?shell\.inert = true;[\s\S]*?shell\.setAttribute\("aria-hidden", "true"\)/);
assert.match(app, /if \(error\.connectionFailure\) showConnectionState\(\)/);
assert.match(app, /scheduleConnectionRetry\(\)/);
assert.match(app, /if \(connectionRetryTimer\) window\.clearTimeout\(connectionRetryTimer\)/);
assert.doesNotMatch(app, /connection-retry/);
assert.match(css, /\.connection-state \{ position:fixed; inset:0; z-index:100;/);
assert.match(css, /body\.is-disconnected \{ overflow:hidden; \}/);

for (const [tab, icon] of [["overview", "house"], ["dashboard", "layout-dashboard"], ["hierarchy", "network"], ["kanban", "columns-3"], ["diagnostics", "activity"], ["settings", "settings"]]) {
  assert.match(indexHtml, new RegExp(`id="tab-${tab}"[\\s\\S]*?<use href="#lucide-${icon}"></use>`));
  assert.match(indexHtml, new RegExp(`id="lucide-${icon}" viewBox="0 0 24 24"`));
}
assert.doesNotMatch(indexHtml, /[⌂▦⑂▥⊙⚙]/);
assert.match(indexHtml, /id="mobile-menu-button"[^>]*aria-label="Open navigation"[^>]*aria-expanded="false"[^>]*aria-controls="console-drawer"/);
assert.match(indexHtml, /class="mobile-app-bar"[\s\S]*?<img src="\/assets\/swarm-wordmark\.png" alt="SWARM"/);
assert.equal((indexHtml.match(/class="nav-list"/g) || []).length, 1);
assert.match(css, /--base: #091321;/);
assert.match(css, /--surface: rgba\(16, 29, 47, \.9\);/);
assert.match(css, /--muted: #c2cedd;/);
assert.match(css, /--shell-top: clamp\(20px, 2\.5vw, 32px\)/);
assert.match(css, /padding: max\(var\(--shell-top\), env\(safe-area-inset-top\)\)/);
assert.match(css, /body\.drawer-open \{ overflow: hidden; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.mobile-app-bar \{ position:sticky;/);
assert.match(css, /\.app-shell\.is-drawer-open \.drawer \{ transform:translateX\(0\); \}/);
assert.match(app, /function setMobileDrawer\(open, restoreFocus = false\)/);
assert.match(app, /workspace\.inert = expanded/);
assert.match(app, /function mobileDrawerFocusable\(\)/);
assert.match(app, /event\.key === "Tab" && \$\("\.app-shell"\)\.classList\.contains\("is-drawer-open"\)/);
assert.match(app, /drawer\.inert = !expanded/);
assert.match(app, /event\.key === "Escape" && \$\("\.app-shell"\)\.classList\.contains\("is-drawer-open"\)/);

for (const label of ["Current work", "Latest updates", "Recent images", "Tokens · 1d", "Completed", "Dashboard", "Where changes apply", "Manage", "Advanced settings"]) {
  assert.match(indexHtml + app, new RegExp(label));
}
assert.match(app, /\/api\/usage-history\?/);
assert.match(app, /usageWindowHours: 24/);
assert.match(indexHtml, /data-usage-hours="1"/);
assert.match(indexHtml, /data-usage-hours="24"/);
assert.doesNotMatch(indexHtml, /data-usage-hours="168"/);
assert.doesNotMatch(indexHtml, />1w<\/button>/);
assert.match(indexHtml, /id="usage-rate-sparkline"/);
assert.match(app, /function usageRateSeries\(series\)/);
assert.match(app, /function downsampleSeries\(values, maximum = 96\)/);
assert.match(app, /source\.status === 'no_data'/);
assert.match(app, /Partial coverage/);
assert.match(app, /Complete coverage/);
assert.match(app, /source\.coverage\?\.observed_threads/);
assert.match(indexHtml, /id="usage-range"/);
assert.match(indexHtml, /id="usage-sparkline" viewBox="0 0 240 52"/);
assert.match(css, /\.usage-chart-pair \{ grid-column:2;/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.usage-chart-pair \{ display:none; \}/);
assert.match(indexHtml, /id="project-progress-section"/);
assert.match(app, /\/api\/project-progress-feed\?/);
assert.match(app, /function renderProjectProgressFeed\(\)/);
assert.match(app, /settingToggle\('console\.project_progress_feed_enabled'/);
assert.match(app, /data-config-key="console\.project_progress_feed_lines"/);
assert.doesNotMatch(app, /setInterval\([^)]*projectProgress|setInterval\([^)]*progressFeed/);
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
const projectNavigationSource = app.slice(app.indexOf("function renderProjectNavigation"), app.indexOf("function drawLine"));
const overviewCardsSource = app.slice(app.indexOf("function overviewCards"), app.indexOf("function latestReceipt"));
assert.doesNotMatch(currentWorkProjectsSource, /project\.status|active_ctrl/);
assert.doesNotMatch(currentWorkControllersSource, /controller\.status/);
assert.match(projectGroupsSource, /historicalProjects\(\)|historicalControllers\(\)/);
assert.doesNotMatch(projectGroupsSource, /currentWorkProjects\(\)|currentWorkControllers\(\)/);
assert.match(projectNavigationSource, /filter\(\(group\) => !group\.standalone\)/);
assert.doesNotMatch(projectNavigationSource, /data-ctrl-id|data-project-toggle|ctrl-subpages/);
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
assert.match(app, /project_id: request\.projectId/);
assert.match(app, /ctrl_id: request\.ctrlId/);
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
assert.match(indexHtml, /id="evidence-page-next"/);
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
assert.match(app, /EVIDENCE_THUMBNAIL_PAGE_SIZE = 24/);
assert.match(app, /proofCollections: new Map\(\)/);
assert.match(app, /state\.proof = state\.proofCollections\.get\(collectionKey\) \|\| \[\]/);
assert.match(app, /return images\.filter\(\(item\) => !item\.project_id \|\| item\.project_id === state\.projectId\)/);
assert.doesNotMatch(app, /catch \{ state\.proof = \[\]; \}/);
assert.match(app, /const previews = images\.slice\(0, 4\)/);
assert.doesNotMatch(app, /figcaption/);
assert.match(css, /\.evidence-lightbox/);
assert.match(css, /\.proof-tile/);
assert.match(app, /subagentDescendants\(card\.ctrlId, tree\)/);
assert.match(app, /params\.set\("project_id", projectId\)/);
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
  const proofControl = overrides.proofControl || { fail: false, feed: proofFeed };
  page.on("console", (message) => { if (message.type() === "error") runtimeErrors.push(message.text()); });
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  await page.route("http://swarm.test/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    requests.push(url.pathname + url.search);
    if (url.pathname === "/") return route.fulfill({ status: 200, contentType: "text/html", body: documentHtml });
    if (url.pathname === "/styles.css") return route.fulfill({ status: 200, contentType: "text/css", body: css });
    if (url.pathname === "/app.js") return route.fulfill({ status: 200, contentType: "text/javascript", body: app });
    if (url.pathname === "/assets/swarm-offline-disconnected.png") return route.fulfill({ status: 200, contentType: "image/png", body: offlineAsset });
    if (overrides.connection?.offline && url.pathname.startsWith("/api/")) return route.abort();
    if (url.pathname === "/api/bootstrap") return route.fulfill(response(fixture.bootstrap));
    if (url.pathname === "/api/overview") return route.fulfill(response(overview));
    if (url.pathname === "/api/proof-feed") return proofControl.fail ? route.fulfill({ status: 200, contentType: "application/json", body: "{" }) : route.fulfill(response(proofControl.feed || proofFeed));
    if (url.pathname === "/api/usage-history") {
      const hours = url.searchParams.get("hours");
      if (!["1", "12", "24"].includes(hours)) return route.fulfill({ status: 400, contentType: "application/json", body: JSON.stringify({ ok: false, error: "unsupported usage window" }) });
      return route.fulfill(response(overrides.usageByHours?.[hours] || fixture.usageHistory));
    }
    if (url.pathname === "/api/project-progress-feed") return route.fulfill(response(overrides.projectProgressFeed || fixture.projectProgressFeed));
    if (url.pathname === "/api/presence") return route.fulfill(response({ ok: true, proof_sequence: proofFeed.sequence || 0 }));
    if (url.pathname === "/api/config") return route.fulfill(response(fixture.config));
    if (url.pathname === "/api/diagnostics") return route.fulfill(response(fixture.diagnostics));
    if (url.pathname === "/api/diagnostics/history") return route.fulfill(response(fixture.diagnosticHistory));
    if (url.pathname === "/api/health/settings") return route.fulfill(response(fixture.healthSettings));
    if (url.pathname === "/api/storage") return route.fulfill(response(fixture.storage));
    if (url.pathname === "/api/ctrl-settings") return route.fulfill(response(fixture.ctrlSettings));
    if (url.pathname === "/api/skills") return route.fulfill(response({ ok: true, settings: { inheritance_enabled: true }, skills: [], overlays: { global: null, project: null, ctrl: null } }));
    if (url.pathname.startsWith("/api/proof-media/")) return route.fulfill({ status: 200, contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="100"><rect width="160" height="100" fill="#0f1726"/></svg>' });
    if (url.pathname === "/assets/swarm-wordmark.png") return route.fulfill({ status: 200, contentType: "image/png", body: wordmarkAsset });
    if (url.pathname === "/swarm-favicon.svg") return route.fulfill({ status: 204 });
    return route.abort();
  });
  await page.goto("http://swarm.test/", { waitUntil: "domcontentloaded" });
  if (overrides.waitForConnectionState) {
    await page.locator("#connection-state").waitFor({ state: "visible" });
    return { runtimeErrors, requests };
  }
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
  const offlinePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
  const connection = { offline: true };
  const offline = await mount(offlinePage, scopedFixture(), { connection, waitForConnectionState: true });
  assert.equal(await offlinePage.getByRole("heading", { name: "Connection lost" }).count(), 1);
  assert.equal(await offlinePage.getByText("Your work is safe. SWARM will reconnect when the console is available.", { exact: true }).count(), 1);
  assert.equal(await offlinePage.getByRole("button").count(), 0);
  assert.equal(await offlinePage.locator('#connection-state img[alt="SWARM octopus holding disconnected cable ends"]').count(), 1);
  assert.equal(await offlinePage.locator("#error-surface").isVisible(), false);
  assert.equal(await offlinePage.locator("#view-overview").isVisible(), false);
  assert.equal(await offlinePage.getByRole("tab", { name: "Diagnostics" }).isVisible(), false);
  assert.deepEqual(await offlinePage.locator(".app-shell").evaluate((shell) => ({ hidden: shell.hidden, inert: shell.inert, ariaHidden: shell.getAttribute("aria-hidden") })), { hidden: true, inert: true, ariaHidden: "true" });
  const desktopOfflineBox = await offlinePage.locator("#connection-state").boundingBox();
  assert.ok(desktopOfflineBox && desktopOfflineBox.x >= 0 && desktopOfflineBox.y >= 0 && desktopOfflineBox.width <= 1024 && desktopOfflineBox.height <= 760);
  await offlinePage.setViewportSize({ width: 390, height: 844 });
  const mobileOfflineBox = await offlinePage.locator("#connection-state").boundingBox();
  assert.ok(mobileOfflineBox && mobileOfflineBox.x >= 0 && mobileOfflineBox.y >= 0 && mobileOfflineBox.width <= 390 && mobileOfflineBox.height <= 844);
  connection.offline = false;
  await offlinePage.locator("#overview-content").waitFor({ state: "visible" });
  assert.equal(await offlinePage.locator("#connection-state").isVisible(), false);
  assert.deepEqual(await offlinePage.locator(".app-shell").evaluate((shell) => ({ hidden: shell.hidden, inert: shell.inert, ariaHidden: shell.getAttribute("aria-hidden") })), { hidden: false, inert: false, ariaHidden: null });
  assert.ok(offline.requests.filter((request) => request === "/api/bootstrap").length >= 2);
  await offlinePage.getByRole("tab", { name: "Settings" }).click();
  await offlinePage.locator("#view-settings").waitFor({ state: "visible" });
  connection.offline = true;
  await offlinePage.getByRole("button", { name: "Refresh overview" }).click();
  await offlinePage.locator("#connection-state").waitFor({ state: "visible" });
  assert.equal(await offlinePage.locator(".app-shell").evaluate((shell) => shell.inert && shell.hidden), true);
  connection.offline = false;
  await offlinePage.locator("#view-settings").waitFor({ state: "visible" });
  assert.equal(await offlinePage.locator("#connection-state").isVisible(), false);
  assert.equal(await offlinePage.locator("#tab-settings").getAttribute("aria-selected"), "true");
  await offlinePage.close();

  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const { runtimeErrors, requests } = await mount(page, scopedFixture());

  assert.equal(await page.locator("#view-title").textContent(), "Overview");
  assert.equal(await page.locator('[role="tab"]').count(), 6);
  assert.equal(await page.locator("#tab-overview use").getAttribute("href"), "#lucide-house");
  assert.equal(await page.locator("#tab-hierarchy use").getAttribute("href"), "#lucide-network");
  assert.equal(await page.locator("#tab-kanban use").getAttribute("href"), "#lucide-columns-3");
  assert.equal(await page.locator("#tab-diagnostics use").getAttribute("href"), "#lucide-activity");
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
  assert.equal(await page.locator("#overview-monitoring-heading").textContent(), "Current work");
  assert.equal(await page.locator("#usage-total").textContent(), "1K");
  assert.equal(await page.locator("#usage-rate").textContent(), "42 / min");
  assert.equal(await page.locator("#project-progress-section").isVisible(), false);
  assert.equal(await page.locator("#overview-monitoring-health-state").textContent(), "Needs attention");
  assert.match(await page.locator("#overview-monitoring-health-note").textContent(), /3 visible lanes need attention/);
  assert.match(await page.locator("#overview-project-cards").textContent(), /Blocker\s*Visual polish/);
  assert.equal(await page.locator("#overview-evidence-gallery img").count(), 0);
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
  assert.equal(await page.locator("#project-navigation [data-ctrl-id]").count(), 0);
  assert.equal(await page.locator("#scope-context strong").textContent(), "swarm");
  assert.match(await page.locator("#overview-project-cards").textContent(), /Review screenshots|Evidence review/);
  assert.ok(requests.some((request) => request.includes("/api/usage-history?project_id=project%3Afixture&ctrl_id=&hours=24")));
  await page.getByRole("tab", { name: "Overview" }).click();
  assert.equal(await page.locator("#project-progress-section").isVisible(), true);
  assert.equal(await page.locator("#project-progress-feed > li").count(), 2);
  assert.match(await page.locator("#project-progress-feed").textContent(), /evidence gallery now preserves every registered image/i);
  assert.ok(requests.some((request) => request.includes("/api/project-progress-feed?project_id=project%3Afixture&after_cursor=0")));
  await page.getByRole("button", { name: "1h", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("#usage-heading")?.textContent === "Tokens · 1h");
  assert.ok(requests.some((request) => request.includes("hours=1")));
  await page.getByRole("button", { name: "1d", exact: true }).click();
  await page.waitForFunction(() => document.querySelector("#usage-heading")?.textContent === "Tokens · 1d");
  assert.ok(requests.some((request) => request.includes("hours=24")));

  await page.getByRole("button", { name: "Flowwweb" }).click();
  assert.equal(await page.locator("#scope-context strong").textContent(), "Flowwweb");

  await page.locator("#tab-diagnostics").focus();
  await page.keyboard.press("ArrowUp");
  assert.equal(await page.locator(":focus").getAttribute("id"), "tab-kanban");
  await page.keyboard.press("End");
  assert.equal(await page.locator(":focus").getAttribute("id"), "tab-settings");
  assert.equal(await page.locator("#view-title").textContent(), "Settings");
  await page.getByRole("tab", { name: "Diagnostics" }).click();
  assert.match(await page.locator("#view-diagnostics").textContent(), /Keep this device healthy/);
  assert.equal(await page.locator("#scope-context strong").textContent(), "Flowwweb");
  await page.getByRole("tab", { name: "Hierarchy" }).click();
  assert.match(await page.locator("#hierarchy-list").textContent(), /Confirm webhooks/);
  await page.getByRole("tab", { name: "Kanban" }).click();
  assert.match(await page.locator("#kanban-board").textContent(), /In progress/);
  assert.match(await page.locator(".kanban-column").nth(1).textContent(), /Confirm webhooks/);
  await page.getByRole("tab", { name: "Settings" }).click();
  assert.match(await page.locator("#settings-grid").textContent(), /Clear history/);
  assert.equal(await page.locator("#settings-scope").inputValue(), "project|project:branch");
  assert.match(await page.locator("#settings-scope").textContent(), /Unassigned planning/);
  assert.match(await page.locator("#settings-scope").textContent(), /Archived project/);
  assert.equal(await page.getByText("Progress feed", { exact: true }).count(), 1);
  assert.equal(await page.locator('[data-config-key="console.project_progress_feed_lines"]').inputValue(), "4");
  assert.equal(await page.getByRole("button", { name: "Manage" }).count(), 1);

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

  const inventoryPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
  const proofControl = { fail: false, feed: imageProofFixture(125) };
  const inventory = await mount(inventoryPage, fixture.overview, { proofControl });
  assert.equal(await inventoryPage.locator("#overview-evidence-gallery .evidence-gallery-item").count(), 4);
  assert.equal(await inventoryPage.locator('[data-evidence-more="121"]').count(), 1);
  await inventoryPage.getByRole("button", { name: /Open 121 more images; 125 images/ }).click();
  const reachableEvidence = new Set();
  while (true) {
    for (const identity of await inventoryPage.locator("#evidence-lightbox-thumbnails [data-evidence-id]").evaluateAll((elements) => elements.map((element) => element.dataset.evidenceId))) reachableEvidence.add(identity);
    if (await inventoryPage.locator("#evidence-page-next").isDisabled()) break;
    await inventoryPage.locator("#evidence-page-next").click();
  }
  assert.equal(reachableEvidence.size, 125);
  assert.equal(await inventoryPage.locator("#evidence-lightbox-thumbnails button").count(), 5);
  assert.equal(await inventoryPage.locator("#evidence-page-status").textContent(), "Images 121–125 of 125");
  await inventoryPage.getByRole("button", { name: "Close evidence gallery" }).click();
  proofControl.fail = true;
  await inventoryPage.locator("#refresh").click();
  await inventoryPage.waitForFunction(() => document.querySelector("#overview-evidence-note")?.textContent?.includes("last received"));
  assert.equal(await inventoryPage.locator('[data-evidence-more="121"]').count(), 1);
  assert.deepEqual(inventory.runtimeErrors, []);
  await inventoryPage.close();

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

  const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const mobile = await mount(mobilePage, scopedFixture());
  const mobileBar = mobilePage.locator(".mobile-app-bar");
  const menuButton = mobilePage.locator("#mobile-menu-button");
  assert.equal(await mobileBar.isVisible(), true);
  assert.equal(await menuButton.getAttribute("aria-label"), "Open navigation");
  assert.equal(await mobilePage.locator(".nav-list").count(), 1);
  assert.equal(await mobilePage.locator("#console-drawer").getAttribute("aria-hidden"), "true");
  const menuBox = await menuButton.boundingBox();
  const logoBox = await mobilePage.locator(".mobile-app-bar img").boundingBox();
  assert.ok(menuBox && menuBox.width >= 44 && menuBox.height >= 44);
  assert.ok(logoBox && menuBox.x < logoBox.x);
  await menuButton.click();
  await mobilePage.locator("#console-drawer[aria-hidden='false']").waitFor();
  await mobilePage.waitForFunction(() => document.querySelector("#console-drawer")?.getBoundingClientRect().left >= -1);
  assert.equal(await menuButton.getAttribute("aria-expanded"), "true");
  assert.equal(await mobilePage.locator("body").evaluate((element) => getComputedStyle(element).overflow), "hidden");
  assert.equal(await mobilePage.locator(".workspace").evaluate((element) => element.inert), true);
  assert.equal(await mobilePage.locator("#tab-overview").evaluate((element) => element === document.activeElement), true);
  const drawerBox = await mobilePage.locator("#console-drawer").boundingBox();
  const navBox = await mobilePage.locator("#tab-overview").boundingBox();
  assert.ok(drawerBox && drawerBox.x >= -1 && drawerBox.x + drawerBox.width <= 391);
  assert.ok(navBox && navBox.height >= 44);
  assert.equal(await mobilePage.locator("#project-navigation button").evaluateAll((elements) => elements.every((element) => element.getBoundingClientRect().height >= 44)), true);
  const drawerFocusable = mobilePage.locator('#console-drawer a[href]:visible, #console-drawer button:not([disabled]):not([tabindex="-1"]):visible, #console-drawer [tabindex]:not([tabindex="-1"]):visible');
  const firstDrawerFocusable = drawerFocusable.first();
  const lastDrawerFocusable = drawerFocusable.last();
  await lastDrawerFocusable.focus();
  await mobilePage.keyboard.press("Tab");
  assert.equal(await firstDrawerFocusable.evaluate((element) => element === document.activeElement), true);
  await mobilePage.keyboard.press("Shift+Tab");
  assert.equal(await lastDrawerFocusable.evaluate((element) => element === document.activeElement), true);
  await mobilePage.keyboard.press("Escape");
  assert.equal(await mobilePage.locator("#console-drawer").getAttribute("aria-hidden"), "true");
  assert.equal(await mobilePage.locator(".workspace").evaluate((element) => element.inert), false);
  assert.equal(await menuButton.evaluate((element) => element === document.activeElement), true);
  await menuButton.click();
  await mobilePage.locator("#drawer-backdrop").click({ position: { x: 380, y: 400 } });
  assert.equal(await menuButton.getAttribute("aria-expanded"), "false");
  for (const [label, panel] of [["Overview", "#view-overview"], ["Dashboard", "#view-dashboard"], ["Hierarchy", "#view-hierarchy"], ["Kanban", "#view-kanban"], ["Settings", "#view-settings"]]) {
    await menuButton.click();
    await mobilePage.getByRole("tab", { name: label }).click();
    assert.equal(await mobilePage.locator(panel).isVisible(), true);
    assert.equal(await menuButton.getAttribute("aria-expanded"), "false");
    const bar = await mobileBar.boundingBox();
    const top = await mobilePage.locator(".topbar").boundingBox();
    const active = await mobilePage.locator(`${panel}.is-active`).boundingBox();
    assert.ok(bar && top && top.y >= bar.y + bar.height - 1, `${label} topbar collides with mobile app bar`);
    assert.ok(top && active && active.y >= top.y + top.height - 1, `${label} content collides with topbar`);
    assert.equal(await mobilePage.locator("[data-qc-scope]").evaluate((element) => element.scrollWidth > element.clientWidth + 1), false);
  }
  await menuButton.click();
  await mobilePage.locator("#console-drawer[aria-hidden='false']").waitFor();
  await mobilePage.waitForFunction(() => document.querySelector("#console-drawer")?.getBoundingClientRect().left >= -1);
  assert.equal(await mobilePage.locator("#tab-settings").evaluate((element) => element === document.activeElement), true);
  const settingsDrawerFocusable = mobilePage.locator('#console-drawer a[href]:visible, #console-drawer button:not([disabled]):not([tabindex="-1"]):visible, #console-drawer [tabindex]:not([tabindex="-1"]):visible');
  await mobilePage.keyboard.press("Shift+Tab");
  assert.equal(await settingsDrawerFocusable.last().evaluate((element) => element === document.activeElement), true);
  await mobilePage.keyboard.press("Tab");
  assert.equal(await mobilePage.locator("#tab-settings").evaluate((element) => element === document.activeElement), true);
  await mobilePage.keyboard.press("Escape");
  assert.deepEqual(mobile.runtimeErrors, []);
  await mobilePage.close();

  for (const viewport of [{ width: 390, height: 844 }, { width: 834, height: 1112 }, { width: 1440, height: 1000 }]) {
    await page.setViewportSize(viewport);
    await page.locator("#tab-overview").evaluate((element) => element.click());
    const overflow = await page.locator("[data-qc-scope]").evaluate((element) => element.scrollWidth > element.clientWidth + 1);
    assert.equal(overflow, false, `horizontal overflow at ${viewport.width}px`);
    const topbarBox = await page.locator(".topbar").boundingBox();
    const activePanelBox = await page.locator("#view-overview.is-active").boundingBox();
    assert.ok(topbarBox && topbarBox.y >= (viewport.width <= 620 ? 64 : 18), `missing shell top inset at ${viewport.width}px`);
    assert.ok(topbarBox && activePanelBox && activePanelBox.y >= topbarBox.y + topbarBox.height - 1, `overview content collides with header at ${viewport.width}px`);
    assert.equal(await page.locator(".mobile-app-bar").isVisible(), viewport.width <= 620);
  }
  assert.deepEqual(runtimeErrors, []);
  console.log("SWARM console Overview UI tests passed");
} finally {
  await browser.close();
}
