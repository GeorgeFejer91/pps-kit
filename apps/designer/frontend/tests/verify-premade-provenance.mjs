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
const resources = resolve(process.env.PPS_PREMADE_RESOURCES || resolve(root, "packages/pps-resources"));
const output = resolve(root, "artifacts/provenance-portability-review");
await mkdir(output, { recursive: true });
const template = "serino_2015_peri_hand_exp3";
const inventory = JSON.parse(await readFile(resolve(resources, "assets/preloads/preload_inventory.json"), "utf8"));
const assets = inventory.profiles.find(row => row.template_id === template).assets;
assert.ok(assets.length > 0 && assets.every(asset => asset.native_generation_provenance));
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml" };
const server = createServer(async (request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const resource = ["/assets/preloads/", "/assets/breathing/", "/study_templates/"].some(prefix => pathname.startsWith(prefix));
  const base = resource ? resources : root;
  const path = resolve(base, `.${pathname}`);
  if (!path.startsWith(base.endsWith(sep) ? base : base + sep)) { response.writeHead(403).end(); return; }
  try { response.writeHead(200, { "Content-Type": types[extname(path)] || "application/octet-stream" }).end(await readFile(path)); }
  catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
const report = { browser: browser.version(), template, resources, checks: [] };
function bundle(bytes) {
  const files = new Map(), view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 0;
  while (view.getUint32(offset, true) === 0x04034b50) {
    const size = view.getUint32(offset + 18, true), nameSize = view.getUint16(offset + 26, true);
    const start = offset + 30 + nameSize + view.getUint16(offset + 28, true);
    files.set(bytes.subarray(offset + 30, offset + 30 + nameSize).toString("utf8"), bytes.subarray(start, start + size));
    offset = start + size;
  }
  return { files, profile: JSON.parse(files.get("profile.json").toString("utf8")) };
}
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  const errors = [], dialogs = [], fetched = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("dialog", async dialog => { dialogs.push(dialog.message()); await dialog.dismiss(); });
  page.on("request", request => { if (request.url().endsWith(".native_generation.json")) fetched.push(request.url()); });
  await page.goto(`http://127.0.0.1:${server.address().port}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&template=${template}`);
  await page.waitForFunction(template => window.PPSDesignerApp?.getState()?.selected_template === template, template);
  const original = await page.evaluate(() => window.PPSDesignerApp.getState());
  await page.locator('[data-step-link="run"]').click();
  const download = page.waitForEvent("download");
  await page.locator("#export-profile-bundle").click();
  const firstPath = resolve(output, "premade-provenance.pps-profile");
  await (await download).saveAs(firstPath);
  const first = bundle(await readFile(firstPath));
  const sources = [...first.profile.design.noises, ...first.profile.design.custom_looming_files];
  assert.equal(fetched.length, assets.length);
  for (const source of sources) {
    const expected = assets.find(asset => asset.label === source.label);
    const receipt = source.native_premade_provenance;
    const bytes = await readFile(resolve(resources, expected.native_generation_provenance));
    assert.equal(receipt.json_utf8, bytes.toString("utf8"));
    assert.equal(receipt.sha256, createHash("sha256").update(bytes).digest("hex"));
    const audio = first.files.get(`assets/${source.browser_asset_id}`);
    assert.equal(JSON.parse(receipt.json_utf8).asset.sha256, createHash("sha256").update(audio).digest("hex"));
    assert.equal(JSON.parse(receipt.json_utf8).provenance.scientific_source_conformance, false);
  }
  report.checks.push("Actual export control embeds exact current Serino receipt bytes bound to each current WAV");
  const portableAssets = first.profile.assets.map(asset => ({ ...asset, base64: first.files.get(asset.path).toString("base64") }));
  await page.evaluate(async ({ original, profile, portableAssets }) => {
    for (const asset of portableAssets) {
      const bytes = Uint8Array.from(atob(asset.base64), character => character.charCodeAt(0));
      await window.PPSDesigner.drafts.storeAudio(new File([bytes], asset.source_name, { type: asset.media_type }));
    }
    original.design = profile.design;
    original.preload_inventory = { assets: [] };
    window.PPSDesignerApp.restoreHostedDraft(original);
  }, { original, profile: first.profile, portableAssets });
  await page.context().setOffline(true);
  const offline = page.waitForEvent("download");
  await page.locator("#export-profile-bundle").click();
  const secondPath = resolve(output, "premade-provenance-offline.pps-profile");
  await (await offline).saveAs(secondPath);
  const second = bundle(await readFile(secondPath));
  assert.deepEqual(second.profile.design, first.profile.design);
  assert.equal(fetched.length, assets.length);
  report.checks.push("Offline re-export uses embedded receipts and stored WAVs; all design provenance survives unchanged");
  await page.screenshot({ path: resolve(output, "premade-provenance-export.png") });
  assert.deepEqual(dialogs, []);
  await page.evaluate(() => {
    const snapshot = window.PPSDesignerApp.getState();
    const source = [...snapshot.design.noises, ...snapshot.design.custom_looming_files][0];
    source.native_premade_provenance.sha256 = "0".repeat(64);
    window.PPSDesignerApp.restoreHostedDraft(snapshot);
  });
  const rejection = page.waitForEvent("dialog");
  await page.locator("#export-profile-bundle").click();
  assert.match((await rejection).message(), /provenance checksum mismatch/i);
  report.checks.push("Corrupt embedded receipt produces a visible export error while offline");
  assert.deepEqual(errors, []);
  report.bundle = firstPath;
  report.offlineBundle = secondPath;
  await writeFile(resolve(output, "browser-report.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
  await new Promise(done => server.close(done));
}
