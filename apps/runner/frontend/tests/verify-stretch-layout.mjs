// Actual compiled browser geometry. No native execution, pairing, output or
// physical timing is inferred from this presentation-only matrix.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { resolve, extname, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
const { chromium } = createRequire(import.meta.url)(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
const root = resolve(fileURLToPath(new URL("../../../../", import.meta.url)));
const output = resolve(root, "artifacts/runner-stretch");
await mkdir(output, { recursive: true });
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };
const server = createServer(async (request, response) => {
  const pathname = new URL(request.url, "http://localhost").pathname;
  const target = resolve(root, `.${pathname}${pathname.endsWith("/") ? "index.html" : ""}`);
  if (!target.startsWith(root + sep)) { response.writeHead(403).end(); return; }
  try { const bytes = await readFile(target); response.writeHead(200, { "Content-Type": types[extname(target)] || "application/octet-stream" }).end(bytes); }
  catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
const browser = await chromium.launch({ headless: true, ignoreDefaultArgs: ["--hide-scrollbars"], args: ["--mute-audio"] });
const base = `http://127.0.0.1:${server.address().port}/apps/runner/compiled/`;
const failures = [], records = [], errors = [];
async function geometry(page, name, screenshot = false) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(140);
  const result = await page.evaluate(() => {
    const visible = e => {
      if (!e.getClientRects().length || getComputedStyle(e).visibility === "hidden") return false;
      for (let parent = e.parentElement; parent; parent = parent.parentElement) {
        if (parent.matches("details:not([open])") && !parent.querySelector(":scope > summary")?.contains(e)) return false;
      }
      return true;
    };
    const controls = [...document.querySelectorAll("button, input:not([type=checkbox]), select, textarea, summary")].filter(visible);
    const panels = [...document.querySelectorAll(".tab-panel.is-active, .workspace-view:not([hidden]), .panel, .phone-shell, .app-shell")].filter(visible);
    const box = e => { const b = e.getBoundingClientRect(); return { id: e.id || e.className, x: b.x, y: b.y, width: b.width, height: b.height }; };
    const overlaps = [];
    for (let i = 0; i < controls.length; i++) for (let j = i + 1; j < controls.length; j++) {
      const a = controls[i].getBoundingClientRect(), b = controls[j].getBoundingClientRect();
      if (Math.min(a.right,b.right) - Math.max(a.left,b.left) > 1 && Math.min(a.bottom,b.bottom) - Math.max(a.top,b.top) > 1)
        overlaps.push([controls[i].id || controls[i].textContent, controls[j].id || controls[j].textContent]);
    }
    return { layout: document.querySelector(".app-shell")?.dataset.layout || "phone-document",
      width: innerWidth, height: innerHeight, clientWidth: document.documentElement.clientWidth, pageWidth: document.documentElement.scrollWidth,
      pageHeight: document.documentElement.scrollHeight, overlaps,
      overflow: panels.filter(e => e.scrollWidth > e.clientWidth + 2 || (e.scrollHeight > e.clientHeight + 2 && getComputedStyle(e).overflowY !== "visible")).map(box),
      scrollPanels: panels.filter(e => ["auto", "scroll", "hidden", "clip"].includes(getComputedStyle(e).overflowY) && e.scrollHeight > e.clientHeight + 2).map(box),
      smallTargets: controls.filter(e => e.getBoundingClientRect().width < 24 || e.getBoundingClientRect().height < 24).map(box),
      smallType: controls.filter(e => parseFloat(getComputedStyle(e).fontSize) < 14).map(box),
      unmeasured: controls.filter(e => e.matches("button,summary") && !e.dataset.pretextResult).map(box),
      textNoFit: [...document.querySelectorAll('[data-pretext-result="no-fit"], [data-pretext-dom-result="no-fit"]')].filter(visible).map(e => ({ ...box(e), prediction: e.dataset.pretextResult, dom: e.dataset.pretextDomResult })),
      pretext: [...new Set(controls.filter(e => e.dataset.pretextResult).map(e => e.dataset.pretextResult))],
      gap: getComputedStyle(document.querySelector(".control-grid") || document.body).gap,
      font: getComputedStyle(document.body).fontSize,
    };
  });
  records.push({ name, ...result });
  if (result.pageWidth > result.clientWidth + 1 || result.overflow.length || result.scrollPanels.length || result.overlaps.length
      || result.smallTargets.length || result.smallType.length || result.unmeasured.length || result.textNoFit.length
      || (result.layout === "stretch" && result.pageHeight > result.height + 2)) failures.push({ name, ...result });
  if (screenshot) await page.screenshot({ path: resolve(output, `${name}.png`), fullPage: true });
  return result;
}
try {
  const page = await browser.newPage();
  page.on("pageerror", error => errors.push(error.message));
  const views = { control: ["run", "participant", "package", "inspection", "output", "overview"], logging: [null], remote: ["remote-access", "browser-control", "advertise"] };
  for (const [size, width, height] of [["minimum",1280,800],["normal",1440,900],["expanded",1920,1200],["compact",1120,768],["wide-minimum",1920,800],["minimum-tall",1280,1200],["wide-short",1600,600],["narrow-tall",850,1200],["phone",320,900]]) {
    await page.setViewportSize({ width, height });
    await page.goto(base);
    for (const theme of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme: theme });
      for (const [route, names] of Object.entries(views)) {
        await page.locator(`[data-tab="${route}"]`).click();
        for (const view of names) {
          if (view) await page.locator(`[data-workspace-open="${view}"]`).click();
          const result = await geometry(page, `${size}-${theme}-${view || route}`, size === "normal" || (size === "phone" && theme === "light"));
          if (["minimum", "normal", "expanded", "wide-minimum", "minimum-tall"].includes(size) && result.layout !== "stretch") failures.push({ name: `${size}-${theme}-${view || route}`, reason: "Default desktop workspace did not fit declared minimum" });
        }
      }
    }
  }
  const minimum = records.find(row => row.name === "minimum-light-run");
  const expanded = records.find(row => row.name === "expanded-light-run");
  assert.ok(parseFloat(expanded.font) > parseFloat(minimum.font), "preferred type can grow again with both budgets");
  assert.ok(parseFloat(expanded.gap) > parseFloat(minimum.gap), "surplus geometry increases cell gaps");
  // Read-only collections keep every item and reveal complete selected pages.
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(base);
  await page.locator('[data-workspace-open="inspection"]').click();
  await page.evaluate(() => {
    const list = document.getElementById("package-block-list");
    list.replaceChildren(...Array.from({ length: 11 }, (_, i) => {
      const row = document.createElement("li"); row.textContent = `Verified source block ${i + 1}`; return row;
    }));
  });
  await page.locator("#package-block-page").filter({ hasText: "1–4 of 11" }).waitFor();
  assert.equal(await page.locator("#package-block-list li").count(), 11);
  assert.equal(await page.locator("#package-block-list li:visible").count(), 4);
  await page.locator("#package-block-next").focus();
  await page.keyboard.press("Enter");
  assert.equal(await page.locator("#package-block-page").innerText(), "5–8 of 11");
  assert.equal(await page.evaluate(() => document.activeElement.id), "package-block-next");
  await page.locator("#package-block-next").click();
  assert.equal(await page.locator("#package-block-list li:visible").count(), 3);
  await geometry(page, "paged-package", true);
  await page.locator('[data-tab="remote"]').click();
  await page.locator('[data-workspace-open="browser-control"]').click();
  await page.evaluate(() => {
    document.getElementById("desktop-controller-targets").replaceChildren(...Array.from({ length: 9 }, (_, i) => {
      const button = document.createElement("button"); button.className = "beacon-target-button";
      button.dataset.streamId = `fixture-${i}`;
      button.textContent = `Unverified test target ${i + 1}`; button.setAttribute("aria-pressed", String(i === 6)); return button;
    }));
  });
  await page.locator("#desktop-controller-targets [aria-pressed=true]").waitFor();
  assert.equal(await page.locator("#desktop-controller-targets button").count(), 9);
  assert.equal(await page.locator("#desktop-controller-targets button:visible").count(), 4);
  await page.locator("#desktop-controller-targets + .collection-navigation button").last().click();
  for (let update = 0; update < 3; update++) {
    await page.evaluate(() => {
      const list = document.getElementById("desktop-controller-targets");
      list.replaceChildren(...[...list.children].map(node => node.cloneNode(true)));
    });
    await page.waitForTimeout(30);
    assert.equal(await page.locator("#desktop-controller-targets button:visible").count(), 1);
    assert.equal(await page.locator("#desktop-controller-targets button:visible").getAttribute("data-stream-id"), "fixture-8");
  }
  await page.evaluate(() => {
    const list = document.getElementById("desktop-controller-targets");
    list.replaceChildren(...[...list.children].map((node, i) => { const copy = node.cloneNode(true); copy.setAttribute("aria-pressed", String(i === 1)); return copy; }));
  });
  await page.locator('#desktop-controller-targets [data-stream-id="fixture-1"]').waitFor();
  await geometry(page, "paged-discovery", true);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(base);
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await geometry(page, "zoom-200", true);
  await page.evaluate(() => { document.documentElement.style.zoom = ""; });
  await page.locator('[data-workspace-open="participant"]').click();
  await page.addStyleTag({ content: "* { line-height:1.5 !important; letter-spacing:0.12em !important; word-spacing:0.16em !important; } p { margin-bottom:2em !important; }" });
  await geometry(page, "user-spacing", true);
  await page.goto(base);
  await page.locator('[data-workspace-open="package"]').click();
  await page.evaluate(() => {
    document.getElementById("package-label").textContent = "Prepared package — ".repeat(24);
    document.getElementById("session-group-status").textContent = "Result publication failed. Keep the existing files for inspection; whole-experiment completion is unconfirmed. ".repeat(40);
    document.getElementById("participant-chip").textContent = "A".repeat(64);
  });
  const long = await geometry(page, "long-status", true);
  assert.equal(long.layout, "flow", "unbounded status must cause explicit readable document reflow");
  await page.goto(base + "companion/index.html");
  for (const [size,width,height] of [["phone",320,900],["landscape",900,480],["normal",1280,800]]) {
    await page.setViewportSize({ width, height });
    for (const theme of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme: theme });
      for (const mode of ["controller", "target"]) {
        await page.locator(`[data-mode="${mode}"]`).click();
        await geometry(page, `companion-${size}-${theme}-${mode}`, theme === "light");
        await page.locator(`.mode-panel.is-active details`).evaluateAll(nodes => nodes.forEach(node => node.open = true));
        await geometry(page, `companion-${size}-${theme}-${mode}-details`);
      }
    }
  }
  await page.setViewportSize({ width: 640, height: 900 });
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await geometry(page, "companion-zoom-200", true);
  await writeFile(resolve(output, "matrix.json"), JSON.stringify({ browser: browser.version(), scope: "actual compiled Chromium presentation; no installed/native/hardware qualification", records, failures, errors }, null, 2));
  console.log(JSON.stringify({ cases: records.length, failures, errors }, null, 2));
  assert.deepEqual(errors, []);
  assert.deepEqual(failures, []);
} finally { await browser.close(); await new Promise(done => server.close(done)); }
