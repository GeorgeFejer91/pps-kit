// Exercise canonical built UI with generated science fixtures; no application API mocks.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../../../", import.meta.url));
const fixtureRoot = resolve(process.env.PPS_MAPPER_FIXTURE_ROOT || root);
const output = resolve(root, "artifacts/mapper-study-links-check");
await mkdir(output, { recursive: true });
const fixtures = new Map();
for (const name of ["publication_study_reviews.v1", "publication_network.v3"]) {
  const bytes = await readFile(resolve(fixtureRoot, `apps/designer/frontend/${name}.json`));
  fixtures.set(name, bytes);
  await writeFile(resolve(output, `${name}.json`), bytes);
}
const reviews = JSON.parse(fixtures.get("publication_study_reviews.v1"));
const graph = JSON.parse(fixtures.get("publication_network.v3"));
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".wav": "audio/wav", ".woff2": "font/woff2" };
const hashes = {};
const server = createServer(async (request, response) => {
  let pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const fixture = [...fixtures].find(([name]) => pathname.includes(`/assets/${name}-`) && pathname.endsWith(".json"));
  const resource = ["/assets/preloads/", "/assets/breathing/", "/study_templates/"].some(prefix => pathname.startsWith(prefix));
  if (resource) pathname = `/packages/pps-resources${pathname}`;
  const base = resource ? fixtureRoot : root;
  const file = resolve(base, `.${pathname}`);
  if (!file.startsWith(base.endsWith(sep) ? base : base + sep)) { response.writeHead(403).end(); return; }
  try {
    const bytes = fixture ? fixture[1] : await readFile(file);
    hashes[pathname] = createHash("sha256").update(bytes).digest("hex");
    response.writeHead(200, { "Content-Type": types[extname(file)] || "application/octet-stream" }).end(bytes);
  } catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
const base = `http://127.0.0.1:${server.address().port}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&page=documentation`;
const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", error => errors.push(error.message));
const report = { browser: browser.version(), fixtureRoot, counts: reviews.counts, inventoryAudit: reviews.inventoryAudit,
  sourceMode: "Canonical compiled UI; generated science JSON and real preset resources from fixtureRoot; no API mocks", checks: [], geometry: [] };
const detail = page.locator("#publication-network-detail");
async function ready() {
  await page.locator("[data-publication-network-root]").scrollIntoViewIfNeeded();
  await page.waitForFunction(() => document.querySelector("[data-publication-network-root]").dataset.publicationNetworkState === "ready");
}
try {
  await page.goto(`${base}#docs-publication-network`);
  await ready();
  for (const [name, doi, count] of [["teneggi", "10.1016/j.cub.2013.01.043", 6], ["ronga", "10.1073/pnas.2024548118", 3]]) {
    await page.locator("#publication-network-search").fill(doi);
    const trigger = page.locator(".publication-network-result-button");
    assert.equal(await trigger.count(), 1);
    await trigger.focus();
    await page.keyboard.press("Enter");
    await detail.waitFor({ state: "visible" });
    const studies = reviews.studies.filter(study => study.networkNodeId === `doi:${doi}`);
    assert.equal(studies.length, count);
    assert.equal(await detail.locator("[data-study-id]").count(), count);
    for (const study of studies) {
      const unit = detail.locator(`[data-study-id="${study.studyRowId}"]`);
      const summary = unit.locator(":scope > summary");
      assert.equal(await summary.locator("span").innerText(), study.experimentLabel || study.label);
      await summary.focus();
      await page.keyboard.press("Enter");
      assert.equal(await unit.evaluate(node => node.open), true);
      await page.waitForURL(url => url.searchParams.get("study") === study.studyRowId);
      assert.equal(new URL(page.url()).searchParams.get("study"), study.studyRowId);
      assert.deepEqual(await unit.locator("[data-open-designer-template]").evaluateAll(nodes => nodes.map(node => node.dataset.openDesignerTemplate)), study.templateIds);
      assert.match(await unit.innerText(), study.templateIds.length ? /Linked preset for this study/ : /No linked Toolkit template for this study/);
    }
    const deepLink = page.url();
    if (name === "teneggi") {
      assert.deepEqual(studies.filter(study => study.templateIds.length).map(study => study.studyRowId), [`doi:${doi}::c`]);
      const link = detail.locator(`[data-study-id="doi:${doi}::c"] [data-open-designer-template]`);
      const popupPromise = page.waitForEvent("popup");
      await link.focus();
      await page.keyboard.press("Enter");
      const preset = await popupPromise;
      const template = studies.find(study => study.studyRowId.endsWith("::c")).templateIds[0];
      await preset.waitForFunction(id => window.PPSDesignerApp?.getState()?.design?.study_profile_id === id, template, { timeout: 45000 });
      assert.equal(new URL(preset.url()).searchParams.get("template"), template);
      report.presetTitle = await preset.evaluate(() => window.PPSDesignerApp.getState().design.study_profile_title);
      assert.match(report.presetTitle, /Experiment 3/);
      await preset.screenshot({ path: resolve(output, "teneggi-preset.png") });
      await preset.close();
      report.checks.push("Only Teneggi Experiment 3 owns the preset; keyboard activation opens its real Designer profile");
    } else {
      assert.equal(await detail.locator("[data-open-designer-template]").count(), 0);
      const pilot = detail.locator(`[data-study-id="doi:${doi}::c"]`);
      await pilot.locator("[data-contract-key]").first().locator(":scope > summary").click();
      const text = await pilot.innerText();
      assert.match(text, /five|5/i);
      assert.match(text, /pilot/i);
      report.checks.push("Ronga newborn, adult and pilot identities remain separate with pilot source limits and no preset links");
    }
    await detail.screenshot({ path: resolve(output, `${name}-detail.png`) });
    await page.keyboard.press("Escape");
    assert.equal(await trigger.evaluate(node => node === document.activeElement), true);
    await page.goto(deepLink);
    await ready();
    await page.waitForFunction(id => [...document.querySelectorAll("[data-study-id]")].some(node => node.dataset.studyId === id && node.open), studies.at(-1).studyRowId);
    await page.keyboard.press("Escape");
    report.checks.push(`${name}: DOI find, keyboard disclosure, study deep-link restoration, Escape focus return`);
  }
  const adjacent = graph.nodes.find(node => node.id === "doi:10.1016/j.neuroimage.2012.06.063");
  assert.match(adjacent.scope.basis, /adjacent/i, "Fixture must contain the reviewed Avenanti boundary");
  await page.goto(`${base}&publication=${encodeURIComponent(adjacent.id)}#docs-publication-network`);
  await detail.waitFor({ state: "visible" });
  assert.ok((await detail.innerText()).includes(adjacent.scope.basis));
  assert.doesNotMatch(await detail.innerText(), /identifying an in-scope audio/);
  report.checks.push("Avenanti retains the generated adjacent-boundary inclusion basis");

  const longest = [...reviews.studies].sort((a, b) => (b.experimentLabel || b.label).length - (a.experimentLabel || a.label).length)[0];
  for (const studyId of [longest.studyRowId, "doi:10.1016/j.cub.2013.01.043::c"]) {
    const specimen = studyId === longest.studyRowId ? "long-label" : "preset";
    await page.goto(`${base}&study=${encodeURIComponent(studyId)}#docs-publication-network`);
    await detail.waitFor({ state: "visible" });
    await page.locator("#toast.visible").waitFor({ state: "hidden" });
    const unit = detail.locator(`[data-study-id="${studyId}"]`);
    for (const [width, accessibleText] of [[320, false], [768, false], [1440, false], [1920, false], [320, true]]) {
      await page.setViewportSize({ width, height: 1000 });
      if (accessibleText) {
        // Snapshot computed sizes before scaling so inherited percentages never compound.
        await page.evaluate(() => [...document.querySelectorAll("#publication-network-detail *")]
          .map(node => [node, parseFloat(getComputedStyle(node).fontSize)])
          .forEach(([node, size]) => node.style.setProperty("font-size", `${size * 2}px`, "important")));
        await page.addStyleTag({ content: "#publication-network-detail * { line-height: 1.5 !important; letter-spacing: .12em !important; word-spacing: .16em !important; } #publication-network-detail p { margin-bottom: 2em !important; }" });
      }
      await unit.locator(":scope > summary").evaluate(node => node.scrollIntoView({ block: "center" }));
      await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
      const geometry = await unit.locator(":scope > summary > span, [data-open-designer-template]").evaluateAll(nodes => nodes.map(node => ({
        text: node.textContent, overflow: node.scrollWidth > node.clientWidth + 1, textLayout: node.dataset.pretextResult,
        fontSize: getComputedStyle(node).fontSize, bounds: node.getBoundingClientRect().toJSON(),
      })));
      assert.ok(geometry.every(node => !node.overflow), JSON.stringify({ studyId, width, accessibleText, geometry }));
      assert.ok(geometry.every(node => ["fit", "reflow", "dom-fallback"].includes(node.textLayout)));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, `page overflow at ${width}`);
      report.geometry.push({ studyId, width, accessibleText, labels: geometry });
      const suffix = `${width}${accessibleText ? "-text-spacing" : ""}`;
      await unit.locator(":scope > summary").screenshot({ path: resolve(output, `${specimen}-${suffix}.png`) });
      if (specimen === "preset") {
        await unit.locator("[data-open-designer-template]").evaluate(node => node.scrollIntoView({ block: "center" }));
        await unit.locator("[data-open-designer-template]").screenshot({ path: resolve(output, `preset-link-${suffix}.png`) });
      }
    }
  }
  report.checks.push("Longest generated study label and actual preset link reflow at 320, 768, 1440 and 1920px, including enlarged spaced text at 320px");
  assert.deepEqual(errors, []);
} catch (error) {
  report.failure = { message: error.message, stack: error.stack };
  throw error;
} finally {
  report.errors = errors;
  report.servedHashes = hashes;
  await writeFile(resolve(output, "report.json"), JSON.stringify(report, null, 2));
  await browser.close();
  await new Promise(done => server.close(done));
}
console.log(JSON.stringify({ checks: report.checks, counts: report.counts, output }, null, 2));
