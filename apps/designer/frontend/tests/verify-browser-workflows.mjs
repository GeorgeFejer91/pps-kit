import { verifyDesignerControlNames, verifyRunnerNavigation } from "./accessibility-browser.mjs";
import { verifySequenceScaling } from "./sequence-scaling-browser.mjs";
import { verifyAbortedBrowserWrites, recordStorageEvents, verifyStartupRestoreOrdering } from "./indexeddb-browser.mjs";
import { verifyNativeDownloads } from "./downloads-browser.mjs";
import { verifyPremadeDuration } from "./premade-duration-browser.mjs";
import { verifySavedRowContracts } from "./row-contract-browser.mjs";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../../../", import.meta.url));
const output = resolve(root, "artifacts/ui-workflow-check");
await mkdir(output, { recursive: true });
const types = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".wav": "audio/wav", ".woff2": "font/woff2" };
const server = createServer(async (request, response) => {
  let path = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  if (path === "/dashboard/") path = "/apps/designer/frontend/compiled/index.html";
  else if (path.startsWith("/dashboard/")) path = path.replace("/dashboard/", "/apps/designer/frontend/compiled/");
  if (path.startsWith("/assets/preloads/")) path = `/packages/pps-resources${path}`;
  if (path.startsWith("/assets/breathing/")) path = `/packages/pps-resources${path}`;
  if (path.startsWith("/study_templates/")) path = `/packages/pps-resources${path}`;
  const target = resolve(root, `.${path}`);
  if (!target.startsWith(root.endsWith(sep) ? root : root + sep)) { response.writeHead(403).end(); return; }
  try { const bytes = await readFile(target); response.writeHead(200, { "Content-Type": types[extname(target)] || "application/octet-stream" }).end(bytes); }
  catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
const report = { browser: browser.version(), checks: [] };
try {
  await verifyStartupRestoreOrdering(browser, base);
  report.checks.push("Startup draft restore waits for the actual initial-template load; it cannot be overwritten by a late initial response");
  await verifyPremadeDuration(browser, base, output);
  report.checks.push("Premade PCM duration survives hosted customization, full block review, lock and portable export");
  await verifySavedRowContracts(browser, base, output);
  report.checks.push("Saved left/right and ITI contracts survive actual strip edit, all 300 trial rows, lock/reload, block CSV and portable export");
  const runner = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  runner.on("pageerror", error => errors.push(error.message));
  await runner.goto(`${base}/apps/runner/compiled/index.html`);
  await runner.locator("#state-chip").filter({ hasText: "Idle" }).waitFor();
  await runner.getByLabel("Participant code", { exact: true }).fill("LOCAL-002");
  await runner.getByLabel("Age", { exact: true }).fill("38");
  await runner.locator("#participant-handedness").selectOption("left");
  await runner.locator("#participant-gender").selectOption("prefer_not_to_say");
  await runner.locator("#participant-name").fill("Local test participant");
  await runner.locator("#name-sharing").check();
  for (let index = 0; index < 3; index++) {
    await runner.getByRole("button", { name: "Refresh snapshot", exact: true }).click();
    await runner.waitForFunction(() => document.getElementById("last-note").textContent !== "");
  }
  assert.equal(await runner.locator("#participant-code").inputValue(), "LOCAL-002");
  assert.equal(await runner.locator("#participant-age").inputValue(), "38");
  assert.equal(await runner.locator("#participant-handedness").inputValue(), "left");
  assert.equal(await runner.locator("#participant-gender").inputValue(), "prefer_not_to_say");
  assert.equal(await runner.locator("#name-sharing").isChecked(), true);
  await runner.locator("#setup-form").screenshot({ path: resolve(output, "runner-draft.png") });
  await runner.getByRole("button", { name: "Submit participant setup", exact: true }).click();
  await runner.locator("#setup-badge").filter({ hasText: /^Ready$/ }).waitFor();
  assert.equal(await runner.locator("#participant-chip").innerText(), "LOCAL-002");
  assert.deepEqual(errors, []);
  await verifyRunnerNavigation(runner);
  report.checks.push("Runner draft survives snapshot refresh and acknowledged submit; ordinary section navigation exposes current page and keyboard order");

  const nativeRunner = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await nativeRunner.addInitScript(() => {
    let callbackId = 0;
    const callbacks = new Map();
    let listener = null;
    window.nativeResponseRequests = [];
    const native = { epoch: 1, revision: 1, run: { phase: "prepared", complete: false },
      active_block: { active: false, display_block_index: 0 }, identity: { session_id: "browser-native-fixture" },
      safety: { local_armed: false }, allowed_actions: [], package_verified: true };
    window.advanceNativeFixture = (phase, block) => {
      native.revision++; native.run = { phase, complete: phase === "completed", participant_capture_ready: phase === "running" };
      native.active_block = { active: phase === "running", display_block_index: block, elapsed_s: 5, duration_s: 5 };
      callbacks.get(listener)?.({ payload: structuredClone(native) });
    };
    window.__TAURI_INTERNALS__ = { transformCallback(callback) { const id = ++callbackId; callbacks.set(id, callback); return id; },
      async invoke(command, args) {
        if (command === "plugin:event|listen") { listener = args.handler; return 1; }
        if (command === "runner_snapshot") return structuredClone(native);
        if (command === "remote_status") return { enabled: false };
        if (command === "runner_record_response") { window.nativeResponseRequests.push(args.request); return {}; }
        if (command === "native_group_status") return { revision: native.revision, partCount: 0, currentPart: 0, completedParts: 0, experimentComplete: false };
        if (command === "native_output_status") return { schema: "pps-runner-native-output-preflight.v1", phase: "idle",
          policyGeneration: "1", serviceGeneration: "1", operationGeneration: "1", inventoryGeneration: null,
          reservationGeneration: null, inFlight: false, cleanupPending: false, silenceOnly: true, executable: false, armed: false, qualified: false };
        if (command === "select_prepared_session") return { snapshot: structuredClone(native), summary: { sessionId: native.identity.session_id, blocks: [{ index: 1, label: "First" }, { index: 2, label: "Second" }] } };
        if (command === "inspect_prepared_execution") return { eventCount: 10, trialRowCount: 2, blockCount: 2, encodedBytes: 500,
          blocks: [{}, {}], inspectionScope: "schedule-only", timingQualification: "unqualified", executable: false };
        if (command === "prepare_first_audio_block") return { schema: "pps-runner-prepared-audio-summary.v1", preparationScope: "pcm-and-output-plan-cache",
          outputQualification: "unqualified", executable: false, outputPlanPrepared: true, blockOrdinal: native.active_block.display_block_index,
          sampleRateHz: 48000, sourceChannels: 3, sourceChannelLayout: "binaural-left-right-tactile", outputRoute: "canonical-three",
          responseMode: "left_right", responseChoices: ["left", "right"],
          scheduledEventCount: 5, frames: 48000, decodedBytes: 576000, cacheCapacityBlocks: 1, cacheByteBudget: 1280 * 1024 * 1024 };
        throw new Error(`Unexpected fixture command: ${command}`);
      } };
  });
  await nativeRunner.goto(`${base}/apps/runner/compiled/index.html`);
  await nativeRunner.locator("#select-session-manifest").click();
  await nativeRunner.locator("#inspect-prepared-execution").click();
  await nativeRunner.locator("#prepare-first-audio-block").click();
  await nativeRunner.locator("#prepared-audio-status").filter({ hasText: "Block 1 prepared" }).waitFor();
  await nativeRunner.evaluate(() => window.advanceNativeFixture("running", 1));
  const leftResponse = nativeRunner.getByRole("button", { name: "Left", exact: true });
  const rightResponse = nativeRunner.getByRole("button", { name: "Right", exact: true });
  await leftResponse.click();
  await rightResponse.focus();
  await nativeRunner.keyboard.press("Enter");
  await nativeRunner.keyboard.press("ArrowLeft");
  await nativeRunner.keyboard.press("ArrowRight");
  await nativeRunner.keyboard.press("Tab");
  assert.deepEqual(await nativeRunner.evaluate(() => window.nativeResponseRequests),
    ["left", "right", "left", "right"].map(choice => ({ choice, x: null, y: null })));
  for (const width of [320, 900, 1440]) {
    await nativeRunner.setViewportSize({ width, height: 900 });
    await leftResponse.scrollIntoViewIfNeeded();
    for (const button of [leftResponse, rightResponse]) {
      await button.evaluate(element => document.fonts.ready);
      assert.ok(await button.evaluate(element => element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight));
    }
    await nativeRunner.locator(".hero-panel").screenshot({ path: resolve(output, `runner-choices-${width}.png`) });
  }
  await nativeRunner.setViewportSize({ width: 900, height: 900 });
  await nativeRunner.evaluate(() => { document.documentElement.style.zoom = "2"; });
  await leftResponse.scrollIntoViewIfNeeded();
  assert.ok(await leftResponse.evaluate(element => element.scrollWidth <= element.clientWidth));
  assert.ok(await rightResponse.evaluate(element => element.scrollWidth <= element.clientWidth));
  for (const button of [leftResponse, rightResponse]) assert.ok(await button.evaluate(element => {
    const range = document.createRange(); range.selectNodeContents(element);
    return range.getClientRects().length === 1;
  }), "Left/Right labels remain on one readable line at 200% CSS zoom");
  await nativeRunner.locator(".hero-panel").screenshot({ path: resolve(output, "runner-choices-zoom.png") });
  await nativeRunner.evaluate(() => { document.documentElement.style.zoom = ""; window.advanceNativeFixture("prepared", 1); });
  await nativeRunner.getByRole("button", { name: "Prepare next audio occurrence", exact: true }).click();
  await nativeRunner.locator("#prepared-audio-status").filter({ hasText: "Block 2 prepared" }).waitFor();
  assert.equal(await nativeRunner.locator("#block-progress").evaluate(element => element.style.width), "0%");
  await nativeRunner.locator("#prepared-audio-status").screenshot({ path: resolve(output, "runner-next-block.png") });
  await nativeRunner.evaluate(() => window.advanceNativeFixture("completed", 2));
  assert.equal(await nativeRunner.locator("#prepare-first-audio-block").isDisabled(), true);
  report.checks.push("Runner real Left/Right pointer and keyboard controls emit distinct native IPC choices, fit 320–1440px/200% CSS zoom, retire on block transition and reject preparation after completion (native IPC mocked)");

  const designer = await browser.newPage({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
  await recordStorageEvents(designer);
  await designer.addInitScript(() => {
    window.previewStarts = 0;
    const create = AudioContext.prototype.createBufferSource;
    AudioContext.prototype.createBufferSource = function (...args) {
      const source = create.apply(this, args);
      const start = source.start;
      source.start = function (...parameters) { window.previewStarts++; return start.apply(this, parameters); };
      return source;
    };
  });
  designer.on("pageerror", error => errors.push(error.message));
  await designer.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1`);
  await designer.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  assert.equal(await designer.locator("#edit-mode-button").isVisible(), true, "Hosted authoring must expose the Edit switch");
  assert.equal(await designer.locator("#companion-panel").isVisible(), false, "Hosted authoring must keep V1 companion controls hidden");
  await verifyNativeDownloads(designer, output);
  report.checks.push("Native Preview installer/checksum links use the exact prerelease tag, preserve keyboard order and fit phone/desktop/200% CSS zoom; remote publication not assessed");
  await designer.locator("#profile-mode-panel").screenshot({ path: resolve(output, "hosted-edit-switch.png") });
  const play = designer.locator("[data-preview-source-label]").first();
  await play.click();
  await designer.waitForFunction(() => window.previewStarts === 1);
  await play.click();
  let releaseAudio;
  const interceptedAudio = new Promise(done => { releaseAudio = done; });
  await designer.route("**/*.wav", async route => { releaseAudio(route); });
  await play.click();
  const heldAudio = await interceptedAudio;
  const cancelledAudio = designer.waitForEvent("requestfailed", request => request.url().endsWith(".wav"));
  await designer.evaluate(() => window.PPSDesignerApp.restoreHostedDraft(window.PPSDesignerApp.getState()));
  await cancelledAudio;
  await heldAudio.abort().catch(() => {});
  await designer.unroute("**/*.wav");
  assert.equal(await designer.evaluate(() => window.previewStarts), 1);
  assert.equal(await designer.locator("[data-preview-source-label].playing").count(), 0);
  await verifyAbortedBrowserWrites(designer, resolve(output, "indexeddb-abort.json"));
  report.checks.push("Real IndexedDB abort after successful put rejects draft/audio writes, closes connections, retains prior data and permits retry");
  await designer.evaluate(async () => {
    const snapshot = window.PPSDesignerApp.getState();
    const asset = snapshot.preload_inventory.assets[0];
    const bytes = await (await fetch(window.PPSDesignerApp.preloadAssetUrl(asset.path))).arrayBuffer();
    const stored = await window.PPSDesigner.drafts.storeAudio(new File([bytes], "Uploaded.wav", { type: "audio/wav" }));
    snapshot.design.prestimulus_files.push({ label: "Restored upload", path: `browser-asset:${stored.id}`, render_mode: "preserve", target_duration_s: 4 });
    window.PPSDesignerApp.restoreHostedDraft(snapshot);
  });
  const restoredClip = designer.locator('[data-preview-source-label="Restored upload"]').first();
  await restoredClip.click();
  await designer.waitForFunction(() => window.previewStarts === 2);
  await restoredClip.click();
  report.checks.push("Premade WAV decodes and starts muted; project replacement cancels pending playback without stale start");
  await designer.evaluate(async () => {
    const snapshot = window.PPSDesignerApp.getState();
    snapshot.design.name = "Browser finalization regression";
    snapshot.design.study_profile_id = "";
    snapshot.design.study_profile_title = "";
    snapshot.design.study_profile_reference_parameters.dashboard_mode = "custom";
    snapshot.design.study_profile_reference_parameters.profile_status = "draft";
    snapshot.custom_workflow = { ...snapshot.custom_workflow, is_custom: true, is_finalized: false,
      edit_step: "run", confirmed_steps: ["study", "stimulus", "trials", "baseline", "block", "schedule"], needs_review_steps: [] };
    snapshot.project = { ...snapshot.project, project_id: "browser-regression", project_kind: "browser_draft" };
    window.PPSDesignerApp.restoreHostedDraft(snapshot);
    window.realDraftSave = window.PPSDesigner.drafts.save;
    window.PPSDesigner.drafts.save = async () => { throw new Error("Storage quota test failure"); };
  });
  const previewFixture = await designer.evaluate(() => window.PPSDesignerApp.getState());
  assert.ok(previewFixture.block_csv_preview.blocks.every(block => block.preview_rows.length === block.trial_count));
  const allPlanRows = previewFixture.block_csv_preview.blocks.flatMap(block => block.preview_rows);
  assert.equal(allPlanRows.length, 204);
  assert.equal(previewFixture.design.protocol.baseline_strategy, "stationary_burst");
  assert.ok(allPlanRows.filter(row => row.family === "baseline").every(row => row.baseline_mode === "stationary_burst"));
  assert.ok(allPlanRows.every(row => row.looming_segment_onset_s === 4));
  assert.ok(allPlanRows.filter(row => ["baseline", "audio_tactile"].includes(row.family))
    .every(row => row.tactile_onset_s === 4 + row.soa_ms / 1000));
  assert.ok(allPlanRows.filter(row => ["catch", "auditory_only"].includes(row.family))
    .every(row => row.tactile_onset_s === ""));
  await writeFile(resolve(output, "browser-full-block-plan.json"), JSON.stringify({
    design: previewFixture.design, block_csv_preview: previewFixture.block_csv_preview,
    variants: await designer.evaluate(() => window.PPSDesignerApp.getAssemblyVariants()),
    run_sequence_setup: previewFixture.run_sequence_setup, participant_orders: previewFixture.participant_orders,
  }, null, 2));
  await designer.locator("#edit-mode-button").click();
  await designer.locator("#save-study-profile").click();
  await designer.waitForFunction(() => document.getElementById("toast").textContent.includes("Storage quota test failure"));
  assert.equal(await designer.evaluate(() => window.PPSDesignerApp.getState().custom_workflow.is_finalized), false);
  assert.equal(await designer.locator("#save-study-profile").isEnabled(), true);
  assert.equal(await designer.locator("#edit-mode-button").getAttribute("aria-checked"), "true");
  await designer.locator("section").filter({ has: designer.locator("#save-study-profile") }).last()
    .screenshot({ path: resolve(output, "designer-save-failure.png") });
  await designer.evaluate(() => {
    window.PPSDesigner.drafts.save = async snapshot => {
      await new Promise(done => { window.finishDraftSave = done; });
      await window.realDraftSave(snapshot);
    };
  });
  await designer.locator("#save-study-profile").click();
  await designer.waitForFunction(() => typeof window.finishDraftSave === "function");
  const pendingCount = await designer.locator("#participants").inputValue();
  assert.equal(await designer.evaluate(() => document.querySelector(".app-shell").inert), true);
  assert.equal(await designer.evaluate(() => window.PPSDesignerApp.restoreHostedDraft({ design: { name: "Other project" } })), false);
  await designer.locator("#participants").focus();
  await designer.keyboard.type("99");
  assert.equal(await designer.locator("#participants").inputValue(), pendingCount);
  await designer.evaluate(() => window.finishDraftSave());
  await designer.waitForFunction(() => window.PPSDesignerApp.getState().custom_workflow.is_finalized);
  assert.equal(await designer.evaluate(() => document.querySelector(".app-shell").inert), false);
  assert.equal(await designer.evaluate(async () => (await window.PPSDesigner.drafts.load()).custom_workflow.is_finalized), true);
  assert.equal(await designer.locator("#edit-mode-button").getAttribute("aria-checked"), "false");
  const downloadPromise = designer.waitForEvent("download");
  const exportError = designer.waitForEvent("dialog").then(async dialog => {
    const message = dialog.message(); await dialog.dismiss(); throw new Error(`Bundle export: ${message}`);
  });
  await designer.locator("#export-profile-bundle").click();
  const download = await Promise.race([downloadPromise, exportError]);
  await download.saveAs(resolve(output, "browser-finalized.pps-profile"));
  assert.equal(await download.failure(), null);
  await designer.locator("section").filter({ has: designer.locator("#export-profile-bundle") }).last()
    .screenshot({ path: resolve(output, "designer-locked-export.png") });
  report.checks.push("Designer storage rejection stays editable; retry persists lock and exports bundle");
  report.text = await designer.locator("#export-profile-bundle").evaluate(element => ({ pretext: element.dataset.pretextResult,
    width: element.clientWidth, scrollWidth: element.scrollWidth, height: element.clientHeight, scrollHeight: element.scrollHeight }));
  assert.ok(report.text.pretext);
  assert.ok(report.text.scrollWidth <= report.text.width + 1);
  assert.ok(report.text.scrollHeight <= report.text.height + 1);
  assert.deepEqual(errors, []);

  const scaling = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await recordStorageEvents(scaling);
  scaling.on("pageerror", error => errors.push(error.message));
  scaling.on("dialog", dialog => dialog.accept());
  await scaling.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1`);
  await verifySequenceScaling(scaling);
  assert.deepEqual(errors, []);
  report.checks.push("Exact 46656 variants and oversized drafts survive real hosted edit, save and restore");
  await scaling.close();
  const accessible = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await recordStorageEvents(accessible);
  accessible.on("pageerror", error => errors.push(error.message));
  accessible.on("dialog", dialog => dialog.accept());
  await accessible.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1`);
  await verifyDesignerControlNames(accessible, resolve(output, "accessible-instructions.png"));
  assert.deepEqual(errors, []);
  report.checks.push("Designer names, keyboard/focus, 320–1920px and 200% CSS zoom; uploaded instruction bytes/hash survive preview, lock, reload and export; last-slot focus clears footer at 620/1000px");
  await accessible.close();

  const companionPreview = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  companionPreview.on("pageerror", error => errors.push(error.message));
  const pendingPreviews = [];
  let onPreview;
  await companionPreview.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/state") await route.fulfill({ json: { ...previewFixture, static_mode: false } });
    else if (path === "/api/run-sequence/preview") { pendingPreviews.push(route); onPreview?.(); }
    else await route.fulfill({ status: 404, json: { detail: "No unrelated mutation in this test" } });
  });
  await companionPreview.goto(`${base}/dashboard/`);
  await companionPreview.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  assert.equal(await companionPreview.evaluate(() => window.PPSDesignerApp.isHosted()), false);
  assert.equal(await companionPreview.locator("#companion-panel").isVisible(), true);
  await companionPreview.locator("#edit-mode-button").click();
  for (const count of [2, 3]) {
    const requested = new Promise((done, fail) => {
      const timeout = setTimeout(() => fail(new Error("Order preview request was not sent")), 10_000);
      onPreview = () => { clearTimeout(timeout); done(); };
    });
    await companionPreview.locator("#participants").fill(String(count));
    await requested;
  }
  assert.equal(pendingPreviews.length, 2);
  const responseFor = route => {
    const payload = route.request().postDataJSON();
    return { ...previewFixture, design: payload.design,
      run_sequence_setup: { ...previewFixture.run_sequence_setup, participant_count: payload.design.protocol.participants } };
  };
  await writeFile(resolve(output, "order-preview-payload.json"), JSON.stringify(pendingPreviews[1].request().postDataJSON(), null, 2));
  await pendingPreviews[1].fulfill({ json: responseFor(pendingPreviews[1]) });
  await companionPreview.waitForFunction(() => window.PPSDesignerApp.getState().design.protocol.participants === 3);
  const oldResponse = companionPreview.waitForResponse(response => response.url().endsWith("/api/run-sequence/preview"));
  await pendingPreviews[0].fulfill({ json: responseFor(pendingPreviews[0]) });
  await oldResponse;
  await companionPreview.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
  assert.equal(await companionPreview.evaluate(() => window.PPSDesignerApp.getState().design.protocol.participants), 3);
  assert.equal(await companionPreview.locator("#participants").inputValue(), "3");
  assert.deepEqual(errors, []);
  report.checks.push("Explicit V1 companion route with mocked reversed HTTP preview responses preserves the latest form and state");
  const mapper = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  mapper.on("pageerror", error => errors.push(error.message));
  let failReview = true;
  await mapper.route("**/publication_study_reviews.v1-*.json", async route => {
    if (failReview) { failReview = false; await route.fulfill({ status: 503 }); }
    else await route.continue();
  });
  await mapper.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&page=documentation#docs-publication-network`);
  const network = mapper.locator("[data-publication-network-root]");
  await network.scrollIntoViewIfNeeded();
  await mapper.locator("#publication-network-retry").waitFor({ state: "visible" });
  assert.equal(await network.getAttribute("data-publication-network-state"), "error");
  await mapper.locator("#publication-network-retry").click();
  await mapper.waitForFunction(() => document.querySelector("[data-publication-network-root]").dataset.publicationNetworkState === "ready");
  const reviewData = JSON.parse(await readFile(resolve(root, "apps/designer/frontend/publication_study_reviews.v1.json"), "utf8"));
  report.catalogueCounts = reviewData.counts;
  assert.equal(await network.getAttribute("data-publication-network-nodes"), String(reviewData.counts.publications));
  assert.equal(await network.getAttribute("data-publication-network-studies"), String(reviewData.counts.studies));
  assert.equal(await mapper.locator("#publication-network-results li").count(), 40);
  const search = mapper.locator("#publication-network-search");
  await search.fill("https://doi.org/10.1007/s00221-013-3532-2");
  assert.equal(await mapper.locator("#publication-network-results li").count(), 1);
  const result = mapper.locator(".publication-network-result-button");
  await result.focus();
  await mapper.keyboard.press("Enter");
  const detail = mapper.locator("#publication-network-detail");
  await detail.waitFor({ state: "visible" });
  assert.equal(await detail.locator("[data-study-id]").count(), 2);
  assert.match(await detail.innerText(), /Publication evidence[\s\S]*Template availability[\s\S]*Native qualification[\s\S]*Not Assessed/i);
  assert.match(await detail.innerText(), /2 reported complete · 2 derived complete · 22 contracts/);
  assert.equal(await detail.locator("[data-open-designer-template]").count(), 0);
  const study = detail.locator("[data-study-id]").first();
  await study.locator(":scope > summary").click();
  await study.locator("[data-contract-key]").first().locator(":scope > summary").click();
  const studyId = await study.getAttribute("data-study-id");
  await mapper.waitForFunction(id => new URL(location.href).searchParams.get("study") === id, studyId);
  const deepLink = mapper.url();
  await detail.screenshot({ path: resolve(output, "mapper-study-review.png") });
  await mapper.keyboard.press("Escape");
  assert.equal(await result.evaluate(element => element === document.activeElement), true);
  await search.fill("NoSuchPublication xxxxxxxxx");
  assert.equal(await mapper.locator("#publication-network-results li").count(), 0);
  assert.ok((await mapper.locator("#publication-network-status").innerText()).startsWith(`0 of ${reviewData.counts.publications}`));
  await search.fill("");
  assert.equal(await mapper.locator("#publication-network-results li").count(), 40);
  await mapper.goto(deepLink);
  await network.scrollIntoViewIfNeeded();
  await mapper.waitForFunction(id => [...document.querySelectorAll("[data-study-id]")].some(element => element.dataset.studyId === id && element.open), studyId);
  for (const width of [320, 768, 1440, 1920]) {
    await mapper.setViewportSize({ width, height: 1000 });
    await network.scrollIntoViewIfNeeded();
    await mapper.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))));
    assert.equal(await mapper.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, `page overflow at ${width}`);
    assert.equal(await detail.evaluate(element => element.getBoundingClientRect().right <= element.parentElement.getBoundingClientRect().right + 1), true, `detail clipping at ${width}`);
    await network.screenshot({ path: resolve(output, `mapper-${width}.png`) });
  }
  await mapper.setViewportSize({ width: 768, height: 1000 });
  await mapper.evaluate(() => {
    const sizes = [...document.querySelectorAll("[data-publication-network-root] p, [data-publication-network-root] button, [data-publication-network-root] input, [data-publication-network-root] label, [data-publication-network-root] summary, [data-publication-network-root] h3, [data-publication-network-root] h4, [data-publication-network-root] dt, [data-publication-network-root] dd, [data-publication-network-root] small")].map(element => [element, parseFloat(getComputedStyle(element).fontSize)]);
    for (const [element, size] of sizes) element.style.fontSize = `${size * 2}px`;
  });
  await network.scrollIntoViewIfNeeded();
  await network.screenshot({ path: resolve(output, "mapper-text-200.png") });
  assert.equal(await mapper.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, "page overflow at enlarged text");
  assert.equal(await detail.evaluate(element => element.getBoundingClientRect().right <= element.parentElement.getBoundingClientRect().right + 1), true, "detail clipping at enlarged text");
  report.mapperText = await mapper.locator("#publication-network-search").evaluate(element => ({ width: element.clientWidth, scrollWidth: element.scrollWidth }));
  const linkedPublication = reviewData.publications.find(publication => publication.templateIds.length);
  const linkedStudy = reviewData.studies.find(study => study.networkNodeId === linkedPublication.networkNodeId && study.templateIds.length);
  await mapper.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&page=documentation&study=${encodeURIComponent(linkedStudy.studyRowId)}#docs-publication-network`);
  await network.scrollIntoViewIfNeeded();
  const templateLink = mapper.locator("[data-open-designer-template]").first();
  await templateLink.waitFor({ state: "visible" });
  const presetPagePromise = mapper.waitForEvent("popup");
  await templateLink.click();
  const presetPage = await presetPagePromise;
  await presetPage.waitForFunction(id => window.PPSDesignerApp?.getState()?.selected_template === id, linkedStudy.templateIds[0]);
  assert.equal(new URL(presetPage.url()).searchParams.get("template"), linkedStudy.templateIds[0]);
  const legacyStudyId = "doi:10.1371/journal.pone.0006582";
  const splitStudyIds = reviewData.studyRowAliases[legacyStudyId];
  await mapper.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&page=documentation&study=${encodeURIComponent(legacyStudyId)}#docs-publication-network`);
  await network.scrollIntoViewIfNeeded();
  await mapper.locator("[data-study-alias-notice]").waitFor();
  assert.equal(await detail.locator("[data-study-id]").count(), splitStudyIds.length);
  assert.match(await detail.innerText(), /Not Applicable/i);
  const rongaId = "doi:10.1073/pnas.2024548118";
  const rongaChildren = reviewData.studyRowAliases[rongaId];
  if (rongaChildren) {
    await mapper.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1&page=documentation&study=${encodeURIComponent(rongaId)}#docs-publication-network`);
    await network.scrollIntoViewIfNeeded();
    await mapper.locator("[data-study-alias-notice]").waitFor();
    assert.equal(await detail.locator("[data-study-id]").count(), rongaChildren.length);
    for (const id of rongaChildren) assert.equal(await detail.locator(`[data-study-id="${id}"]`).count(), 1);
    assert.match(await detail.innerText(), /newborn/i);
    assert.match(await detail.innerText(), /adult/i);
  }
  assert.deepEqual(errors, []);
  report.checks.push("Mapper retry, DOI search, keyboard detail, study deep link, evidence separation, responsive layout and preset navigation");
  const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: "reduce" });
  await phone.goto(`${base}/apps/designer/frontend/compiled/index.html?forceStaticPreview=1`);
  await phone.waitForFunction(() => window.PPSDesignerApp?.getState()?.design);
  assert.equal(await phone.locator("#edit-mode-button").isVisible(), true, "Phone authoring must expose the Edit switch");
  await phone.evaluate(() => { document.documentElement.dataset.theme = "dark"; });
  assert.equal(await phone.locator("#mobile-companion-toggle").evaluate(element => getComputedStyle(element).display), "none");
  const removalControls = phone.locator(".panel.profile-readonly [data-remove-noise], .panel.profile-readonly [data-remove-audio]");
  assert.ok(await removalControls.count() > 0);
  for (const control of await removalControls.all()) assert.equal(await control.evaluate(element => getComputedStyle(element).display), "none");
  assert.equal(await phone.locator(".segment-collapse-icon").first().evaluate(element => getComputedStyle(element).transitionDuration), "0s");
  assert.equal(await phone.locator(".arch-hw-label").first().evaluate(element => getComputedStyle(element).color), await phone.evaluate(() => {
    const probe = document.createElement("span"); probe.style.color = "var(--muted)"; document.body.append(probe);
    const color = getComputedStyle(probe).color; probe.remove(); return color;
  }));
  await phone.screenshot({ path: resolve(output, "designer-phone-dark-reduced-motion.png") });
  report.checks.push("Hosted desktop and phone expose Edit while hiding companion controls; phone preserves dark labels, readonly removal and reduced motion");
  await writeFile(resolve(output, "report.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
} catch (error) {
  for (const [index, page] of browser.contexts().flatMap(context => context.pages()).entries()) {
    await writeFile(resolve(output, `failure-${index}-storage.json`), JSON.stringify({ error: error.message,
      events: await page.evaluate(() => window.storageTestEvents || []).catch(() => []) }, null, 2));
    await page.screenshot({ path: resolve(output, `failure-${index}.png`), fullPage: true });
  }
  throw error;
} finally {
  await browser.close();
  await new Promise(done => server.close(done));
}
