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

async function mount(page) {
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
    if (pathname === "/api/bootstrap") return route.fulfill(response(fixture.bootstrap));
    if (pathname === "/api/overview") return route.fulfill(response(fixture.overview));
    if (pathname === "/api/config" && request.method() === "POST") {
      const payload = request.postDataJSON();
      config.settings.execution.usage_saver = payload.changes["execution.usage_saver"];
      return route.fulfill(response({ ok: true, ...config }));
    }
    if (pathname === "/api/config") return route.fulfill(response(config));
    return route.abort();
  });
  await page.goto("http://swarm.test/", { waitUntil: "domcontentloaded" });
  await page.locator("#usage-saver-toggle").waitFor({ state: "attached" });
  try {
    await page.waitForFunction(() => {
      const toggle = document.querySelector("#usage-saver-toggle");
      return toggle && !toggle.disabled &&
        document.querySelector("#usage-saver-state")?.textContent === "Off";
    });
  } catch (error) {
    throw new Error(`Console fixture did not initialize: ${runtimeErrors.join(" | ") || error.message}`);
  }
  return runtimeErrors;
}

async function focusToggleWithKeyboard(page) {
  for (let presses = 1; presses <= 12; presses += 1) {
    await page.keyboard.press("Tab");
    if (await page.locator("#usage-saver-toggle").evaluate(
      (element) => document.activeElement === element,
    )) return presses;
  }
  throw new Error("Usage Saver was not reachable in the first 12 Tab stops");
}

const browser = await chromium.launch({
  headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
    : {}),
});
const results = [];
try {
  for (const width of [320, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 844 } });
    const runtimeErrors = await mount(page);

    const geometry = await page.evaluate(() => {
      const control = document.querySelector("#usage-saver-control");
      const label = control.querySelector("strong");
      const state = document.querySelector("#usage-saver-state");
      const rect = control.getBoundingClientRect();
      return {
        viewport: innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        control: { left: rect.left, right: rect.right, width: rect.width, height: rect.height },
        labelVisible: Boolean(label.offsetWidth && label.offsetHeight),
        stateVisible: Boolean(state.offsetWidth && state.offsetHeight),
        stateText: state.textContent,
      };
    });
    assert.ok(geometry.documentWidth <= width + 1, `${width}px document overflow`);
    assert.ok(geometry.bodyWidth <= width + 1, `${width}px body overflow`);
    assert.ok(geometry.control.left >= -1 && geometry.control.right <= width + 1);
    assert.equal(geometry.labelVisible, true);
    assert.equal(geometry.stateVisible, true);
    assert.equal(geometry.stateText, "Off");

    const tabPresses = await focusToggleWithKeyboard(page);
    const focus = await page.locator("#usage-saver-toggle").evaluate((element) => {
      const indicator = getComputedStyle(element.nextElementSibling);
      const rect = element.closest("#usage-saver-control").getBoundingClientRect();
      const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
      return {
        outlineStyle: indicator.outlineStyle,
        outlineWidth: indicator.outlineWidth,
        unobscured: Boolean(top && element.closest("#usage-saver-control").contains(top)),
      };
    });
    assert.notEqual(focus.outlineStyle, "none");
    assert.ok(parseFloat(focus.outlineWidth) >= 2);
    assert.equal(focus.unobscured, true);

    await page.keyboard.press("Space");
    await page.waitForFunction(() =>
      document.querySelector("#usage-saver-toggle")?.checked &&
      document.querySelector("#usage-saver-state")?.textContent === "On",
    );
    const screenshot = path.join(evidenceRoot, `usage-saver-${width}.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    await page.locator('[data-view="swarm"]').click();
    const hierarchy = await page.evaluate(() => {
      const ctrl = document.querySelector(".swarm-node.role-ctrl").getBoundingClientRect();
      const lead = document.querySelector(".swarm-node.role-lead").getBoundingClientRect();
      const stage = document.querySelector(".swarm-stage").getBoundingClientRect();
      const slots = [...document.querySelectorAll(".swarm-node.role-lead .doer-slot")];
      const slotRects = slots.map((slot) => slot.getBoundingClientRect());
      const spinner = document.querySelector(".swarm-node.role-lead > .node-meta .node-status.is-processing i");
      const spinnerStyle = getComputedStyle(spinner);
      const hierarchyRoot = document.querySelector("#swarm-nodes");
      return {
        ctrlAboveLead: ctrl.top < lead.top,
        ctrlVisible: ctrl.left < stage.right && ctrl.right > stage.left && ctrl.top < stage.bottom,
        slots: slots.length,
        standaloneDoers: hierarchyRoot.querySelectorAll(".swarm-node.role-doer").length,
        childArtifactCounts: ["Hierarchy renderer", "Visual polish", "Responsive proof"].map(
          (artifact) => hierarchyRoot.innerText.split(artifact).length - 1,
        ),
        slotTops: slotRects.map((rect) => Math.round(rect.top)),
        slotWidths: slotRects.map((rect) => Math.round(rect.width)),
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
      };
    });
    assert.equal(hierarchy.ctrlAboveLead, true);
    assert.equal(hierarchy.ctrlVisible, true);
    assert.equal(hierarchy.slots, 3);
    assert.equal(hierarchy.standaloneDoers, 0);
    assert.deepEqual(hierarchy.childArtifactCounts, [1, 1, 1]);
    assert.equal(new Set(hierarchy.slotTops).size, 1);
    assert.ok(hierarchy.slotWidths.every((slotWidth) => slotWidth > 60));
    assert.equal(hierarchy.titleAttributes, 0);
    assert.equal(hierarchy.metadataSurfaces, 0);
    assert.equal(hierarchy.hasEllipsisIndicator, false);
    assert.equal(hierarchy.statusLabel, "Status: active");
    assert.equal(hierarchy.spinner.width, "10px");
    assert.equal(hierarchy.spinner.height, "10px");
    assert.equal(hierarchy.spinner.borderRadius, "50%");
    assert.equal(hierarchy.spinner.animationName, "hierarchy-spin");
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
} finally {
  await browser.close();
}

console.log(JSON.stringify({ ok: true, evidenceRoot, results }, null, 2));
