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
const wordmark = fs.readFileSync(path.resolve(consoleRoot, "..", "skills", "swarm", "assets", "swarm-wordmark.png"));
const favicon = fs.readFileSync(path.join(staticRoot, "swarm-favicon.svg"));
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
const viewportWidths = process.env.SWARM_UI_WIDTHS
  ? process.env.SWARM_UI_WIDTHS.split(",").map(Number)
  : [390, 834, 1440];

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
      return route.fulfill({ status: 200, contentType: "image/png", body: wordmark });
    }
    if (pathname === "/swarm-favicon.svg") {
      return route.fulfill({ status: 200, contentType: "image/svg+xml", body: favicon });
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

async function sidepanelAppearance(page) {
  return page.evaluate(() => {
    const icon = document.querySelector("#rail-toggle svg");
    const panel = document.querySelector("#console-sidepanel");
    const collapse = document.querySelector("#panel-collapse");
    const iconStyle = getComputedStyle(icon);
    const panelStyle = getComputedStyle(panel);
    const collapseStyle = getComputedStyle(collapse);
    const collapseRect = collapse.getBoundingClientRect();
    const collapseTop = document.elementFromPoint(
      collapseRect.left + collapseRect.width / 2,
      collapseRect.top + collapseRect.height / 2,
    );
    return {
      iconVisible: icon.getBoundingClientRect().width > 0 && iconStyle.display !== "none" && iconStyle.visibility !== "hidden" && Number(iconStyle.opacity) > 0,
      panelVisible: panelStyle.display !== "none" && panelStyle.visibility !== "hidden" && Number(panelStyle.opacity) > 0,
      collapseVisible: collapseRect.width > 0 && collapseRect.height > 0 && collapseStyle.display !== "none" && collapseStyle.visibility !== "hidden" && Number(collapseStyle.opacity) > 0,
      collapseUnobscured: Boolean(collapseTop && collapse.contains(collapseTop)),
      collapseSize: { width: collapseRect.width, height: collapseRect.height },
      collapseLabel: collapse.getAttribute("aria-label"),
      expanded: document.querySelector("#rail-toggle").getAttribute("aria-expanded"),
      panelHidden: panel.getAttribute("aria-hidden"),
      panelInert: panel.hasAttribute("inert"),
    };
  });
}

const browser = await chromium.launch({
  headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
    : {}),
});
const results = [];
try {
  for (const width of viewportWidths) {
    const page = await browser.newPage({ viewport: { width, height: width === 1440 ? 1000 : 844 }, hasTouch: width === 834 });
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
    if (width === 1440) {
      const faviconContract = await page.evaluate(async () => {
        const link = document.querySelector('link[rel~="icon"]');
        const response = await fetch(link.href);
        return {
          href: new URL(link.href).pathname,
          type: link.type,
          responseType: response.headers.get("content-type"),
          body: await response.text(),
        };
      });
      assert.equal(faviconContract.href, "/swarm-favicon.svg");
      assert.equal(faviconContract.type, "image/svg+xml");
      assert.match(faviconContract.responseType, /^image\/svg\+xml/);
      assert.match(faviconContract.body, /viewBox="0 0 128 128"/);
      assert.doesNotMatch(faviconContract.body, /SWARM/);
    }

    let sidepanel = await sidepanelAppearance(page);
    assert.equal(sidepanel.iconVisible && sidepanel.panelVisible, false, `${width}px rail icon and sidepanel rendered together`);
    if (width <= 720) {
      assert.equal(sidepanel.iconVisible, false);
      assert.equal(sidepanel.panelVisible, true);
      assert.equal(sidepanel.collapseVisible, false);
      assert.equal(sidepanel.expanded, "false");
      assert.equal(sidepanel.panelHidden, "false");
      assert.equal(sidepanel.panelInert, false);
    } else {
      assert.equal(sidepanel.iconVisible, true);
      assert.equal(sidepanel.panelVisible, false);
      assert.equal(sidepanel.collapseVisible, false);
      assert.equal(sidepanel.expanded, "false");
      assert.equal(sidepanel.panelHidden, "true");
      assert.equal(sidepanel.panelInert, true);
      const toggle = page.locator("#rail-toggle");
      const collapse = page.locator("#panel-collapse");
      if (width === 1440) {
        const toggleBox = await toggle.boundingBox();
        assert.ok(toggleBox, "rail control did not have a pointer target");
        await page.mouse.move(toggleBox.x + toggleBox.width / 2, toggleBox.y + toggleBox.height / 2);
        sidepanel = await sidepanelAppearance(page);
        assert.equal(sidepanel.panelVisible, true, "hover did not reveal the sidepanel");
        assert.equal(sidepanel.iconVisible, false, "rail icon remained visible beside the hover panel");
        assert.equal(sidepanel.collapseVisible, true, "hover panel did not render its in-panel control");
        assert.equal(sidepanel.collapseUnobscured, true, "hover panel control was obscured");
        assert.deepEqual(sidepanel.collapseSize, { width: 44, height: 44 });
        assert.equal(sidepanel.collapseLabel, "Keep sidepanel open");
        await page.waitForTimeout(220);
        await page.screenshot({ path: path.join(evidenceRoot, "sidepanel-hover-1440.png"), fullPage: true });
        await page.locator(".workspace").hover({ position: { x: 240, y: 160 } });
        assert.equal((await sidepanelAppearance(page)).panelVisible, false, "hover preview did not close after pointer exit");
        await toggle.focus();
        sidepanel = await sidepanelAppearance(page);
        assert.equal(sidepanel.panelVisible, true, "keyboard focus did not reveal the sidepanel");
        assert.equal(sidepanel.iconVisible, false, "rail icon remained visible beside the focused panel");
        assert.equal(await collapse.evaluate((element) => document.activeElement === element), true, "focus did not move to the visible panel control");
        await collapse.press("Enter");
      } else {
        await toggle.tap();
        await page.waitForTimeout(220);
        await page.screenshot({ path: path.join(evidenceRoot, "sidepanel-touch-834.png"), fullPage: true });
      }
      sidepanel = await sidepanelAppearance(page);
      assert.equal(sidepanel.panelVisible, true, `${width}px activation did not pin the sidepanel`);
      assert.equal(sidepanel.iconVisible, false, `${width}px rail icon remained visible beside the pinned panel`);
      assert.equal(sidepanel.collapseVisible, true, `${width}px pinned panel did not render its collapse control`);
      assert.equal(sidepanel.collapseUnobscured, true, `${width}px pinned panel collapse control was obscured`);
      assert.deepEqual(sidepanel.collapseSize, { width: 44, height: 44 });
      assert.equal(sidepanel.collapseLabel, "Collapse sidepanel");
      assert.equal(sidepanel.panelInert, false);
      if (width === 834) {
        await collapse.tap();
        sidepanel = await sidepanelAppearance(page);
        assert.equal(sidepanel.panelVisible, false, "visible touch control did not collapse the sidepanel");
        assert.equal(sidepanel.iconVisible, true, "touch collapse did not restore the rail icon");
        assert.equal(sidepanel.collapseVisible, false, "touch collapse left the in-panel control visible");
        await toggle.tap();
      } else {
        await collapse.click();
        sidepanel = await sidepanelAppearance(page);
        assert.equal(sidepanel.panelVisible, false, "visible desktop control did not collapse the sidepanel");
        assert.equal(sidepanel.iconVisible, true, "desktop collapse did not restore the rail icon");
        assert.equal(sidepanel.collapseVisible, false, "desktop collapse left the in-panel control visible");
        await toggle.click();
      }
      await page.waitForTimeout(220);
    }

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
        rect: { top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right },
        topElement: top ? `${top.tagName}.${top.className}` : "none",
      };
    });
    assert.notEqual(focus.outlineStyle, "none");
    assert.ok(parseFloat(focus.outlineWidth) >= 2);
    assert.equal(focus.unobscured, true, `${width}px focused setting was obscured: ${JSON.stringify(focus)}`);

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
        models: [...hierarchyRoot.querySelectorAll(".node-model")].map((node) => node.textContent.trim()),
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
        proofBadge: document.querySelector("#proof-badge")?.textContent,
        proofGates: [...document.querySelectorAll("#scope-proof .proof-columns section:first-child li")].map((node) => node.textContent.trim()),
        proofClaims: [...document.querySelectorAll("#scope-proof .proof-columns section:nth-child(2) li")].map((node) => node.textContent.trim()),
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
    assert.deepEqual(hierarchy.models, ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-luna", "gpt-5.6-luna"]);
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
    assert.equal(hierarchy.proofBadge, "T2 · PROOF_READY");
    assert.deepEqual(hierarchy.proofGates, ["contracts-fastSOURCE_STATIC · EXECUTEDPASS", "console-browserBROWSER_LOCAL · EXECUTEDPASS"]);
    assert.deepEqual(hierarchy.proofClaims, ["responsive consoleBROWSER_LOCALVERIFIED"]);
    assert.match(hierarchy.scopeCopy, /5 nodes/);
    assert.equal(hierarchy.scopedActivity, 3);
    if (width === 1440) {
      const toggle = page.locator("#rail-toggle");
      const collapse = page.locator("#panel-collapse");
      assert.equal(await toggle.getAttribute("aria-expanded"), "true");
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.locator('[data-setting="execution.usage_saver"]').waitFor({ state: "attached" });
      assert.equal(await page.locator("#rail-toggle").getAttribute("aria-expanded"), "true", "expanded sidepanel state did not persist");
      assert.equal((await sidepanelAppearance(page)).collapseVisible, true, "persisted panel lost its visible collapse control");
      await page.locator("#panel-collapse").press("Enter");
      assert.equal(await toggle.getAttribute("aria-expanded"), "false");
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.locator('[data-setting="execution.usage_saver"]').waitFor({ state: "attached" });
      assert.equal(await page.locator("#rail-toggle").getAttribute("aria-expanded"), "false", "collapsed sidepanel state did not persist");
      await page.screenshot({ path: path.join(evidenceRoot, "hierarchy-1440-collapsed.png"), fullPage: true });
      await page.locator("#rail-toggle").focus();
      await page.locator("#panel-collapse").press("Enter");
      await page.keyboard.press("Escape");
      assert.equal(await page.locator("#rail-toggle").getAttribute("aria-expanded"), "false", "Escape did not collapse the sidepanel");
      await page.locator("#rail-toggle").focus();
      await page.locator("#panel-collapse").press("Enter");
    }
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.waitForFunction(() => {
      const spinner = document.querySelector(".swarm-node.role-lead > .node-meta .node-status.is-processing i");
      return spinner?.isConnected && getComputedStyle(spinner).animationName === "none";
    });
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
    if (width > 720) await page.locator("#panel-collapse").click();
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
  assert.equal(await multiPage.locator("#proof-badge").textContent(), "Unavailable");
  assert.match(await multiPage.locator("#scope-proof").innerText(), /Host activity does not imply a passing gate/);
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
