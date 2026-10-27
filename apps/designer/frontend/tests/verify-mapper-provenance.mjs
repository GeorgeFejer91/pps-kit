// Render canonical UI with the science owner's generated projection, optionally supplied externally.
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
const output = resolve(root, "artifacts/ui-workflow-check");
await mkdir(output, { recursive: true });
const fixturePath = process.env.PPS_STUDY_REVIEW_FIXTURE || resolve(root, "apps/designer/frontend/publication_study_reviews.v1.json");
const bytes = await readFile(fixturePath);
const reviews = JSON.parse(bytes);
assert.ok(reviews.inventoryAudit, "The fixture must contain generated inventory audit evidence");
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
const server = createServer(async (request, response) => {
  const path = resolve(root, `.${decodeURIComponent(new URL(request.url, "http://localhost").pathname)}`);
  if (!path.startsWith(root.endsWith(sep) ? root : root + sep)) { response.writeHead(403).end(); return; }
  try { const bytes = await readFile(path); response.writeHead(200, { "Content-Type": types[extname(path)] || "application/octet-stream" }).end(bytes); }
  catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
const base = `http://127.0.0.1:${server.address().port}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&page=documentation`;
const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
const report = { browser: browser.version(), fixtureSha256: createHash("sha256").update(bytes).digest("hex"), fixturePath, checks: [] };
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/publication_study_reviews.v1-*.json", route => route.fulfill({ json: reviews }));
  const author = reviews.publications.find(row => row.inventoryAudit?.evidenceStatus === "author_version_methods_reviewed_final_comparison_pending");
  assert.ok(author);
  const study = reviews.studies.find(row => row.networkNodeId === author.networkNodeId && row.contracts.some(contract => contract.evidenceSourceUrl && contract.evidenceSourceUrl !== contract.sourceUrl));
  assert.ok(study);
  const contract = study.contracts.find(row => row.evidenceSourceUrl && row.evidenceSourceUrl !== row.sourceUrl);
  await page.goto(`${base}&study=${encodeURIComponent(study.studyRowId)}#docs-publication-network`);
  const detail = page.locator("#publication-network-detail");
  await detail.waitFor({ state: "visible" });
  assert.match(await detail.innerText(), /Author-version Methods reviewed; final-version comparison pending/);
  const cell = detail.locator(`[data-study-id="${study.studyRowId}"] [data-contract-key="${contract.key}"]`);
  await cell.locator(":scope > summary").click();
  assert.equal(await cell.getByRole("link", { name: "Reviewed source / access record", exact: true }).getAttribute("href"), contract.evidenceSourceUrl);
  assert.equal(await cell.getByRole("link", { name: "Publication DOI", exact: true }).getAttribute("href"), contract.sourceUrl);
  assert.match(await cell.innerText(), /Review source type:/);
  const inventoryText = await page.locator("#publication-network-inventory-note").innerText();
  assert.ok(inventoryText.includes(`${reviews.inventoryAudit.registeredInventories} of ${reviews.inventoryAudit.publications} inventories registered`));
  assert.ok(inventoryText.includes(`${reviews.inventoryAudit.inventoryAndContractsAudited} inventory and contract audits complete`));
  report.checks.push("Actual reviewed source and DOI remain separate; author-version comparison remains pending; aggregate counts come from projection");
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await detail.scrollIntoViewIfNeeded();
    await page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, `overflow at ${width}`);
    await detail.screenshot({ path: resolve(output, `mapper-provenance-${width}.png`) });
  }
  report.geometry = await detail.locator(".publication-network-readiness dd").evaluateAll(nodes => nodes.map(node => ({
    text: node.textContent, overflow: node.scrollWidth > node.clientWidth + 1, fontSize: getComputedStyle(node).fontSize,
    textLayout: node.dataset.pretextResult || null,
  })));
  assert.ok(report.geometry.every(item => !item.overflow));
  assert.ok(report.geometry.every(item => ["fit", "reflow", "dom-fallback"].includes(item.textLayout)));
  await page.screenshot({ path: resolve(output, "mapper-provenance-viewport.png") });
  for (const evidenceStatus of ["abstract_or_metadata_inventory", "audited_source_access_gap", "not_registered"]) {
    const publication = reviews.publications.find(row => row.inventoryAudit?.evidenceStatus === evidenceStatus);
    assert.ok(publication, evidenceStatus);
    await page.goto(`${base}&publication=${encodeURIComponent(publication.networkNodeId)}#docs-publication-network`);
    await detail.waitFor({ state: "visible" });
    assert.equal(await detail.locator("dt").filter({ hasText: /^Inventory registry$/ }).locator("+ dd").innerText(), publication.inventoryAudit.registered ? "Registered" : "Not registered");
    const value = await detail.locator("dt").filter({ hasText: /^Methods inventory \/ access audit$/ }).locator("+ dd").innerText();
    assert.match(value, evidenceStatus === "abstract_or_metadata_inventory" ? /Methods inventory unresolved/ : evidenceStatus === "audited_source_access_gap" ? /Methods unavailable/ : /No registered inventory/);
  }
  report.checks.push("Registered abstract-only inventory, audited access blocker, and absent registry entry stay distinct");
  assert.deepEqual(errors, []);
  await writeFile(resolve(output, "mapper-provenance-report.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
  await new Promise(done => server.close(done));
}
