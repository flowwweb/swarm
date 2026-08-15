import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const testsRoot = path.dirname(fileURLToPath(import.meta.url));
const consoleRoot = path.resolve(testsRoot, "..");
const staticRoot = path.join(consoleRoot, "static");
const fixture = JSON.parse(
  fs.readFileSync(path.join(testsRoot, "fixtures", "console-ui.json"), "utf8"),
);
const multiFixtureOverview = structuredClone(fixture.overview);
multiFixtureOverview.nodes.push(
  { id: "nested-ctrl", title: "🐙CTRL - Nested proof", role: "ctrl", role_label: "CTRL", icon: "🐙", artifact: "Nested proof", project_id: "project:fixture", project: "swarm", status: "active", created_at: 2050, updated_at: 2050, quiet_ms: 0, virtual: false, controller_ids: ["ctrl", "nested-ctrl"] },
  { id: "nested-doer", title: "📋TASK - Nested result", role: "doer", role_label: "TASK", worker_role: "DEV", icon: "📋", artifact: "Nested result", project_id: "project:fixture", project: "swarm", status: "active", created_at: 2060, updated_at: 2060, quiet_ms: 0, virtual: false, controller_ids: ["ctrl", "nested-ctrl"] },
  { id: "branch-ctrl", title: "🐙CTRL - Parallel proof", role: "ctrl", role_label: "CTRL", icon: "🐙", artifact: "Parallel proof", project_id: "project:fixture", project: "swarm", status: "quiet", created_at: 2100, updated_at: 2100, quiet_ms: 0, virtual: false, controller_ids: ["branch-ctrl"] },
  ...["One", "Two", "Three"].map((artifact, index) => ({ id: `branch-${index}`, title: `📋TASK - ${artifact}`, role: "doer", role_label: "TASK", worker_role: "DEV", icon: "📋", artifact, project_id: "project:fixture", project: "swarm", status: "quiet", created_at: 2200 + index, updated_at: 2200 + index, quiet_ms: 0, virtual: false, controller_ids: ["branch-ctrl"] })),
);
multiFixtureOverview.links.push({ source: "lead", target: "nested-ctrl" }, { source: "nested-ctrl", target: "nested-doer" });
multiFixtureOverview.links.push(...[0, 1, 2].map((index) => ({ source: "branch-ctrl", target: `branch-${index}` })));
multiFixtureOverview.roots.push("branch-ctrl");
multiFixtureOverview.controllers[0].nodes = 7;
multiFixtureOverview.controllers.push({ id: "nested-ctrl", title: "🐙CTRL - Nested proof", artifact: "Nested proof", project_id: "project:fixture", project: "swarm", status: "active", virtual: false, nodes: 2, active: 2 });
multiFixtureOverview.controllers.push({ id: "branch-ctrl", title: "🐙CTRL - Parallel proof", artifact: "Parallel proof", project_id: "project:fixture", project: "swarm", status: "quiet", virtual: false, nodes: 4, active: 0 });
const evidenceRoot = process.env.SWARM_UI_EVIDENCE_DIR ||
  fs.mkdtempSync(path.join(os.tmpdir(), "swarm-console-ui-"));
fs.mkdirSync(evidenceRoot, { recursive: true });

const css = fs.readFileSync(path.join(staticRoot, "styles.css"), "utf8");
const app = fs.readFileSync(path.join(staticRoot, "app.js"), "utf8");
const documentHtml = fs.readFileSync(path.join(staticRoot, "index.html"), "utf8")
  .replace('<link rel="stylesheet" href="/styles.css" />', () => `<style>${css}</style>`)
  .replace('<script src="/app.js" defer></script>', () => `<script>${app}</script>`)
  .replace("<head>", '<head><base href="http://swarm.test/">');

function response(body) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

async function mount(page, overview = fixture.overview) {
  const config = structuredClone(fixture.config);
  const runtimeErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") runtimeErrors.push(message.text());
  });
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  await page.route("http://swarm.test/**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (pathname === "/") {
      return route.fulfill({ status: 200, contentType: "text/html", body: documentHtml });
    }
    if (pathname === "/assets/swarm-wordmark.png") {
      return route.fulfill({ status: 200, contentType: "image/png", body: Buffer.from("fixture") });
    }
    if (pathname === "/api/bootstrap") return route.fulfill(response(fixture.bootstrap));
    if (pathname === "/api/overview") return route.fulfill(response(overview));
    if (pathname === "/api/config" && request.method() === "POST") {
      const payload = request.postDataJSON();
      config.settings.execution.usage_saver = payload.changes["execution.usage_saver"];
      return route.fulfill(response({ ok: true, ...config }));
    }
    if (pathname === "/api/config") return route.fulfill(response(config));
    return route.abort();
  });
  await page.goto("http://swarm.test/", { waitUntil: "domcontentloaded" });
  await page.locator('[data-setting="execution.usage_saver"]').waitFor({ state: "attached" });
  try {
    await page.waitForFunction(() => {
      const toggle = document.querySelector('[data-setting="execution.usage_saver"]');
      return toggle && !toggle.disabled && document.querySelector("#view-title")?.textContent === "Graph";
    });
  } catch (error) {
    throw new Error(`Console fixture did not initialize: ${runtimeErrors.join(" | ") || error.message}`);
  }
  return runtimeErrors;
}

async function focusToggleWithKeyboard(page) {
  for (let presses = 1; presses <= 30; presses += 1) {
    await page.keyboard.press("Tab");
    if (await page.locator('[data-setting="execution.usage_saver"]').evaluate(
      (element) => document.activeElement === element,
    )) return presses;
  }
  throw new Error("Usage Saver was not reachable in the first 30 Tab stops");
}

const browser = await chromium.launch({
  headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
    : {}),
});
const results = [];
try {
  for (const width of [390, 834, 1440]) {
    const page = await browser.newPage({ viewport: { width, height: width === 1440 ? 1000 : 844 } });
    const runtimeErrors = await mount(page);

    const geometry = await page.evaluate(() => {
      return {
        viewport: innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        title: document.querySelector("#view-title")?.textContent,
      };
    });
    assert.ok(geometry.documentWidth <= width + 1, `${width}px document overflow`);
    assert.ok(geometry.bodyWidth <= width + 1, `${width}px body overflow`);
    assert.equal(geometry.title, "Graph");

    await page.locator('[data-view="settings"]').click();
    const tabPresses = await focusToggleWithKeyboard(page);
    const focus = await page.locator('[data-setting="execution.usage_saver"]').evaluate((element) => {
      const indicator = getComputedStyle(element.nextElementSibling);
      const rect = element.closest(".switch").getBoundingClientRect();
      const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return {
        outlineStyle: indicator.outlineStyle,
        outlineWidth: indicator.outlineWidth,
        unobscured: Boolean(top && element.closest(".switch").contains(top)),
      };
    });
    assert.notEqual(focus.outlineStyle, "none");
    assert.ok(parseFloat(focus.outlineWidth) >= 2);
    assert.equal(focus.unobscured, true);

    await page.keyboard.press("Space");
    await page.waitForFunction(() => document.querySelector('[data-setting="execution.usage_saver"]')?.checked && !document.querySelector("#save-settings")?.disabled);
    const screenshot = path.join(evidenceRoot, `usage-saver-${width}.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    await page.locator('[data-view="swarm"]').click();
    const hierarchy = await page.evaluate(() => {
      const ctrl = document.querySelector(".swarm-node.role-ctrl").getBoundingClientRect();
      const lead = document.querySelector(".swarm-node.role-lead").getBoundingClientRect();
      const stage = document.querySelector(".swarm-stage").getBoundingClientRect();
      const spinner = document.querySelector(".swarm-node.role-lead > .node-meta .node-status.is-processing i");
      const spinnerStyle = getComputedStyle(spinner);
      const hierarchyRoot = document.querySelector("#swarm-nodes");
      return {
        ctrlAboveLead: ctrl.top < lead.top,
        ctrlVisible: ctrl.left < stage.right && ctrl.right > stage.left && ctrl.top < stage.bottom,
        taskNodes: hierarchyRoot.querySelectorAll(".swarm-node").length,
        standaloneDoers: hierarchyRoot.querySelectorAll(".swarm-node.role-doer").length,
        workers: [...hierarchyRoot.querySelectorAll(".node-worker")].map((node) => node.textContent.trim()),
        delegatedLabels: [...hierarchyRoot.querySelectorAll(".swarm-node:not(.role-ctrl) .node-role")].map((node) => node.textContent.trim()),
        childArtifactCounts: ["Hierarchy renderer", "Visual polish", "Responsive proof"].map(
          (artifact) => hierarchyRoot.innerText.split(artifact).length - 1,
        ),
        titleAttributes: hierarchyRoot.querySelectorAll("[title]").length,
        metadataSurfaces: document.querySelectorAll(".stage-legend, .claim-note").length,
        hasEllipsisIndicator: /(^|\s)(\.{3}|…)(\s|$)/.test(hierarchyRoot.textContent),
        statusLabel: document.querySelector(".swarm-node.role-lead .node-status").getAttribute("aria-label"),
        spinner: {
          width: spinnerStyle.width,
          height: spinnerStyle.height,
          borderRadius: spinnerStyle.borderRadius,
          animationName: spinnerStyle.animationName,
        },
        controllerOptions: document.querySelectorAll("#controller-filter option").length,
        scopeCopy: document.querySelector("#scope-copy")?.textContent,
        scopedActivity: document.querySelectorAll("#scope-activity .pulse-row").length,
        scroll: (() => {
          const scroller = document.querySelector(".swarm-scroll");
          return { clientWidth: scroller.clientWidth, scrollWidth: scroller.scrollWidth, clientHeight: scroller.clientHeight, scrollHeight: scroller.scrollHeight };
        })(),
      };
    });
    assert.equal(hierarchy.ctrlAboveLead, true);
    assert.equal(hierarchy.ctrlVisible, true);
    assert.equal(hierarchy.taskNodes, 5);
    assert.equal(hierarchy.standaloneDoers, 3);
    assert.deepEqual(hierarchy.workers, ["LEAD●Carson", "DEV●Lovelace", "DESIGN●Eames", "TEST●Noether"]);
    assert.ok(hierarchy.delegatedLabels.every((label) => label === "TASK"));
    assert.deepEqual(hierarchy.childArtifactCounts, [1, 1, 1]);
    assert.equal(hierarchy.titleAttributes, 0);
    assert.equal(hierarchy.metadataSurfaces, 0);
    assert.equal(hierarchy.hasEllipsisIndicator, false);
    assert.equal(hierarchy.statusLabel, "Status: active");
    assert.equal(hierarchy.spinner.width, "10px");
    assert.equal(hierarchy.spinner.height, "10px");
    assert.equal(hierarchy.spinner.borderRadius, "50%");
    assert.equal(hierarchy.spinner.animationName, "hierarchy-spin");
    assert.equal(hierarchy.controllerOptions, 1);
    assert.match(hierarchy.scopeCopy, /5 nodes/);
    assert.equal(hierarchy.scopedActivity, 3);
    if (width === 1440) {
      const toggle = page.locator("#rail-toggle");
      assert.equal(await toggle.getAttribute("aria-expanded"), "true");
      await toggle.focus();
      await page.keyboard.press("Enter");
      assert.equal(await toggle.getAttribute("aria-expanded"), "false");
      assert.equal(await page.locator(".app-shell").evaluate((node) => node.classList.contains("rail-collapsed")), true);
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.locator('[data-setting="execution.usage_saver"]').waitFor({ state: "attached" });
      assert.equal(await page.locator("#rail-toggle").getAttribute("aria-expanded"), "false", "collapsed rail state did not persist");
      await page.screenshot({ path: path.join(evidenceRoot, "hierarchy-1440-collapsed.png"), fullPage: true });
      await page.locator("#rail-toggle").click();
    }
    await page.emulateMedia({ reducedMotion: "reduce" });
    assert.equal(
      await page.locator(".swarm-node.role-lead > .node-meta .node-status.is-processing i").evaluate(
        (spinner) => getComputedStyle(spinner).animationName,
      ),
      "none",
    );
    const hierarchyScreenshot = path.join(evidenceRoot, `hierarchy-${width}.png`);
    await page.screenshot({ path: hierarchyScreenshot, fullPage: true });
    const runtime = {
      errors: [...runtimeErrors],
      result: runtimeErrors.length === 0 ? "clear" : "errors",
    };
    results.push({ width, tabPresses, focus, geometry, hierarchy, screenshot, hierarchyScreenshot, runtime });
    assert.deepEqual(runtimeErrors, []);
    await page.close();
  }
  const sparseOverview = structuredClone(fixture.overview);
  sparseOverview.nodes = sparseOverview.nodes.slice(0, 1);
  sparseOverview.links = [];
  sparseOverview.controllers[0].nodes = 1;
  const sparsePage = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const sparseErrors = await mount(sparsePage, sparseOverview);
  const sparseScroll = await sparsePage.evaluate(() => {
    const scroller = document.querySelector(".swarm-scroll");
    return { documentWidth: document.documentElement.scrollWidth, clientWidth: scroller.clientWidth, scrollWidth: scroller.scrollWidth, clientHeight: scroller.clientHeight, scrollHeight: scroller.scrollHeight };
  });
  assert.ok(sparseScroll.documentWidth <= 391);
  assert.ok(sparseScroll.scrollWidth <= sparseScroll.clientWidth, "one task graph has horizontal scroll");
  assert.ok(sparseScroll.scrollHeight <= sparseScroll.clientHeight, "one task graph has vertical scroll");
  assert.deepEqual(sparseErrors, []);
  await sparsePage.close();
  const multiPage = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const multiErrors = await mount(multiPage, multiFixtureOverview);
  await multiPage.locator('[data-view="swarm"]').click();
  assert.deepEqual(await multiPage.locator("#controller-filter option").allTextContents(), [
    "Ship console · 7 nodes", "Nested proof · 2 nodes", "Parallel proof · 4 nodes",
  ]);
  await multiPage.locator("#controller-filter").selectOption("nested-ctrl");
  assert.equal(await multiPage.locator(".swarm-node").count(), 2, "nested CTRL does not own its independent subtree");
  assert.match(await multiPage.locator("#swarm-nodes").innerText(), /Nested result/);
  await multiPage.locator("#controller-filter").selectOption("ctrl");
  assert.match(await multiPage.locator("#swarm-nodes").innerText(), /Nested result/, "parent CTRL lost a nested descendant");
  await multiPage.locator("#controller-filter").selectOption("branch-ctrl");
  const multiGeometry = await multiPage.evaluate(() => {
    const scroller = document.querySelector(".swarm-scroll");
    return { documentWidth: document.documentElement.scrollWidth, clientWidth: scroller.clientWidth, scrollWidth: scroller.scrollWidth, nodes: document.querySelectorAll(".swarm-node").length };
  });
  assert.ok(multiGeometry.documentWidth <= 391, "multi-node graph leaked into document overflow");
  assert.ok(multiGeometry.scrollWidth > multiGeometry.clientWidth, "wide multi-node graph did not retain contained navigation");
  assert.equal(multiGeometry.nodes, 4);
  assert.deepEqual(multiErrors, []);
  await multiPage.close();
} finally {
  await browser.close();
}

assert.match(app, /document\.visibilityState === "visible"/);
assert.match(app, /document\.visibilityState === "hidden"/);
assert.match(app, /api\("\/api\/presence", \{ method: "POST" \}\)/);
assert.match(app, /controller-filter/);
console.log(JSON.stringify({ ok: true, evidenceRoot, results }, null, 2));
