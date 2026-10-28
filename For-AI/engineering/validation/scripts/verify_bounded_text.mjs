// Real DOM and locked Pretext regression; no native or physical timing claim.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../../../", import.meta.url));
const server = createServer(async (request, response) => {
  const path = resolve(root, `.${new URL(request.url, "http://localhost").pathname}`);
  if (!path.startsWith(root.endsWith(sep) ? root : root + sep)) return response.writeHead(403).end();
  try { response.writeHead(200, { "Content-Type": "text/javascript" }).end(await readFile(path)); }
  catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.setContent(`<html lang="en"><style>
    [data-pretext] { box-sizing:border-box; width:160px; height:64px;
      padding:4px; border:1px solid; font:16px/20px Arial; overflow-wrap:break-word; }
    .large { font-size:32px; line-height:40px; }
  </style><body>
    <div id="fit" data-pretext>Save profile</div>
    <div id="short" data-pretext style="height:18px;overflow:hidden">Save profile</div>
    <div id="wrap" data-pretext>Save the complete experimental profile</div>
    <div id="one" data-pretext data-pretext-mode="single-line">Save the complete experimental profile</div>
    <div id="rich" data-pretext style="height:20px;overflow:hidden"><strong>Read the full experimental profile</strong></div>
    <div id="rich-lines" data-pretext data-pretext-max-lines="1"><strong>Read the full experimental profile</strong></div>
    <div id="mixed-line" data-pretext data-pretext-max-lines="1">SOA <sup>2</sup> <span style="font-size:12px">(ms)</span></div>
    <div id="space" data-pretext style="word-spacing:3px;height:auto">Readable fallback text</div>
    <div id="grow" data-pretext style="height:32px">Save</div>
    <div id="empty" data-pretext></div>
    <div id="normal" data-pretext style="line-height:normal;height:auto">Natural line height</div>
  </body></html>`);
  await page.evaluate(async () => {
    const pretext = await import("/apps/designer/frontend/node_modules/@chenglou/pretext/dist/layout.js");
    const { initializeBoundedText } = await import("/packages/pps-resources/assets/ui/bounded-text.mjs");
    window.prepares = 0; window.clears = 0;
    window.measurement = initializeBoundedText(document.body, { ...pretext,
      prepareWithSegments(...args) { window.prepares++; return pretext.prepareWithSegments(...args); },
      clearCache() { window.clears++; pretext.clearCache(); },
    });
  });
  const result = id => page.locator(`#${id}`).getAttribute("data-pretext-result");
  await page.waitForFunction(() => document.getElementById("fit").dataset.pretextResult);
  assert.equal(await result("fit"), "fit");
  assert.equal(await result("short"), "no-fit", "hidden vertical overflow cannot qualify");
  assert.equal(await result("wrap"), "reflow");
  assert.equal(await result("one"), "no-fit", "single-line policy checks line budget");
  assert.equal(await result("rich"), "no-fit", "rich DOM fallback still checks clipping");
  assert.equal(await result("rich-lines"), "no-fit", "rich rendered lines obey their budget");
  assert.equal(await result("mixed-line"), "dom-fallback", "mixed inline type still occupies one rendered line");
  assert.equal(await page.locator("#mixed-line").getAttribute("data-pretext-dom-line-count"), "1");
  assert.equal(await page.locator("#mixed-line").getAttribute("data-pretext-line-count"), null, "flattened prediction is not a verified rich DOM count");
  assert.equal(await result("space"), "dom-fallback");
  assert.equal(await page.locator("#space").getAttribute("data-pretext-dom-result"), "fit");
  assert.equal(await result("empty"), "fit");
  assert.equal(await result("normal"), "dom-fallback", "normal line height never uses invented Pretext height");
  const initial = await page.evaluate(() => ({ prepares: window.prepares, clears: window.clears }));
  await page.evaluate(() => { document.getElementById("fit").style.width = "180px"; });
  await page.waitForFunction(() => getComputedStyle(document.getElementById("fit")).width === "180px");
  await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
  assert.equal(await page.evaluate(() => window.prepares), initial.prepares, "width-only edits reuse preparation");
  await page.evaluate(() => document.fonts.dispatchEvent(new Event("loadingdone")));
  await page.waitForFunction(count => window.prepares > count, initial.prepares);
  assert.ok(await page.evaluate(count => window.clears > count, initial.clears), "font loads clear Pretext's own caches");
  const originalStyle = await page.locator("#fit").getAttribute("style");
  await page.evaluate(() => { document.getElementById("fit").style.fontSize = "18px"; });
  await page.waitForFunction(() => document.getElementById("fit").dataset.pretextFontSize === "18");
  await page.evaluate(value => document.getElementById("fit").setAttribute("style", value), originalStyle);
  await page.waitForFunction(() => document.getElementById("fit").dataset.pretextFontSize === "16");
  await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
  assert.equal(await result("fit"), "fit");
  assert.equal(await page.locator("#fit").evaluate(node => getComputedStyle(node).fontSize), "16px", "zoom is not canceled by smaller CSS type");
  await page.evaluate(() => { document.documentElement.style.zoom = ""; });
  await page.evaluate(() => document.getElementById("grow").classList.add("large"));
  await page.waitForFunction(() => document.getElementById("grow").dataset.pretextFontSize === "32");
  assert.equal(await result("grow"), "no-fit", "fixed box typography changes are remeasured");
  assert.equal(await page.locator("#grow").evaluate(node => getComputedStyle(node).fontSize), "32px", "user type never shrinks");
  await page.evaluate(() => { document.getElementById("grow").style.height = "60px"; });
  await page.waitForFunction(() => document.getElementById("grow").dataset.pretextResult === "fit");
  await page.evaluate(() => { document.documentElement.lang = "invalid_locale"; });
  await page.waitForFunction(() => document.getElementById("fit").dataset.pretextResult === "unavailable");
  await page.evaluate(() => { document.documentElement.lang = "en"; document.documentElement.dir = "rtl"; });
  await page.waitForFunction(() => document.getElementById("fit").dataset.pretextResult === "dom-fallback");
  await page.evaluate(() => { document.documentElement.dir = "ltr"; });
  await page.waitForFunction(() => document.getElementById("fit").dataset.pretextResult === "fit");
  const disconnected = await page.evaluate(() => { window.measurement.disconnect(); return window.prepares; });
  await page.evaluate(() => { document.getElementById("fit").textContent = "Changed"; window.measurement.refresh();
    document.fonts.dispatchEvent(new Event("loadingdone")); });
  await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
  assert.equal(await page.evaluate(() => window.prepares), disconnected, "disconnect retires every refresh path");
  assert.deepEqual(errors, []);
  console.log(`Bounded text: actual Chromium ${browser.version()}, locked Pretext, height/line/DOM limits, font/style/locale updates and cleanup passed.`);
} finally {
  await browser?.close();
  await new Promise(done => server.close(done));
}
