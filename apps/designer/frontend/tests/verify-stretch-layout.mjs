// Actual compiled Chromium geometry; no native/device qualification.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { verifyAboutDialog } from "./about-dialog-browser.mjs";
const { chromium } = createRequire(import.meta.url)(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../../../", import.meta.url));
const output = resolve(root, "artifacts/designer-stretch");
await mkdir(output, { recursive: true });
const types = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".wav": "audio/wav" };
const server = createServer(async (request, response) => {
  let path = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  if (path.startsWith("/assets/preloads/") || path.startsWith("/assets/breathing/") || path.startsWith("/study_templates/")) path = `/packages/pps-resources${path}`;
  const target = resolve(root, `.${path}`);
  if (!target.startsWith(root.endsWith(sep) ? root : root + sep)) { response.writeHead(403).end(); return; }
  try { response.writeHead(200, { "Content-Type": types[extname(target)] || "application/octet-stream" }).end(await readFile(target)); }
  catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
const report = { browser: browser.version(), scope: "compiled hosted Chromium; ordered workflow/document flow and embedded settings panels",
  documentPolicies: ["Existing closed details do not paint their contents", "Narrow scientific tables use labelled row cards with existing six-row/all-row reveal", "Complete workflow, catalogue details and fullscreen root retain document scrolling"], cases: [], errors: [] };
const page = await browser.newPage();
await page.addInitScript(() => {
  window.stretchLongTasks = [];
  new PerformanceObserver(list => window.stretchLongTasks.push(...list.getEntries().map(entry => ({ start: entry.startTime, duration: entry.duration })))).observe({ type: "longtask", buffered: true });
});
page.on("pageerror", error => report.errors.push(error.message));
const settle = () => page.evaluate(async () => { await document.fonts.ready; await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))); });
try {
  await page.goto(`http://127.0.0.1:${server.address().port}/apps/designer/frontend/compiled/index.html`);
  await page.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  await settle();
  const matrix = [
    [900, 620, "light"], [1920, 620, "dark"], [900, 1400, "dark"],
    [1440, 1000, "light"], [1920, 1440, "light"], [320, 1000, "dark"],
    [568, 320, "light"], [760, 900, "light"], [761, 900, "dark"],
    [1440, 1000, "light", "zoom"], [1440, 1000, "dark", "spacing"],
  ];
  for (const [width, height, theme, mode = "normal"] of matrix) {
    await page.setViewportSize({ width, height });
    await page.evaluate(({ theme, mode }) => {
      document.documentElement.dataset.theme = theme;
      document.documentElement.style.zoom = mode === "zoom" ? "2" : "";
      document.getElementById("spacing-override")?.remove();
      if (mode === "spacing") {
        const style = document.createElement("style"); style.id = "spacing-override";
        style.textContent = "body * {line-height:1.5!important;letter-spacing:.12em!important;word-spacing:.16em!important} p {margin-bottom:2em!important}";
        document.head.appendChild(style);
      }
    }, { theme, mode });
    await settle();
    const geometry = await page.evaluate(() => {
      const visible = node => {
        if (!node.getClientRects().length || getComputedStyle(node).visibility === "hidden") return false;
        for (let parent = node.parentElement; parent; parent = parent.parentElement) {
          if (parent.tagName === "DETAILS" && !parent.open && !parent.querySelector(":scope > summary")?.contains(node)) return false;
        }
        const header = node.closest("thead");
        return !header || getComputedStyle(header).clipPath !== "inset(50%)";
      };
      const bounded = [...document.querySelectorAll(".panel[data-resizable-panel], .ingredient-editor, .trajectory-settings, .rail")].filter(visible);
      return {
        documentOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        outside: [...document.querySelectorAll(".decision-segment *")].filter(visible)
          .filter(node => node.getBoundingClientRect().right > innerWidth + 1).slice(0, 20).map(node => ({ id: node.id, class: node.className, right: node.getBoundingClientRect().right })),
        panels: bounded.map(node => ({ id: node.id || node.dataset.panelId || node.className,
          width: node.clientWidth, height: node.clientHeight, scrollWidth: node.scrollWidth, scrollHeight: node.scrollHeight,
          overflowX: getComputedStyle(node).overflowX, overflowY: getComputedStyle(node).overflowY })),
        clipped: [...document.querySelectorAll(".decision-segment button, .decision-segment .field-row > label, .bounded-select-value")]
          .filter(visible).filter(node => {
            // Hidden ::after help bubbles contribute to scroll metrics; measure
            // actual painted label ranges rather than suppressing that content.
            const range = document.createRange(); range.selectNodeContents(node);
            const text = range.getBoundingClientRect(), box = node.getBoundingClientRect();
            return text.width && (text.left < box.left - 2 || text.right > box.right + 2 || text.top < box.top - 2 || text.bottom > box.bottom + 2);
          })
          .map(node => ({ id: node.id, text: node.textContent.slice(0, 80), width: node.clientWidth, scrollWidth: node.scrollWidth, height: node.clientHeight, scrollHeight: node.scrollHeight })),
      };
    });
    report.cases.push({ width, height, theme, mode, ...geometry });
    // Keep all diagnostics, including failures, for the visual review iteration.
    for (const segment of ["study", "stimulus", "baseline", "run"]) {
      await page.locator(`#${segment}-segment`).evaluate(node => node.scrollIntoView({ block: "start", behavior: "instant" }));
      if ([900, 1440, 320].includes(width) && mode !== "zoom") await page.screenshot({ path: resolve(output, `${width}-${height}-${theme}-${mode}-${segment}.png`) });
    }
  }
  await page.evaluate(() => { document.documentElement.style.zoom = ""; document.getElementById("spacing-override")?.remove(); });
  await page.setViewportSize({ width: 900, height: 620 });
  const rowReveal = page.locator('[data-mobile-table-toggle="block-preview-table-1"]');
  const rowCount = Number(await rowReveal.getAttribute("data-row-count"));
  assert.equal(await page.locator("#block-preview-table-1 tbody tr:visible").count(), Math.min(6, rowCount));
  await rowReveal.click();
  assert.equal(await page.locator("#block-preview-table-1 tbody tr:visible").count(), rowCount);
  await rowReveal.click();
  assert.equal(await page.locator("#block-preview-table-1 tbody tr:visible").count(), 6);
  report.rowReveal = { first: 6, all: rowCount, completePlanRetained: true };
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator("#study").scrollIntoViewIfNeeded();
  // Existing keyboard panel resize must distribute the added space among groups.
  const positions = () => page.locator("#study").evaluate(panel => {
    const groups = [...panel.children].filter(node => !node.classList.contains("panel-resize-handle") && node.getClientRects().length);
    return { height: panel.clientHeight, gaps: groups.slice(1).map((node, i) => node.getBoundingClientRect().top - groups[i].getBoundingClientRect().bottom) };
  });
  const compact = await positions();
  const handle = page.getByRole("separator", { name: "Resize study panel", exact: true });
  await handle.focus();
  for (let i = 0; i < 8; i++) await handle.press("ArrowDown");
  await settle();
  const expanded = await positions();
  assert.ok(expanded.height > compact.height + 40);
  assert.ok(expanded.gaps.every((gap, i) => gap > compact.gaps[i] + 10), "Extra height is shared between ordered groups");
  report.keyboardResize = { compact, expanded };
  // Real modal focus and close return, using an existing action.
  await page.getByRole("button", { name: "About Segment 0: Choose or Create Study", exact: true }).click();
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => document.activeElement.dataset.segmentInfo), "study");
  report.focusReturn = true;
  report.aboutDialogs = await verifyAboutDialog(page, output);
  // Stress only presentation strings, then restore the actual profile by reload.
  const longLabel = "Long study label — العربية 漢字 👩🏽‍🔬 " + "unbroken-profile-identifier".repeat(5);
  for (const width of [320, 900, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.locator(".segment-zero-picker .bounded-select-value").evaluate((node, label) => node.textContent = label, longLabel);
    await settle();
    const measured = await page.locator(".segment-zero-picker .bounded-select-value").evaluate(node => ({ width: node.clientWidth,
      scrollWidth: node.scrollWidth, height: node.clientHeight, scrollHeight: node.scrollHeight, result: node.dataset.pretextResult }));
    assert.ok(measured.scrollWidth <= measured.width + 1 && measured.scrollHeight <= measured.height + 1, JSON.stringify(measured));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    await page.locator("#study").evaluate(node => node.scrollIntoView({ block: "start", behavior: "instant" }));
    await page.screenshot({ path: resolve(output, `long-label-${width}.png`) });
  }
  await page.reload();
  await page.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => document.documentElement.style.zoom = "2");
  await page.getByRole("combobox", { name: "Profile", exact: true }).click();
  await settle();
  report.zoomMenu = await page.evaluate(() => {
    const owner = document.getElementById("template-select-combobox").getBoundingClientRect();
    const menu = document.getElementById("bounded-select-menu").getBoundingClientRect();
    return { leftDifference: Math.abs(owner.left - menu.left), widthDifference: Math.abs(owner.width - menu.width), right: menu.right };
  });
  assert.ok(report.zoomMenu.leftDifference < 1 && report.zoomMenu.widthDifference < 1 && report.zoomMenu.right <= 1440);
  await page.keyboard.press("Escape");
  await page.evaluate(() => document.documentElement.style.zoom = "");
  await page.setViewportSize({ width: 900, height: 620 });
  await page.locator("#trajectory-frame").scrollIntoViewIfNeeded();
  await page.waitForFunction(() => typeof document.getElementById("trajectory-frame").contentWindow?.updateTrajectory === "function");
  await page.waitForFunction(() => document.getElementById("trajectory-frame").contentDocument.querySelector("#hud strong").dataset.pretextResult);
  report.iframe = await page.locator("#trajectory-frame").evaluate(frame => {
    const hud = frame.contentDocument.getElementById("hud");
    const box = hud.getBoundingClientRect();
    return { left: box.left, top: box.top, right: box.right, bottom: box.bottom,
      width: frame.contentWindow.innerWidth, height: frame.contentWindow.innerHeight,
      measured: [...hud.children].map(node => ({ text: node.textContent, result: node.dataset.pretextResult })) };
  });
  assert.ok(report.iframe.right <= report.iframe.width && report.iframe.bottom <= report.iframe.height);
  assert.ok(report.iframe.measured.every(node => node.result));
  await page.setViewportSize({ width: 320, height: 1000 });
  await page.locator("#trajectory-frame").evaluate(frame => frame.contentDocument.documentElement.style.fontSize = "200%");
  await settle();
  report.iframeEnlarged = await page.locator("#trajectory-frame").evaluate(frame => {
    const box = frame.contentDocument.getElementById("hud").getBoundingClientRect();
    return { right: box.right, bottom: box.bottom, width: frame.contentWindow.innerWidth, height: frame.contentWindow.innerHeight };
  });
  assert.ok(report.iframeEnlarged.right <= report.iframeEnlarged.width && report.iframeEnlarged.bottom <= report.iframeEnlarged.height);
  await page.locator("#trajectory-frame").evaluate(frame => frame.contentDocument.documentElement.style.fontSize = "");
  await page.setViewportSize({ width: 900, height: 620 });
  // The existing populated schedule is the performance specimen; observe the
  // actual navigation/measurement work without inventing a pass threshold.
  const before = await page.evaluate(() => performance.now());
  await page.locator("#schedule-segment").scrollIntoViewIfNeeded();
  await settle();
  report.schedule = await page.evaluate(start => ({ rows: document.querySelectorAll("#schedule-segment tbody tr").length,
    measuredLabels: document.querySelectorAll("#schedule-segment [data-pretext-result]").length,
    elapsedMs: performance.now() - start, longTasks: window.stretchLongTasks.filter(task => task.start >= start),
    heapBytes: performance.memory?.usedJSHeapSize ?? null }), before);

  // Real preserve-clip mode must keep irrelevant trajectory controls hidden and
  // out of the keyboard path; CSS layout must not override the hidden attribute.
  await page.locator("#edit-mode-button").click();
  await page.locator("#customize-study-name").fill("Stretch control fixture");
  await page.setViewportSize({ width: 320, height: 620 });
  await page.screenshot({ path: resolve(output, "custom-dialog-320.png") });
  await page.locator("#customize-submit").click();
  await page.locator("#customize-modal").waitFor({ state: "hidden" });
  await page.locator("#import-audio-preserve").click();
  assert.equal(await page.locator("#trajectory-settings").isVisible(), false);
  assert.equal(await page.locator("#fixed-clip-trajectory-note").isVisible(), true);
  await page.locator("#import-audio-preserve").focus();
  for (let index = 0; index < 15; index++) {
    await page.keyboard.press("Tab");
    assert.equal(await page.evaluate(() => Boolean(document.activeElement.closest("#trajectory-settings"))), false);
  }
  await page.locator("#manual-audio-color").click();
  await page.locator("#audio-color-modal").waitFor({ state: "visible" });
  await page.locator("#audio-color-hex").focus();
  await page.keyboard.press("Tab");
  const colorControls = await page.locator("#audio-color-modal .modal-card").evaluate(node => ({
    width: node.clientWidth, scrollWidth: node.scrollWidth, overflow: getComputedStyle(node).overflowY,
    outside: [...node.querySelectorAll("*")].filter(child => child.getBoundingClientRect().right > node.getBoundingClientRect().right).map(child => ({ id: child.id, className: child.className, bounds: child.getBoundingClientRect().toJSON() })),
  }));
  await page.screenshot({ path: resolve(output, "color-dialog-320.png") });
  assert.equal(colorControls.width, colorControls.scrollWidth, JSON.stringify(colorControls));
  assert.equal(colorControls.overflow, "visible");
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#manual-audio-color").evaluate(node => node === document.activeElement), true);
  report.preserveClip = { trajectoryHidden: true, excludedFromKeyboardOrder: true, colorControls };

  await page.goto(`http://127.0.0.1:${server.address().port}/apps/designer/frontend/compiled/index.html?page=documentation#docs-publication-network`);
  await page.locator("[data-publication-network-root]").scrollIntoViewIfNeeded();
  await page.waitForFunction(() => document.querySelector("[data-publication-network-root]").dataset.publicationNetworkState === "ready");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator("#publication-network-search").fill("10.1371/journal.pone.0044306");
  const trigger = page.locator(".publication-network-result-button").first();
  await trigger.focus(); await trigger.press("Enter");
  const detail = page.locator("#publication-network-detail");
  await detail.waitFor({ state: "visible" });
  const connected = detail.locator("div").filter({ has: page.locator(":scope > .publication-network-citation-list") });
  report.citations = [];
  for (let index = 0; index < await connected.count(); index++) {
    const group = connected.nth(index);
    const summary = group.locator(":scope > p");
    const total = Number((await summary.innerText()).match(/of (\d+)/)[1]);
    const more = group.getByRole("button", { name: "Show more connected papers", exact: true });
    while (await more.isVisible()) {
      const previous = await group.locator("li").count();
      await more.focus(); await more.press("Enter");
      assert.equal(await group.locator("li button").nth(previous).evaluate(node => node === document.activeElement), true);
    }
    assert.equal(await group.locator("li").count(), total);
    report.citations.push({ total, shown: await group.locator("li").count() });
  }
  assert.ok(report.citations.some(group => group.total > 24), "Exercise a real formerly truncated citation list");
  await page.screenshot({ path: resolve(output, "connected-papers.png") });
  await page.keyboard.press("Escape");
  assert.equal(await trigger.evaluate(node => node === document.activeElement), true);
  await page.locator("#publication-network-search").fill("");
  await page.setViewportSize({ width: 1920, height: 620 });
  await page.locator("#publication-network-fullscreen").click();
  await page.waitForFunction(() => Boolean(document.fullscreenElement));
  await settle();
  report.fullscreen = await page.locator(".publication-network-shell").evaluate(node => ({
    bounds: node.getBoundingClientRect().toJSON(), summary: node.querySelector(".publication-network-summary-row").getBoundingClientRect().toJSON(),
    search: node.querySelector(".publication-network-search-row").getBoundingClientRect().toJSON(),
    graph: node.querySelector("#publication-network-graph").getBoundingClientRect().toJSON(),
  }));
  assert.ok(report.fullscreen.summary.bottom <= report.fullscreen.search.top + 1);
  assert.ok(report.fullscreen.graph.top >= 0 && report.fullscreen.graph.bottom <= 620, "Entire fullscreen graph fits below its measured controls");
  // Exercise the long fullscreen document, including controls below the graph.
  if (!await page.locator(".publication-network-results-panel").evaluate(node => node.open)) await page.locator(".publication-network-results-panel > summary").click();
  await page.getByRole("combobox", { name: "Sort list by", exact: true }).click();
  await page.getByRole("option", { name: "Title", exact: true }).click();
  assert.equal(await page.locator("#publication-network-results-sort").inputValue(), "title");
  await page.locator("#publication-network-results-more").click();
  await page.locator(".publication-network-result-button").last().focus();
  report.fullscreenResults = await page.evaluate(() => ({ focused: document.activeElement.className,
    scrollTop: document.fullscreenElement.scrollTop, bounds: document.activeElement.getBoundingClientRect().toJSON() }));
  assert.ok(report.fullscreenResults.bounds.top >= 0 && report.fullscreenResults.bounds.bottom <= 620);
  await page.screenshot({ path: resolve(output, "mapper-fullscreen-results-1920-620.png") });
  await page.locator("#publication-network-fullscreen").focus();
  await page.locator(".publication-network-shell").evaluate(node => node.scrollTo({ top: 0, behavior: "instant" }));
  await settle();
  await page.screenshot({ path: resolve(output, "mapper-fullscreen.png") });
  await page.locator("#publication-network-fullscreen").click();
  await page.waitForFunction(() => !document.fullscreenElement);
  await page.setViewportSize({ width: 320, height: 1000 });
  await page.locator("#publication-network-graph").scrollIntoViewIfNeeded();
  const point = await page.locator(".publication-network-node").first().boundingBox();
  await page.mouse.move(point.x + point.width / 2, point.y + point.height / 2);
  await page.locator("#publication-network-tooltip").waitFor({ state: "visible" });
  await settle();
  report.tooltip = await page.locator("#publication-network-tooltip").evaluate(node => {
    const box = node.getBoundingClientRect(), stage = node.parentElement.getBoundingClientRect();
    return { inline: node.dataset.inline, box: box.toJSON(), stage: stage.toJSON(), text: node.textContent };
  });
  assert.ok(report.tooltip.box.left >= report.tooltip.stage.left && report.tooltip.box.right <= report.tooltip.stage.right);
  assert.ok(report.tooltip.box.bottom <= report.tooltip.stage.bottom);
  await page.screenshot({ path: resolve(output, "mapper-tooltip-320.png") });
  await page.locator("#publication-network-tooltip").evaluate(node => node.style.fontSize = "24px");
  await page.mouse.move(point.x + point.width / 2 + 1, point.y + point.height / 2);
  await settle();
  const expandedTooltip = await page.locator("#publication-network-tooltip").evaluate(node => ({ inline: node.dataset.inline,
    bottom: node.getBoundingClientRect().bottom, stageBottom: node.parentElement.getBoundingClientRect().bottom, text: node.textContent }));
  assert.equal(expandedTooltip.inline, "true", "Oversized tooltip becomes complete document content below the graph");
  assert.ok(expandedTooltip.bottom <= expandedTooltip.stageBottom);
  assert.equal(expandedTooltip.text, report.tooltip.text);
  report.enlargedTooltip = expandedTooltip;
  await page.screenshot({ path: resolve(output, "mapper-tooltip-enlarged-320.png") });
  // The complete detail is document content; no silent nested clipping.
  for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.locator("#page-tab-downloads").click();
    await settle();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    await page.screenshot({ path: resolve(output, `downloads-${width}.png`) });
  }
  assert.deepEqual(report.errors, []);
  for (const item of report.cases) {
    assert.equal(item.documentOverflow, false, `${item.width}/${item.height}/${item.mode}: document overflow`);
    assert.deepEqual(item.outside, [], `${item.width}/${item.height}/${item.mode}: visible control/table outside the document`);
    assert.deepEqual(item.clipped, [], `${item.width}/${item.height}/${item.mode}: clipped labels`);
    for (const panel of item.panels) {
      assert.ok(panel.scrollWidth <= panel.width + 2 && panel.scrollHeight <= panel.height + 2, `${item.width}/${item.height}/${item.mode}: ${panel.id} overflow`);
      assert.ok(!["auto", "scroll", "hidden", "clip"].includes(panel.overflowY), `${panel.id} inner scroll/clipping`);
    }
  }
  report.passed = true;
} finally {
  await writeFile(resolve(output, "report.json"), JSON.stringify(report, null, 2));
  await browser.close(); await new Promise(done => server.close(done));
}
console.log("Designer stretch geometry, keyboard resize and dialog focus passed.");
