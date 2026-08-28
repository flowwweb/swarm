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
const agentsSourceOnly = process.argv.includes("--agents-source-only");
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
if (!agentsSourceOnly) assert.equal(pluginServer, server);
assert.match(server, /"\/assets\/swarm-offline-disconnected\.png": \("swarm-offline-disconnected\.png", "image\/png"\)/);
assert.match(indexHtml, /id="connection-state" hidden role="alert" aria-labelledby="connection-state-title"/);
assert.match(indexHtml, /src="\/assets\/swarm-offline-disconnected\.png" width="1536" height="1024"/);
assert.match(indexHtml, /id="connection-retry"[^>]*>Retry connection<\/button>/);
assert.match(app, /if \(error instanceof TypeError\) throw connectionFailure/);
assert.match(app, /if \(error\.connectionFailure && !state\.overview\) showConnectionState\(\)/);
assert.match(app, /\$\("#connection-retry"\)\.addEventListener\("click", initialize\)/);
assert.match(css, /\.workspace\.is-disconnected \.view \{ display:none; \}/);

for (const [tab, icon] of [["overview", "folder"], ["agents", "users"], ["review", "shield-check"], ["assets", "image"], ["settings", "settings"]]) {
  assert.match(indexHtml, new RegExp(`id="tab-${tab}"[\\s\\S]*?<use href="#lucide-${icon}"></use>`));
  assert.match(indexHtml, new RegExp(`id="lucide-${icon}" viewBox="0 0 24 24"`));
}
for (const retiredTab of ["dashboard", "hierarchy", "kanban", "diagnostics"]) assert.doesNotMatch(indexHtml, new RegExp(`id="tab-${retiredTab}"`));
assert.doesNotMatch(indexHtml, /[⌂▦⑂▥⊙⚙]/);
assert.match(indexHtml, /id="mobile-menu-button"[^>]*aria-label="Open navigation"[^>]*aria-expanded="false"[^>]*aria-controls="console-drawer"/);
assert.match(indexHtml, /class="mobile-app-bar"[\s\S]*?<img src="\/assets\/swarm-wordmark\.png" alt="SWARM"/);
assert.equal((indexHtml.match(/class="nav-list"/g) || []).length, 1);
assert.match(indexHtml, /class="nav-footer"[\s\S]*?id="tab-settings"/);
assert.match(indexHtml, /id="project-scope-filter" aria-label="Project scope"/);
assert.match(indexHtml, /id="notifications"[^>]*aria-label="Notifications"/);
assert.match(indexHtml, /id="profile"[^>]*aria-label="Profile unavailable"[^>]*disabled/);
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

for (const label of ["Current work", "Latest updates", "Recent images", "Tokens · 1d", "Where changes apply", "Manage", "Advanced settings"]) {
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
assert.match(app, /\/api\/project-progress\?/);
assert.match(app, /function renderProjectProgressFeed\(\)/);
assert.match(app, /settingToggle\('console\.project_progress_feed_enabled'/);
assert.match(app, /data-config-key="console\.project_progress_feed_lines"/);
assert.doesNotMatch(app, /setInterval\([^)]*projectProgress|setInterval\([^)]*progressFeed/);
for (const tab of ["overview", "roadmap", "lanes", "hierarchy", "proof", "ledger", "logs"]) {
  assert.match(indexHtml, new RegExp(`id="project-tab-${tab}"[^>]*data-project-tab="${tab}"[^>]*role="tab"[^>]*aria-controls="project-tab-panel"`));
}
assert.equal((indexHtml.match(/data-project-tab=/g) || []).length, 7);
assert.match(indexHtml, /id="project-detail" hidden aria-labelledby="project-detail-title"/);
assert.match(indexHtml, /id="project-tab-panel" role="tabpanel" aria-labelledby="project-tab-overview"/);
assert.match(app, /function renderProjectDetail\(\)/);
assert.match(app, /const selectedTabId = "project-tab-" \+ state\.projectTab/);
assert.match(app, /\$\("#project-tab-panel"\)\.setAttribute\("aria-labelledby", selectedTabId\)/);
assert.match(app, /function projectTabMarkup\(tab, progress, nodes\)/);
assert.match(app, /function yieldChartMarkup\(item\)/);
assert.match(app, /Observed tokens/);
assert.match(app, /Admitted scope/);
assert.match(app, /yield-scope-divider/);
assert.match(indexHtml, /id="verified-yield-rows" aria-label="Verified yield by project and task"/);
assert.match(app, /Net admitted scope points per 100k observed tokens/);
assert.doesNotMatch(indexHtml + app, /lines of code|productivity score|leaderboard/i);
assert.match(app, /node\?\.owner_id \|\| node\?\.worker/);
assert.match(indexHtml, /id="view-review"[\s\S]*id="review-list"/);
assert.match(indexHtml, /id="view-assets"[\s\S]*id="asset-gallery"[\s\S]*id="asset-detail"/);
assert.match(app, /function renderReview\(\)/);
assert.match(app, /function renderAssets\(\)/);
assert.match(app, /class="asset-revisions" aria-label="Retained asset revisions"/);
assert.match(app, /Review feedback command is not available/);
assert.match(app, /Proof admission command is not available/);
assert.match(app, /Asset revision command is not available/);
assert.match(app, /Asset approval command is not available/);
assert.doesNotMatch(app, /REVIEW_FEEDBACK_SUBMIT|PROOF_ADMIT|ASSET_REVISION_CREATE|ASSET_APPROVE/);
assert.match(indexHtml, /id="notifications"[^>]*aria-expanded="false"[^>]*aria-controls="notifications-panel"/);
assert.match(indexHtml, /id="notifications-panel"[^>]*hidden tabindex="-1"/);
assert.match(app, /const NOTIFICATION_KINDS = new Set\(\["BLOCKER", "STALLED", "RETRYING", "ETA_DRIFT", "PROOF_INVALIDATED", "TOKEN_OVERRUN"\]\)/);
assert.match(app, /All tentacles moving\./);
assert.match(app, /notificationLastSeen/);
assert.doesNotMatch(app, /notification.*(?:POST|PUT|PATCH)/i);
assert.match(indexHtml, /id="overview-monitoring-health-state"/);
assert.match(app, /function renderOverviewHealth\(nodes\)/);
assert.match(app, /function routeView\(\)/);
assert.match(app, /\["overview", "agents", "review", "assets", "settings"\]/);
assert.doesNotMatch(app.slice(app.indexOf("function routeView"), app.indexOf("function setView")), /dashboard|hierarchy|kanban|diagnostics/);
for (const retiredView of ["dashboard", "hierarchy", "kanban", "diagnostics"]) {
  assert.doesNotMatch(indexHtml, new RegExp(`id="view-${retiredView}"`));
}
for (const retiredRenderer of ["renderDashboard", "renderHierarchy", "renderKanban", "renderDiagnostics", "renderMetrics", "renderTable", "renderProof", "renderBurnRate", "renderOverviewDiagnostics"]) {
  assert.doesNotMatch(app, new RegExp(`function ${retiredRenderer}\\(`));
}
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
assert.doesNotMatch(indexHtml, /id="(?:task-table|proof-feed|burn-chart|overview-diagnostics-heading)"/);
assert.match(app, /Needs attention/);
assert.match(app, /function attentionStatus\(node\)/);
assert.match(app, /\[node\?\.status, node\?\.eta\?\.status\]/);
assert.match(app, /tasks\.find\(needsAttention\)/);
assert.match(app, /project_id: request\.projectId/);
assert.match(app, /ctrl_id: request\.ctrlId/);
assert.match(app, /setInterval\(reportPresence, 60_000\)/);
assert.match(app, /async function refreshMonitoring/);
assert.match(app, /function renderAllViews\(\) \{ renderOverview\(\); renderAgents\(\); renderReview\(\); renderAssets\(\); renderSettings\(\); \}/);
assert.doesNotMatch(app, /\/api\/diagnostics\/history/);
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
assert.match(app, /return items\.filter\(\(item\) => !item\.project_id \|\| item\.project_id === state\.projectId\)/);
const evidenceScopeSource = app.slice(app.indexOf("function scopedProofItems"), app.indexOf("function renderEvidenceLightbox"));
assert.ok(evidenceScopeSource.indexOf("if (state.ctrlId)") < evidenceScopeSource.indexOf('if (state.projectId !== "all"'));
assert.match(app, /function selectedProgressProjectId\(\) \{\s*if \(state\.ctrlId\) return "";/);
assert.doesNotMatch(app, /catch \{ state\.proof = \[\]; \}/);
assert.match(app, /renderEvidenceGallery\(nodes, "#overview-evidence-gallery", "#overview-evidence-note", 4\)/);
assert.doesNotMatch(app, /figcaption/);
assert.match(css, /\.evidence-lightbox/);
assert.match(css, /\.evidence-gallery-item/);
assert.match(app, /subagentDescendants\(card\.ctrlId, tree\)/);
assert.match(app, /params\.set\("project_id", projectId\)/);
assert.doesNotMatch(app, /params\.set\("task_id", state\.ctrlId\)/);
assert.match(app, /\["blocked", "at_risk", "stalled", "critical"\]/);
assert.match(app, /const lanes = nodes\.filter\(\(node\) => !isSubagent\(node\)\);/);
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
const settingsSource = app.slice(app.indexOf("function renderSettings"), app.indexOf("function renderAllViews"));
const settingsMarkupSource = settingsSource.slice(settingsSource.indexOf('$("#settings-grid").innerHTML ='));
const primarySettingsSource = settingsMarkupSource.slice(0, settingsMarkupSource.indexOf('<details class="panel settings-advanced'));
const primaryControlCount = (primarySettingsSource.match(/settingToggle\(/g) || []).length
  + (primarySettingsSource.match(/settingSelect\(/g) || []).length
  + (primarySettingsSource.match(/<input /g) || []).length
  + (primarySettingsSource.match(/<select /g) || []).length
  + 1; // Skills Manage action.
assert.ok(primaryControlCount <= 12, `primary settings controls: ${primaryControlCount}`);
assert.match(settingsSource, /<details class="panel settings-advanced settings-wide"/);
assert.match(app, /function forecastSummary\(node\)/);
assert.match(app, /baseline_eta_end_ms/);
assert.match(app, /delta_from_baseline_ms/);
assert.match(app, /last_material_heartbeat_at_ms/);
assert.match(app, /skillsError/);
assert.match(app, /Try again to refresh this scope/);
assert.match(app, /refreshSkills\(\)\]\)\.then\(renderAllViews\)/);
assert.match(app, /Raw host logs are not projected into project scope/);
assert.match(app, /\.replace\(\/\\blocalhost\\b\/gi, "console"\)/);
assert.match(indexHtml, /id="view-agents"[\s\S]*?Active swarm[\s\S]*?Role library/);
assert.match(indexHtml, /id="agents-panel-active"[\s\S]*?id="agents-panel-library"/);
assert.match(indexHtml, /id="role-library-status" role="status"/);
assert.match(app, /Role manifests unavailable · built-in names only/);
assert.match(app, /function renderAgentHierarchy\(\)/);
assert.match(app, /<details class="agent-project" open>/);
assert.match(app, /agentBranch\(ctrl, "CTRL"/);
assert.match(app, /agentBranch\(lead, "LEAD"/);
assert.match(app, /agentRow\(node, "DOER"\)/);
assert.match(app, /project\.visibility !== "archived" && project\.archived !== true/);
assert.match(app, /Unknown task/);
const expectedProfessions = ["Accountant", "Analyst", "Architect", "Artist", "Auditor", "Critic", "Designer", "Developer", "Educator", "Inventor", "Legal", "Manager", "Marketer", "Operator", "Producer", "Recruiter", "Researcher", "Reviewer", "Security", "Specialist", "Strategist", "Support", "Tester", "Writer"];
for (const profession of expectedProfessions) assert.match(app, new RegExp(`\\["[a-z]+", "${profession}"`));
assert.equal((app.match(/\["[a-z]+", "(?:Accountant|Analyst|Architect|Artist|Auditor|Critic|Designer|Developer|Educator|Inventor|Legal|Manager|Marketer|Operator|Producer|Recruiter|Researcher|Reviewer|Security|Specialist|Strategist|Support|Tester|Writer)"/g) || []).length, 24);
assert.match(app, /function roleManifestProjection\(\)/);
assert.match(app, /state\.roleManifests && Array\.isArray\(state\.roleManifests\.roles\)/);
assert.doesNotMatch(app, /localStorage|sessionStorage/);
assert.match(indexHtml, /id="role-editor" aria-labelledby="role-editor-title"/);
for (const field of ["role-field-id", "role-field-name", "role-field-purpose", "role-field-owns", "role-field-instructions", "role-field-boundaries", "role-field-skills", "role-field-avatar", "role-field-accent", "role-field-version", "role-field-source"]) assert.match(indexHtml, new RegExp(`id="${field}"`));
assert.match(indexHtml, /Tasks already in progress keep the version they started with/);
assert.match(indexHtml, /Choose or upload an approved avatar through Assets/);
assert.match(indexHtml, /data-role-action="choose-avatar" type="button" disabled>Choose in Assets/);
assert.match(indexHtml, /id="role-save" type="submit" disabled/);
assert.match(indexHtml, /id="role-reset" data-role-action="reset" type="button" disabled/);
assert.match(app, /state\.roleEditorTrigger\?\.focus/);
assert.match(app, /\.showModal\(\)/);
assert.match(app, /await api\('\/api\/role-manifests'\)/);
assert.doesNotMatch(app, /ROLE_MANIFEST_CREATE|ROLE_MANIFEST_REVISE|ROLE_MANIFEST_RESET/);
assert.match(css, /\.role-avatar/);
assert.match(css, /\.role-library-grid/);
assert.match(css, /\.role-editor::backdrop/);
assert.match(app, /<span class="role-avatar"[\s\S]*?<use href="#lucide-circle-user-round"><\/use><\/svg>/);
assert.doesNotMatch(css, /\.role-avatar i::before|\.role-avatar i::after/);
assert.match(app, /aria-label="Inspect ' \+ escapeHTML\(role\.name\)/);
assert.match(app, /Read-only until the server accepts the role-manifest command contract/);
assert.match(app, /const items = state\.overview\?\.attention_items \|\| \[\]/);
assert.doesNotMatch(app, /verifiedYieldProjection\(\)\?\.attention_items/);
assert.doesNotMatch(indexHtml + app + css, /--legacy-browser|mockup|prototype reference/i);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.agents-tabs button \{ min-height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.project-tabs button \{ min-height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.review-actions \.icon-button,\.review-actions summary \{ width:44px; height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.settings-card input,\.settings-card select,\.settings-card \.quiet-button \{ min-height:44px; \}/);
assert.match(css, /\.assets-layout/);
assert.match(css, /\.project-overview-grid/);
assert.match(css, /\.notifications-panel/);
assert.match(app, /<details class="panel settings-advanced settings-wide"/);
for (const forbidden of ["hidden usage", "developer instructions", "prompts", "tools", "credentials"]) {
  assert.equal((indexHtml + app).toLowerCase().includes(forbidden), false, `forbidden copy: ${forbidden}`);
}

if (process.argv.includes("--source-only") || agentsSourceOnly) {
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

function sameProjectCtrlProofFixture() {
  return {
    ok: true,
    sequence: 2,
    items: [
      { task_id: "ctrl", project_id: "project:fixture", evidence_id: "ctrl-image", digest: "a".repeat(64), media_type: "image/png", caption: "CTRL evidence" },
      { task_id: "nested-ctrl", project_id: "project:fixture", evidence_id: "nested-ctrl-image", digest: "b".repeat(64), media_type: "image/png", caption: "Other CTRL evidence" },
    ],
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
    if (url.pathname === "/api/project-progress") return route.fulfill(response(overrides.projectProgress || { ok: true, project_id: url.searchParams.get("project_id"), scope_version: 1, status: "UNMEASURED", percent: null, blocks: [], cursor: { event_seq: 0 } }));
    if (url.pathname === "/api/role-manifests") return route.fulfill(response(overrides.roleManifests || { ok: true, schema_version: 1, built_in_count: 24, roles: [], assignments: [], cursor: { event_seq: 0 } }));
    if (url.pathname === "/api/presence") return route.fulfill(response({ ok: true, proof_sequence: proofFeed.sequence || 0 }));
    if (url.pathname === "/api/config") return route.fulfill(response(fixture.config));
    if (url.pathname === "/api/diagnostics") return route.fulfill(response(fixture.diagnostics));
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
const proofFeed = imageProofFixture(6);
  const usageHistory = structuredClone(fixture.usageHistory);
  usageHistory.verified_yield = {
    schema_version: 1,
    formula: "net_scope_points * 100000 / observed_tokens",
    portfolio: { scope: { type: "portfolio", id: "all" }, measurement_state: "MEASURED", confidence: "HIGH", observed_tokens: 120000, yield_per_100k: 2.5, rework_drag: 4, series: [{ observed_tokens: 40000, net_scope_points: 1, scope_version: 1 }, { observed_tokens: 80000, net_scope_points: 2, scope_version: 1 }] },
    projects: [{ scope: { type: "project", id: "project:fixture" }, measurement_state: "MEASURED", confidence: "HIGH", observed_tokens: 80000, yield_per_100k: 3.1, rework_drag: 0, series: [{ observed_tokens: 30000, net_scope_points: 1, scope_version: 1 }, { observed_tokens: 50000, net_scope_points: 1.5, scope_version: 2 }] }],
    tasks: [{ scope: { type: "task", id: "ctrl", project_id: "project:fixture" }, measurement_state: "MEASURED", confidence: "HIGH", observed_tokens: 50000, yield_per_100k: 2, rework_drag: 0, series: [{ observed_tokens: 50000, net_scope_points: 1, scope_version: 1 }] }],
    owners: [{ scope: { type: "owner", id: "CTRL", project_id: "project:fixture" }, measurement_state: "MEASURED", confidence: "PARTIAL", observed_tokens: 50000, yield_per_100k: 2, rework_drag: 0, series: [{ observed_tokens: 50000, net_scope_points: 1, scope_version: 1 }] }],
  };
  const overview = scopedFixture();
  overview.attention_items = [{ id: "attention-1", kind: "ETA_DRIFT", project_id: "project:fixture", task_id: "ctrl", owner_id: "CTRL", material_sequence: 3, material_digest: "attention-digest", observed_at_ms: 1712550180000, severity: "warning", sentence: "Forecast range widened after a dependency changed." }];
  const projectProgress = {
    ok: true,
    project_id: "project:fixture",
    scope_version: 2,
    status: "MEASURED",
    percent: 60,
    cursor: { event_seq: 2 },
    blocks: [
      { milestone_id: "Foundation", block_id: "Identity contract", task_id: "ctrl", owner_id: "CTRL", lifecycle_state: "VERIFIED", measurement_state: "MEASURED", committed_weight: 5, admitted_proof_weight: 5, eta: {}, proof_receipt_ids: ["receipt-1"] },
      { milestone_id: "Interface", block_id: "Console surfaces", task_id: "nested-task", owner_id: "Designer", lifecycle_state: "ACTIVE", measurement_state: "MEASURED", committed_weight: 5, admitted_proof_weight: 1, eta: { end_ms: Date.now() + 3600000 }, proof_receipt_ids: [] },
    ],
  };
  const overrides = { proofFeed, usageByHours: { 1: usageHistory, 24: usageHistory }, projectProgress, projectProgressFeed: fixture.projectProgressFeed };
  try {
    const offlinePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const connection = { offline: true };
    const offline = await mount(offlinePage, scopedFixture(), { connection, waitForConnectionState: true });
    assert.equal(await offlinePage.getByRole("heading", { name: "Local console unavailable" }).count(), 1);
    assert.equal(await offlinePage.locator('#connection-state img[alt="SWARM octopus holding disconnected cable ends"]').count(), 1);
    connection.offline = false;
    await offlinePage.getByRole("button", { name: "Retry connection" }).click();
    await offlinePage.locator("#overview-content").waitFor({ state: "visible" });
    assert.equal(await offlinePage.locator("#connection-state").isVisible(), false);
    assert.ok(offline.requests.filter((request) => request === "/api/bootstrap").length >= 2);
    await offlinePage.close();

    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const desktop = await mount(page, overview, overrides);
    for (const label of ["Projects", "Agents", "Review", "Assets", "Settings"]) assert.equal(await page.getByRole("tab", { name: label, exact: true }).count(), 1);
    for (const retired of ["Dashboard", "Hierarchy", "Kanban", "Diagnostics"]) assert.equal(await page.getByRole("tab", { name: retired, exact: true }).count(), 0);
    assert.equal(await page.locator("#project-scope-filter").isVisible(), true);
    assert.equal(await page.locator("#profile").isDisabled(), true);
    assert.equal(await page.locator("#verified-yield-heading").textContent(), "2.5");
    assert.equal(await page.locator("#notification-unread").textContent(), "1");
    await page.locator("#notifications").click();
    assert.match(await page.locator("#notifications-list").textContent(), /Forecast range widened/);
    await page.locator("#notifications-close").click();
    await page.getByRole("button", { name: /^swarm\b/i }).click();
    await page.locator("#project-detail").waitFor({ state: "visible" });
    assert.equal(await page.locator("[data-project-tab]").count(), 7);
    assert.match(await page.locator("#project-detail-summary").textContent(), /60%/);
    assert.equal(await page.locator(".milestone-ring").count(), 2);
    assert.equal(await page.locator(".project-yield-chart").count(), 1);
    assert.equal(await page.locator(".project-detail-feed > li").count(), 2);
    await page.getByRole("tab", { name: "Roadmap", exact: true }).click();
    assert.equal(await page.locator("#project-tab-panel").getAttribute("aria-labelledby"), "project-tab-roadmap");
    assert.match(await page.locator("#project-tab-panel").textContent(), /Foundation/);
    await page.getByRole("tab", { name: "Lanes", exact: true }).click();
    assert.equal(await page.locator("#project-tab-panel").getAttribute("aria-labelledby"), "project-tab-lanes");
    assert.match(await page.locator("#project-tab-panel").textContent(), /Console surfaces/);
    await page.getByRole("tab", { name: "Agents", exact: true }).click();
    assert.match(await page.locator("#agent-hierarchy").textContent(), /CTRL/);
    await page.getByRole("tab", { name: "Role library", exact: true }).click();
    assert.equal(await page.locator(".role-card").count(), 24);
    assert.match(await page.locator("#role-library-status").textContent(), /server-owned|unavailable|No role manifests/i);
    await page.getByRole("tab", { name: "Review", exact: true }).click();
    assert.equal(await page.locator(".review-row").count(), 6);
    assert.equal(await page.getByRole("button", { name: "Send feedback unavailable" }).first().isDisabled(), true);
    await page.getByRole("tab", { name: "Assets", exact: true }).click();
    assert.equal(await page.locator(".asset-tile").count(), 6);
    assert.match(await page.locator("#asset-detail").textContent(), /Revision history/);
    await page.getByRole("tab", { name: "Settings", exact: true }).click();
    assert.equal(await page.locator("#settings-grid > .settings-card").count(), 3);
    assert.equal(await page.locator("#settings-advanced").count(), 1);
    assert.equal(await page.locator("[data-qc-scope]").evaluate((element) => element.scrollWidth > element.clientWidth + 1), false);
    assert.deepEqual(desktop.runtimeErrors, []);
    await page.close();

    const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const mobile = await mount(mobilePage, scopedFixture(), overrides);
    const menuButton = mobilePage.locator("#mobile-menu-button");
    const menuBox = await menuButton.boundingBox();
    assert.ok(menuBox && menuBox.width >= 44 && menuBox.height >= 44);
    await menuButton.click();
    assert.equal(await mobilePage.locator("#console-drawer").getAttribute("aria-hidden"), "false");
    assert.equal(await mobilePage.locator(".workspace").evaluate((element) => element.inert), true);
    assert.equal(await mobilePage.locator("#project-navigation button").evaluateAll((elements) => elements.every((element) => element.getBoundingClientRect().height >= 44)), true);
    await mobilePage.keyboard.press("Escape");
    assert.equal(await menuButton.evaluate((element) => element === document.activeElement), true);
    assert.equal(await mobilePage.locator("[data-qc-scope]").evaluate((element) => element.scrollWidth > element.clientWidth + 1), false);
    assert.deepEqual(mobile.runtimeErrors, []);
    await mobilePage.close();
    console.log("SWARM console six-screen UI tests passed");
  } finally {
    await browser.close();
  }
