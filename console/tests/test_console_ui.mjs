import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
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
const mascotAsset = fs.readFileSync(path.join(staticRoot, "swarm-mascot-512.png"));
const pluginMascotAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-mascot-512.png"));
const onboardingRoleGroupAsset = fs.readFileSync(path.join(staticRoot, "swarm-guided-tour-role-group.png"));
const pluginOnboardingRoleGroupAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-guided-tour-role-group.png"));
const iconAsset = fs.readFileSync(path.join(staticRoot, "swarm-icon-64.png"));
const pluginIconAsset = fs.readFileSync(path.join(pluginStaticRoot, "swarm-icon-64.png"));
const wordmarkAsset = fs.readFileSync(path.join(repositoryRoot, "skills", "swarm", "assets", "swarm-wordmark.png"));
const documentHtml = indexHtml
  .replace("<head>", '<head><base href="http://swarm.test/">');

const offlineAssetDigest = crypto.createHash("sha256").update(offlineAsset).digest("hex");
assert.equal(offlineAssetDigest, "6f58eb1dc3c77634c0bb476591843a4226ccd73932589c70aae4a25cf02f8650");
assert.deepEqual(pluginOfflineAsset, offlineAsset);
assert.equal(crypto.createHash("sha256").update(mascotAsset).digest("hex"), "afb7e94cb63e994a929211dd8a81d816d2dd5b19d819ec72d81f121474ae8b07");
assert.equal(crypto.createHash("sha256").update(onboardingRoleGroupAsset).digest("hex"), "dc9ed5015aff55402e9f266cfbb59676d2deaa1465a16b634e4064bdf490d48e");
assert.equal(crypto.createHash("sha256").update(iconAsset).digest("hex"), "fbc528b1b7233105a5ddb5a32b1dfed9dbfe1a0db26e0bdb45a4c2d54f3c0bf4");
assert.deepEqual(pluginMascotAsset, mascotAsset);
assert.deepEqual(pluginOnboardingRoleGroupAsset, onboardingRoleGroupAsset);
assert.deepEqual(pluginIconAsset, iconAsset);
assert.equal(pluginCss, css);
assert.equal(pluginApp, app);
assert.equal(pluginIndexHtml, indexHtml);
if (!agentsSourceOnly) assert.equal(pluginServer, server);
assert.match(server, /"\/assets\/swarm-offline-disconnected\.png": \("swarm-offline-disconnected\.png", "image\/png"\)/);
assert.match(server, /"\/assets\/swarm-mascot-512\.png": \("swarm-mascot-512\.png", "image\/png"\)/);
assert.match(server, /"\/assets\/swarm-guided-tour-role-group\.png": \("swarm-guided-tour-role-group\.png", "image\/png"\)/);
assert.match(pluginServer, /"\/assets\/swarm-guided-tour-role-group\.png": \("swarm-guided-tour-role-group\.png", "image\/png"\)/);
assert.match(server, /"\/swarm-icon-64\.png": \("swarm-icon-64\.png", "image\/png"\)/);
assert.match(indexHtml, /id="connection-state" hidden role="alert" aria-labelledby="connection-state-title"/);
assert.match(indexHtml, /src="\/assets\/swarm-offline-disconnected\.png" width="1536" height="1024"/);
assert.match(indexHtml, /id="connection-state-title">Connection lost<\/h2><p>Your work is safe\. SWARM will reconnect when the console is available\.<\/p>/);
assert.match(indexHtml, /id="connection-retry"[^>]*>Retry connection<\/button>/);
assert.match(app, /if \(error instanceof TypeError\) throw connectionFailure/);
assert.match(app, /if \(error\.connectionFailure && !state\.overview\) showConnectionState\(\)/);
assert.match(app, /\$\("#connection-retry"\)\.addEventListener\("click", initialize\)/);
assert.match(app, /\$\("\.app-shell"\)\.classList\.add\("is-disconnected"\)/);
assert.match(app, /\$\("\.app-shell"\)\.classList\.remove\("is-disconnected"\)/);
assert.match(css, /\.app-shell\.is-disconnected > \.mobile-app-bar,[\s\S]*?\.app-shell\.is-disconnected > \.drawer,[\s\S]*?\.app-shell\.is-disconnected > \.drawer-backdrop \{ display:none; \}/);
assert.match(css, /\.app-shell\.is-disconnected \.workspace > :not\(#connection-state\) \{ display:none; \}/);
assert.match(indexHtml, /id="system-health-control"[^>]*aria-label="System health: Reconnecting"[^>]*title="System health: Reconnecting"[^>]*aria-controls="system-health-panel"/);
assert.match(indexHtml, /id="system-health-panel"[^>]*tabindex="-1"[^>]*aria-labelledby="system-health-heading"[\s\S]*?System health[\s\S]*?Reconnecting/);
assert.match(indexHtml, /id="snapshot-status-dot"[^>]*class="status-dot is-reconnecting"|class="status-dot is-reconnecting" id="snapshot-status-dot"/);
assert.doesNotMatch(indexHtml, /class="snapshot-status"|>System healthy</);
for (const status of ["Live", "Reconnecting", "Offline"]) assert.match(app, new RegExp(`(?:title|snapshot)\\.textContent = "${status}`));
assert.match(css, /\.status-dot\.is-reconnecting/);
assert.match(css, /\.status-dot\.is-offline/);

for (const [tab, icon] of [["overview", "layout-dashboard"], ["agents", "users"], ["review", "shield-check"], ["assets", "image"], ["settings", "settings"]]) {
  assert.match(indexHtml, new RegExp(`id="tab-${tab}"[\\s\\S]*?<use href="#lucide-${icon}"></use>`));
  assert.match(indexHtml, new RegExp(`id="lucide-${icon}" viewBox="0 0 24 24"`));
}
for (const retiredTab of ["dashboard", "hierarchy", "kanban", "diagnostics"]) assert.doesNotMatch(indexHtml, new RegExp(`id="tab-${retiredTab}"`));
assert.doesNotMatch(indexHtml, />Graph<\/b>|data-view="graph"/);
assert.doesNotMatch(indexHtml, /[⌂▦⑂▥⊙⚙]/);
assert.match(indexHtml, /id="mobile-menu-button"[^>]*aria-label="Open navigation"[^>]*aria-expanded="false"[^>]*aria-controls="console-drawer"/);
assert.match(indexHtml, /class="mobile-app-bar"[\s\S]*?<img src="\/assets\/swarm-wordmark\.png" alt="SWARM"/);
assert.equal((indexHtml.match(/class="nav-list"/g) || []).length, 1);
assert.match(indexHtml, /class="nav-footer"[\s\S]*?id="tab-settings"/);
assert.match(indexHtml, /id="tab-overview"[\s\S]*?<b>Overview<\/b>/);
assert.equal((indexHtml.match(/id="project-navigation-heading"/g) || []).length, 1);
assert.match(indexHtml, /id="project-navigation-heading">Projects<\/p>[\s\S]*?id="project-navigation"/);
assert.match(indexHtml, /id="project-scope-filter" aria-label="Project scope"/);
assert.match(indexHtml, /id="notifications"[^>]*aria-label="Notifications"/);
assert.match(indexHtml, /id="profile"[^>]*aria-label="Profile unavailable"[^>]*disabled/);
assert.match(indexHtml, /id="profile"[^>]*><svg[\s\S]*?<use href="#lucide-circle-user-round"><\/use><\/svg><\/button>/);
assert.doesNotMatch(indexHtml, /id="profile"[^>]*>[\s\S]*?<span>Profile<\/span>/);
assert.match(css, /\.profile-button \{[^}]*width:40px;[^}]*height:40px;[^}]*border-radius:50%/);
assert.match(indexHtml, /id="onboarding-dialog"[^>]*aria-labelledby="onboarding-dialog-title"[^>]*aria-describedby="onboarding-step-status"/);
assert.match(indexHtml, /id="onboarding-step-status" aria-live="polite">Welcome\. Step 1 of 5\.<\/p>/);
const onboardingWithoutNonvisualStatus = indexHtml.replace(/<p class="sr-only" id="onboarding-step-status"[\s\S]*?<\/p>/, "");
assert.doesNotMatch(onboardingWithoutNonvisualStatus, /Step [1-5] of 5/i);
assert.equal((indexHtml.match(/data-onboarding-step=/g) || []).length, 5);
assert.match(indexHtml, /data-onboarding-step="0"[^>]*aria-label="Show welcome"[^>]*aria-controls="onboarding-panel-1"[^>]*aria-selected="true"[^>]*aria-current="step"/);
for (const control of ["onboarding-close", "onboarding-skip", "onboarding-primary"]) assert.match(indexHtml, new RegExp(`id="${control}"[^>]*type="button"`));
assert.match(indexHtml, /SWARM coordinates focused roles, clear ownership, and proof you can review\./);
assert.match(css, /\.onboarding-dialog \{ width:min\(1040px,calc\(100vw - 48px\)\); height:min\(720px,calc\(100dvh - 48px\)\);/);
assert.match(css, /\.onboarding-shell \{[^}]*padding:clamp\(16px,2\.2vw,28px\);/);
assert.match(css, /\.onboarding-mascot \{ width:clamp\(144px,17vw,196px\);/);
assert.match(css, /\.onboarding-actions \{[^}]*display:grid;[^}]*grid-template-columns:minmax\(44px,1fr\) minmax\(220px,auto\) minmax\(44px,1fr\);/);
assert.match(css, /\.onboarding-actions \.onboarding-skip \{ grid-column:2; grid-row:2;[^}]*\}/);
assert.match(css, /\.onboarding-actions \.primary-action \{ grid-column:2; grid-row:1;[^}]*\}/);
assert.match(indexHtml, /id="onboarding-close"[^>]*aria-label="Close onboarding"/);
assert.match(indexHtml, /class="onboarding-mascot onboarding-artwork" src="\/assets\/swarm-mascot-512\.png" width="512" height="512" alt="" aria-hidden="true"/);
assert.match(indexHtml, /<link rel="icon" type="image\/png" sizes="64x64" href="\/swarm-icon-64\.png"/);
assert.doesNotMatch(indexHtml, /swarm-favicon\.svg|<div class="onboarding-mascot"/);
assert.match(indexHtml, /<h2>One prompt\. A coordinated team\.<\/h2>/);
assert.match(indexHtml, /Prompt[\s\S]*?CTRL[\s\S]*?Designer[\s\S]*?Developer[\s\S]*?Reviewer/);
assert.match(indexHtml, /class="onboarding-flag-mascot onboarding-artwork"[\s\S]*?swarm-mascot-512\.png[\s\S]*?class="onboarding-flag"/);
assert.match(indexHtml, /class="onboarding-flow onboarding-supporting-visual" role="img" aria-label="A prompt enters CTRL, which routes work through three connected lines to Designer, Developer, and Reviewer\."/);
assert.equal((indexHtml.match(/class="onboarding-flow-fanout"[\s\S]*?<i><\/i>/g) || []).length, 1);
assert.match(css, /\.onboarding-flag i \{[^}]*conic-gradient\([^}]*#fff4df[^}]*#ff7a18/);
assert.match(css, /\.onboarding-flow-node\.is-ctrl \{[^}]*clip-path:polygon\(18% 0,82% 0,100% 50%,82% 100%,18% 100%,0 50%\)/);
assert.match(css, /\.onboarding-flow-fanout i:nth-child\(3\) \{ top:83\.33%; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*?\.onboarding-flow \{[^}]*grid-template-columns:66px 24px 70px 28px minmax\(88px,1fr\)/);
assert.match(indexHtml, /<h2>A role for every kind of work\.<\/h2>/);
assert.match(indexHtml, /24 curated roles, ready to work—from development and design to security and content\./);
const onboardingRolePanel = indexHtml.match(/id="onboarding-panel-3"[\s\S]*?<\/section>/)?.[0] || "";
assert.match(onboardingRolePanel, /<img class="onboarding-role-group onboarding-artwork" src="\/assets\/swarm-guided-tour-role-group\.png" width="1920" height="1080" alt="Developer, Designer, Architect, and Security SWARM role mascots working together\." loading="lazy" decoding="async" \/>/);
assert.equal((onboardingRolePanel.match(/<img\b/g) || []).length, 1);
assert.doesNotMatch(onboardingRolePanel, /onboarding-role-examples|data-role-media|role="list"|<article/);
assert.doesNotMatch(app, /ONBOARDING_ROLE_IDS|onboardingRoleExamplesMarkup|renderOnboardingRoleExamples/);
assert.doesNotMatch(css, /onboarding-role-examples|onboarding-role-media/);
assert.match(css, /\.onboarding-role-group \{[^}]*width:min\(700px,100%\);[^}]*max-height:min\(310px,42dvh\);[^}]*height:auto;[^}]*object-fit:contain;/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*?\.onboarding-role-group \{[^}]*width:min\(100%,340px\);[^}]*max-height:min\(220px,30dvh\);/);
assert.match(css, /--motion-enter-duration: 220ms;[\s\S]*?--motion-enter-distance: 8px;[\s\S]*?--motion-stagger: 55ms;/);
assert.match(css, /@keyframes swarm-enter \{ from \{ opacity:0; transform:translateY\(var\(--motion-enter-distance\)\); \} to \{ opacity:1; transform:translateY\(0\); \} \}/);
assert.match(css, /\.view\.is-active:not\(\[hidden\]\) \{ animation:swarm-enter var\(--motion-enter-duration\) var\(--motion-ease\) both; \}/);
assert.match(css, /#onboarding-primary \{ --motion-enter-delay:calc\(var\(--motion-stagger\) \* 4\); \}[\s\S]*?#onboarding-skip \{ --motion-enter-delay:calc\(var\(--motion-stagger\) \* 5\); \}/);
assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?animation:none!important; opacity:1!important; transform:none!important;/);
const onboardingMotionSource = app.match(/function updateOnboardingEntrance\(step\) \{[\s\S]*?\n\}/)?.[0] || "";
assert.match(onboardingMotionSource, /dialog\.dataset\.motionStep === motionStep/);
assert.match(onboardingMotionSource, /dialog\.classList\.remove\("is-step-entering"\)[\s\S]*?void dialog\.offsetWidth;[\s\S]*?dialog\.classList\.add\("is-step-entering"\)/);
assert.doesNotMatch(onboardingMotionSource, /setTimeout|setInterval|requestAnimationFrame/);
assert.match(indexHtml, /<h2>Your project finds its shape\.<\/h2>/);
assert.match(indexHtml, /SWARM turns a project into the useful views it needs—screens, flow maps, tables, and shared project data—automatically\./);
const projectViewsPanel = indexHtml.match(/id="onboarding-panel-4"[\s\S]*?<\/section>/)?.[0] || "";
assert.match(projectViewsPanel, /Your project[\s\S]*?Screens[\s\S]*?App map[\s\S]*?Tables[\s\S]*?Shared data/);
assert.doesNotMatch(projectViewsPanel, /manifest|schema|digest|source of truth/i);
assert.match(indexHtml, /id="onboarding-panel-5"[\s\S]*?<h2>Choose how SWARM works\.<\/h2>[\s\S]*?id="onboarding-configuration"/);
assert.doesNotMatch(indexHtml, /class="onboarding-(topology|evidence)"/);
assert.equal((indexHtml.match(/swarm-mascot-512\.png/g) || []).length, 2);
assert.match(app, /const ONBOARDING_STEPS = \[/);
assert.match(app, /function renderOnboarding\(\)/);
assert.match(app, /dot\.toggleAttribute\("aria-current", selected\)/);
assert.match(app, /if \(selected\) dot\.setAttribute\("aria-current", "step"\)/);
assert.match(app, /panel\.hidden = !selected/);
assert.match(app, /function setOnboardingStep\(step, focusDot = false\)/);
assert.match(app, /state\.onboardingStep === ONBOARDING_STEPS\.length - 1/);
assert.match(app, /state\.onboardingTrigger\?\.focus/);
assert.match(app, /const ONBOARDING_PRESENTATION_KEY = "swarm\.onboarding\.v2\.seen"/);
assert.match(app, /\{ name: "Configuration", primary: "Start using SWARM" \}/);
assert.match(app, /function onboardingConfigurationMarkup\(\)/);
assert.match(app, /function onboardingControlIdentity\(element\)/);
assert.match(app, /function onboardingControlForIdentity\(root, identity\)/);
assert.match(app, /element\.matches\("summary"\)[\s\S]*?return "summary:" \+ summaryOwner\.dataset\.onboardingControl/);
assert.match(app, /kind === "summary"[\s\S]*?querySelector\("summary"\)/);
assert.match(app, /function saveOnboardingConfig\(key, value\)/);
assert.match(app, /let configMutationTail = Promise\.resolve\(\)/);
assert.match(app, /let configAuthorityGeneration = 0/);
assert.match(app, /function saveConfigMutation\(changes\)[\s\S]*?configMutationTail = operation\.then/);
assert.match(app, /function saveConfigMutation\(changes\)[\s\S]*?configAuthorityGeneration \+= 1/);
assert.match(app, /function readConfigState\(previousConfig = state\.config, saveError = ""\)[\s\S]*?let pendingWrites = configMutationTail[\s\S]*?while \(pendingWrites !== configMutationTail\)[\s\S]*?const generation = configAuthorityGeneration[\s\S]*?generation !== configAuthorityGeneration/);
assert.match(app, /state\.onboardingConfigPending\.set\(key, \{ value, focusIdentity \}\)/);
assert.match(app, /state\.onboardingConfigFailures\.set\(key, \{ value, error:/);
assert.match(app, /configEditable\(key\) && !state\.onboardingConfigPending\.has\(key\)/);
assert.match(app, /if \(state\.onboardingStep === ONBOARDING_STEPS\.length - 1 && onboardingConfigBlocked\(\)\) return false/);
assert.match(app, /\$\("#onboarding-primary"\)\.disabled = blocked/);
assert.match(app, /data-onboarding-control="retry-config">Retry/);
const onboardingCloseSource = app.slice(app.indexOf('$("#onboarding-dialog").addEventListener("close"'), app.indexOf('$("#evidence-lightbox").addEventListener("close"'));
assert.doesNotMatch(onboardingCloseSource, /markOnboardingSeen/);
assert.match(onboardingCloseSource, /addEventListener\("cancel"[\s\S]*?event\.preventDefault\(\)[\s\S]*?onboardingCanDismiss\(\)/);
assert.match(app, /Task lifetime and handoff/);
assert.match(app, /Use ChatGPT for eligible work/);
assert.match(app, /Unlimited is available only when the server projects it/);
assert.doesNotMatch(app, /artifact-13|config-usage-first/i);
assert.match(app, /function openOnboarding\(force = false, trigger = null\)/);
assert.match(app, /\(!force && \(state\.onboardingShown \|\| onboardingSeen\(\)\)\)/);
assert.match(app, /data-setting-action="replay-tour" type="button">Replay tour<\/button>/);
assert.match(app, /if \(action === 'replay-tour'\)[\s\S]*openOnboarding\(true, event\.target\.closest\('\[data-setting-action\]'\)\)/);
const onboardingPersistenceStart = app.indexOf("function onboardingSeen");
const onboardingPersistenceEnd = app.indexOf("\nfunction openOnboarding", onboardingPersistenceStart);
const onboardingPersistence = vm.runInNewContext(`(() => { const ONBOARDING_PRESENTATION_KEY = "swarm.onboarding.v2.seen"; ${app.slice(onboardingPersistenceStart, onboardingPersistenceEnd)}; return { onboardingSeen, markOnboardingSeen }; })()`);
const presentationValues = new Map([["unrelated.presentation", "preserve"]]);
const presentationStorage = { getItem: (key) => presentationValues.get(key) ?? null, setItem: (key, value) => presentationValues.set(key, value) };
assert.equal(onboardingPersistence.onboardingSeen(presentationStorage), false);
onboardingPersistence.markOnboardingSeen(presentationStorage);
assert.equal(onboardingPersistence.onboardingSeen(presentationStorage), true);
assert.equal(presentationValues.get("unrelated.presentation"), "preserve");
assert.equal(onboardingPersistence.onboardingSeen({ getItem() { throw new Error("unavailable"); } }), false);
assert.doesNotThrow(() => onboardingPersistence.markOnboardingSeen({ setItem() { throw new Error("unavailable"); } }));
assert.match(css, /\.onboarding-progress button \{[^}]*width:44px; height:44px/);
assert.match(css, /\.onboarding-panel-config \{[^}]*overflow:hidden/);
assert.match(css, /\.onboarding-configuration \{[^}]*overflow-x:hidden; overflow-y:auto/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.onboarding-dialog \{ width:100vw; height:100dvh;/);
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

for (const label of ["Projects", "Latest updates", "Recent images", "Tokens · 1d", "Where changes apply", "Manage", "Advanced settings"]) {
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
for (const tab of ["overview", "roadmap", "lanes", "hierarchy", "proof", "ledger", "ui", "logs"]) {
  assert.match(indexHtml, new RegExp(`id="project-tab-${tab}"[^>]*data-project-tab="${tab}"[^>]*role="tab"[^>]*aria-controls="project-tab-panel"`));
}
assert.equal((indexHtml.match(/data-project-tab=/g) || []).length, 8);
assert.match(indexHtml, /id="project-tab-ui"[^>]*hidden>UI<\/button>/);
assert.match(indexHtml, /id="project-detail" hidden aria-labelledby="project-detail-title"/);
assert.match(indexHtml, /id="project-tab-panel" role="tabpanel" aria-labelledby="project-tab-overview"/);
assert.match(app, /function renderProjectDetail\(\)/);
assert.match(app, /const selectedTabId = "project-tab-" \+ state\.projectTab/);
assert.match(app, /tabPanel\.setAttribute\("aria-labelledby", selectedTabId\)/);
assert.match(app, /function projectTabMarkup\(tab, progress, nodes\)/);
assert.match(app, /function currentProjectView\(\)/);
assert.match(app, /projection && projection\.project_id === projectId && projection\.tab\?\.id === "ui"/);
assert.match(app, /if \(tab === "ui"\) return projectViewMarkup\(\)/);
assert.match(app, /uiTab\.hidden = !projectView/);
assert.match(app, /function openProjectViewEvidence\(screenKey, trigger\)/);
assert.match(app, /function projectViewRequirementGroup\(nodeIds\)/);
assert.match(app, /state\.evidenceImages = evidence\.map\(\(item\) => \(\{ \.\.\.item, project_requirement_summary: requirementSummary \}\)\)/);
assert.match(app, /item\.project_requirement_summary \? " · " \+ item\.project_requirement_summary/);
assert.match(app, /data-project-ui-mode=/);
assert.match(app, /data-project-view-evidence=/);
assert.match(app, /function projectViewMapModel\(projection, selectedGroupId = ""\)/);
assert.match(app, /class="project-ui-flowchart-connectors" aria-hidden="true"/);
assert.match(app, /data-project-map-group=/);
assert.match(app, /function drawProjectViewConnectors\(\)/);
assert.match(app, /function setProjectSelection\(projectId, ctrlId = ""\)[\s\S]*?state\.projectUiGroupId = ""/);
assert.match(app, /\$\$\('\[data-project-map-group\]'\)\.find\(\(element\) => element\.dataset\.projectMapGroup === previousGroupId\)/);
assert.doesNotMatch(app, /data-project-map-group=\\?"['"]?\s*\+\s*previousGroupId/);
assert.match(app, /\["runtime", "data", "state"\]\.includes\(node\.type\)/);
assert.match(app, /Flowchart unavailable\. The accepted map projection could not be rendered safely\./);
assert.doesNotMatch(app, /Sanguine|D&D|Dungeon|project:\/\/swarm/i);
assert.doesNotMatch(app, /setInterval\([^)]*projectView|localStorage[^\n]*projectView|sessionStorage[^\n]*projectView/i);
assert.match(css, /\.project-ui-screens \{[^}]*grid-template-columns:repeat\(3,minmax\(0,1fr\)\)/);
assert.match(css, /\.project-ui-flowchart-connectors \{[^}]*position:absolute;[^}]*z-index:0/);
assert.match(css, /\.project-ui-flowchart-layers \{[^}]*position:relative;[^}]*z-index:1/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.project-ui-flowchart-layer \{[^}]*flex-direction:column/);
assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
assert.match(indexHtml, /id="run-log-overview"[^>]*data-run-log-surface="overview"[^>]*hidden/);
assert.match(indexHtml, /id="run-log-agent"[^>]*data-run-log-surface="agent"[^>]*hidden/);
assert.match(app, /data-run-log-surface="project" aria-label="Project run log"/);
assert.match(app, /api\("\/api\/run-log\?" \+ params\.toString\(\)\)/);
assert.match(app, /new URLSearchParams\(\{ ctrl_id: binding\.ctrlId, project_id: binding\.projectId, after_cursor: String\(previous\.cursor \|\| 0\) \}\)/);
assert.match(app, /if \(binding\.agentId\) params\.set\("agent_id", binding\.agentId\)/);
assert.match(app, /function runLogBindingsForProject\(projectId\)/);
assert.match(app, /project\.ctrl_ids\.map\(\(ctrlId\) => runLogBindingForCtrl\(ctrlId\)\)/);
assert.match(app, /function refreshRunLogs\(\)/);
assert.match(app, /refreshMonitoring[\s\S]*refreshRunLogs\(\)/);
assert.doesNotMatch(app, /setInterval\([^)]*runLog|setTimeout\([^)]*runLog|WebSocket[^\n]*runLog|localStorage[^\n]*runLog|sessionStorage[^\n]*runLog/i);
assert.match(app, /class="run-log-list" role="log" aria-labelledby=/);
assert.doesNotMatch(app, /class="run-log-list" role="log"[^>]*aria-live=/);
assert.match(app, /class="run-log-announcer sr-only" role="status" aria-live="polite" aria-atomic="true"/);
assert.match(app, /data-run-log-latest=/);
assert.match(app, /runLogNearBottom\(scroller\.scrollHeight, scroller\.scrollTop, scroller\.clientHeight\)/);
assert.match(app, /anchorIdentity/);
assert.match(app, /Cursor reset to the retained range/);
assert.match(app, /Showing a bounded retained window/);
assert.match(app, /Offline · showing the last received entries/);
assert.match(app, /Run log unavailable\. Refresh to try again\./);
assert.match(app, /Run log needs a current host-confirmed CTRL binding\./);
assert.match(app, /setDataStatus[\s\S]*renderRunLogSurfaces\(\)/);
assert.match(app, /class="agent-identity"[^\n]*data-run-log-agent=/);
assert.match(app, /const exactCtrlBinding = runLogBindingForCtrl\(ctrl\.id\)/);
assert.match(app, /const bindingFor = \(node\) => exactCtrlBinding \?/);
assert.match(css, /\.run-log-list \{[^}]*max-height:312px;[^}]*overflow-y:auto/);
assert.match(css, /\.run-log-list:focus-visible/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.run-log-new \{ min-height:44px; \}/);
const runLogHelperStart = app.indexOf("function runLogBindingKey");
const runLogHelperEnd = app.indexOf("\nfunction escapeHTML", runLogHelperStart);
assert.ok(runLogHelperStart >= 0 && runLogHelperEnd > runLogHelperStart);
const runLogHelpers = vm.runInNewContext(`(() => { const RUN_LOG_CLIENT_LIMIT = 200; ${app.slice(runLogHelperStart, runLogHelperEnd)}; return { runLogBindingKey, runLogPlanBindingKey, runLogSurfaceStateKey, runLogItemIdentity, runLogResponseMatches, mergeRunLogItems, runLogNearBottom, runLogAnnouncement, runLogReplaceSnapshot, runLogCanAnnounce }; })()`);
const runLogBinding = { projectId: "project:one", ctrlId: "ctrl:one", agentId: "owner:one" };
assert.equal(runLogHelpers.runLogBindingKey(runLogBinding), "project:one|ctrl:one|owner:one");
assert.equal(runLogHelpers.runLogPlanBindingKey({ bindings: [{ projectId: "project:one", ctrlId: "ctrl:two" }, { projectId: "project:one", ctrlId: "ctrl:one" }] }), '["project:one|ctrl:one|","project:one|ctrl:two|"]');
assert.notEqual(runLogHelpers.runLogSurfaceStateKey("project", "project:one|ctrl:one|"), runLogHelpers.runLogSurfaceStateKey("project", "project:one|ctrl:two|"));
assert.equal(runLogHelpers.runLogResponseMatches({ ok: true, scope: { project_id: "project:one", ctrl_id: "ctrl:one", agent_id: "owner:one" }, items: [] }, runLogBinding), true);
assert.equal(runLogHelpers.runLogResponseMatches({ ok: true, scope: { project_id: "project:other", ctrl_id: "ctrl:one", agent_id: "owner:one" }, items: [] }, runLogBinding), false);
const runLogA = { event_id: "event-a", event_digest: "digest-a", event_seq: 4, summary: "Proof was admitted." };
const runLogB = { event_id: "event-b", event_digest: "digest-b", event_seq: 5, summary: "Review was requested." };
const mergedRunLog = runLogHelpers.mergeRunLogItems([runLogA], [runLogA, runLogB], false, 200);
assert.deepEqual(Array.from(mergedRunLog.items, (item) => item.event_id), ["event-a", "event-b"]);
assert.equal(mergedRunLog.added, 1);
assert.deepEqual(Array.from(mergedRunLog.addedItems, (item) => item.event_id), ["event-b"]);
assert.deepEqual(Array.from(runLogHelpers.mergeRunLogItems([runLogA], [runLogB], true, 200).items, (item) => item.event_id), ["event-b"]);
assert.equal(runLogHelpers.mergeRunLogItems([runLogA], [runLogA], true, 200).added, 0);
assert.deepEqual(Array.from(runLogHelpers.mergeRunLogItems([runLogA], [runLogB], false, 1).items, (item) => item.event_id), ["event-b"]);
assert.equal(runLogHelpers.mergeRunLogItems([], [{ ...runLogA, summary: "" }], false, 200).items.length, 0);
assert.equal(runLogHelpers.runLogNearBottom(1000, 660, 300), true);
assert.equal(runLogHelpers.runLogNearBottom(1000, 400, 300), false);
assert.equal(runLogHelpers.runLogAnnouncement([runLogB]), "New run log entry 5: Review was requested.");
assert.equal(runLogHelpers.runLogAnnouncement([runLogA, runLogB]), "2 new run log entries. Latest, 5: Review was requested.");
assert.equal(runLogHelpers.runLogReplaceSnapshot({ initialized: false, items: [], cursor: 0 }, {}), true);
assert.equal(runLogHelpers.runLogCanAnnounce({ initialized: false, items: [], cursor: 0 }, true), false);
assert.equal(runLogHelpers.runLogReplaceSnapshot({ initialized: true, items: [], cursor: 0 }, {}), false);
assert.equal(runLogHelpers.runLogCanAnnounce({ initialized: true, items: [], cursor: 0 }, false), true);
assert.equal(runLogHelpers.runLogReplaceSnapshot({ initialized: true, items: [runLogA], cursor: 4 }, { stale_cursor: true }), true);
assert.equal(runLogHelpers.runLogCanAnnounce({ initialized: true, items: [runLogA], cursor: 4 }, true), false);
const runLogStateStart = app.indexOf("function runLogSurfaceState(surface, bindingKey)");
const runLogStateEnd = app.indexOf("\nfunction runLogEntries", runLogStateStart);
const runLogStateKeyStart = app.indexOf("function runLogSurfaceStateKey");
const runLogStateKeyEnd = app.indexOf("\nfunction runLogItemIdentity", runLogStateKeyStart);
const runLogStateHelpers = vm.runInNewContext(`(() => { const state = { runLogSurfaceStates: new Map() }; ${app.slice(runLogStateKeyStart, runLogStateKeyEnd)} ${app.slice(runLogStateStart, runLogStateEnd)}; return { take: runLogSurfaceState, size: () => state.runLogSurfaceStates.size }; })()`);
runLogStateHelpers.take("project", '["project:one|ctrl:one|"]').newEntries = 4;
assert.equal(runLogStateHelpers.take("project", '["project:one|ctrl:one|"]').newEntries, 4);
assert.equal(runLogStateHelpers.take("project", '["project:one|ctrl:two|"]').newEntries, 0);
assert.equal(runLogStateHelpers.size(), 1);
const runLogSource = app.slice(app.indexOf("function runLogBindingKey"), app.indexOf("function drawLine"));
assert.doesNotMatch(runLogSource, /evidence_refs|raw prompt|terminal output|hidden path/i);
assert.match(runLogSource, /function ensureRunLogShell\(mount, surface\) \{\s*if \(\$\("\.run-log-list", mount\)\) return;/);
const runLogRenderSource = app.slice(app.indexOf("function renderRunLogSurfaces"), app.indexOf("function markRunLogNewEntries"));
assert.doesNotMatch(runLogRenderSource, /mount\.innerHTML/);
assert.match(runLogRenderSource, /const sameBinding = mount\.dataset\.runLogBindingKey === bindingKey/);
assert.match(runLogRenderSource, /const viewport = sameBinding \? captureRunLogViewport\(mount\) : null/);
assert.match(runLogRenderSource, /announcer\.dataset\.revision !== String\(surfaceState\.announcementRevision\)/);
assert.match(runLogSource, /runLogSurfaceState\(surface, runLogPlanBindingKey\(plan\)\)/);
assert.match(runLogSource, /if \(runLogCanAnnounce\(previous, replace\)\) markRunLogNewEntries\(key, merged\.addedItems\)/);
const projectDetailSource = app.slice(app.indexOf("function renderProjectDetail"), app.indexOf("function proofReviewState"));
assert.match(projectDetailSource, /const retainedRunLogMount = state\.projectTab === "logs" && \$\('\[data-run-log-surface="project"\]', tabPanel\)/);
assert.match(projectDetailSource, /if \(!retainedRunLogMount\) tabPanel\.innerHTML = projectTabMarkup/);
const renderOverviewSource = app.slice(app.indexOf("function renderOverview"), app.indexOf("function observedAgentRole"));
const refreshMonitoringSource = app.slice(app.indexOf("async function refreshMonitoring"), app.indexOf("async function refreshCtrlSettings"));
const runLogOuterRenderHarness = vm.runInNewContext(`(() => {
  const runLogMount = { identity: "stable-project-run-log" };
  let panelWrites = 0;
  const tabPanel = {
    setAttribute() {},
    querySelector(selector) { return selector === '[data-run-log-surface="project"]' ? runLogMount : null; },
    get innerHTML() { return ""; },
    set innerHTML(value) { panelWrites += 1; },
  };
  const element = () => ({ hidden: false, textContent: "", innerHTML: "", setAttribute() {} });
  const elements = new Map([
    ["#projects-portfolio", element()], ["#project-detail", element()], ["#view-title", element()], ["#view-subtitle", element()],
    ["#project-detail-title", element()], ["#project-detail-status", element()], ["#project-detail-summary", element()],
    ["#project-tab-panel", tabPanel], ["#project-tab-ui", element()], ["#sync-time", element()],
  ]);
  const tabs = [{ dataset: { projectTab: "logs" }, classList: { toggle() {} }, setAttribute() {}, tabIndex: 0 }];
  const state = { view: "overview", projectTab: "logs", projectProgressStatus: "current", connectionStatus: "reconnecting", proofSequence: 0, overview: null };
  function $(selector, root) { return root === tabPanel ? tabPanel.querySelector(selector) : elements.get(selector); }
  function $$(selector) { return selector === '[data-project-tab]' ? tabs : []; }
  function selectedProgressProjectId() { return "project:one"; }
  function currentProjectView() { return null; }
  function projectGroups() { return [{ id: "project:one", label: "Project One" }]; }
  function selectedProjectProgress() { return null; }
  function scopedNodes() { return []; }
  function projectEta() { return "—"; }
  function humanize(value) { return String(value || ""); }
  function escapeHTML(value) { return String(value ?? ""); }
  function projectTabMarkup() { return '<section data-run-log-surface="project"></section>'; }
  function renderOverviewMetrics() {} function renderOverviewProjectCards() {}
  function renderEvidenceGallery() {} function renderUsage() {} function renderProjectProgressFeed() {} function renderNotifications() {}
  function clearConnectionState() {} function setDataStatus() {} function renderProjectNavigation() {} function renderAgents() {} function renderReview() {} function renderAssets() {} function renderRunLogSurfaces() {}
  async function api() { return { generated_at: 1 }; }
  async function refreshUsageHistory() {} async function refreshNotifications() {} async function refreshRunLogs() {} async function refreshProof() {}
  ${projectDetailSource}
  ${renderOverviewSource}
  ${refreshMonitoringSource}
  return { run: async () => { await refreshMonitoring(0); return { panelWrites, sameMount: tabPanel.querySelector('[data-run-log-surface="project"]') === runLogMount }; } };
})()`);
assert.deepEqual({ ...(await runLogOuterRenderHarness.run()) }, { panelWrites: 0, sameMount: true });
const refreshRunLogBindingSource = app.slice(app.indexOf("async function refreshRunLogBinding"), app.indexOf("async function refreshRunLogs"));
const runLogEmptyBaselineHarness = vm.runInNewContext(`(() => {
  const RUN_LOG_CLIENT_LIMIT = 200;
  ${app.slice(runLogHelperStart, runLogHelperEnd)}
  const binding = { projectId: "project:one", ctrlId: "ctrl:one", agentId: "" };
  const appended = { event_id: "event:first", event_digest: "digest:first", event_seq: 1, project_id: "project:one", ctrl_id: "ctrl:one", summary: "First material event." };
  const responses = [
    { ok: true, scope: { project_id: "project:one", ctrl_id: "ctrl:one", agent_id: "" }, items: [], cursor: { next_event_seq: 0 }, retention: {} },
    { ok: true, scope: { project_id: "project:one", ctrl_id: "ctrl:one", agent_id: "" }, items: [appended], cursor: { next_event_seq: 1 }, retention: {} },
    { ok: true, scope: { project_id: "project:one", ctrl_id: "ctrl:one", agent_id: "" }, items: [appended], cursor: { next_event_seq: 1 }, retention: { stale_cursor: true } },
  ];
  const state = { runLogs: new Map(), runLogRequestGenerations: new Map() };
  const announced = [];
  async function api() { return responses.shift(); }
  function markRunLogNewEntries(key, items) { announced.push(...items); }
  ${refreshRunLogBindingSource}
  return { run: async () => { await refreshRunLogBinding(binding); await refreshRunLogBinding(binding); await refreshRunLogBinding(binding); return { announced, record: state.runLogs.get(runLogBindingKey(binding)) }; } };
})()`, { URLSearchParams });
const emptyBaselineResult = await runLogEmptyBaselineHarness.run();
assert.deepEqual(Array.from(emptyBaselineResult.announced, (item) => item.event_id), ["event:first"]);
assert.equal(emptyBaselineResult.record.initialized, true);
const progressQueueHelperStart = app.indexOf("function projectProgressQueueProjection");
const progressQueueHelperEnd = app.indexOf("\nfunction projectTabMarkup", progressQueueHelperStart);
assert.ok(progressQueueHelperStart >= 0 && progressQueueHelperEnd > progressQueueHelperStart);
const progressQueueHelpers = vm.runInNewContext(`(() => {
  const state = { projectProgressStatus: "current" };
  function selectedProgressProjectId() { return "project:alpha"; }
  function escapeHTML(value) { return String(value ?? ""); }
  function humanize(value) { return String(value ?? ""); }
  function formatDuration(value) { return String(value) + " ms"; }
  function formatEta(value) { return String(value); }
  ${app.slice(progressQueueHelperStart, progressQueueHelperEnd)}
  return { projectProgressQueueProjection, progressQueueRowPresentation, projectProgressQueueSegments, projectProgressQueueRowMarkup, projectProgressQueueMarkup };
})()`);
const progressCursor = { event_seq: 8, event_id: "event-8", event_digest: "digest-8" };
const progressRow = {
  scope_binding: { ctrl_id: "ctrl-a", project_id: "project:alpha", cursor: progressCursor },
  task_id: "task-a", task_name: "Task A", lifecycle: "ACTIVE", queue_state: null, runnable: null,
  progress: { state: "KNOWN", completed_milestones: 1, total_milestones: 2, percent: 50 },
  eta: { state: "KNOWN", start_ms: 10, end_ms: 20, confidence: 80, basis_receipt_ids: ["eta-1"] },
  elapsed: { state: "KNOWN", elapsed_ms: 10 }, freshness: { state: "UNKNOWN", observed_at_ms: 10 },
};
const progressQueueFixture = {
  view_id: "view.project.progress", renderer: "table", project_id: "project:alpha",
  scope_binding: { project_id: "project:alpha", ctrl_ids: ["ctrl-a"], cursor: progressCursor },
  accepted_cursor: progressCursor, status: "CURRENT", available: true,
  segments: [
    { segment_id: "segment.project.progress.active", label: "Active", rows: [progressRow] },
    { segment_id: "segment.project.progress.queue", label: "Queue", rows: [] },
  ],
};
assert.equal(progressQueueHelpers.projectProgressQueueProjection({ status: "MEASURED", cursor: progressCursor, progress_queue: progressQueueFixture }).status, "CURRENT");
assert.equal(progressQueueHelpers.projectProgressQueueProjection({ cursor: { ...progressCursor, event_seq: 7 }, progress_queue: progressQueueFixture }), null);
assert.equal(progressQueueHelpers.projectProgressQueueProjection({ cursor: progressCursor, progress_queue: { ...progressQueueFixture, segments: [...progressQueueFixture.segments].reverse() } }), null);
const unavailableQueue = {
  ...progressQueueFixture,
  scope_binding: { project_id: "project:alpha", ctrl_ids: ["ctrl-a"], cursor: null },
  accepted_cursor: null,
  status: "RESYNC_REQUIRED",
  reason: "MIXED_SCOPE_REJECTED",
  available: false,
  segments: progressQueueFixture.segments.map((segment) => ({ ...segment, rows: [] })),
};
const unavailableProgress = { status: "UNKNOWN", cursor: { event_seq: null, event_id: null, event_digest: null }, progress_queue: unavailableQueue };
assert.equal(progressQueueHelpers.projectProgressQueueProjection(unavailableProgress).status, "RESYNC_REQUIRED");
assert.match(progressQueueHelpers.projectProgressQueueMarkup(unavailableProgress), /—[\s\S]*UNKNOWN[\s\S]*Active and queue are unavailable until a fresh accepted scope is restored/);
assert.doesNotMatch(progressQueueHelpers.projectProgressQueueMarkup(unavailableProgress), /<table/);
const staleProgressRow = progressQueueHelpers.progressQueueRowPresentation(progressRow, true);
assert.deepEqual(
  { progress: staleProgressRow.progress.state, eta: staleProgressRow.eta.state, elapsed: staleProgressRow.elapsed.state, queue: staleProgressRow.queue_state, runnable: staleProgressRow.runnable },
  { progress: "UNKNOWN", eta: "UNKNOWN", elapsed: "UNKNOWN", queue: "UNKNOWN", runnable: false },
);
assert.equal(progressQueueHelpers.projectProgressQueueSegments(progressQueueFixture, false)[0].rows[0].progress.percent, 50);
const blockedRow = {
  ...progressRow,
  lifecycle: "ACTIVE", queue_state: "SCOPED_BLOCKED", runnable: false,
  blocked_recovery: {
    blocked_attempts: 3,
    blocked_critical_path: true,
    blocked_release_condition: { release_event_id: "release-1", release_event_digest: "release-digest", condition: "Owner releases the lane." },
    blocked_suggested_recovery: {
      action: "request_authority", route_id: "route-a", responsible_authority: "owner-lead",
      evidence_receipt_refs: [{ event_id: "receipt-1", event_digest: "receipt-digest" }],
    },
  },
};
const blockedMarkup = progressQueueHelpers.projectProgressQueueRowMarkup(blockedRow, "segment.project.progress.queue");
for (const visible of ["CTRL ctrl-a", "Owner releases the lane.", "route-a", "Critical path", "Yes", "release-1", "release-digest", "request_authority", "owner-lead", "3", "receipt-1", "receipt-digest"]) assert.match(blockedMarkup, new RegExp(visible));
assert.match(blockedMarkup, /<details class="project-progress-recovery"><summary>Recovery details<\/summary>/);
assert.doesNotMatch(progressQueueHelpers.projectProgressQueueRowMarkup({ ...blockedRow, blocked_recovery: { ...blockedRow.blocked_recovery, blocked_suggested_recovery: { ...blockedRow.blocked_recovery.blocked_suggested_recovery, route_id: "" } } }, "segment.project.progress.queue"), /Recovery details/);
const progressQueueSource = app.slice(progressQueueHelperStart, progressQueueHelperEnd);
assert.match(progressQueueSource, /role="progressbar"[^>]*aria-valuetext=/);
assert.match(progressQueueSource, /<table class="project-progress-table">/);
assert.match(progressQueueSource, /segment\.project\.progress\.active/);
assert.match(progressQueueSource, /segment\.project\.progress\.queue/);
assert.doesNotMatch(progressQueueSource, /localStorage|sessionStorage|setInterval|setTimeout|WebSocket|fetch\(/);
assert.match(css, /\.project-progress-table-wrap \{[^}]*overflow-x:auto;/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.project-progress-table tr \{[^}]*display:grid;/);
assert.match(app, /function yieldChartMarkup\(item\)/);
assert.match(app, /Observed tokens/);
assert.match(app, /Admitted scope/);
assert.match(app, /yield-scope-divider/);
assert.match(indexHtml, /id="overview-metrics" aria-label="Overview diagnostics"/);
assert.deepEqual([...indexHtml.matchAll(/data-overview-metric="([^"]+)"/g)].map((match) => match[1]), ["active-work", "needs-attention", "verified-progress", "usage"]);
assert.doesNotMatch(indexHtml, /verified-yield-summary|verified-yield-rows|overview-monitoring-health-state|>Unmeasured</);
assert.match(css, /\.overview-metrics \{[^}]*grid-template-columns:repeat\(4,minmax\(0,1fr\)\)/);
assert.match(css, /\.overview-metric-card \{[^}]*min-height:108px/);
assert.match(app, /function overviewMetricsProjectionValue\(value, expectedScopeId = ""\)/);
assert.match(app, /overviewMetricsProjectionValue\(state\.overview\?\.overview_metrics, overviewMetricsScopeId\(\)\)/);
const overviewMetricsStart = app.indexOf("const OVERVIEW_METRIC_FIELDS");
const overviewMetricsEnd = app.indexOf("\nfunction renderOverviewMetric", overviewMetricsStart);
const overviewMetricHelpers = vm.runInNewContext(`(() => { ${app.slice(overviewMetricsStart, overviewMetricsEnd)}; return { overviewMetricsProjectionValue, overviewMetricPresentation }; })()`);
const knownMetricState = Object.fromEntries(["active_projects", "active_lanes", "actionable_items", "oldest_wait", "admitted_milestones", "admitted_proof", "completed", "total", "percent", "trend", "window", "used_tokens", "remaining_tokens", "burn_rate_series", "coverage"].map((field) => [field, "KNOWN"]));
const overviewMetricFixture = {
  accepted_scope_id: "all", accepted_cursor: { event_seq: 12 },
  active_work: { active_projects: 3, active_lanes: 5 },
  needs_attention: { actionable_items: 2, oldest_wait: { reason: "Waiting for capacity", release_condition: "Capacity returns" } },
  verified_progress: { admitted_milestones: 4, admitted_proof: 7, completed: 6, total: 8, percent: 75, trend: [40, 60, 75] },
  usage: { window: "24h", used_tokens: 125000, remaining_tokens: 75000, burn_rate_series: [1000, 1200, 900], coverage: "complete" },
  field_state: knownMetricState,
};
const acceptedOverviewMetrics = overviewMetricHelpers.overviewMetricsProjectionValue(overviewMetricFixture, "all");
assert.equal(acceptedOverviewMetrics.accepted_scope_id, "all");
assert.equal(overviewMetricHelpers.overviewMetricsProjectionValue(overviewMetricFixture, "project:other"), null);
assert.equal(overviewMetricHelpers.overviewMetricsProjectionValue({ ...overviewMetricFixture, accepted_cursor: null }, "all"), null);
assert.equal(overviewMetricHelpers.overviewMetricsProjectionValue({ ...overviewMetricFixture, field_state: { ...knownMetricState, active_lanes: "STALE" } }, "all"), null);
assert.equal(overviewMetricHelpers.overviewMetricsProjectionValue({ ...overviewMetricFixture, active_work: { ...overviewMetricFixture.active_work, active_projects: null } }, "all"), null);
const metricPresentation = overviewMetricHelpers.overviewMetricPresentation(acceptedOverviewMetrics);
assert.deepEqual([metricPresentation.active.value, metricPresentation.attention.value, metricPresentation.progress.value, metricPresentation.usage.value], ["3 / 5", "2", "75%", "125k used"]);
assert.match(metricPresentation.attention.note, /Waiting for capacity · Capacity returns/);
const unknownMetricPresentation = overviewMetricHelpers.overviewMetricPresentation(null);
assert.deepEqual([unknownMetricPresentation.active.value, unknownMetricPresentation.attention.value, unknownMetricPresentation.progress.value, unknownMetricPresentation.usage.value], ["—", "—", "—", "—"]);
assert.ok(Object.values(unknownMetricPresentation).filter((item) => item && typeof item === "object").every((item) => item.state === "UNKNOWN"));
assert.doesNotMatch(indexHtml + app, /lines of code|productivity score|leaderboard/i);
assert.match(app, /node\?\.owner_id \|\| node\?\.worker/);
assert.match(indexHtml, /id="view-review"[\s\S]*id="review-list"/);
assert.match(indexHtml, /id="view-assets"[\s\S]*id="asset-gallery"[\s\S]*id="asset-detail"/);
assert.match(indexHtml, /class="asset-view-toggle" role="group" aria-label="Asset view"/);
assert.match(indexHtml, /data-asset-view="grid" aria-pressed="true"/);
assert.match(indexHtml, /data-asset-view="list" aria-pressed="false"/);
assert.match(app, /function renderReview\(\)/);
assert.match(app, /function renderAssets\(\)/);
assert.match(app, /assetView: "grid"/);
assert.match(app, /function assetGridMarkup\(item\)/);
assert.match(app, /function assetListMarkup\(item\)/);
const assetGridSource = app.slice(app.indexOf("function assetGridMarkup"), app.indexOf("function assetListMarkup"));
assert.match(assetGridSource, /class="asset-image-button"/);
assert.match(assetGridSource, /class="asset-quick-actions"/);
assert.match(assetGridSource, /aria-label="Open asset details for/);
assert.doesNotMatch(assetGridSource, /<strong>|<small>|asset-list-copy|proofReviewState/);
const assetListSource = app.slice(app.indexOf("function assetListMarkup"), app.indexOf("function renderAssets"));
assert.match(assetListSource, /asset-list-copy/);
assert.match(assetListSource, /proofReviewState\(item\)/);
assert.match(app, /data-asset-detail/);
assert.match(app, /state\.assetView = assetView\.dataset\.assetView === "list" \? "list" : "grid"/);
assert.match(app, /data-asset-image loading="lazy"/);
assert.match(app, /Preview unavailable/);
assert.match(css, /\.asset-image-frame img \{[^}]*object-fit:contain/);
assert.match(css, /\.asset-tile:hover \.asset-quick-actions,\.asset-tile:focus-within \.asset-quick-actions/);
assert.match(css, /@media \(hover: none\) \{[\s\S]*\.asset-quick-actions \{ opacity:1; pointer-events:auto; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.asset-quick-actions \.icon-button \{ width:44px; height:44px; \}/);
assert.match(app, /class="asset-revisions" aria-label="Retained asset revisions"/);
assert.match(app, /Review feedback command is not available/);
assert.match(app, /Proof admission command is not available/);
assert.match(app, /Asset revision command is not available/);
assert.match(app, /Asset approval command is not available/);
assert.doesNotMatch(app, /REVIEW_FEEDBACK_SUBMIT|PROOF_ADMIT|ASSET_REVISION_CREATE|ASSET_APPROVE/);
assert.match(indexHtml, /id="notifications"[^>]*aria-expanded="false"[^>]*aria-controls="notifications-panel"/);
assert.match(indexHtml, /id="notifications-panel" role="dialog"[^>]*aria-labelledby="notifications-heading"[^>]*aria-describedby="notifications-status"[^>]*hidden tabindex="-1"/);
assert.match(indexHtml, /id="notifications-unread-list"/);
assert.match(indexHtml, /id="notifications-recent-list"/);
assert.match(indexHtml, /id="notifications-retry"[^>]*hidden>Try again<\/button>/);
assert.match(app, /All tentacles moving\./);
assert.match(app, /await api\("\/api\/notifications\/seen", \{ method: "POST"/);
assert.match(app, /api\("\/api\/notifications\?" \+ params\.toString\(\)\)/);
assert.doesNotMatch(app, /notificationLastSeen|overview\?\.attention_items|sessionStorage/);
const notificationHelperStart = app.indexOf("const NOTIFICATION_PANEL_UNREAD_LIMIT");
const notificationHelperEnd = app.indexOf("\nfunction notificationBinding", notificationHelperStart);
assert.ok(notificationHelperStart >= 0 && notificationHelperEnd > notificationHelperStart);
const notificationHelpers = vm.runInNewContext(`(() => {${app.slice(notificationHelperStart, notificationHelperEnd)}; return { dedupeNotificationItems, notificationToastPlan, notificationAcknowledgePayload, notificationDismissIds, notificationPanelMessage, notificationNextGeneration, notificationGenerationIsCurrent, notificationFeedMatchesBinding, notificationFeedResult, notificationActionAfterAcknowledgement, notificationActionEntry, notificationNavigateEntry, notificationAcknowledgementFlight, notificationSafeTarget }; })()`);
const unreadA = { id: "a".repeat(64), severity: "warning", material_sequence: 4 };
const unreadB = { id: "b".repeat(64), severity: "critical", material_sequence: 3 };
const notificationBindingFixture = { projectId: "project:one", ctrlId: "ctrl:one" };
const exactActionItem = { ...unreadA, project_id: "project:one", ctrl_id: "ctrl:one", action_target: { view: "review", project_id: "project:one", ctrl_id: "ctrl:one", task_id: "task", subject_id: "proof" } };
assert.deepEqual(Array.from(notificationHelpers.dedupeNotificationItems([unreadA, unreadA, unreadB]), (item) => item.id), [unreadA.id, unreadB.id]);
const burst = notificationHelpers.notificationToastPlan([unreadA, unreadB], new Set());
assert.equal(burst.item.id, unreadB.id);
assert.equal(burst.additionalCount, 1);
assert.deepEqual(Array.from(burst.presentedIds), [unreadA.id, unreadB.id]);
assert.equal(notificationHelpers.notificationToastPlan([unreadB, unreadA], new Set(burst.presentedIds)).item, null);
assert.equal(notificationHelpers.notificationToastPlan([{ ...unreadA, id: "c".repeat(64) }], new Set(burst.presentedIds)).item.id, "c".repeat(64));
assert.deepEqual(JSON.parse(JSON.stringify(notificationHelpers.notificationAcknowledgePayload({ ctrlId: "ctrl", projectId: "project:one" }, [unreadA.id]))), { ctrl_id: "ctrl", project_id: "project:one", notification_ids: [unreadA.id] });
assert.deepEqual(Array.from(notificationHelpers.notificationDismissIds({ item: unreadA }, false)), []);
assert.deepEqual(Array.from(notificationHelpers.notificationDismissIds({ item: unreadA }, true)), [unreadA.id]);
assert.equal(notificationHelpers.notificationSafeTarget(exactActionItem, notificationBindingFixture).view, "review");
assert.equal(notificationHelpers.notificationSafeTarget({ ...exactActionItem, action_target: { ...exactActionItem.action_target, view: "settings" } }, notificationBindingFixture), null);
assert.equal(notificationHelpers.notificationSafeTarget({ ...exactActionItem, project_id: "project:other", action_target: { ...exactActionItem.action_target, project_id: "project:other" } }, notificationBindingFixture), null);
assert.equal(notificationHelpers.notificationSafeTarget({ ...exactActionItem, ctrl_id: "ctrl:other", action_target: { ...exactActionItem.action_target, ctrl_id: "ctrl:other" } }, notificationBindingFixture), null);
assert.equal(notificationHelpers.notificationSafeTarget({ ...exactActionItem, action_target: { ...exactActionItem.action_target, route: "https://example.invalid" } }, notificationBindingFixture), null);
assert.equal(notificationHelpers.notificationFeedMatchesBinding({ ok: true, project_id: "project:one", ctrl_id: "ctrl:one", unread: [], recent_seen: [] }, notificationBindingFixture), true);
assert.equal(notificationHelpers.notificationFeedMatchesBinding({ ok: true, project_id: "project:one", ctrl_id: "ctrl:other", unread: [], recent_seen: [] }, notificationBindingFixture), false);
assert.equal(notificationHelpers.notificationActionEntry({ unread: [exactActionItem], recent_seen: [] }, exactActionItem.id).requiresAcknowledgement, true);
assert.equal(notificationHelpers.notificationActionEntry({ unread: [], recent_seen: [exactActionItem] }, exactActionItem.id).requiresAcknowledgement, false);
assert.equal(notificationHelpers.notificationActionEntry({ unread: [], recent_seen: [] }, exactActionItem.id), null);
let attemptedNavigation = 0;
assert.equal(await notificationHelpers.notificationActionAfterAcknowledgement(exactActionItem, async () => false, () => { attemptedNavigation += 1; }), false);
assert.equal(attemptedNavigation, 0);
let acknowledgementPosts = 0;
let resolvePanelAcknowledgement;
const panelAcknowledgementResult = new Promise((resolve) => { resolvePanelAcknowledgement = resolve; });
const panelAcknowledgement = notificationHelpers.notificationAcknowledgementFlight(null, "project:one|ctrl:one", [unreadA.id, unreadB.id], () => {
  acknowledgementPosts += 1;
  return panelAcknowledgementResult;
});
const concurrentUnreadAction = notificationHelpers.notificationAcknowledgementFlight(panelAcknowledgement.flight, "project:one|ctrl:one", [unreadA.id], () => {
  acknowledgementPosts += 1;
  return Promise.resolve(true);
});
assert.equal(panelAcknowledgement.started, true);
assert.equal(concurrentUnreadAction.started, false);
assert.equal(concurrentUnreadAction.flight, panelAcknowledgement.flight);
assert.equal(acknowledgementPosts, 1);
let concurrentSuccessNavigations = 0;
const concurrentSuccessAction = notificationHelpers.notificationNavigateEntry(
  notificationHelpers.notificationActionEntry({ unread: [exactActionItem], recent_seen: [] }, exactActionItem.id),
  async () => concurrentUnreadAction.flight.promise,
  () => { concurrentSuccessNavigations += 1; },
);
resolvePanelAcknowledgement(true);
assert.equal(await concurrentSuccessAction, true);
assert.equal(concurrentSuccessNavigations, 1);
assert.equal(acknowledgementPosts, 1);
const reconciledSeenEntry = notificationHelpers.notificationActionEntry({ unread: [], recent_seen: [exactActionItem] }, exactActionItem.id);
assert.equal(reconciledSeenEntry.requiresAcknowledgement, false);
let recentSeenNavigations = 0;
assert.equal(await notificationHelpers.notificationNavigateEntry(
  reconciledSeenEntry,
  async () => { acknowledgementPosts += 1; return true; },
  () => { recentSeenNavigations += 1; },
), true);
assert.equal(recentSeenNavigations, 1);
assert.equal(acknowledgementPosts, 1);
let resolveFailedPanelAcknowledgement;
const failedPanelAcknowledgementResult = new Promise((resolve) => { resolveFailedPanelAcknowledgement = resolve; });
const failedPanelAcknowledgement = notificationHelpers.notificationAcknowledgementFlight(null, "project:one|ctrl:one", [unreadA.id], () => {
  acknowledgementPosts += 1;
  return failedPanelAcknowledgementResult;
});
const concurrentFailedAction = notificationHelpers.notificationAcknowledgementFlight(failedPanelAcknowledgement.flight, "project:one|ctrl:one", [unreadA.id], () => {
  acknowledgementPosts += 1;
  return Promise.resolve(true);
});
let concurrentFailureNavigations = 0;
const failedActionResult = notificationHelpers.notificationNavigateEntry(
  notificationHelpers.notificationActionEntry({ unread: [exactActionItem], recent_seen: [] }, exactActionItem.id),
  async () => concurrentFailedAction.flight.promise,
  () => { concurrentFailureNavigations += 1; },
);
resolveFailedPanelAcknowledgement(false);
assert.equal(await failedActionResult, false);
assert.equal(concurrentFailureNavigations, 0);
assert.equal(acknowledgementPosts, 2);
assert.equal(notificationHelpers.notificationAcknowledgementFlight(failedPanelAcknowledgement.flight, "project:other|ctrl:other", [unreadA.id], () => Promise.resolve(true)).flight, null);
assert.match(notificationHelpers.notificationPanelMessage("stale", true, "live", "Read status failed. Try again."), /read-only.*Try again/i);
assert.match(notificationHelpers.notificationPanelMessage("current", true, "offline"), /Offline.*read-only/i);
const raceGenerations = new Map();
const raceBinding = "project:one|ctrl:one";
let resolveOldFeed;
const oldFeed = new Promise((resolve) => { resolveOldFeed = resolve; });
const oldGeneration = notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
const lateOldResult = notificationHelpers.notificationFeedResult(raceGenerations, raceBinding, oldGeneration, () => raceBinding, () => oldFeed);
const freshGeneration = notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
const freshResult = await notificationHelpers.notificationFeedResult(raceGenerations, raceBinding, freshGeneration, () => raceBinding, async () => ({ id: "fresh" }));
resolveOldFeed({ id: "old" });
assert.equal(freshResult.id, "fresh");
assert.equal(await lateOldResult, null);
let resolvePreAckFeed;
const preAckFeed = new Promise((resolve) => { resolvePreAckFeed = resolve; });
const preAckGeneration = notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
const invalidatedByAck = notificationHelpers.notificationFeedResult(raceGenerations, raceBinding, preAckGeneration, () => raceBinding, () => preAckFeed);
notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
resolvePreAckFeed({ id: "pre-ack" });
assert.equal(await invalidatedByAck, null);
const postAckGeneration = notificationHelpers.notificationNextGeneration(raceGenerations, raceBinding);
assert.equal((await notificationHelpers.notificationFeedResult(raceGenerations, raceBinding, postAckGeneration, () => raceBinding, async () => ({ id: "post-ack" }))).id, "post-ack");
const notificationSource = app.slice(notificationHelperStart, app.indexOf("\nfunction selectedProjectProgress", notificationHelperStart));
assert.doesNotMatch(notificationSource, /localStorage|sessionStorage|attention_items|setInterval|new Worker|new WebSocket/);
assert.match(notificationSource, /window\.setTimeout\(\(\) => dismissNotificationToast\(false\), 8_000\)/);
const notificationAckSource = app.slice(app.indexOf("async function performNotificationAcknowledgement"), app.indexOf("async function refreshNotifications"));
assert.equal((notificationAckSource.match(/notificationNextGeneration\(state\.notificationRequestGenerations, bindingKey\)/g) || []).length, 3);
assert.match(notificationAckSource, /notificationAcknowledgementFlight\([\s\S]*state\.notificationAckFlight/);
assert.doesNotMatch(notificationAckSource, /notificationAckPending/);
assert.match(app, /await notificationNavigateEntry\(entry, \(identity\) => acknowledgeNotifications\(\[identity\]\), navigateNotification\)/);
assert.match(app, /const ctrlId = ctrlIds\.includes\(project\.active_ctrl_id\) \? project\.active_ctrl_id : ""/);
assert.match(app, /if \(!\$\("#notifications-panel"\)\.hidden && !event\.target\.closest\("#notifications-panel, #notifications"\)\)/);
assert.match(app, /event\.key === "Escape" && !\$\("#notifications-panel"\)\.hidden/);
assert.match(app, /panel\.focus\(\{ preventScroll: true \}\)/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.notification-toast-region \{ top:auto;[^}]*bottom:max\(14px,env\(safe-area-inset-bottom\)\)/);
assert.doesNotMatch(indexHtml, /id="overview-monitoring-health-state"/);
assert.doesNotMatch(app, /function renderOverviewHealth\(nodes\)/);
const healthPresentationStart = app.indexOf("function systemHealthPresentation");
const healthPresentationEnd = app.indexOf("\nfunction renderSystemHealth", healthPresentationStart);
const healthPresentationHarness = vm.runInNewContext(`(() => {
  const state = { connectionStatus: "live", diagnostics: null };
  ${app.slice(healthPresentationStart, healthPresentationEnd)}
  return {
    run(connectionStatus, diagnostics) {
      state.connectionStatus = connectionStatus;
      state.diagnostics = diagnostics;
      return systemHealthPresentation();
    },
  };
})()`);
assert.equal(healthPresentationHarness.run("reconnecting", null).label, "Reconnecting");
assert.equal(healthPresentationHarness.run("offline", null).label, "Offline");
assert.equal(healthPresentationHarness.run("live", null).label, "Unknown");
assert.equal(healthPresentationHarness.run("live", { ok: true, config_valid: true, latest: { payload: { health_state: "HEALTHY" } }, health: { incidents: [], open_requests: [] } }).label, "Healthy");
assert.equal(healthPresentationHarness.run("live", { ok: true, config_valid: true, latest: { payload: { health_state: "HEALTHY" } }, health: { incidents: [{}], open_requests: [] } }).label, "Needs attention");
assert.match(app, /function openSystemHealth\(\)[\s\S]*?setView\("settings"\)[\s\S]*?panel\?\.focus\(\{ preventScroll: true \}\)/);
assert.match(app, /chromeDot\.className = "status-dot" \+ \(presentation\.className \? " " \+ presentation\.className : ""\)/);
assert.match(app, /\$\("#system-health-control"\)\.addEventListener\("click", openSystemHealth\)/);
assert.match(app, /function overviewRequestPath\(\)[\s\S]*?project_id=" \+ encodeURIComponent\(projectId\)/);
assert.match(app, /\$\("#project-navigation"\)\.addEventListener\("click", async \(event\) =>[\s\S]*?await selectProjectScope\(scope\.dataset\.projectId\)/);
assert.match(app, /async function selectProjectScope\(projectId\)[\s\S]*?await refreshOverview\(false\)/);
assert.match(app, /id="system-health-panel"[\s\S]*?Diagnostics[\s\S]*?System health/);
assert.match(css, /\.system-health-control[\s\S]*?\.status-dot\.is-attention/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*?\.icon-button \{ flex: 0 0 46px; height: 46px; \}/);
assert.match(app, /function routeView\(\)/);
assert.match(app, /\["overview", "agents", "review", "assets", "settings"\]/);
assert.doesNotMatch(app.slice(app.indexOf("function routeView"), app.indexOf("function setView")), /dashboard|hierarchy|kanban|diagnostics/);
for (const retiredView of ["dashboard", "hierarchy", "kanban", "diagnostics"]) {
  assert.doesNotMatch(indexHtml, new RegExp(`id="view-${retiredView}"`));
}
for (const retiredRenderer of ["renderDashboard", "renderHierarchy", "renderKanban", "renderDiagnostics", "renderMetrics", "renderTable", "renderProof", "renderBurnRate", "renderOverviewDiagnostics"]) {
  assert.doesNotMatch(app, new RegExp(`function ${retiredRenderer}\\(`));
}
assert.match(app, /renderOverviewProjectCards\(\)/);
const overviewProjectCardsSource = app.slice(app.indexOf("function renderOverviewProjectCards"), app.indexOf("function renderOverview()"));
assert.match(overviewProjectCardsSource, /const roster = savedProjectRoster\(\)/);
assert.match(overviewProjectCardsSource, /Saved projects are unavailable/);
assert.match(overviewProjectCardsSource, /No CTRL/);
assert.doesNotMatch(overviewProjectCardsSource, /currentWorkProjects\(\)|overviewCards\(|scopedCards|slice\(0, 5\)|Unmeasured/);
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
assert.match(app, /function savedProjectRoster\(\)/);
assert.match(app, /project\.visibility === "visible" && project\.archived === false && project\.project_eligibility === "swarm_ctrl"/);
assert.match(app, /controller\.visibility === "visible" && controller\.archived === false && allowedControllerProjects\.get\(controller\.id\) === controller\.project_id/);
assert.match(app, /project\.ctrl_ids\.includes\(ctrl\.id\)/);
assert.doesNotMatch(app, /function activeControllers\(\)/);
assert.doesNotMatch(app, /function hasCurrentOverviewWork\(card\)/);
assert.match(app, /expectedControllerIds\.some\(\(ctrlId\) => !resolvedControllerIds\.has\(ctrlId\)\)/);
assert.match(app, /if \(currentWorkScopeUnavailable\(\)\) return \[\]/);
const currentWorkProjectsSource = app.slice(app.indexOf("function currentWorkProjects"), app.indexOf("function currentWorkControllers"));
const currentWorkControllersSource = app.slice(app.indexOf("function currentWorkControllers"), app.indexOf("function publicLabel"));
const projectGroupsSource = app.slice(app.indexOf("function projectGroups"), app.indexOf("const PROJECT_NAVIGATION_STATUS_RANK"));
const savedProjectRosterSource = app.slice(app.indexOf("const PROJECT_NAVIGATION_STATUS_RANK"), app.indexOf("function scopeLabel"));
const projectNavigationSource = app.slice(app.indexOf("function renderProjectNavigation"), app.indexOf("function runLogBindingForCtrl"));
const overviewCardsSource = app.slice(app.indexOf("function overviewCards"), app.indexOf("function latestReceipt"));
assert.doesNotMatch(currentWorkProjectsSource, /project\.status|active_ctrl/);
assert.doesNotMatch(currentWorkControllersSource, /controller\.status/);
assert.match(projectGroupsSource, /historicalProjects\(\)|historicalControllers\(\)/);
assert.doesNotMatch(projectGroupsSource, /currentWorkProjects\(\)|currentWorkControllers\(\)/);
assert.match(savedProjectRosterSource, /navigation\?\.project_inventory/);
assert.match(savedProjectRosterSource, /inventory\?\.state !== "KNOWN"/);
assert.match(savedProjectRosterSource, /PROJECT_NAVIGATION_STATUS_RANK\[a\.status\] - PROJECT_NAVIGATION_STATUS_RANK\[b\.status\]/);
assert.doesNotMatch(savedProjectRosterSource, /currentWorkProjects\(\)|historicalProjects\(\)|historicalControllers\(\)|projectGroups\(\)/);
assert.match(projectNavigationSource, /const roster = savedProjectRoster\(\)/);
assert.match(projectNavigationSource, /scope-dot is-' \+ project\.status/);
assert.match(projectNavigationSource, /Saved projects unavailable/);
assert.doesNotMatch(projectNavigationSource, /data-project-id="all"|scope-dot is-live|projectGroups\(\)|currentWorkProjects\(\)/);
assert.doesNotMatch(projectNavigationSource, /data-ctrl-id|data-project-toggle|ctrl-subpages/);
assert.doesNotMatch(overviewCardsSource, /node\.role|node\.title/);
const savedProjectRosterHarness = vm.runInNewContext(`((overview) => {
  const state = { overview };
  const publicLabel = (value, fallback) => String(value || fallback);
  ${savedProjectRosterSource}
  return savedProjectRoster();
})`);
const rosterFixture = {
  navigation: {
    project_inventory: { state: "KNOWN", available: true },
    projects: [
      { id: "inactive", name: "Zulu", archived: false, visibility: "visible", project_eligibility: "no_ctrl", ctrl_ids: [], active_ctrl_id: null, task_count: 0, status: "inactive", status_facts: { active: false, stalled: false, inactive: true } },
      { id: "stalled", name: "Beta", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["ctrl-b"], active_ctrl_id: null, task_count: 2, status: "stalled", status_facts: { active: false, stalled: true, inactive: false } },
      { id: "active-b", name: "Charlie", archived: false, visibility: "visible", project_eligibility: "swarm_ctrl", ctrl_ids: ["ctrl-c"], active_ctrl_id: "ctrl-c", task_count: 3, status: "active", status_facts: { active: true, stalled: false, inactive: false } },
      { id: "active-a", name: "Alpha", archived: false, visibility: "visible", project_eligibility: "no_ctrl", ctrl_ids: [], active_ctrl_id: null, task_count: 0, status: "active", status_facts: { active: true, stalled: false, inactive: false } },
    ],
  },
};
assert.deepEqual(Array.from(savedProjectRosterHarness(rosterFixture).projects, (project) => project.id), ["active-a", "active-b", "stalled", "inactive"]);
assert.equal(savedProjectRosterHarness({ navigation: { project_inventory: { state: "UNKNOWN", available: false }, projects: [] } }).state, "UNKNOWN");
const conflictedRoster = structuredClone(rosterFixture);
conflictedRoster.navigation.projects[0].status_facts.active = true;
assert.equal(savedProjectRosterHarness(conflictedRoster).state, "UNKNOWN");
assert.equal(fixture.overview.progress.controllers.ctrl.progress.percent, 80);
assert.equal(fixture.overview.progress.controllers.ctrl.progress.source, "material_receipts");
assert.equal(fixture.overview.navigation.projects[0].project_eligibility, "swarm_ctrl");
assert.match(css, /\.overview-project-card/);
assert.match(css, /\.project-navigation \{ display:flex; min-height:0; flex:1; flex-direction:column;[^}]*overflow:hidden; \}/);
assert.match(css, /#project-navigation \{[^}]*min-height:0;[^}]*overflow-y:auto;[^}]*overscroll-behavior:contain;/);
assert.match(css, /\.nav-footer \{[^}]*flex:0 0 auto;[^}]*margin-top:auto;/);
assert.match(css, /\.project-scope-button \{[^}]*min-height: 44px;/);
assert.ok(indexHtml.indexOf('id="project-tab-logs"') < indexHtml.indexOf('id="project-tab-ui"'));
for (const status of ["active", "stalled", "inactive"]) assert.match(css, new RegExp(`\\.scope-dot\\.is-${status}`));
assert.doesNotMatch(indexHtml, /id="(?:task-table|proof-feed|burn-chart|overview-diagnostics-heading)"/);
assert.match(app, /Needs attention/);
assert.match(app, /project_id: request\.projectId/);
assert.match(app, /ctrl_id: request\.ctrlId/);
assert.match(app, /setInterval\(reportPresence, 60_000\)/);
assert.match(app, /async function refreshMonitoring/);
assert.match(app, /function renderAllViews\(\) \{ renderOverview\(\); renderAgents\(\); renderReview\(\); renderAssets\(\); renderSettings\(\); renderRunLogSurfaces\(\); if \(\$\("#onboarding-dialog"\)\?\.open\) renderOnboarding\(\); \}/);
assert.doesNotMatch(app, /\/api\/diagnostics\/history/);
assert.match(app, /api\(overviewRequestPath\(\), \{ timeoutMs: 15_000 \}\)/);
assert.match(indexHtml, /id="data-status-title">Connecting</);
assert.match(indexHtml, /id="data-status-note">Waiting for data</);
assert.doesNotMatch(indexHtml, /Projects are up to date|<strong>Connected<\/strong>/);
assert.match(app, /active \? \(group\?\.label \|\| "Project"\) : "Overview"/);
assert.match(app, /setDataStatus\("current", state\.overview\?\.generated_at\)/);
assert.match(app, /setDataStatus\(state\.overview \? "stale" : "unavailable"/);
assert.match(app, /Project data request timed out/);
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
assert.match(app, /params\.set\("project_id", projectId\)/);
assert.doesNotMatch(app, /params\.set\("task_id", state\.ctrlId\)/);
const overviewMetricsRenderSource = app.slice(app.indexOf("function renderOverviewMetrics"), app.indexOf("function yieldChartMarkup"));
assert.doesNotMatch(overviewMetricsRenderSource, /scopedNodes|projectGroups|usageHistory|verifiedYieldProjection|attentionStatus/);
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
  + (primarySettingsSource.match(/autoSettingsMarkup\(\)/g) || []).length
  + (primarySettingsSource.match(/<input /g) || []).length
  + (primarySettingsSource.match(/<select /g) || []).length
  + 1; // Skills Manage action.
assert.ok(primaryControlCount <= 12, `primary settings controls: ${primaryControlCount}`);
assert.match(settingsSource, /<details class="panel settings-advanced settings-wide"/);
const autoReadSource = app.slice(app.indexOf("async function refreshAutoStatus"), app.indexOf("async function refreshRoleManifests"));
assert.match(autoReadSource, /await api\('\/api\/auto\?' \+ params\.toString\(\)\)/);
assert.doesNotMatch(autoReadSource, /method:|'POST'|"POST"/);
assert.doesNotMatch(settingsSource, /api\('\/api\/auto/);
assert.match(app, /const command = event\.target\.checked \? "ENABLE" : "DISABLE"/);
assert.match(app, /body: JSON\.stringify\(\{ command, ctrl_id: binding\.ctrlId, project_id: binding\.projectId, request_id: autoRequestId\(command\) \}\)/);
assert.doesNotMatch(app, /RELEASE_UNREACHABLE/);
assert.match(app, /aria-label="Continue eligible work automatically" aria-describedby="auto-continuation-status"/);
assert.match(app, /id="auto-continuation-status" aria-live="polite"/);
const autoPresentationStart = app.indexOf("function autoPresentation");
const autoPresentationEnd = app.indexOf("\n}\n\nfunction autoSettingsMarkup", autoPresentationStart) + 2;
assert.ok(autoPresentationStart >= 0 && autoPresentationEnd > autoPresentationStart, "autoPresentation source is extractable");
const evaluateAutoPresentation = vm.runInNewContext("(" + app.slice(autoPresentationStart, autoPresentationEnd) + ")");
assert.equal(evaluateAutoPresentation({ enabled: true, in_flight: true, attention: { kind: "IN_FLIGHT_OUTCOME_UNVERIFIED", reason: "reconcile retained turn" } })[0], "Active");
assert.equal(evaluateAutoPresentation({ enabled: true, in_flight: false, attention: { kind: "WAIT_USER", reason: "user decision required" } })[0], "Waiting for user");
assert.equal(evaluateAutoPresentation({ enabled: true, in_flight: false, attention: { kind: "TERMINAL_BLOCKED", reason: "release required" } })[0], "Attention");
assert.equal(evaluateAutoPresentation({ enabled: false, in_flight: false, attention: null })[0], "Off");
assert.equal(evaluateAutoPresentation({ enabled: true, in_flight: false, attention: null })[0], "Enabled");
assert.match(app, /state\.autoStatus === "stale"[\s\S]*?last known value is shown read-only/);
assert.match(app, /!current \|\| state\.autoSaving \? ' disabled' : ''/);
assert.match(primarySettingsSource, /autoSettingsMarkup\(\)/);
assert.doesNotMatch(primarySettingsSource, /chatRelaySettingsMarkup\(\)/);
assert.match(settingsSource, /chatRelaySettingsMarkup\(\)/);
assert.match(app, /aria-label="Use ChatGPT for eligible work" aria-describedby="chat-relay-status"/);
assert.match(app, /id="chat-relay-status" aria-live="polite"/);
const chatRelayPresentationStart = app.indexOf("function chatRelayPresentation");
const chatRelayPresentationEnd = app.indexOf("\n}\n\nfunction chatRelayMutation", chatRelayPresentationStart) + 2;
assert.ok(chatRelayPresentationStart >= 0 && chatRelayPresentationEnd > chatRelayPresentationStart, "chatRelayPresentation source is extractable");
const evaluateChatRelayPresentation = vm.runInNewContext("(" + app.slice(chatRelayPresentationStart, chatRelayPresentationEnd) + ")");
const relayOff = { editable: ["chat_relay.enabled"], settings: { chat_relay: { enabled: false } } };
const relayOn = { editable: ["chat_relay.enabled"], settings: { chat_relay: { enabled: true } } };
assert.deepEqual(
  [evaluateChatRelayPresentation(relayOff, "current", false, "").checked, evaluateChatRelayPresentation(relayOff, "current", false, "").disabled, evaluateChatRelayPresentation(relayOff, "current", false, "").title],
  [false, false, "Off"],
);
assert.deepEqual(
  [evaluateChatRelayPresentation(relayOn, "current", false, "").checked, evaluateChatRelayPresentation(relayOn, "current", false, "").disabled, evaluateChatRelayPresentation(relayOn, "current", false, "").title],
  [true, false, "Enabled"],
);
const relayMissing = evaluateChatRelayPresentation({ editable: ["chat_relay.enabled"], settings: {} }, "current", false, "");
assert.deepEqual([relayMissing.checked, relayMissing.disabled, relayMissing.title], [false, true, "Unavailable"]);
const relayManaged = evaluateChatRelayPresentation({ editable: [], settings: { chat_relay: { enabled: false } } }, "current", false, "");
assert.deepEqual([relayManaged.checked, relayManaged.disabled, relayManaged.title], [false, true, "Off"]);
const relayStale = evaluateChatRelayPresentation(relayOn, "stale", false, "Settings could not be loaded.");
assert.deepEqual([relayStale.checked, relayStale.disabled, relayStale.title], [true, true, "Unavailable"]);
assert.match(relayStale.note, /last known value is shown read-only[.] Settings could not be loaded[.]/);
const relaySaving = evaluateChatRelayPresentation(relayOff, "current", true, "");
assert.deepEqual([relaySaving.checked, relaySaving.disabled, relaySaving.title], [false, true, "Saving"]);
const chatRelayMutationStart = app.indexOf("function chatRelayMutation");
const chatRelayMutationEnd = app.indexOf("\n}\n\nfunction chatRelayFailureState", chatRelayMutationStart) + 2;
const evaluateChatRelayMutation = vm.runInNewContext("(" + app.slice(chatRelayMutationStart, chatRelayMutationEnd) + ")");
assert.equal(JSON.stringify(evaluateChatRelayMutation(true)), '{"changes":{"chat_relay.enabled":true}}');
assert.equal(JSON.stringify(evaluateChatRelayMutation(false)), '{"changes":{"chat_relay.enabled":false}}');
const chatRelayFailureStart = app.indexOf("function chatRelayFailureState");
const chatRelayFailureEnd = app.indexOf("\n}\n\nfunction chatRelaySettingsMarkup", chatRelayFailureStart) + 2;
const evaluateChatRelayFailure = vm.runInNewContext("(" + app.slice(chatRelayFailureStart, chatRelayFailureEnd) + ")");
const relayReloaded = evaluateChatRelayFailure(relayOff, relayOn, "Save failed.");
assert.deepEqual([relayReloaded.config.settings.chat_relay.enabled, relayReloaded.configStatus], [true, "current"]);
assert.match(relayReloaded.configError, /Save failed[.] The current server value was reloaded[.]/);
const relayReadbackFailed = evaluateChatRelayFailure(relayOn, null, "Save failed.");
assert.deepEqual([relayReadbackFailed.config.settings.chat_relay.enabled, relayReadbackFailed.configStatus], [true, "stale"]);
assert.match(relayReadbackFailed.configError, /current server value could not be reloaded/);
assert.equal(evaluateChatRelayFailure(null, null, "Save failed.").configStatus, "unavailable");
assert.match(app, /await saveConfigMutation\(chatRelayMutation\(requestedValue\)\.changes\)/);
assert.match(app, /await readConfigState\(previousConfig, saveError\)/);
assert.match(app, /readConfigState\(previousConfig\)/);
assert.equal((app.match(/api\('\/api\/config'\)/g) || []).length, 1, "all config GET readbacks use the guarded authority seam");
assert.doesNotMatch(settingsSource, /api\('\/api\/config'/);
assert.doesNotMatch(app, /\/api\/(?:chat-relay|relay)|CodexAppServerAdapter|chat_relay\.(?:provider|surface|mode)/);
assert.match(app, /function forecastSummary\(node\)/);
assert.match(app, /baseline_eta_end_ms/);
assert.match(app, /delta_from_baseline_ms/);
assert.match(app, /last_material_heartbeat_at_ms/);
assert.match(app, /skillsError/);
assert.match(app, /Try again to refresh this scope/);
assert.match(app, /\$\("#project-navigation"\)\.addEventListener\("click", async \(event\) =>[\s\S]*?await selectProjectScope\(scope\.dataset\.projectId\)/);
assert.doesNotMatch(app, /Raw host logs|terminal output|hidden paths/);
assert.match(app, /\.replace\(\/\\blocalhost\\b\/gi, "console"\)/);
assert.match(indexHtml, /id="view-agents"[\s\S]*?Active swarm[\s\S]*?Role library/);
assert.match(indexHtml, /id="agents-panel-active"[\s\S]*?id="agents-panel-library"/);
assert.match(indexHtml, /id="role-library-status" role="status"/);
assert.match(app, /function renderAgentHierarchy\(\)/);
assert.match(app, /<details class="agent-project" open>/);
assert.match(app, /agentBranch\(ctrl, "CTRL"/);
assert.match(app, /agentBranch\(lead, "LEAD"/);
assert.match(app, /agentRow\(node, "DOER"\)/);
assert.match(app, /project\.visibility !== "archived" && project\.archived !== true/);
assert.match(app, /Unknown task/);
const expectedProfessions = ["Accountant", "Analyst", "Architect", "Artist", "Auditor", "Assistant", "Designer", "Developer", "Educator", "Inventor", "Legal", "Manager", "Marketer", "Operator", "Producer", "Recruiter", "Researcher", "Reviewer", "Security", "Specialist", "Strategist", "Support", "Tester", "Writer"];
function roleManifestFixture() {
  return {
    ok: true,
    schema_version: 1,
    built_in_count: 24,
    roles: expectedProfessions.map((name, index) => {
      const id = name.toLowerCase();
      const digest = String(index + 1).padStart(64, "0");
      const specializations = id === "developer"
        ? ["Game Development", "Developer two", "Developer three", "Developer four"]
        : id === "designer"
          ? ["Game Design", "Designer two", "Designer three", "Designer four"]
          : [`${name} one`, `${name} two`, `${name} three`, `${name} four`];
      return {
        id, name, purpose: `${name} purpose`, owns: [`${name} surface`], instructions: [`Use ${name} judgment`], boundaries: ["No authority transfer"],
        default_skills: [`${id}-skill`], specializations,
        avatar_asset_digest: digest, accent: "#ff6948", version: `${id}-v1`, source: "builtin", provenance: ["fixture"],
        built_in: true, active_version: `${id}-v1`, canonical_version: `${id}-v1`, override_active: false,
        versions: [], source_event_ids: [],
      };
    }),
    assignments: [{ task_id: "nested-task", role_id: "developer", manifest_version: "developer-v1", event_id: "assignment-1", event_seq: 1 }],
    cursor: { event_seq: 1 },
    hierarchy_binding: { project_field: "project_id", ctrl_membership_field: "controller_ids", task_identity_field: "id", assignment_task_field: "task_id", levels: ["PROJECT", "CTRL", "LEAD", "DOER"] },
    command_contract: {
      endpoint: "/api/role-manifests/commands",
      commands: ["ROLE_MANIFEST_CREATE", "ROLE_MANIFEST_REVISE", "ROLE_MANIFEST_RESET"],
      optimistic_concurrency_field: "expected_active_version",
      avatar: { selection_field: "avatar_asset_digest", selection_commands: ["ROLE_MANIFEST_CREATE", "ROLE_MANIFEST_REVISE"], requires_retained_immutable_asset: true, generation_command: null },
    },
    claim_limit: "Server-owned role manifests are projected without transferring task authority.",
  };
}
assert.doesNotMatch(app, /ROLE_PROFESSIONS|\["accountant", "Accountant"\]|\["critic", "Critic"\]/);
assert.match(app, /function roleManifestProjection\(\)/);
assert.match(app, /filtered\.map\(\(\{ role, match \}\) => roleChooserMarkup\(role, match, role\.id === state\.selectedRoleId\)\)\.join\(""\)/);
const roleProjectionStart = app.indexOf("function roleManifestProjectionValue");
const roleProjectionEnd = app.indexOf("\nfunction roleManifestProjection()", roleProjectionStart);
const evaluateRoleProjection = vm.runInNewContext(`(() => { ${app.slice(roleProjectionStart, roleProjectionEnd)}; return roleManifestProjectionValue; })()`);
const validRoleProjection = roleManifestFixture();
assert.equal(evaluateRoleProjection(validRoleProjection).roles.length, 24);
assert.equal(evaluateRoleProjection({ ...validRoleProjection, roles: validRoleProjection.roles.filter((role) => role.id !== "assistant") }), null);
const historicalCriticProjection = { ...validRoleProjection, roles: [...validRoleProjection.roles, { ...validRoleProjection.roles[0], id: "critic", name: "Critic", built_in: false }] };
assert.equal(evaluateRoleProjection(historicalCriticProjection).roles.length, 25);
const roleCurrentStart = app.indexOf("function roleCurrentRecords");
const roleCurrentEnd = app.indexOf("\nfunction roleRecord", roleCurrentStart);
const evaluateRoleCurrentRecords = vm.runInNewContext(`(() => { ${app.slice(roleCurrentStart, roleCurrentEnd)}; return roleCurrentRecords; })()`);
assert.equal(evaluateRoleCurrentRecords(historicalCriticProjection).some((role) => role.id === "critic"), false);
assert.equal(evaluateRoleCurrentRecords(historicalCriticProjection).length, 24);
const roleDisplayStart = app.indexOf("function roleDisplayName");
const roleDisplayEnd = app.indexOf("\nfunction roleAvatar", roleDisplayStart);
const evaluateRoleDisplayName = vm.runInNewContext(`(() => { ${app.slice(roleDisplayStart, roleDisplayEnd)}; return roleDisplayName; })()`);
assert.equal(evaluateRoleDisplayName({ id: "dev", name: "Dev" }), "Dev");
assert.equal(evaluateRoleDisplayName({ id: "developer", name: "Software builder" }), "Software builder");
assert.equal(evaluateRoleDisplayName({ id: "designer", name: "Designer" }), "Designer");
const roleSearchStart = app.indexOf("function roleSearchBuckets");
const roleSearchEnd = app.indexOf("\nfunction roleFilterChipsMarkup", roleSearchStart);
const roleSearchHelpers = vm.runInNewContext(`(() => { function roleSpecializations(role) { return role.specializations || []; } ${app.slice(roleSearchStart, roleSearchEnd)}; return { roleSearchMatch, roleFilterRecords }; })()`);
const searchableRole = { id: "developer", name: "Developer", built_in: true, specializations: ["Game Development"], aliases: ["Coder"], tags: ["Software"], default_skills: ["javascript"], purpose: "Build reliable products" };
for (const [query, label] of [["developer", "profession"], ["game", "specialization"], ["coder", "alias or tag"], ["javascript", "skill"], ["reliable", "purpose"]]) {
  const result = roleSearchHelpers.roleSearchMatch(searchableRole, query, new Set(["profession", "specialization", "alias", "skills", "purpose"]));
  assert.equal(result.matched, true);
  assert.match(result.label, new RegExp(label));
}
assert.equal(roleSearchHelpers.roleSearchMatch(searchableRole, "coder", new Set(["profession"])).matched, false);
assert.equal(roleSearchHelpers.roleFilterRecords([searchableRole], "game", new Set(["builtin"]), new Set(["specialization"])).length, 1);
assert.equal(roleSearchHelpers.roleFilterRecords([searchableRole], "game", new Set(["custom"]), new Set(["specialization"])).length, 0);
assert.equal(evaluateRoleProjection({ ...validRoleProjection, roles: validRoleProjection.roles.map((role) => role.id === "developer" ? { ...role, specializations: role.specializations.slice(0, 3) } : role) }), null);
const customRoleProjection = { ...validRoleProjection, roles: [...validRoleProjection.roles, { ...validRoleProjection.roles[0], id: "custom-helper", name: "Custom helper", source: "custom", built_in: false, specializations: [] }] };
assert.equal(evaluateRoleProjection(customRoleProjection).roles.length, 25);
assert.equal(evaluateRoleProjection({ ...customRoleProjection, roles: customRoleProjection.roles.map((role) => role.id === "custom-helper" ? { ...role, specializations: ["1", "2", "3", "4", "5"] } : role) }), null);
const roleCommandStart = app.indexOf("function roleCommandPayload");
const roleCommandEnd = app.indexOf("\nfunction roleEditorCommand", roleCommandStart);
const roleCommandHelpers = vm.runInNewContext(`(() => { ${app.slice(roleCommandStart, roleCommandEnd)}; return { roleCommandPayload, roleCommandFingerprint, roleCommandReceiptMatches, roleCommandObserved, roleCommandResolution, roleCurrentIdAllowed }; })()`);
const manifestDraft = { name: "Custom helper", purpose: "Help", owns: [], instructions: [], boundaries: [], default_skills: [], specializations: [], avatar_asset_digest: "f".repeat(64), accent: "#ff6948" };
const createPayload = roleCommandHelpers.roleCommandPayload("ROLE_MANIFEST_CREATE", "custom-helper", null, manifestDraft, "event-create", "dedupe-create", 100);
assert.deepEqual(JSON.parse(JSON.stringify(createPayload)), { command: "ROLE_MANIFEST_CREATE", role_id: "custom-helper", event_id: "event-create", dedupe_key: "dedupe-create", expected_active_version: null, provenance: "console:role-library", observed_at_ms: 100, manifest: manifestDraft });
const revisePayload = roleCommandHelpers.roleCommandPayload("ROLE_MANIFEST_REVISE", "developer", "developer-v1", manifestDraft, "event-revise", "dedupe-revise", 101);
assert.equal(revisePayload.expected_active_version, "developer-v1");
const resetPayload = roleCommandHelpers.roleCommandPayload("ROLE_MANIFEST_RESET", "developer", "developer-v2", null, "event-reset", "dedupe-reset", 102);
assert.equal(Object.hasOwn(resetPayload, "manifest"), false);
assert.equal(roleCommandHelpers.roleCommandReceiptMatches({ ok: true, receipt: { command: "ROLE_MANIFEST_REVISE", role_id: "developer", event_id: "event-revise" } }, revisePayload), true);
assert.equal(roleCommandHelpers.roleCommandObserved({ roles: [{ id: "developer", source_event_ids: ["event-revise"] }] }, revisePayload), true);
assert.equal(roleCommandHelpers.roleCommandResolution(null, { status: 409 }, true, false), "conflict");
assert.equal(roleCommandHelpers.roleCommandResolution(null, { status: 400 }, true, false), "rejected");
assert.equal(roleCommandHelpers.roleCommandResolution(null, { status: 403 }, true, false), "rejected");
assert.equal(roleCommandHelpers.roleCommandResolution(null, { status: 500 }, true, false), "ambiguous");
assert.equal(roleCommandHelpers.roleCommandResolution(null, { connectionFailure: true }, true, false), "ambiguous");
assert.equal(roleCommandHelpers.roleCommandResolution({ ok: true }, null, false, false), "accepted-unreadable");
assert.equal(roleCommandHelpers.roleCommandResolution(null, null, true, false), "ambiguous");
assert.equal(roleCommandHelpers.roleCommandResolution(null, { status: 409 }, true, true), "observed");
assert.equal(roleCommandHelpers.roleCurrentIdAllowed("assistant"), true);
assert.equal(roleCommandHelpers.roleCurrentIdAllowed("custom-helper"), true);
assert.equal(roleCommandHelpers.roleCurrentIdAllowed("critic"), false);
assert.equal(roleCommandHelpers.roleCurrentIdAllowed("Critic"), false);
assert.equal(roleCommandHelpers.roleCurrentIdAllowed("unsafe role"), false);
const roleAvatarStart = app.indexOf("function roleAvatarDigestAllowed");
const roleAvatarEnd = app.indexOf("\nfunction roleAvatarDigestValid", roleAvatarStart);
const evaluateRoleAvatarDigest = vm.runInNewContext(`(() => { ${app.slice(roleAvatarStart, roleAvatarEnd)}; return roleAvatarDigestAllowed; })()`);
assert.equal(evaluateRoleAvatarDigest("a".repeat(64), [{ avatar_asset_digest: "a".repeat(64) }], []), true);
assert.equal(evaluateRoleAvatarDigest("b".repeat(64), [], [{ digest: "b".repeat(64) }]), true);
assert.equal(evaluateRoleAvatarDigest("c".repeat(64), [], []), false);
assert.equal((app.match(/window\.localStorage/g) || []).length, 2);
assert.doesNotMatch(app, /sessionStorage/);
assert.match(indexHtml, /id="role-editor" aria-labelledby="role-editor-title"/);
assert.match(indexHtml, /id="role-search" type="search" autocomplete="off" placeholder="Search roles"/);
assert.match(indexHtml, /class="role-filter"[\s\S]*aria-label="Filter roles"[\s\S]*data-role-search-field="profession"[\s\S]*data-role-search-field="specialization"[\s\S]*data-role-search-field="alias"[\s\S]*data-role-search-field="skills"[\s\S]*data-role-search-field="purpose"/);
assert.match(indexHtml, /data-role-type="builtin" checked[\s\S]*data-role-type="custom" checked/);
assert.match(app, /roleSearchFields: new Set\(\["profession", "specialization", "alias", "skills", "purpose"\]\)/);
assert.match(app, /filtered\.map\(\(\{ role, match \}\) => roleChooserMarkup\(role, match, role\.id === state\.selectedRoleId\)\)/);
assert.match(indexHtml, /id="role-library-grid" role="listbox" aria-label="Roles"/);
assert.match(indexHtml, /id="role-library-detail" aria-live="polite"/);
assert.doesNotMatch(app, /Game Development|Game Design/);
for (const field of ["role-field-id", "role-field-name", "role-field-purpose", "role-field-owns", "role-field-instructions", "role-field-boundaries", "role-field-skills", "role-field-avatar", "role-field-accent", "role-field-specializations", "role-field-version", "role-field-source"]) assert.match(indexHtml, new RegExp(`id="${field}"`));
assert.match(indexHtml, /Tasks already in progress keep the version they started with/);
assert.match(indexHtml, /Choose a retained immutable image asset/);
assert.doesNotMatch(indexHtml, /Choose in Assets/);
assert.match(indexHtml, /data-role-action="generate-avatar" type="button" disabled aria-label="Generate avatar" title="Generate avatar"/);
assert.match(app, /function roleSpecializations\(role\)/);
assert.match(app, /role\.specializations[\s\S]*?\.slice\(0, 4\)/);
assert.match(app, /Specializations<\/h4><div>' \+ roleSpecializationsMarkup\(role\)/);
assert.doesNotMatch(indexHtml + app, /Game Development|Game Design/);
assert.match(indexHtml, /id="role-save" type="submit" disabled/);
assert.match(indexHtml, /id="role-reset" data-role-action="reset" type="button" disabled/);
assert.match(app, /state\.roleEditorTrigger = trigger\?\.dataset\.roleAction === "edit"/);
assert.match(app, /\.showModal\(\)/);
assert.match(app, /await api\('\/api\/role-manifests'\)/);
assert.match(app, /await api\("\/api\/role-manifests\/commands"/);
assert.match(app, /const reloaded = await refreshRoleManifests\(\)/);
assert.match(app, /roleCommandResolution\(result, failure, reloaded, observed\)/);
assert.match(app, /Role change rejected:/);
assert.match(app, /if \(!roleCurrentIdAllowed\(roleId\)\) throw new Error\("Choose a safe role ID/);
assert.match(app, /assignment\.task_id \+ " · " \+ \(assignment\.manifest_version/);
assert.match(app, /Active tasks retain their accepted role version/);
assert.match(css, /\.role-avatar/);
assert.match(css, /\.role-library-grid/);
assert.match(css, /\.role-editor::backdrop/);
assert.match(app, /const visual = retained \? '<img[\s\S]*?<use href="#lucide-circle-user-round"><\/use><\/svg>/);
assert.match(app, /return '<span class="role-avatar '/);
assert.match(app, /retained \? 'has-image' : 'is-fallback'/);
assert.doesNotMatch(css, /\.role-avatar i::before|\.role-avatar i::after/);
assert.match(app, /<button class="role-choice/);
assert.match(app, /role="option" aria-label=/);
assert.match(app, /aria-controls="role-library-detail"/);
assert.match(app, /tabindex="' \+ \(selected \? '0' : '-1'\) \+ '"/);
assert.match(app, /class="role-choice-source">' \+ escapeHTML\(sourceLabel\)/);
assert.match(app, /function roleDetailMarkup\(role/);
assert.match(app, /function roleInstructionsMarkup\(items\)/);
assert.match(app, /instructions\.slice\(0, 3\)/);
assert.match(app, /<summary>Show all ' \+ escapeHTML\(instructions\.length\) \+ ' instructions<\/summary>/);
assert.match(app, /aria-label="Edit ' \+ escapeHTML\(displayName\)/);
assert.doesNotMatch(app.slice(app.indexOf("function roleChooserMarkup"), app.indexOf("function renderRoleLibrary")), /active_version|avatar_asset_digest|<code>/);
assert.doesNotMatch(app, /reviewerStancesMarkup|Collaborative strengths, gaps, and clear repairs|Red-team the artifact/);
const roleContentStart = app.indexOf("function roleTextList");
const roleContentEnd = app.indexOf("\nfunction renderRoleLibrary", roleContentStart);
const roleContentRenderers = vm.runInNewContext(`(() => {
  const escapeHTML = (value) => String(value ?? "");
  const roleDisplayName = (role) => role?.name || role?.id || "Unknown role";
  const roleAvatar = () => "";
  const roleSourceLabel = (role) => role?.source === "builtin" ? "Built in" : "Custom role";
  const roleCanMutate = () => true;
  const roleAssignmentsMarkup = () => '<p>No current owners.</p>';
  const roleSpecializationsMarkup = (role) => '<ul>' + role.specializations.map((item) => '<li>' + escapeHTML(item) + '</li>').join("") + '</ul>';
  const roleHasRetainedAvatar = () => false;
  ${app.slice(roleContentStart, roleContentEnd)}
  return { roleChooserMarkup, roleDetailMarkup };
})()`);
const manifestDrivenReviewer = {
  id: "reviewer", name: "Fixture review lead", source: "builtin", purpose: "Fixture purpose", owns: ["Fixture surface"],
  instructions: ["Fixture instruction one", "Fixture instruction two", "Fixture instruction three", "Fixture instruction four"],
  specializations: ["Careful", "Adversarial", "Evidence", "Repair"], default_skills: ["fixture-skill"], boundaries: ["Fixture boundary"],
};
const manifestCard = roleContentRenderers.roleChooserMarkup(manifestDrivenReviewer, { label: "Matched: Fixture review lead · profession" }, true);
const manifestDetail = roleContentRenderers.roleDetailMarkup(manifestDrivenReviewer);
for (const value of ["Fixture review lead", "Fixture purpose", "Fixture surface", "Fixture instruction one", "Fixture instruction four", "Careful", "Adversarial", "fixture-skill", "Fixture boundary"]) assert.match(manifestCard + manifestDetail, new RegExp(value));
assert.doesNotMatch(manifestCard + manifestDetail, /Friendly|Hostile/);
const fixtureStances = roleContentRenderers.roleDetailMarkup({ ...manifestDrivenReviewer, specializations: ["Friendly", "Hostile", "Evidence", "Repair"] });
assert.match(fixtureStances, /Friendly[\s\S]*Hostile/);
assert.match(app, /server exposes no generation command/);
assert.match(app, /generate\.disabled = true/);
assert.match(indexHtml, /id="role-create"[\s\S]*?aria-label="Create custom role"[\s\S]*?<svg[\s\S]*?<\/svg><\/button>/);
assert.doesNotMatch(indexHtml, /id="role-create"[^>]*>[\s\S]*?Create role<\/button>/);
assert.doesNotMatch(app, /verifiedYieldProjection\(\)\?\.attention_items/);
assert.doesNotMatch(indexHtml + app + css, /--legacy-browser|mockup|prototype reference/i);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.agents-tabs button \{ min-height:44px; \}/);
assert.match(css, /\.role-library-layout \{[^}]*grid-template-columns:minmax\(680px,1\.55fr\) minmax\(360px,\.75fr\)/);
assert.match(css, /\.role-library-grid \{[^}]*grid-template-columns:repeat\(4,minmax\(0,1fr\)\)[^}]*overflow-x:hidden; overflow-y:auto; scrollbar-gutter:stable/);
assert.match(css, /\.role-choice \{[^}]*min-height:154px[^}]*grid-template-rows:96px auto/);
assert.match(css, /\.role-choice \.role-avatar \{ width:96px; height:96px; \}/);
assert.match(app, /choice\?\.scrollIntoView\(\{ block: "nearest", inline: "nearest" \}\)/);
assert.match(css, /\.role-detail-sections section,\.reviewer-stances \{[^}]*grid-template-columns:128px minmax\(0,1fr\)/);
assert.match(css, /\.role-library-detail \{[^}]*height:100%[^}]*overflow-y:auto; scrollbar-gutter:stable/);
assert.match(css, /@media \(max-width: 1220px\)[\s\S]*\.role-detail-head \{ grid-template-columns:72px minmax\(0,1fr\);[^}]*\}[\s\S]*\.role-detail-actions \{ grid-column:1 \/ -1; justify-content:flex-end; \}/);
assert.match(css, /@media \(max-width: 860px\)[\s\S]*\.role-detail-actions \.icon-button,\.role-editor-head \.icon-button \{ width:44px; height:44px; flex-basis:44px; \}/);
assert.match(css, /@media \(max-width: 860px\)[\s\S]*\.role-editor-actions \.quiet-button,\.role-editor-actions \.primary-action \{ min-height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.role-library-layout \{ grid-template-columns:1fr; \}[\s\S]*\.role-library-grid \{[^}]*grid-template-columns:repeat\(2,minmax\(0,1fr\)\)[\s\S]*\.role-choice \{ min-height:72px/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.role-filter > summary \{ width:44px; height:44px; \}/);
assert.match(css, /\.app-shell\[data-current-view="overview"\] \.usage-strip \{ display:none; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.profile-button \{ position:fixed;[^}]*right:14px/);
assert.match(css, /\.role-editor-fields input,.role-editor-fields textarea,.role-editor-fields select[\s\S]*?\.role-editor-fields input,.role-editor-fields select \{ min-height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.project-tabs button \{ min-height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.review-actions \.icon-button,\.review-actions summary \{ width:44px; height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.settings-card input,\.settings-card select,\.settings-card \.quiet-button \{ min-height:44px; \}/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.error-surface \{ top:calc\(64px \+ env\(safe-area-inset-top\) \+ 8px\);/);
assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.error-surface button \{ min-height:44px; \}/);
assert.match(css, /\.assets-layout/);
assert.match(css, /\.project-overview-grid/);
assert.match(css, /\.notifications-panel/);
const roleGridTargetStart = app.indexOf("function roleGridTargetIndex");
const roleGridTargetEnd = app.indexOf("\nfunction renderRoleLibrary", roleGridTargetStart);
const roleGridTargetIndex = vm.runInNewContext(`(() => { ${app.slice(roleGridTargetStart, roleGridTargetEnd)}; return roleGridTargetIndex; })()`);
assert.equal(roleGridTargetIndex("ArrowRight", 0, 24, 4), 1);
assert.equal(roleGridTargetIndex("ArrowRight", 3, 24, 4), 3);
assert.equal(roleGridTargetIndex("ArrowDown", 1, 24, 3), 4);
assert.equal(roleGridTargetIndex("ArrowDown", 22, 24, 3), 23);
assert.equal(roleGridTargetIndex("ArrowLeft", 3, 24, 3), 3);
assert.equal(roleGridTargetIndex("Home", 17, 24, 2), 0);
assert.equal(roleGridTargetIndex("End", 0, 24, 2), 23);
assert.match(app, /roleEditorTrigger = trigger\?\.dataset\.roleAction === "edit"[\s\S]*\{ action: "edit", roleId:/);
assert.match(app, /function roleEditorReturnTarget\(origin\)/);
assert.match(app, /if \(trigger && !trigger\.disabled && !trigger\.hidden\) return trigger;/);
assert.match(app, /requestAnimationFrame\(\(\) => \{[\s\S]*roleEditorReturnTarget\(origin\)/);
assert.match(app, /addEventListener\("cancel", \(event\) => \{ event\.preventDefault\(\); closeRoleEditor\(\); \}\)/);
assert.match(app, /addEventListener\("close", restoreRoleEditorFocus\)/);
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

function applyConfigChanges(config, changes) {
  const next = structuredClone(config);
  for (const [key, value] of Object.entries(changes || {})) {
    const parts = key.split(".");
    let cursor = next.settings;
    parts.slice(0, -1).forEach((part) => { cursor = cursor[part] ||= {}; });
    cursor[parts.at(-1)] = value;
  }
  return next;
}

function projectViewFixture() {
  return {
    schema_version: 1,
    project_id: "project:fixture",
    tab: { id: "ui", label: "UI" },
    modes: [{ id: "screens", label: "Screens" }, { id: "map", label: "Map" }],
    screens: [
      {
        id: "overview/default", screen_id: "overview", state_id: "default", label: "Projects overview",
        status: "DESIGNED", devices: ["desktop", "tablet", "mobile"], alternative_count: 3,
        evidence: [
          { evidence_id: "fixture-image-1", digest: "1".padStart(64, "0"), media_type: "image/png", caption: "Overview desktop", device: "desktop", alternative_id: "overview-default" },
          { evidence_id: "fixture-image-2", digest: "2".padStart(64, "0"), media_type: "image/png", caption: "Overview tablet", device: "tablet", alternative_id: "overview-tablet" },
          { evidence_id: "fixture-image-3", digest: "3".padStart(64, "0"), media_type: "image/png", caption: "Overview mobile", device: "mobile", alternative_id: "overview-mobile" },
        ],
      },
      { id: "assets/empty", screen_id: "assets", state_id: "empty", label: "Assets empty", status: "MISSING_DESIGN", devices: [], alternative_count: 0, evidence: [] },
    ],
    map: {
      schema_version: 1,
      flowchart_id: "fixture-app-map",
      version: 1,
      nodes: [
        { id: "workspace", label: "Workspace", type: "group", visibility: "visible", order: 0 },
        { id: "overview", label: "Overview", type: "screen", visibility: "visible", group_id: "workspace", order: 0, screen_key: "overview/default" },
        { id: "assets", label: "Assets", type: "screen", visibility: "conditional", group_id: "workspace", order: 1, screen_key: "assets/empty" },
        { id: "runtime-state", label: "Runtime state", type: "runtime", visibility: "visible", order: 2 },
      ],
      edges: [{ id: "overview-assets", source: "overview", target: "assets", label: "Open assets" }],
    },
    requirements: {
      contract_id: "screen.groups.requirements.v1",
      version: "1.0.0",
      requirement_count: 31,
      counts_by_state: { KNOWN_SATISFIED: 8, PARTIAL: 8, MISSING: 7, UNKNOWN: 8 },
      groups: [
        {
          group_id: "group.overview", label: "Overview", node_ids: ["overview"],
          counts_by_state: { KNOWN_SATISFIED: 1, PARTIAL: 1, MISSING: 2, UNKNOWN: 1 },
        },
        {
          group_id: "group.assets", label: "Assets", node_ids: ["assets"],
          counts_by_state: { KNOWN_SATISFIED: 0, PARTIAL: 0, MISSING: 4, UNKNOWN: 1 },
        },
      ],
    },
    identity: { manifest_id: "fixture-views", manifest_version: 1, manifest_digest: "sha256:" + "a".repeat(64), source_digests: ["sha256:" + "b".repeat(64), "sha256:" + "c".repeat(64)] },
    claim_limit: "Project UI is a read-only digest-bound projection; actions and acceptance remain separate authority.",
  };
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
    { id: "project:waiting", name: "Unassigned planning", archived: false, visibility: "visible", project_eligibility: "no_ctrl", ctrl_ids: [], active_ctrl_id: null, active_ctrl: false }
  );
  const projectStatuses = new Map([
    ["project:fixture", "active"], ["project:branch", "active"], ["project:arc", "active"], ["project:atlas", "active"],
    ["project:stalled", "stalled"], ["project:idle", "inactive"], ["project:waiting", "inactive"],
  ]);
  overview.navigation.project_inventory = { state: "KNOWN", available: true, source: "host_projects", claim_limit: "Fixture saved-project inventory" };
  overview.project_inventory = structuredClone(overview.navigation.project_inventory);
  overview.navigation.projects = overview.navigation.projects.map((project, position) => {
    const status = projectStatuses.get(project.id);
    return {
      ...project,
      ordering: { position, normalized_name: project.name.toLowerCase(), project_id: project.id },
      status,
      status_facts: { active: status === "active", stalled: status === "stalled", inactive: status === "inactive", source: "fixture" },
      status_source: "fixture",
      task_count: overview.nodes.filter((node) => node.project_id === project.id).length,
    };
  });
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
  overview.project_view = projectViewFixture();
  return overview;
}

function overflowingProjectFixture(count = 24) {
  const overview = scopedFixture();
  for (let index = 1; index <= count; index += 1) {
    const id = "project:overflow-" + String(index).padStart(2, "0");
    overview.navigation.projects.push({
      id,
      name: "Saved project " + String(index).padStart(2, "0"),
      archived: false,
      visibility: "visible",
      project_eligibility: "no_ctrl",
      ctrl_ids: [],
      active_ctrl_id: null,
      active_ctrl: false,
      ordering: { position: overview.navigation.projects.length, normalized_name: id, project_id: id },
      status: "inactive",
      status_facts: { active: false, stalled: false, inactive: true, source: "fixture" },
      status_source: "fixture",
      task_count: 0,
    });
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

function notificationFixture() {
  return {
    ok: true,
    schema_version: 1,
    ctrl_id: "ctrl",
    project_id: "project:fixture",
    unread: [{
      id: "a".repeat(64), kind: "REVIEW_REQUESTED", severity: "warning", requires_action: true,
      project_id: "project:fixture", ctrl_id: "ctrl", task_id: "ctrl", subject_id: "proof-1", owner_id: "CTRL",
      material_sequence: 3, observed_at_ms: 1712550180000, sentence: "Independent review is required for this artifact.",
      action_target: { view: "review", project_id: "project:fixture", ctrl_id: "ctrl", task_id: "ctrl", subject_id: "proof-1" },
    }],
    recent_seen: [],
  };
}

async function mount(page, overview, overrides = {}) {
  const runtimeErrors = [];
  const requests = [];
  const notificationSeenRequests = [];
  const configRequests = [];
  const proofFeed = overrides.proofFeed || fixture.proofFeed;
  const proofControl = overrides.proofControl || { fail: false, feed: proofFeed };
  const notificationControl = overrides.notificationControl || { failGet: false, failSeen: false, feed: structuredClone(overrides.notifications || notificationFixture()) };
  const configControl = overrides.configControl || { failPost: false, deferredPost: null, feed: structuredClone(fixture.config) };
  if (!overrides.preserveOnboardingPresentation) {
    await page.addInitScript(() => {
      if (sessionStorage.getItem("swarm-test-onboarding-initialized") === "1") return;
      localStorage.removeItem("swarm.onboarding.v2.seen");
      sessionStorage.setItem("swarm-test-onboarding-initialized", "1");
    });
  }
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
    if (url.pathname === "/api/role-manifests") return route.fulfill(response(overrides.roleManifests || roleManifestFixture()));
    if (url.pathname === "/api/notifications" && request.method() === "GET") return notificationControl.failGet ? route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "notification feed unavailable" }) }) : route.fulfill(response(notificationControl.feed));
    if (url.pathname === "/api/notifications/seen" && request.method() === "POST") {
      const payload = request.postDataJSON();
      notificationSeenRequests.push(payload);
      if (notificationControl.failSeen) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "notification acknowledgement unavailable" }) });
      const acknowledged = new Set(payload.notification_ids || []);
      const newlySeen = notificationControl.feed.unread.filter((item) => acknowledged.has(item.id)).map((item) => ({ ...item, seen_at_ms: Date.now() }));
      notificationControl.feed.unread = notificationControl.feed.unread.filter((item) => !acknowledged.has(item.id));
      notificationControl.feed.recent_seen = [...newlySeen, ...notificationControl.feed.recent_seen];
      return route.fulfill(response({ ok: true, acknowledged: acknowledged.size, newly_seen: newlySeen.length, pruned: 0, feed: notificationControl.feed }));
    }
    if (url.pathname === "/api/presence") return route.fulfill(response({ ok: true, proof_sequence: proofFeed.sequence || 0 }));
    if (url.pathname === "/api/config") {
      if (request.method() === "GET") {
        const snapshot = structuredClone(configControl.feed);
        if (Array.isArray(configControl.getSnapshots)) configControl.getSnapshots.push(snapshot);
        const deferredGet = Array.isArray(configControl.deferredGets) ? configControl.deferredGets.shift() : configControl.deferredGet;
        if (deferredGet) await deferredGet;
        if (configControl.failGet) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "settings readback unavailable" }) });
        return route.fulfill(response(snapshot));
      }
      const payload = request.postDataJSON();
      configRequests.push(payload);
      const deferredPost = Array.isArray(configControl.deferredPosts) ? configControl.deferredPosts.shift() : configControl.deferredPost;
      if (deferredPost) await deferredPost;
      if (configControl.failPost) return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ ok: false, error: "setting acknowledgement unavailable" }) });
      configControl.feed = applyConfigChanges(configControl.feed, payload.changes);
      return route.fulfill(response(configControl.feed));
    }
    if (url.pathname === "/api/diagnostics") return route.fulfill(response(fixture.diagnostics));
    if (url.pathname === "/api/health/settings") return route.fulfill(response(fixture.healthSettings));
    if (url.pathname === "/api/storage") return route.fulfill(response(fixture.storage));
    if (url.pathname === "/api/ctrl-settings") return route.fulfill(response(fixture.ctrlSettings));
    if (url.pathname === "/api/skills") return route.fulfill(response({ ok: true, settings: { inheritance_enabled: true }, skills: [], overlays: { global: null, project: null, ctrl: null } }));
    if (url.pathname.startsWith("/api/proof-media/")) return route.fulfill({ status: 200, contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="100"><rect width="160" height="100" fill="#0f1726"/></svg>' });
    if (url.pathname === "/assets/swarm-wordmark.png") return route.fulfill({ status: 200, contentType: "image/png", body: wordmarkAsset });
    if (url.pathname === "/assets/swarm-mascot-512.png") return route.fulfill({ status: 200, contentType: "image/png", body: mascotAsset });
    if (url.pathname === "/assets/swarm-guided-tour-role-group.png") return route.fulfill({ status: 200, contentType: "image/png", body: onboardingRoleGroupAsset });
    if (url.pathname === "/swarm-icon-64.png") return route.fulfill({ status: 200, contentType: "image/png", body: iconAsset });
    return route.abort();
  });
  await page.goto("http://swarm.test/", { waitUntil: "domcontentloaded" });
  if (overrides.waitForConnectionState) {
    await page.locator("#connection-state").waitFor({ state: "visible" });
    return { runtimeErrors, requests, notificationSeenRequests, configRequests };
  }
  try {
    await page.locator("#overview-content").waitFor({ state: "visible" });
  } catch (error) {
    const message = await page.locator("#error-message").textContent().catch(() => "");
    throw new Error(`${error.message}; console=${runtimeErrors.join(" | ")}; surface=${message}`);
  }
  await page.locator("#onboarding-dialog").waitFor({ state: "visible" });
  if (!overrides.keepOnboarding) await page.getByRole("button", { name: "Skip for now" }).click();
  return { runtimeErrors, requests, notificationSeenRequests, configRequests };
}

async function assertOnboardingRoleGroup(page, viewportWidth) {
  const image = page.locator("#onboarding-panel-3 .onboarding-role-group");
  await image.waitFor({ state: "visible" });
  assert.equal(await image.count(), 1);
  await image.evaluate((node) => Promise.all(node.getAnimations().map((animation) => animation.finished.catch(() => undefined))));
  const geometry = await image.evaluate((node) => {
    const imageRect = node.getBoundingClientRect();
    const panelRect = node.closest(".onboarding-panel").getBoundingClientRect();
    return {
      naturalWidth: node.naturalWidth,
      naturalHeight: node.naturalHeight,
      image: { left: imageRect.left, top: imageRect.top, right: imageRect.right, bottom: imageRect.bottom, width: imageRect.width, height: imageRect.height },
      panel: { left: panelRect.left, top: panelRect.top, right: panelRect.right, bottom: panelRect.bottom },
      documentWidth: document.documentElement.scrollWidth,
    };
  });
  assert.equal(geometry.naturalWidth, 1920);
  assert.equal(geometry.naturalHeight, 1080);
  assert.ok(geometry.image.width > 0 && geometry.image.height > 0);
  assert.ok(geometry.image.left >= geometry.panel.left - 1 && geometry.image.right <= geometry.panel.right + 1);
  assert.ok(geometry.image.top >= geometry.panel.top - 1 && geometry.image.bottom <= geometry.panel.bottom + 1);
  assert.ok(geometry.documentWidth <= viewportWidth);
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
  overview.overview_metrics = structuredClone(overviewMetricFixture);
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
  const overrides = {
    proofFeed,
    usageByHours: { 1: usageHistory, 24: usageHistory },
    projectProgress,
    projectProgressFeed: fixture.projectProgressFeed,
    notifications: notificationFixture(),
    roleManifests: roleManifestFixture(),
  };
  try {
    const onboardingPage = await browser.newPage({ viewport: { width: 1536, height: 1024 } });
    const onboarding = await mount(onboardingPage, scopedFixture(), { ...overrides, keepOnboarding: true });
    assert.equal(await onboardingPage.getByText(/^Step [1-5] of 5$/).count(), 0);
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "0");
    const desktopGeometry = await onboardingPage.locator("#onboarding-dialog").evaluate((dialog) => {
      const rect = (element) => { const value = element.getBoundingClientRect(); return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height }; };
      const primary = rect(document.querySelector("#onboarding-primary"));
      const skip = rect(document.querySelector("#onboarding-skip"));
      const controls = [...dialog.querySelectorAll("button")].filter((button) => !button.hidden).map(rect);
      return { dialog: rect(dialog), primary, skip, controls, viewport: { width: innerWidth, height: innerHeight }, documentWidth: document.documentElement.scrollWidth };
    });
    assert.ok(desktopGeometry.dialog.width <= 1041 && desktopGeometry.dialog.height <= 721);
    assert.ok(desktopGeometry.dialog.left >= 0 && desktopGeometry.dialog.right <= desktopGeometry.viewport.width);
    assert.ok(desktopGeometry.dialog.top >= 0 && desktopGeometry.dialog.bottom <= desktopGeometry.viewport.height);
    assert.ok(desktopGeometry.controls.every((control) => control.width >= 44 && control.height >= 44));
    assert.ok(Math.abs((desktopGeometry.primary.left + desktopGeometry.primary.width / 2) - (desktopGeometry.skip.left + desktopGeometry.skip.width / 2)) <= 1);
    assert.ok(desktopGeometry.skip.top >= desktopGeometry.primary.bottom);
    assert.ok(desktopGeometry.documentWidth <= desktopGeometry.viewport.width);
    await onboardingPage.getByRole("button", { name: "Start guided tour" }).click();
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "1");
    const motionTiming = await onboardingPage.locator("#onboarding-dialog").evaluate((dialog) => {
      const timing = (selector) => {
        const style = getComputedStyle(dialog.querySelector(selector));
        return { delay: parseFloat(style.animationDelay) * 1000, duration: parseFloat(style.animationDuration) * 1000 };
      };
      return [timing(".onboarding-panel.is-active .onboarding-artwork"), timing(".onboarding-panel.is-active > h2"), timing(".onboarding-panel.is-active > p"), timing(".onboarding-panel.is-active .onboarding-supporting-visual"), timing("#onboarding-primary"), timing("#onboarding-skip")];
    });
    assert.deepEqual(motionTiming.map((item) => Math.round(item.delay)), [0, 55, 110, 165, 220, 275]);
    assert.ok(Math.max(...motionTiming.map((item) => item.delay + item.duration)) <= 550);
    assert.equal(await onboardingPage.locator(".onboarding-flow-fanout i").count(), 3);
    assert.match(await onboardingPage.locator(".onboarding-flow .is-ctrl").evaluate((element) => getComputedStyle(element).clipPath), /polygon/);
    assert.match(await onboardingPage.locator(".onboarding-flag i").evaluate((element) => getComputedStyle(element).backgroundImage), /conic-gradient/);
    await onboardingPage.getByRole("button", { name: "Continue" }).click();
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "2");
    assert.equal(await onboardingPage.locator("#onboarding-dialog").getAttribute("data-motion-step"), "2");
    assert.equal(await onboardingPage.evaluate(() => document.activeElement?.id), "onboarding-primary");
    await assertOnboardingRoleGroup(onboardingPage, 1536);
    await onboardingPage.getByRole("button", { name: "Continue" }).click();
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "3");
    assert.equal(await onboardingPage.locator('.onboarding-project-views[role="img"]').count(), 1);
    assert.match(await onboardingPage.locator("#onboarding-panel-4").textContent(), /useful views it needs/);
    await onboardingPage.getByRole("button", { name: "Continue" }).click();
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "4");
    assert.equal(await onboardingPage.getByRole("button", { name: "Start using SWARM" }).count(), 1);
  const onboardingConfigPanel = onboardingPage.locator("#onboarding-panel-5");
  assert.equal(await onboardingConfigPanel.getByLabel("Codex model").inputValue(), "gpt-5.6-sol");
  assert.equal(await onboardingConfigPanel.getByLabel("Fast Mode").isChecked(), false);
  assert.equal(await onboardingConfigPanel.getByLabel("Progress feed").isChecked(), true);
    await onboardingPage.evaluate(() => {
      window.__onboardingMotionClassMutations = 0;
      window.__onboardingMotionObserver = new MutationObserver((records) => { window.__onboardingMotionClassMutations += records.length; });
      window.__onboardingMotionObserver.observe(document.querySelector("#onboarding-dialog"), { attributes: true, attributeFilter: ["class"] });
    });
    await onboardingConfigPanel.getByLabel("Fast Mode").check();
    await onboardingPage.waitForFunction(() => {
      const input = document.querySelector('#onboarding-configuration input[data-config-key="execution.fast_mode"]');
      return input?.checked && !input.disabled;
    });
    assert.deepEqual(await onboardingPage.locator("#onboarding-dialog").evaluate((dialog) => ({ step: dialog.dataset.motionStep, classMutations: window.__onboardingMotionClassMutations })), { step: "4", classMutations: 0 });
    await onboardingPage.evaluate(() => window.__onboardingMotionObserver.disconnect());
    assert.equal(await onboardingPage.getByRole("button", { name: "Close onboarding" }).count(), 1);
    assert.equal(await onboardingPage.getByRole("button", { name: "Skip for now" }).count(), 1);
    await onboardingPage.getByRole("button", { name: "Start using SWARM" }).click();
    assert.equal(await onboardingPage.locator("#onboarding-dialog").isVisible(), false);
    assert.equal(await onboardingPage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), "1");
    await onboardingPage.reload({ waitUntil: "domcontentloaded" });
    await onboardingPage.waitForFunction(() => !document.querySelector("#overview-content")?.hasAttribute("hidden"));
    assert.equal(await onboardingPage.locator("#onboarding-dialog").isVisible(), false);
    await onboardingPage.getByRole("tab", { name: "Settings", exact: true }).click();
    await onboardingPage.getByRole("button", { name: "Replay tour" }).click();
    assert.equal(await onboardingPage.locator('[data-onboarding-step][aria-current="step"]').getAttribute("data-onboarding-step"), "0");
    await onboardingPage.getByRole("button", { name: "Skip for now" }).click();
    await onboardingPage.reload({ waitUntil: "domcontentloaded" });
    await onboardingPage.waitForFunction(() => !document.querySelector("#overview-content")?.hasAttribute("hidden"));
    assert.equal(await onboardingPage.locator("#onboarding-dialog").isVisible(), false);
    assert.deepEqual(onboarding.runtimeErrors, []);
    await onboardingPage.close();

    const onboardingTabletPage = await browser.newPage({ viewport: { width: 834, height: 1112 } });
    const onboardingTablet = await mount(onboardingTabletPage, scopedFixture(), { ...overrides, keepOnboarding: true });
    await onboardingTabletPage.getByRole("button", { name: "Start guided tour" }).click();
    const tabletFlowGeometry = await onboardingTabletPage.locator(".onboarding-flow-scene").evaluate((scene) => {
      const roleNodes = [...scene.querySelectorAll(".onboarding-flow-roles b")];
      return {
        sceneWidth: scene.scrollWidth,
        sceneClientWidth: scene.clientWidth,
        roleTargets: roleNodes.map((node) => ({ width: node.getBoundingClientRect().width, height: node.getBoundingClientRect().height })),
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
      };
    });
    assert.ok(tabletFlowGeometry.sceneWidth <= tabletFlowGeometry.sceneClientWidth + 1);
    assert.ok(tabletFlowGeometry.roleTargets.every((role) => role.width >= 44 && role.height >= 44));
    assert.ok(tabletFlowGeometry.documentWidth <= tabletFlowGeometry.viewportWidth);
    await onboardingTabletPage.getByRole("button", { name: "Continue" }).click();
    await assertOnboardingRoleGroup(onboardingTabletPage, 834);
    await onboardingTabletPage.getByRole("button", { name: "Continue" }).click();
    assert.ok(await onboardingTabletPage.locator(".onboarding-project-views").evaluate((node) => node.scrollWidth <= node.clientWidth + 1));
    assert.deepEqual(onboardingTablet.runtimeErrors, []);
    await onboardingTabletPage.close();

    const onboardingMobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const onboardingMobile = await mount(onboardingMobilePage, scopedFixture(), { ...overrides, keepOnboarding: true });
    await onboardingMobilePage.getByRole("button", { name: "Start guided tour" }).click();
    const mobileFlowGeometry = await onboardingMobilePage.locator(".onboarding-flow").evaluate((flow) => {
      const rect = (element) => { const value = element.getBoundingClientRect(); return { left: value.left, right: value.right, top: value.top, bottom: value.bottom, width: value.width, height: value.height }; };
      const ctrl = rect(flow.querySelector(".is-ctrl"));
      const roles = [...flow.querySelectorAll(".onboarding-flow-roles b")].map((element) => ({ ...rect(element), fontSize: parseFloat(getComputedStyle(element).fontSize) }));
      return { ctrl, roles, scrollWidth: flow.scrollWidth, clientWidth: flow.clientWidth };
    });
    assert.equal(mobileFlowGeometry.roles.length, 3);
    assert.ok(mobileFlowGeometry.roles.every((role) => role.width >= 88 && role.height >= 44 && role.fontSize >= 9));
    assert.ok(mobileFlowGeometry.roles.every((role) => role.left > mobileFlowGeometry.ctrl.right));
    assert.ok(mobileFlowGeometry.roles[0].top < mobileFlowGeometry.roles[1].top && mobileFlowGeometry.roles[1].top < mobileFlowGeometry.roles[2].top);
    assert.ok(mobileFlowGeometry.scrollWidth <= mobileFlowGeometry.clientWidth + 1);
    await onboardingMobilePage.getByRole("button", { name: "Continue" }).click();
    await assertOnboardingRoleGroup(onboardingMobilePage, 390);
    await onboardingMobilePage.getByRole("button", { name: "Continue" }).click();
    assert.ok(await onboardingMobilePage.locator(".onboarding-project-views").evaluate((node) => node.scrollWidth <= node.clientWidth + 1));
    await onboardingMobilePage.getByRole("button", { name: "Continue" }).click();
    const mobileGeometry = await onboardingMobilePage.locator("#onboarding-dialog").evaluate((dialog) => {
      const rect = (element) => { const value = element.getBoundingClientRect(); return { left: value.left, top: value.top, right: value.right, bottom: value.bottom, width: value.width, height: value.height }; };
      const primary = rect(document.querySelector("#onboarding-primary"));
      const skip = rect(document.querySelector("#onboarding-skip"));
      const panel = document.querySelector("#onboarding-panel-5");
      const configuration = document.querySelector("#onboarding-configuration");
      const controls = [...dialog.querySelectorAll("button")].filter((control) => !control.hidden && getComputedStyle(control).display !== "none").map(rect);
      const configControls = [...configuration.querySelectorAll("input,select,summary,button")].filter((control) => !control.hidden && getComputedStyle(control).display !== "none" && control.getClientRects().length).map((control) => rect(control.matches('input[type="checkbox"]') ? control.closest(".toggle-row") : control));
      return { dialog: rect(dialog), primary, skip, controls, configControls, panel: { scrollWidth: panel.scrollWidth, clientWidth: panel.clientWidth, overflowY: getComputedStyle(panel).overflowY }, configuration: { scrollWidth: configuration.scrollWidth, clientWidth: configuration.clientWidth, scrollHeight: configuration.scrollHeight, clientHeight: configuration.clientHeight, overflowY: getComputedStyle(configuration).overflowY }, viewport: { width: innerWidth, height: innerHeight }, documentWidth: document.documentElement.scrollWidth };
    });
    assert.ok(Math.abs(mobileGeometry.dialog.width - 390) <= 1 && Math.abs(mobileGeometry.dialog.height - 844) <= 1);
    assert.ok(mobileGeometry.controls.every((control) => control.width >= 44 && control.height >= 44));
    assert.ok(Math.abs((mobileGeometry.primary.left + mobileGeometry.primary.width / 2) - (mobileGeometry.skip.left + mobileGeometry.skip.width / 2)) <= 1);
    assert.ok(mobileGeometry.skip.top >= mobileGeometry.primary.bottom);
    assert.ok(mobileGeometry.panel.scrollWidth <= mobileGeometry.panel.clientWidth + 1);
    assert.equal(mobileGeometry.panel.overflowY, "hidden");
    assert.equal(mobileGeometry.configuration.overflowY, "auto");
    assert.ok(mobileGeometry.configuration.scrollWidth <= mobileGeometry.configuration.clientWidth + 1);
    assert.ok(mobileGeometry.configuration.scrollHeight > mobileGeometry.configuration.clientHeight);
    assert.ok(mobileGeometry.configControls.every((control) => control.width >= 44 && control.height >= 44), JSON.stringify(mobileGeometry.configControls));
    assert.ok(mobileGeometry.documentWidth <= mobileGeometry.viewport.width);
    assert.deepEqual(onboardingMobile.runtimeErrors, []);
    await onboardingMobilePage.close();

    const reducedMotionPage = await browser.newPage({ viewport: { width: 834, height: 1112 } });
    await reducedMotionPage.emulateMedia({ reducedMotion: "reduce" });
    const reducedMotion = await mount(reducedMotionPage, scopedFixture(), { ...overrides, keepOnboarding: true });
    await reducedMotionPage.getByRole("button", { name: "Start guided tour" }).click();
    const reducedMotionStyles = await reducedMotionPage.locator("#onboarding-dialog").evaluate((dialog) => [
      ".onboarding-panel.is-active .onboarding-artwork",
      ".onboarding-panel.is-active > h2",
      ".onboarding-panel.is-active > p",
      ".onboarding-panel.is-active .onboarding-supporting-visual",
      "#onboarding-primary",
      "#onboarding-skip",
    ].map((selector) => {
      const style = getComputedStyle(dialog.querySelector(selector));
      return { animationName: style.animationName, transform: style.transform };
    }));
    assert.ok(reducedMotionStyles.every((item) => item.animationName === "none" && item.transform === "none"));
    assert.deepEqual(reducedMotion.runtimeErrors, []);
    await reducedMotionPage.close();

    let releaseConfigPost;
    const pendingConfigControl = { failPost: false, feed: structuredClone(fixture.config), deferredPost: new Promise((resolve) => { releaseConfigPost = resolve; }) };
    const pendingPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const pending = await mount(pendingPage, scopedFixture(), { ...overrides, keepOnboarding: true, configControl: pendingConfigControl });
    await pendingPage.getByRole("button", { name: "Start guided tour" }).click();
    for (let step = 0; step < 3; step += 1) await pendingPage.getByRole("button", { name: "Continue" }).click();
    const pendingFastMode = pendingPage.locator("#onboarding-panel-5").getByLabel("Fast Mode");
    await pendingFastMode.focus();
    const pendingRequest = pendingPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await pendingFastMode.click();
    await pendingRequest;
    await pendingPage.waitForFunction(() => document.activeElement?.id === "onboarding-config-status");
    assert.equal(await pendingPage.getByRole("button", { name: "Start using SWARM" }).isDisabled(), true);
    assert.equal(await pendingPage.locator("#onboarding-config-status").textContent().then((text) => /Saving/.test(text)), true);
    assert.equal(await pendingPage.locator("#onboarding-panel-5").getByLabel("Fast Mode").isDisabled(), true);
    await assert.rejects(pendingPage.locator("#onboarding-panel-5").getByLabel("Fast Mode").click({ timeout: 200 }), /Timeout/);
    assert.deepEqual(pending.configRequests, [{ changes: { "execution.fast_mode": true } }]);
    await pendingPage.keyboard.press("Escape");
    assert.equal(await pendingPage.locator("#onboarding-dialog").isVisible(), true);
    assert.equal(await pendingPage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), null);
    assert.equal(await pendingPage.locator("#onboarding-config-status").textContent().then((text) => /Saving/.test(text)), true);
    const usageSummary = pendingPage.locator('details[data-onboarding-control="usage-policy"] > summary');
    await usageSummary.focus();
    await pendingPage.evaluate(() => renderOnboarding());
    await pendingPage.waitForFunction(() => document.activeElement?.tagName === "SUMMARY" && document.activeElement?.textContent === "Usage saver policy");
    releaseConfigPost();
    pendingConfigControl.deferredPost = null;
    await pendingPage.getByRole("button", { name: "Start using SWARM" }).waitFor({ state: "visible" });
    await pendingPage.waitForFunction(() => !document.querySelector("#onboarding-primary")?.disabled);
    assert.equal(await pendingPage.evaluate(() => document.activeElement?.dataset.configKey), "execution.fast_mode");
    assert.deepEqual(pending.configRequests, [{ changes: { "execution.fast_mode": true } }]);
    assert.deepEqual(pending.runtimeErrors, []);
    await pendingPage.close();

    let releaseFirstConfigPost;
    let releaseSecondConfigPost;
    const serialConfigControl = {
      failPost: false,
      feed: structuredClone(fixture.config),
      deferredPosts: [
        new Promise((resolve) => { releaseFirstConfigPost = resolve; }),
        new Promise((resolve) => { releaseSecondConfigPost = resolve; }),
      ],
    };
    const serialPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const serial = await mount(serialPage, scopedFixture(), { ...overrides, keepOnboarding: true, configControl: serialConfigControl });
    await serialPage.getByRole("button", { name: "Start guided tour" }).click();
    for (let step = 0; step < 3; step += 1) await serialPage.getByRole("button", { name: "Continue" }).click();
    const firstSerialRequest = serialPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await serialPage.locator("#onboarding-panel-5").getByLabel("Fast Mode").click();
    await firstSerialRequest;
    await serialPage.locator("#onboarding-panel-5").getByLabel("Usage saver").click();
    await serialPage.waitForTimeout(100);
    assert.deepEqual(serial.configRequests, [{ changes: { "execution.fast_mode": true } }]);
    const secondSerialRequest = serialPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST" && request.postDataJSON().changes["execution.usage_saver"] === true);
    releaseFirstConfigPost();
    await secondSerialRequest;
    releaseSecondConfigPost();
    await serialPage.waitForFunction(() => !document.querySelector("#onboarding-primary")?.disabled);
    assert.deepEqual(serial.configRequests, [{ changes: { "execution.fast_mode": true } }, { changes: { "execution.usage_saver": true } }]);
    assert.equal(await serialPage.locator("#onboarding-panel-5").getByLabel("Fast Mode").isChecked(), true);
    assert.equal(await serialPage.locator("#onboarding-panel-5").getByLabel("Usage saver").isChecked(), true);
    assert.deepEqual(serial.runtimeErrors, []);
    await serialPage.close();

    let releaseWriteBeforeRead;
    const writeBeforeReadControl = {
      failPost: false,
      feed: structuredClone(fixture.config),
      deferredPost: new Promise((resolve) => { releaseWriteBeforeRead = resolve; }),
      getSnapshots: [],
    };
    const writeBeforeReadPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const writeBeforeRead = await mount(writeBeforeReadPage, scopedFixture(), { ...overrides, configControl: writeBeforeReadControl });
    writeBeforeReadControl.getSnapshots.length = 0;
    const writeFirstRequest = writeBeforeReadPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await writeBeforeReadPage.evaluate(() => { window.__configWriteBeforeRead = saveConfigMutation({ "execution.fast_mode": true }); });
    await writeFirstRequest;
    await writeBeforeReadPage.evaluate(() => { window.__configReadAfterWrite = readConfigState(); });
    await writeBeforeReadPage.waitForTimeout(80);
    assert.equal(writeBeforeReadControl.getSnapshots.length, 0, "a read queued behind an in-flight write must not capture the old config");
    const orderedGetRequest = writeBeforeReadPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "GET");
    releaseWriteBeforeRead();
    writeBeforeReadControl.deferredPost = null;
    await orderedGetRequest;
    await writeBeforeReadPage.evaluate(() => Promise.all([window.__configWriteBeforeRead, window.__configReadAfterWrite]));
    assert.equal(writeBeforeReadControl.getSnapshots.length, 1);
    assert.equal(writeBeforeReadControl.getSnapshots[0].settings.execution.fast_mode, true);
    assert.equal(await writeBeforeReadPage.evaluate(() => state.config.settings.execution.fast_mode), true, "the acknowledged write survives its ordered readback");
    assert.deepEqual(writeBeforeRead.configRequests, [{ changes: { "execution.fast_mode": true } }]);
    assert.deepEqual(writeBeforeRead.runtimeErrors, []);
    await writeBeforeReadPage.close();

    let releaseStaleConfigGet;
    const readRaceControl = {
      failPost: false,
      feed: structuredClone(fixture.config),
      deferredGet: null,
    };
    const readRacePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const readRace = await mount(readRacePage, scopedFixture(), { ...overrides, configControl: readRaceControl });
    readRaceControl.deferredGet = new Promise((resolve) => { releaseStaleConfigGet = resolve; });
    const staleGetRequest = readRacePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "GET");
    const staleRefresh = readRacePage.evaluate(() => refreshOverview(false));
    await staleGetRequest;
    const newerPostRequest = readRacePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await readRacePage.evaluate(() => saveConfigMutation({ "execution.fast_mode": true }));
    await newerPostRequest;
    assert.equal(await readRacePage.evaluate(() => state.config.settings.execution.fast_mode), true);
    releaseStaleConfigGet();
    readRaceControl.deferredGet = null;
    await staleRefresh;
    assert.equal(await readRacePage.evaluate(() => state.config.settings.execution.fast_mode), true, "a GET started before an acknowledged POST cannot overwrite its config");
    assert.deepEqual(readRace.configRequests, [{ changes: { "execution.fast_mode": true } }]);
    assert.deepEqual(readRace.runtimeErrors, []);
    await readRacePage.close();

    let releaseFailedWriteReadback;
    const failedReadbackRaceControl = {
      failPost: false,
      feed: {
        ...structuredClone(fixture.config),
        editable: [...fixture.config.editable, "chat_relay.enabled"],
        settings: { ...structuredClone(fixture.config.settings), chat_relay: { enabled: false } },
      },
      deferredGet: null,
    };
    const failedReadbackRacePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const failedReadbackRace = await mount(failedReadbackRacePage, scopedFixture(), { ...overrides, configControl: failedReadbackRaceControl });
    await failedReadbackRacePage.evaluate(() => setView("settings"));
    await failedReadbackRacePage.locator("#settings-advanced > summary").click();
    await failedReadbackRacePage.locator("#chat-relay-enabled").waitFor({ state: "visible" });
    failedReadbackRaceControl.failPost = true;
    failedReadbackRaceControl.deferredGet = new Promise((resolve) => { releaseFailedWriteReadback = resolve; });
    const failedRelayPost = failedReadbackRacePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    const delayedReadback = failedReadbackRacePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "GET");
    await failedReadbackRacePage.locator("#chat-relay-enabled").click();
    await failedRelayPost;
    await delayedReadback;
    failedReadbackRaceControl.failPost = false;
    const replacementPost = failedReadbackRacePage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await failedReadbackRacePage.evaluate(() => saveConfigMutation({ "execution.usage_saver": true }));
    await replacementPost;
    assert.equal(await failedReadbackRacePage.evaluate(() => state.config.settings.execution.usage_saver), true);
    releaseFailedWriteReadback();
    failedReadbackRaceControl.deferredGet = null;
    await failedReadbackRacePage.waitForFunction(() => state.chatRelaySaving === false);
    assert.equal(await failedReadbackRacePage.evaluate(() => state.config.settings.execution.usage_saver), true, "a failed-write readback cannot overwrite a later acknowledged config");
    assert.equal(await failedReadbackRacePage.evaluate(() => state.configStatus), "current");
    assert.match(await failedReadbackRacePage.evaluate(() => state.configError), /setting acknowledgement unavailable[\s\S]*Current settings changed before the reload completed/);
    assert.deepEqual(failedReadbackRace.configRequests, [{ changes: { "chat_relay.enabled": true } }, { changes: { "execution.usage_saver": true } }]);
    assert.equal(failedReadbackRace.runtimeErrors.length, 1);
    assert.match(failedReadbackRace.runtimeErrors[0], /503 \(Service Unavailable\)/);
    await failedReadbackRacePage.close();

    const failedConfigControl = { failPost: true, feed: structuredClone(fixture.config), deferredPost: null };
    const failedPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const failed = await mount(failedPage, scopedFixture(), { ...overrides, keepOnboarding: true, configControl: failedConfigControl });
    await failedPage.getByRole("button", { name: "Start guided tour" }).click();
    for (let step = 0; step < 3; step += 1) await failedPage.getByRole("button", { name: "Continue" }).click();
    await failedPage.locator("#onboarding-panel-5").getByLabel("Fast Mode").click();
    await failedPage.getByRole("button", { name: "Retry" }).waitFor({ state: "visible" });
    assert.equal(await failedPage.getByRole("button", { name: "Start using SWARM" }).isDisabled(), true);
    assert.equal(await failedPage.locator("#onboarding-dialog").isVisible(), true);
    assert.equal(await failedPage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), null);
    assert.equal(await failedPage.locator("#onboarding-panel-5").getByLabel("Fast Mode").isChecked(), true);
    await failedPage.getByRole("button", { name: "Retry" }).focus();
    await failedPage.keyboard.press("Escape");
    assert.equal(await failedPage.locator("#onboarding-dialog").isVisible(), true);
    assert.equal(await failedPage.getByRole("button", { name: "Retry" }).isVisible(), true);
    assert.equal(await failedPage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), null);
    let releaseRetryPost;
    failedConfigControl.deferredPost = new Promise((resolve) => { releaseRetryPost = resolve; });
    failedConfigControl.failPost = false;
    const retryRequest = failedPage.waitForRequest((request) => request.url().endsWith("/api/config") && request.method() === "POST");
    await failedPage.getByRole("button", { name: "Retry" }).click();
    await retryRequest;
    await failedPage.waitForFunction(() => document.activeElement?.id === "onboarding-config-status");
    assert.match(await failedPage.locator("#onboarding-config-status").textContent(), /Saving/);
    releaseRetryPost();
    failedConfigControl.deferredPost = null;
    await failedPage.waitForFunction(() => !document.querySelector("#onboarding-primary")?.disabled);
    assert.equal(await failedPage.evaluate(() => document.activeElement?.id), "onboarding-config-status");
    assert.deepEqual(failed.configRequests, [{ changes: { "execution.fast_mode": true } }, { changes: { "execution.fast_mode": true } }]);
    await failedPage.getByRole("button", { name: "Start using SWARM" }).click();
    assert.equal(await failedPage.locator("#onboarding-dialog").isVisible(), false);
    assert.equal(await failedPage.evaluate(() => localStorage.getItem("swarm.onboarding.v2.seen")), "1");
    assert.equal(failed.runtimeErrors.filter((message) => /503 \(Service Unavailable\)/.test(message)).length, 1);
    assert.deepEqual(failed.runtimeErrors.filter((message) => !/503 \(Service Unavailable\)/.test(message)), []);
    await failedPage.close();

    const offlinePage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const connection = { offline: true };
    const offline = await mount(offlinePage, scopedFixture(), { connection, waitForConnectionState: true });
    assert.equal(await offlinePage.getByRole("heading", { name: "Connection lost" }).count(), 1);
    assert.equal(await offlinePage.locator("#sync-time").textContent(), "Offline");
    assert.equal(await offlinePage.locator('#connection-state img[alt="SWARM octopus holding disconnected cable ends"]').count(), 1);
    connection.offline = false;
    await offlinePage.getByRole("button", { name: "Retry connection" }).click();
    await offlinePage.locator("#overview-content").waitFor({ state: "visible" });
    assert.equal(await offlinePage.locator("#connection-state").isVisible(), false);
    assert.match(await offlinePage.locator("#sync-time").textContent(), /^Live/);
    assert.ok(offline.requests.filter((request) => request === "/api/bootstrap").length >= 2);
    await offlinePage.close();

    const page = await browser.newPage({ viewport: { width: 1536, height: 1024 } });
    const desktop = await mount(page, overview, overrides);
    for (const view of ["overview", "agents", "review", "assets", "settings"]) assert.equal(await page.locator('.nav-item[data-view="' + view + '"]').count(), 1);
    assert.equal(await page.getByRole("tab", { name: "Projects", exact: true }).count(), 0);
    for (const retired of ["dashboard", "hierarchy", "kanban", "diagnostics"]) assert.equal(await page.locator('.nav-item[data-view="' + retired + '"]').count(), 0);
    assert.equal(await page.locator("#project-scope-filter").isVisible(), true);
    assert.deepEqual(await page.locator("#project-navigation button").evaluateAll((elements) => elements.map((element) => element.getAttribute("aria-label") || element.textContent.trim())), [
      "Arc, Active",
      "Atlas, Active",
      "Flowwweb, Active",
      "swarm, Active",
      "Stalled project, Stalled",
      "Idle project, Inactive",
      "Unassigned planning, Inactive",
    ]);
    assert.deepEqual(await page.locator("#project-navigation .scope-dot").evaluateAll((elements) => elements.map((element) => [...element.classList].find((name) => name.startsWith("is-")))), [
      "is-active", "is-active", "is-active", "is-active", "is-stalled", "is-inactive", "is-inactive",
    ]);
    assert.doesNotMatch(await page.locator("#project-navigation").textContent(), /All projects|Archived project|Resolve customer export/);
    assert.deepEqual(await page.locator("#project-scope-filter option").allTextContents(), ["All projects", "Arc", "Atlas", "Flowwweb", "swarm", "Stalled project", "Idle project", "Unassigned planning"]);
    assert.equal(await page.locator("#profile").isDisabled(), true);
    assert.deepEqual(await page.locator(".overview-metric-card > header > span").allTextContents(), ["Active work", "Needs attention", "Verified progress", "Usage"]);
    assert.deepEqual(await page.locator(".overview-metric-card > strong").allTextContents(), ["3 / 5", "2", "75%", "125k used"]);
    assert.equal(await page.locator("#overview-monitoring-heading").isVisible(), true);
    assert.deepEqual(await page.locator("#overview-project-cards [data-overview-project-id] strong").allTextContents(), ["Arc", "Atlas", "Flowwweb", "swarm", "Stalled project", "Idle project", "Unassigned planning"]);
    assert.match(await page.locator('[data-overview-project-id="project:waiting"]').locator("xpath=..").textContent(), /No CTRL/);
    assert.equal(await page.locator(".overview-metrics").evaluate((metrics) => metrics.getBoundingClientRect().bottom <= document.querySelector("#overview-monitoring-heading").closest(".overview-section").getBoundingClientRect().top), true);
    const keyboardScopeRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname === "/api/overview" && url.searchParams.get("project_id") === "project:arc";
    });
    await page.locator('#project-navigation [data-project-id="project:arc"]').focus();
    await page.keyboard.press("Enter");
    await keyboardScopeRequest;
    assert.equal(await page.locator('#project-navigation [data-project-id="project:arc"]').getAttribute("aria-pressed"), "true");
    assert.equal(await page.locator('#project-navigation [data-project-id="project:waiting"]').count(), 1);
    const scopedOverviewRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname === "/api/overview" && url.searchParams.get("project_id") === "project:fixture";
    });
    await page.locator('#project-navigation [data-project-id="project:fixture"]').click();
    await scopedOverviewRequest;
    await page.locator("#project-detail").waitFor({ state: "visible" });
    assert.ok(desktop.requests.includes("/api/overview?project_id=project%3Afixture"));
    assert.equal(await page.locator('#project-navigation [data-project-id="project:waiting"]').count(), 1);
    await page.locator("#notification-unread").waitFor({ state: "visible" });
    await page.waitForFunction(() => document.querySelector("#notification-unread")?.textContent === "1");
    assert.equal(await page.locator("#notification-unread").textContent(), "1");
    const seenRequest = page.waitForRequest((request) => new URL(request.url()).pathname === "/api/notifications/seen");
    await page.locator("#notifications").click();
    assert.match(await page.locator("#notifications-panel").textContent(), /Independent review is required/);
    assert.deepEqual((await seenRequest).postDataJSON(), { ctrl_id: "ctrl", project_id: "project:fixture", notification_ids: ["a".repeat(64)] });
    await page.waitForFunction(() => {
      const unread = document.querySelector("#notification-unread");
      return unread?.hidden === true && unread.textContent === "0";
    });
    await page.locator("#notifications-close").click();
    assert.equal(await page.locator("[data-project-tab]").count(), 8);
    assert.equal(await page.getByRole("tab", { name: "UI", exact: true }).isVisible(), true);
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
    await page.getByRole("tab", { name: "UI", exact: true }).click();
    assert.equal(await page.locator("#project-tab-panel").getAttribute("aria-labelledby"), "project-tab-ui");
    assert.deepEqual(await page.locator("[data-project-tab]:visible").allTextContents(), ["Overview", "Roadmap", "Lanes", "Hierarchy", "Proof", "Ledger", "Logs", "UI"]);
    assert.equal(await page.locator(".project-ui-card").count(), 2);
    assert.deepEqual(await page.locator('.project-ui-card[data-project-view-screen="overview/default"] .project-ui-devices li').allTextContents(), ["Desktop", "Tablet", "Mobile"]);
    assert.equal(await page.locator('.project-ui-card[data-project-view-screen="overview/default"] .project-ui-alternatives').textContent(), "3 alternatives");
    assert.equal(await page.locator('.project-ui-card[data-project-view-screen="assets/empty"] .project-ui-alternatives').count(), 0);
    assert.equal(await page.locator('.project-ui-card[data-project-view-screen="assets/empty"] .project-ui-devices').count(), 0);
    assert.match(await page.locator('.project-ui-card[data-project-view-screen="overview/default"] .project-ui-requirements').textContent(), /Overview · 1 satisfied · 1 partial · 2 missing · 1 unknown/);
    await page.locator('.project-ui-card[data-project-view-screen="overview/default"] [data-project-view-evidence]').click();
    assert.equal(await page.locator("#evidence-lightbox").isVisible(), true);
    assert.match(await page.locator("#evidence-lightbox-caption").textContent(), /Overview · 1 satisfied · 1 partial · 2 missing · 1 unknown/);
    await page.getByRole("button", { name: "Close evidence gallery" }).click();
    await page.getByRole("button", { name: "Map", exact: true }).click();
    assert.equal(await page.locator('[data-project-map-node="runtime-state"]').count(), 0);
    const groupNode = page.locator('[data-project-map-group="workspace"]');
    assert.equal(await groupNode.count(), 1);
    await groupNode.focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator(".project-ui-flowchart-node").count(), 2);
    assert.equal(await page.locator('[data-project-map-edge="overview-assets"]').count(), 1);
    await page.waitForFunction(() => Boolean(document.querySelector('[data-project-map-edge="overview-assets"]')?.getAttribute("d")));
    assert.match(await page.locator('.project-ui-flowchart [aria-label="Map connections"]').textContent(), /Overview to Assets: Open assets/);
    assert.equal(await page.locator(".project-ui-flowchart").evaluate((stage) => {
      const svg = stage.querySelector(".project-ui-flowchart-connectors");
      const layers = stage.querySelector(".project-ui-flowchart-layers");
      return Boolean(svg.compareDocumentPosition(layers) & Node.DOCUMENT_POSITION_FOLLOWING);
    }), true);
    const firstLayout = await page.locator(".project-ui-flowchart").evaluate((stage) => ({ layers: [...stage.querySelectorAll("[data-flow-layer]")].map((layer) => [...layer.querySelectorAll("[data-project-map-node]")].map((node) => node.dataset.projectMapNode)), edge: stage.querySelector('[data-project-map-edge="overview-assets"]')?.getAttribute("d") }));
    await page.evaluate(() => renderProjectDetail());
    await page.waitForFunction(() => Boolean(document.querySelector('[data-project-map-edge="overview-assets"]')?.getAttribute("d")));
    const secondLayout = await page.locator(".project-ui-flowchart").evaluate((stage) => ({ layers: [...stage.querySelectorAll("[data-flow-layer]")].map((layer) => [...layer.querySelectorAll("[data-project-map-node]")].map((node) => node.dataset.projectMapNode)), edge: stage.querySelector('[data-project-map-edge="overview-assets"]')?.getAttribute("d") }));
    assert.deepEqual(secondLayout, firstLayout);
    assert.match(await page.locator('[data-project-view-evidence="overview/default"] .project-ui-requirements').textContent(), /Overview · 1 satisfied/);
    await page.locator('[data-project-view-evidence="overview/default"]').click();
    assert.equal(await page.locator("#evidence-lightbox").isVisible(), true);
    assert.equal(await page.locator("#evidence-lightbox-thumbnails .evidence-lightbox-thumbnail").count(), 3);
    await page.getByRole("button", { name: "Close evidence gallery" }).click();
    await page.getByRole("button", { name: "Back to App Map" }).click();
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute("data-project-map-group")), "workspace");
    const hostileGroupId = 'group\'"][data-project-map-group="spoof';
    await page.evaluate((groupId) => {
      const nodes = state.overview.project_view.map.nodes;
      nodes.find((node) => node.id === "workspace").id = groupId;
      nodes.filter((node) => ["overview", "assets"].includes(node.id)).forEach((node) => { node.group_id = groupId; });
      state.projectUiGroupId = "";
      renderProjectDetail();
    }, hostileGroupId);
    await page.getByRole("button", { name: "Open Workspace group" }).click();
    await page.getByRole("button", { name: "Back to App Map" }).click();
    assert.equal(await page.evaluate(() => document.activeElement?.dataset.projectMapGroup), hostileGroupId);
    await page.evaluate((groupId) => {
      const nodes = state.overview.project_view.map.nodes;
      nodes.find((node) => node.id === groupId).id = "workspace";
      nodes.filter((node) => ["overview", "assets"].includes(node.id)).forEach((node) => { node.group_id = "workspace"; });
      state.projectUiGroupId = "";
      renderProjectDetail();
    }, hostileGroupId);
    await page.evaluate(() => {
      const projection = state.overview.project_view;
      projection.map.edges = [{ id: "bad-edge", source: "overview", target: "missing" }];
      state.projectUiGroupId = "workspace";
      renderProjectDetail();
    });
    assert.match(await page.locator(".project-ui-map[role], .project-ui-map").textContent(), /Flowchart unavailable/);
    assert.equal(await page.locator("[data-project-map-node]").count(), 0);
    await page.evaluate(() => {
      state.overview.project_view.map.edges = [{ id: "overview-assets", source: "overview", target: "assets", label: "Open assets" }];
      state.projectUiGroupId = "";
      renderProjectDetail();
    });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    await page.emulateMedia({ reducedMotion: "reduce" });
    assert.equal(await page.locator(".project-ui-flowchart-node").evaluate((node) => parseFloat(getComputedStyle(node).transitionDuration) <= 0.001), true);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page.evaluate(() => {
      state.projectUiGroupId = "workspace";
      state.projectId = "project:fixture";
      state.ctrlId = "branch-ctrl";
      state.notificationBindingKey = "project:branch|branch-ctrl";
      navigateNotification({
        project_id: "project:branch", ctrl_id: "branch-ctrl",
        action_target: { view: "review", project_id: "project:branch", ctrl_id: "branch-ctrl", task_id: "branch-ctrl", subject_id: "proof-branch" },
      });
    });
    assert.deepEqual(await page.evaluate(() => ({ projectId: state.projectId, ctrlId: state.ctrlId, groupId: state.projectUiGroupId })), { projectId: "project:branch", ctrlId: "branch-ctrl", groupId: "" });
    await page.evaluate(() => selectProjectScope("project:fixture"));
    await page.evaluate(() => { state.projectUiGroupId = "workspace"; setView("settings"); renderSettings(); });
    await page.locator("#settings-scope").selectOption("project|project:branch");
    await page.waitForFunction(() => state.projectId === "project:branch" && state.projectUiGroupId === "");
    assert.deepEqual(await page.evaluate(() => ({ projectId: state.projectId, ctrlId: state.ctrlId, groupId: state.projectUiGroupId })), { projectId: "project:branch", ctrlId: "", groupId: "" });
    await page.evaluate(() => selectProjectScope("project:fixture"));
    await page.getByRole("tab", { name: "Agents", exact: true }).click();
    assert.match(await page.locator("#agent-hierarchy").textContent(), /CTRL/);
    await page.getByRole("tab", { name: "Role library", exact: true }).click();
    assert.equal(await page.locator(".role-choice").count(), 24);
    assert.match(await page.locator("#role-library-status").textContent(), /24 server-owned role manifests/);
    await page.locator("#role-search").fill("Game Development");
    assert.equal(await page.locator(".role-choice").count(), 1);
    assert.equal(await page.locator('.role-choice[data-role-select="developer"]').getAttribute("aria-selected"), "true");
    assert.match(await page.locator('#role-library-detail .role-match').textContent(), /Matched: Game Development · specialization/);
    await page.locator("#role-search").fill("");
    await page.locator(".role-filter > summary").click();
    await page.locator('[data-role-type="custom"]').uncheck();
    assert.equal(await page.locator(".role-choice").count(), 24);
    await page.locator('[data-role-type="builtin"]').uncheck();
    assert.equal(await page.locator(".role-choice").count(), 0);
    await page.locator("#role-filter-reset").click();
    assert.equal(await page.locator(".role-choice").count(), 24);
    await page.locator('.role-choice[data-role-select="developer"]').click();
    assert.equal(await page.locator('#role-library-detail .role-specializations li').count(), 4);
    assert.match(await page.locator('#role-library-detail').textContent(), /Developer[\s\S]*Boundaries/);
    await page.locator('.role-choice[data-role-select="reviewer"]').click();
    assert.match(await page.locator('#role-library-detail').textContent(), /Reviewer one[\s\S]*Reviewer four/);
    assert.doesNotMatch(await page.locator('#role-library-detail').textContent(), /Friendly|Hostile/);
    await page.locator('.role-choice[data-role-select="developer"]').click();
    await page.getByRole("button", { name: "Edit Developer" }).focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator("#role-editor").getByRole("button", { name: "Generate avatar" }).isDisabled(), true);
    assert.equal((await page.locator("#role-field-specializations").inputValue()).split("\n").length, 4);
    await page.getByRole("button", { name: "Close role editor" }).click();
    await page.getByRole("tab", { name: "Review", exact: true }).click();
    assert.equal(await page.locator(".review-row").count(), 6);
    assert.equal(await page.getByRole("button", { name: "Send feedback unavailable" }).first().isDisabled(), true);
    await page.getByRole("tab", { name: "Assets", exact: true }).click();
    assert.equal(await page.locator(".asset-tile").count(), 6);
    assert.equal(await page.locator(".asset-tile .asset-list-copy").count(), 0);
    assert.equal(await page.locator(".asset-tile .asset-quick-actions").count(), 6);
    assert.equal(await page.locator(".asset-tile .asset-image-button").first().getAttribute("aria-label"), "Open asset details for Evidence image 1");
    await page.locator(".asset-tile .asset-image-button").nth(1).click();
    assert.match(await page.locator("#asset-detail").textContent(), /Evidence image 2/);
    await page.getByRole("button", { name: "List", exact: true }).click();
    assert.equal(await page.locator(".asset-list-row").count(), 6);
    assert.equal(await page.getByRole("button", { name: "New revision", exact: true }).first().isDisabled(), true);
    assert.equal(await page.getByRole("button", { name: "Approve digest", exact: true }).first().isDisabled(), true);
    assert.match(await page.locator("#asset-detail").textContent(), /Revision history/);
    await page.getByRole("tab", { name: "Settings", exact: true }).click();
    assert.equal(await page.locator("#settings-grid > .settings-card").count(), 4);
    assert.equal(await page.getByRole("button", { name: "Replay tour" }).count(), 1);
    assert.equal(await page.locator("#settings-advanced").count(), 1);
    assert.equal(await page.locator("[data-qc-scope]").evaluate((element) => element.scrollWidth > element.clientWidth + 1), false);
    assert.deepEqual(desktop.runtimeErrors, []);
    await page.close();

    const noManifestPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const noManifestOverview = scopedFixture();
    delete noManifestOverview.project_view;
    const noManifest = await mount(noManifestPage, noManifestOverview, overrides);
    await noManifestPage.locator('#project-navigation [data-project-id="project:fixture"]').click();
    assert.equal(await noManifestPage.getByRole("tab", { name: "UI", exact: true }).isVisible(), false);
    assert.deepEqual(noManifest.runtimeErrors, []);
    await noManifestPage.close();

    const unknownPage = await browser.newPage({ viewport: { width: 1024, height: 760 } });
    const unknownOverview = scopedFixture();
    unknownOverview.project_inventory = { state: "UNKNOWN", available: false, source: "host_projects" };
    unknownOverview.navigation.project_inventory = structuredClone(unknownOverview.project_inventory);
    unknownOverview.navigation.projects = [];
    const unknown = await mount(unknownPage, unknownOverview, overrides);
    assert.equal(await unknownPage.locator("#project-navigation").textContent(), "Saved projects unavailable");
    assert.equal(await unknownPage.locator("#project-scope-filter").isDisabled(), true);
    assert.match(await unknownPage.locator("#overview-project-cards").textContent(), /Saved projects are unavailable/);
    assert.equal(await unknownPage.locator("#overview-summary").textContent(), "Project inventory unavailable");
    assert.deepEqual(unknown.runtimeErrors, []);
    await unknownPage.close();

    const tabletPage = await browser.newPage({ viewport: { width: 834, height: 1112 } });
    const tablet = await mount(tabletPage, scopedFixture(), overrides);
    assert.equal(await tabletPage.locator("#overview-project-cards .overview-project-card").count(), 7);
    assert.equal(await tabletPage.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
    assert.equal(await tabletPage.locator("#overview-project-cards [data-overview-project-id]").evaluateAll((elements) => elements.every((element) => {
      const box = element.getBoundingClientRect();
      return box.height >= 44 && box.right <= document.documentElement.clientWidth;
    })), true);
    await tabletPage.evaluate(() => selectProjectScope("project:fixture"));
    await tabletPage.getByRole("tab", { name: "UI", exact: true }).click();
    await tabletPage.getByRole("button", { name: "Map", exact: true }).click();
    await tabletPage.locator('[data-project-map-group="workspace"]').click();
    await tabletPage.waitForFunction(() => Boolean(document.querySelector('[data-project-map-edge="overview-assets"]')?.getAttribute("d")));
    const tabletFlow = await tabletPage.locator(".project-ui-flowchart").evaluate((stage) => {
      const box = stage.getBoundingClientRect();
      return { left: box.left, right: box.right, viewport: innerWidth, scrollWidth: stage.scrollWidth, clientWidth: stage.clientWidth };
    });
    assert.ok(tabletFlow.left >= 0 && tabletFlow.right <= tabletFlow.viewport && tabletFlow.scrollWidth <= tabletFlow.clientWidth, JSON.stringify(tabletFlow));
    assert.equal(await tabletPage.locator(".project-ui-flowchart-node").evaluateAll((nodes) => nodes.every((node) => node.getBoundingClientRect().height >= 44)), true);
    assert.equal(await tabletPage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    await tabletPage.locator('[data-view="agents"]').click();
    await tabletPage.getByRole("tab", { name: "Role library", exact: true }).click();
    const tabletGrid = tabletPage.locator("#role-library-grid");
    assert.equal(await tabletGrid.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length), 3);
    assert.equal(await tabletGrid.evaluate((element) => getComputedStyle(element).overflowY), "auto");
    assert.equal(await tabletGrid.evaluate((element) => element.scrollHeight > element.clientHeight), true);
    assert.equal(await tabletPage.locator('.role-choice[tabindex="0"]').count(), 1);
    await tabletPage.locator('.role-choice[tabindex="0"]').focus();
    await tabletPage.keyboard.press("ArrowRight");
    assert.equal(await tabletPage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), "analyst");
    await tabletPage.keyboard.press("ArrowDown");
    assert.equal(await tabletPage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), "auditor");
    await tabletPage.keyboard.press("Home");
    assert.equal(await tabletPage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), "accountant");
    await tabletPage.keyboard.press("End");
    assert.equal(await tabletPage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), "writer");
    assert.equal(await tabletPage.locator('.role-choice[aria-selected="true"]').evaluate((element) => {
      const grid = document.querySelector("#role-library-grid").getBoundingClientRect();
      const choice = element.getBoundingClientRect();
      return choice.top >= grid.top && choice.bottom <= grid.bottom;
    }), true);
    await tabletPage.keyboard.press("Home");
    await tabletPage.keyboard.press("Tab");
    assert.equal(await tabletPage.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Edit Accountant");
    assert.equal(await tabletPage.locator(".role-detail-actions .icon-button").evaluateAll((elements) => elements.every((element) => {
      const box = element.getBoundingClientRect();
      return box.width >= 44 && box.height >= 44;
    })), true);
    await tabletPage.getByRole("button", { name: "Edit Accountant" }).click();
    assert.equal(await tabletPage.locator("#role-editor button").evaluateAll((elements) => elements.filter((element) => !element.disabled).every((element) => {
      const box = element.getBoundingClientRect();
      return box.width >= 44 && box.height >= 44;
    })), true);
    await tabletPage.evaluate(() => renderRoleLibrary());
    await tabletPage.getByRole("button", { name: "Cancel" }).click();
    await tabletPage.waitForTimeout(50);
    assert.equal(await tabletPage.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Edit Accountant");
    await tabletPage.getByRole("button", { name: "Edit Accountant" }).click();
    await tabletPage.keyboard.press("Escape");
    await tabletPage.waitForTimeout(50);
    assert.equal(await tabletPage.locator("#role-editor").isVisible(), false);
    assert.equal(await tabletPage.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Edit Accountant");
    assert.equal(await tabletPage.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
    assert.deepEqual(tablet.runtimeErrors, []);
    await tabletPage.close();

    const mobilePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const mobile = await mount(mobilePage, overflowingProjectFixture(), overrides);
    const menuButton = mobilePage.locator("#mobile-menu-button");
    const menuBox = await menuButton.boundingBox();
    assert.ok(menuBox && menuBox.width >= 44 && menuBox.height >= 44);
    await mobilePage.evaluate(() => showError("Project refresh failed"));
    const errorBox = await mobilePage.locator("#error-surface").boundingBox();
    assert.ok(errorBox && menuBox && errorBox.y >= menuBox.y + menuBox.height);
    assert.ok((await mobilePage.getByRole("button", { name: "Try again" }).boundingBox())?.height >= 44);
    await menuButton.click();
    assert.equal(await mobilePage.locator("#console-drawer").getAttribute("aria-hidden"), "false");
    assert.equal(await mobilePage.locator(".workspace").evaluate((element) => element.inert), true);
    assert.equal(await mobilePage.locator("#project-navigation button").evaluateAll((elements) => elements.every((element) => element.getBoundingClientRect().height >= 44)), true);
    assert.equal(await mobilePage.locator("#project-navigation").evaluate((element) => getComputedStyle(element).overflowY), "auto");
    assert.equal(await mobilePage.locator("#project-navigation").evaluate((element) => element.scrollHeight > element.clientHeight), true);
    assert.equal(await mobilePage.locator(".project-navigation").evaluate((element) => getComputedStyle(element).overflowY), "hidden");
    assert.equal(await mobilePage.locator(".nav-footer").evaluate((element) => element.getBoundingClientRect().bottom <= document.querySelector("#console-drawer").getBoundingClientRect().bottom), true);
    assert.equal(await mobilePage.locator("#project-navigation").textContent().then((text) => text.includes("All projects")), false);
    assert.equal(await mobilePage.locator('#project-navigation [data-project-id="project:overflow-24"]').count(), 1);
    await mobilePage.keyboard.press("Escape");
    assert.equal(await menuButton.evaluate((element) => element === document.activeElement), true);
    await menuButton.click();
    await mobilePage.locator('[data-view="agents"]').click();
    await mobilePage.getByRole("tab", { name: "Role library", exact: true }).click();
    const mobileGrid = mobilePage.locator("#role-library-grid");
    assert.equal(await mobileGrid.evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length), 2);
    assert.equal(await mobileGrid.evaluate((element) => getComputedStyle(element).overflowY), "auto");
    assert.equal(await mobileGrid.evaluate((element) => element.scrollHeight > element.clientHeight), true);
    assert.equal(await mobilePage.locator('.role-choice[tabindex="0"]').count(), 1);
    await mobilePage.locator('.role-choice[tabindex="0"]').focus();
    await mobilePage.keyboard.press("ArrowRight");
    assert.equal(await mobilePage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), "analyst");
    await mobilePage.keyboard.press("ArrowDown");
    assert.equal(await mobilePage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), "artist");
    await mobilePage.keyboard.press("Home");
    await mobilePage.keyboard.press("End");
    assert.equal(await mobilePage.locator('.role-choice[aria-selected="true"]').getAttribute("data-role-select"), "writer");
    assert.equal(await mobilePage.locator('.role-choice[aria-selected="true"]').evaluate((element) => {
      const grid = document.querySelector("#role-library-grid").getBoundingClientRect();
      const choice = element.getBoundingClientRect();
      return choice.top >= grid.top && choice.bottom <= grid.bottom;
    }), true);
    await mobilePage.keyboard.press("Home");
    await mobilePage.keyboard.press("Tab");
    assert.equal(await mobilePage.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Edit Accountant");
    await mobilePage.getByRole("button", { name: "Edit Accountant" }).click();
    assert.equal(await mobilePage.locator("#role-editor").evaluate((element) => {
      const box = element.getBoundingClientRect();
      return box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight;
    }), true);
    assert.equal(await mobilePage.locator("#role-editor button").evaluateAll((elements) => elements.filter((element) => !element.disabled).every((element) => {
      const box = element.getBoundingClientRect();
      return box.width >= 44 && box.height >= 44;
    })), true);
    assert.equal(await mobilePage.locator(".role-editor-fields").evaluate((element) => getComputedStyle(element).overflowY), "auto");
    await mobilePage.keyboard.press("Escape");
    await mobilePage.waitForTimeout(50);
    assert.equal(await mobilePage.locator("#role-editor").isVisible(), false);
    assert.equal(await mobilePage.evaluate(() => document.activeElement?.getAttribute("aria-label")), "Edit Accountant");
    await menuButton.click();
    await mobilePage.getByRole("button", { name: /^swarm\b/i }).click();
    await mobilePage.getByRole("tab", { name: "UI", exact: true }).click();
    assert.equal(await mobilePage.locator(".project-ui-card").count(), 2);
    assert.equal(await mobilePage.locator(".project-ui-toolbar .segmented-control button").evaluateAll((elements) => elements.every((element) => element.getBoundingClientRect().height >= 44)), true);
    assert.equal(await mobilePage.locator(".project-ui-screens").evaluate((element) => getComputedStyle(element).gridTemplateColumns.split(" ").length), 1);
    await mobilePage.getByRole("button", { name: "Map", exact: true }).click();
    await mobilePage.locator('[data-project-map-group="workspace"]').click();
    await mobilePage.waitForFunction(() => Boolean(document.querySelector('[data-project-map-edge="overview-assets"]')?.getAttribute("d")));
    assert.equal(await mobilePage.locator(".project-ui-flowchart").evaluate((stage) => {
      const box = stage.getBoundingClientRect();
      return box.left >= 0 && box.right <= innerWidth && stage.scrollWidth <= stage.clientWidth;
    }), true);
    assert.equal(await mobilePage.locator(".project-ui-flowchart-node").evaluateAll((nodes) => nodes.every((node) => {
      const box = node.getBoundingClientRect();
      return box.height >= 44 && box.left >= 0 && box.right <= innerWidth;
    })), true);
    assert.equal(await mobilePage.locator("[data-qc-scope]").evaluate((element) => element.scrollWidth > element.clientWidth + 1), false);
    assert.deepEqual(mobile.runtimeErrors, []);
    await mobilePage.close();
    console.log("SWARM console six-screen UI tests passed");
  } finally {
    await browser.close();
  }
