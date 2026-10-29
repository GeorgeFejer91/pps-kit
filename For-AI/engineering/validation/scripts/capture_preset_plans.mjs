// Development audit: capture complete shipped plans through public browser APIs.
// No state injection, count overrides, audio playback, or native acceptance.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../../../", import.meta.url));
const output = resolve(process.argv[2] || resolve(root, "artifacts/preset-functional-audit"));
const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");
const json = async path => JSON.parse(await readFile(resolve(root, path), "utf8"));
const templateDir = "packages/pps-resources/study_templates";
const templateFiles = (await readdir(resolve(root, templateDir))).filter(x => x.endsWith(".json")).sort();
const status = await json("packages/pps-resources/assets/preloads/profile_recreation_status.json");
assert.deepEqual(templateFiles.map(x => x.slice(0, -5)).sort(), status.profiles.map(x => x.template_id).sort());
const inputFiles = ["apps/designer/frontend/compiled/index.html", "apps/designer/frontend/app.js",
  "apps/designer/frontend/sequence_variants.js", "packages/pps-resources/assets/preloads/preload_inventory.json",
  "packages/pps-resources/assets/preloads/profile_recreation_status.json"];
for (const name of await readdir(resolve(root, "apps/designer/frontend/compiled/assets"))) {
  if (/\.(js|css)$/.test(name)) inputFiles.push(`apps/designer/frontend/compiled/assets/${name}`);
}
const inputHashes = {};
for (const path of inputFiles) inputHashes[path] = sha256(await readFile(resolve(root, path)));
await mkdir(output, { recursive: true });
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".wav": "audio/wav", ".woff2": "font/woff2" };
const server = createServer(async (request, response) => {
  let path;
  try { path = decodeURIComponent(new URL(request.url, "http://localhost").pathname); }
  catch { response.writeHead(400).end(); return; }
  if (path === "/dashboard/") path = "/apps/designer/frontend/compiled/index.html";
  else if (path.startsWith("/dashboard/")) path = path.replace("/dashboard/", "/apps/designer/frontend/compiled/");
  if (path.startsWith("/assets/") || path.startsWith("/study_templates/")) path = `/packages/pps-resources${path}`;
  const target = resolve(root, `.${path}`);
  if (!target.startsWith(root.endsWith(sep) ? root : root + sep)) { response.writeHead(403).end(); return; }
  try { response.writeHead(200, { "Content-Type": types[extname(target)] || "application/octet-stream" }).end(await readFile(target)); }
  catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
let browser;
const report = { schema: "pps-preset-plan-capture.v1", captured_at: new Date().toISOString(), input_hashes: inputHashes,
  evidence_scope: "Complete as-shipped browser plans; no native preparation or execution claim.", cases: [] };
try {
  browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
  report.browser = browser.version();
  for (const file of templateFiles) {
    const template_id = file.slice(0, -5);
    const entry = status.profiles.find(x => x.template_id === template_id);
    const result = { template_id, template_sha256: sha256(await readFile(resolve(root, templateDir, file))),
      configuration_eligible: entry.runner_readiness === "ready" && entry.profile_checks_passed === true,
      page_errors: [] };
    const page = await browser.newPage();
    page.on("pageerror", error => result.page_errors.push(error.message));
    try {
      await page.goto(`http://127.0.0.1:${server.address().port}/dashboard/?page=toolkit&forceStaticPreview=1&template=${template_id}`);
      await page.waitForFunction(id => window.PPSDesignerApp?.getState()?.design?.study_profile_id === id, template_id, { timeout: 30000 });
      const capture = await page.evaluate(() => {
        const state = window.PPSDesignerApp.getState();
        return { design: state.design, block_csv_preview: state.block_csv_preview,
          variants: window.PPSDesignerApp.getAssemblyVariants(), run_sequence_setup: state.run_sequence_setup,
          participant_orders: state.participant_orders, trial_pool_bake: state.trial_pool_bake,
          custom_workflow: state.custom_workflow, preload_inventory: state.preload_inventory };
      });
      const blocks = capture.block_csv_preview?.blocks || [];
      assert.ok(blocks.every(block => block.preview_rows.length === block.trial_count), "Truncated block rows");
      const count = blocks.reduce((sum, block) => sum + block.preview_rows.length, 0);
      if (result.configuration_eligible) {
        assert.ok(count > 0, "Eligible preset has no complete block rows");
        assert.equal(count, capture.trial_pool_bake.total_count, "Block rows do not cover the full trial pool");
      } else {
        assert.equal(count, 0, "Blocked preset unexpectedly offers an executable block plan");
        assert.equal(capture.custom_workflow.ready_to_prepare, false);
      }
      assert.deepEqual(result.page_errors, [], "Browser exception");
      const bytes = JSON.stringify(capture, null, 2) + "\n";
      result.capture_file = `${template_id}.json`;
      result.capture_sha256 = sha256(bytes);
      result.source_trial_count = count;
      result.source_block_rows = blocks.map(block => ({ index: block.block_index, label: block.block_label, rows: block.trial_count }));
      result.variant_count = capture.variants.length;
      result.status = result.configuration_eligible ? "complete_plan_captured" : "blocked_as_shipped";
      await writeFile(resolve(output, result.capture_file), bytes);
    } catch (error) { result.status = "failed"; result.error = String(error.stack || error); }
    finally { await page.close(); }
    report.cases.push(result);
    await writeFile(resolve(output, "capture-report.json"), JSON.stringify(report, null, 2) + "\n");
    console.log(`${template_id}: ${result.status}${result.source_trial_count !== undefined ? ` (${result.source_trial_count} source rows)` : ""}`);
  }
} finally { await browser?.close(); await new Promise(done => server.close(done)); }
process.exitCode = report.cases.some(x => x.status === "failed") ? 1 : 0;
