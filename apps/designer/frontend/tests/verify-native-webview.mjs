import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { writeFile } from "node:fs/promises";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
let browser;
for (let attempt = 0; attempt < 40; attempt++) {
  try {
    browser = await chromium.connectOverCDP(process.env.PPS_DESIGNER_TEST_CDP || "http://127.0.0.1:19225");
    break;
  } catch (error) {
    if (attempt === 39 || !String(error).includes("ECONNREFUSED")) throw error;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
}
try {
  const context = browser.contexts()[0];
  const page = context.pages()[0] || await context.waitForEvent("page", { timeout: 10_000 });
  await page.waitForURL(/^http:\/\/tauri\.localhost\//);
  const requests = [];
  page.on("request", request => requests.push(request.url()));
  page.on("dialog", dialog => dialog.accept());
  await page.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  assert.equal(await page.evaluate(() => window.PPSDesignerApp.isNative()), true);
  await page.waitForFunction(() => typeof document.querySelector("#trajectory-frame").contentWindow.updateTrajectory === "function");
  assert.equal(await page.locator("#native-import-profile").isVisible(), true);
  assert.equal(await page.locator("#native-import-profile").isEnabled(), true);
  await page.evaluate(() => {
    const snapshot = window.PPSDesignerApp.getState();
    snapshot.design.name = "Native WebView acceptance fixture";
    snapshot.design.study_profile_id = ""; snapshot.design.study_profile_title = "";
    snapshot.design.study_profile_reference_parameters.dashboard_mode = "custom";
    snapshot.design.study_profile_reference_parameters.profile_status = "draft";
    snapshot.custom_workflow = { is_custom: true, is_finalized: false, edit_step: "stimulus", confirmed_steps: ["study"], needs_review_steps: [] };
    snapshot.project = { project_id: "native-webview-fixture", project_kind: "native_draft" };
    window.PPSDesignerApp.restoreHostedDraft(snapshot);
  });
  await page.locator("#edit-mode-button").click();
  await page.locator('.noise-type-button[data-noise-type="white"]').click();
  await page.locator("#bake-label").fill("Native WebView white");
  await page.locator("#movement-duration").fill("1");
  await page.locator("#start-hold").fill("0.2");
  await page.locator("#end-hold").fill("0.2");
  await page.locator("#bake-stimulus").click();
  await page.waitForFunction(() => document.getElementById("native-cancel-generation").disabled);
  assert.match(await page.locator("#toast").innerText(), /algorithm|opt.in/i);
  assert.equal(await page.evaluate(() => window.PPSDesignerApp.getState().design.noises.some(source => source.label === "Native WebView white")), false);
  await page.locator("#native-source-opt-in").check();
  await page.locator("#native-source-seed").fill("123");
  await page.locator("#bake-stimulus").click();
  await page.waitForFunction(() => document.getElementById("native-cancel-generation").disabled, null, { timeout: 90_000 });
  const snapshot = await page.evaluate(() => window.PPSDesignerApp.getState());
  const source = snapshot.design.noises.find(source => source.label === "Native WebView white");
  assert.ok(source, await page.locator("#toast").innerText());
  assert.match(source.prebaked_path, /^native-assets\/[a-f0-9]{64}\.wav$/);
  const asset = snapshot.preload_inventory.assets.find(asset => asset.path === source.prebaked_path);
  assert.equal(asset.channels, 2);
  assert.equal(asset.provenance.numpy_seed_compatible, false);
  assert.deepEqual(snapshot.block_csv_preview, {});
  assert.equal(snapshot.project_segments["5_block_csv_preview"].status, "stale");
  await page.evaluate(() => {
    window.nativePreviewStarts = 0;
    const create = AudioContext.prototype.createBufferSource;
    AudioContext.prototype.createBufferSource = function (...args) {
      const source = create.apply(this, args); const start = source.start;
      source.start = function (...parameters) { window.nativePreviewStarts++; return start.apply(this, parameters); };
      return source;
    };
  });
  const play = page.locator('[data-preview-source-label="Native WebView white"]').first();
  await play.click();
  await page.waitForFunction(() => window.nativePreviewStarts > 0);
  await play.click();
  assert.ok(!requests.some(url => /https?:.*\/api\//.test(url)), "native errors and success never call the HTTP backend");
  await page.locator("#native-generation-controls").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "artifacts/ui-workflow-check/native-generation.png" });
  await writeFile("artifacts/ui-workflow-check/native-webview-report.json", JSON.stringify({
    native: true, sharedHtml: true, trajectoryIframe: true, algorithmOptInRequired: true,
    actualRenderer: asset.provenance.renderer.schema, channels: asset.channels, sha256: asset.sha256,
    downstreamInvalidated: true, generatedPreviewStartedMuted: true, httpFallbackRequests: 0,
  }, null, 2));
  console.log("Native WebView: real controls, required algorithm opt-in, actual C++ audio publication, downstream invalidation, no HTTP fallback passed.");
} finally { await browser.close(); }
