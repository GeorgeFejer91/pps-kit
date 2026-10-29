// Real compiled DOM with a deterministic native boundary fixture. Native gate,
// durable-result and group execution are exercised by the Rust owner's tests.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { extname, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const { chromium } = createRequire(import.meta.url)(process.env.PPS_PLAYWRIGHT_MODULE || "playwright");
const root = fileURLToPath(new URL("../../../../", import.meta.url));
const output = resolve(root, "artifacts/ui-workflow-check");
await mkdir(output, { recursive: true });
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".woff2": "font/woff2" };
const server = createServer(async (request, response) => {
  const target = resolve(root, `.${new URL(request.url, "http://localhost").pathname}`);
  if (!target.startsWith(root.endsWith(sep) ? root : root + sep)) { response.writeHead(403).end(); return; }
  try { const bytes = await readFile(target); response.writeHead(200, { "Content-Type": types[extname(target)] || "application/octet-stream" }).end(bytes); }
  catch { response.writeHead(404).end(); }
});
await new Promise(done => server.listen(0, "127.0.0.1", done));
const browser = await chromium.launch({ headless: true, args: ["--mute-audio"] });
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(() => {
    let listener, callbackId = 0, stage = 0, part = 1, completed = 0, groupSelected = false, receipt = false, responseMode = null, publicationFailed = false;
    const callbacks = new Map();
    const native = { epoch: 900, revision: 1, run: { phase: "prepared", complete: false },
      active_block: { active: false, display_block_index: 0 }, identity: { session_id: "fixture-part-1" },
      part: { selected_part: 1, current_package_part: 1 }, safety: { local_armed: false }, allowed_actions: [], package_verified: true };
    const snapshot = () => structuredClone(native);
    function emit() { native.revision++; callbacks.get(listener)?.({ payload: snapshot() }); }
    window.sequenceCalls = [];
    window.sequenceFixture = {
      gate(mode) {
        native.run = { phase: "instruction_gate", complete: false, participant_capture_ready: false };
        native.instruction_gate = { waiting: mode !== "delay", gate_id: `gate-${mode}`, instruction_label: `${mode} instruction`,
          button_label: "Ready for the next instruction", next_action: `continue-${mode}` };
        native.allowed_actions = mode === "button" ? ["instruction.continue"] : [];
        emit();
      },
      finishWait() { stage++; native.run.phase = "prepared"; native.instruction_gate = null; emit(); },
      completePart() { completed = part; native.run = { phase: "completed", complete: false }; native.instruction_gate = null; emit(); },
      publishReceipt() { receipt = true; native.run.complete = true; emit(); },
      failReceipt() { publicationFailed = true; emit(); },
      choiceMode(mode) { responseMode = mode; native.run = { phase: "prepared", complete: false }; native.instruction_gate = null; emit(); },
      startResponses() { native.run = { phase: "running", participant_capture_ready: true, complete: false }; emit(); },
      retiredResponse() { callbacks.get(listener)?.({ payload: { ...snapshot(), epoch: 900, revision: 999, identity: { session_id: "fixture-part-1" } } }); },
    };
    window.__TAURI_INTERNALS__ = { transformCallback(callback) { const id = ++callbackId; callbacks.set(id, callback); return id; },
      async invoke(command, args) {
        window.sequenceCalls.push({ command, args });
        if (command === "plugin:event|listen") { listener = args.handler; return 1; }
        if (command === "runner_snapshot") return snapshot();
        if (command === "remote_status") return { enabled: false };
        if (command === "rotate_pairing") { native.epoch = 1; emit(); return { enabled: false }; }
        if (command === "native_output_status") return { schema: "pps-runner-native-output-preflight.v1", phase: "idle",
          policyGeneration: "1", serviceGeneration: "1", operationGeneration: "1", inventoryGeneration: null,
          reservationGeneration: null, inFlight: false, cleanupPending: false, silenceOnly: true, executable: false, armed: false, qualified: false };
        if (command === "native_group_status") return { revision: native.revision, partCount: groupSelected ? 2 : 0,
          currentPart: groupSelected ? part : 0, completedParts: groupSelected ? completed : 0, experimentComplete: groupSelected && receipt,
          publicationStatus: receipt ? "complete" : publicationFailed ? "failed" : completed === 2 ? "publishing" : "not_started" };
        if (command === "select_prepared_group") {
          groupSelected = true; emit();
          const assessment = { schema: "pps.native-result-assessment.v1", inspectionScope: "read-only-file-prefix", timingQualification: "unqualified",
              completeScan: true, reason: "assessed", attempts: [{ attemptId: "a".repeat(32), status: "interrupted", reason: "readable_prefix",
                commonEventSequence: 3, commonEventRecords: 4, commonDatasetRows: 1 }] };
          return { snapshot: snapshot(), summary: { sessionId: native.identity.session_id, blocks: [{ index: 1, label: "Part one source" }] },
            resultsAssessment: assessment, groupResultsAssessment: { schema: "pps.native-group-result-assessment.v1", timingQualification: "unqualified",
              completeScan: false, reason: "group_scan_limit", parts: [{ partNumber: 1, assessment }, { partNumber: 2, assessment: { ...assessment, attempts: [] } }],
              groups: [{ groupAttemptId: "prior-group", status: "not_assessed", reason: "group_scan_limit", partCount: null, scoredTrialCount: null, datasetRowCount: null }] } };
        }
        if (command === "inspect_prepared_execution") return { eventCount: 10, trialRowCount: 2, blockCount: 1, encodedBytes: 500,
          blocks: [{}], inspectionScope: "schedule-only", timingQualification: "unqualified", executable: false };
        if (command === "prepare_first_audio_block") return { schema: "pps-runner-prepared-audio-summary.v1", preparationScope: responseMode ? "pcm-and-output-plan-cache" : "instruction-pcm-and-output-plan-cache",
          mediaKind: responseMode ? "block" : "instruction", responseMode: responseMode || "go", responseChoices: responseMode === "left_right" ? ["left", "right"] : [], stageOrdinal: stage, blockOrdinal: 0, instructionLabel: "Opening instruction", instructionContinueMode: "click", instructionNeedsContinue: true,
          outputQualification: "unqualified", executable: false, outputPlanPrepared: true, sampleRateHz: 44100, sourceChannels: 3,
          sourceChannelLayout: "binaural-left-right-tactile", outputRoute: "canonical-three", scheduledEventCount: 2,
          frames: 44100, decodedBytes: 529200, cacheCapacityBlocks: 1, cacheByteBudget: 1280 * 1024 * 1024 };
        if (command === "runner_record_response") {
          if (responseMode && native.run.phase === "running") return snapshot();
          if (native.instruction_gate?.next_action !== "continue-click") throw Error("Unexpected trial response");
          window.sequenceFixture.finishWait(); return snapshot();
        }
        if (command === "runner_dispatch") {
          if (args.action !== "instruction.continue" || args.args.gate_id !== "gate-button") throw Error("Wrong gate identity");
          window.sequenceFixture.finishWait(); return { snapshot: snapshot(), status: "accepted" };
        }
        if (command === "advance_prepared_group_part") {
          if (args.expectedRevision !== native.revision || completed !== 1) throw Error("Stale group advance");
          part = 2; native.epoch = 2; native.identity.session_id = "fixture-part-2"; native.part = { selected_part: 2, current_package_part: 2 };
          native.run = { phase: "prepared", complete: false }; emit(); return snapshot();
        }
        throw Error(`Unexpected fixture command: ${command}`);
      } };
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/apps/runner/compiled/index.html`);
  await page.locator('[data-workspace-open="output"]').click();
  await page.locator("#lsl-ready").filter({ hasText: "Not supported in this preview" }).waitFor();
  await page.getByRole("button", { name: "Data Logging", exact: true }).click();
  assert.match(await page.locator('[data-panel="logging"]').innerText(), /Durable event log and result receipts\s+Supported in the native Runner/);
  assert.equal(await page.locator("#native-recording-status").innerText(), "Trial-response recording not started.");
  await page.locator('[data-panel="logging"]').screenshot({ path: resolve(output, "runner-recording-capabilities.png") });
  await page.getByRole("button", { name: "Experiment Control", exact: true }).click();
  await page.locator('[data-workspace-open="package"]').click();
  await page.locator("#select-session-group").click();
  await page.locator('[data-workspace-open="inspection"]').click();
  await page.locator("#native-results-summary").filter({ hasText: "not resumed" }).waitFor();
  assert.match(await page.locator("#native-results-list").innerText(), /interrupted/);
  assert.match(await page.locator("#native-group-results-list").innerText(), /not assessed/);
  assert.doesNotMatch(await page.locator("#session-group-status").innerText(), /Experiment complete/);
  await page.locator("#native-results-part").selectOption("2");
  assert.equal(await page.locator("#native-results-list li").count(), 0);
  await page.locator("#native-results-part").selectOption("1");
  assert.equal(await page.locator("#native-results-list li").count(), 1);
  await page.locator("#native-group-results").screenshot({ path: resolve(output, "runner-group-recovery.png") });
  assert.equal(await page.locator("#advance-session-part").isDisabled(), true);
  await page.locator('[data-workspace-open="package"]').click();
  await page.locator("#inspect-prepared-execution").click();
  await page.locator("#prepare-first-audio-block").click();
  await page.locator('[data-workspace-open="overview"]').click();
  await page.locator("#prepared-audio-status").filter({ hasText: "Instruction: Opening instruction" }).waitFor();
  await page.locator('[data-workspace-open="run"]').click();
  await page.evaluate(() => window.sequenceFixture.gate("click"));
  await page.locator("#participant-response").filter({ hasText: "Continue instruction" }).waitFor();
  assert.equal(await page.locator('[data-action="instruction.continue"]').isVisible(), false);
  assert.equal(await page.locator("#prepared-audio-status").innerText(), "Not prepared");
  await page.locator("#participant-response").focus();
  await page.keyboard.press("Enter");
  await page.locator("#state-chip").filter({ hasText: "Prepared" }).waitFor();
  assert.deepEqual(await page.evaluate(() => window.sequenceCalls.find(call => call.command === "runner_record_response").args),
    { request: { choice: "", x: 0.5, y: 0.5 } });
  await page.evaluate(() => window.sequenceFixture.gate("button"));
  assert.equal(await page.locator("#participant-response").isDisabled(), true);
  await page.getByRole("button", { name: "Ready for the next instruction", exact: true }).click();
  await page.evaluate(() => window.sequenceFixture.gate("delay"));
  assert.equal(await page.locator('[data-action="instruction.continue"]').isVisible(), false);
  assert.equal(await page.locator("#participant-response").isDisabled(), true);
  await page.locator("#run-progress").filter({ hasText: "native instruction timer" }).waitFor();
  await page.screenshot({ path: resolve(output, "runner-instruction-wait.png") });
  await page.evaluate(() => window.sequenceFixture.completePart());
  await page.locator('[data-workspace-open="package"]').click();
  await page.locator("#session-group-status").filter({ hasText: "Part 1 of 2 · 1 complete" }).waitFor();
  await page.getByRole("button", { name: "Load part 2", exact: true }).click();
  await page.locator('[data-workspace-open="overview"]').click();
  await page.locator("#session-id").filter({ hasText: "fixture-part-2" }).waitFor();
  await page.evaluate(() => window.sequenceFixture.retiredResponse());
  assert.equal(await page.locator("#session-id").innerText(), "fixture-part-2");
  assert.equal(await page.locator("#package-block-list li").count(), 0, "part one detail retired");
  assert.equal(await page.locator("#native-results-assessment").evaluate(node => node.hidden), true);
  assert.equal(await page.locator("#inspect-prepared-execution").isEnabled(), true);
  assert.equal(await page.locator("#prepare-first-audio-block").isDisabled(), true, "part two requires a fresh inspection");
  await page.locator('[data-workspace-open="package"]').click();
  await page.locator("#inspect-prepared-execution").click();
  await page.evaluate(() => window.sequenceFixture.completePart());
  await page.locator('[data-workspace-open="run"]').click();
  await page.locator("#session-group-status").filter({ hasText: "waiting for the native group completion receipt" }).waitFor();
  assert.equal(await page.locator("#advance-session-part").isDisabled(), true);
  await page.evaluate(() => window.sequenceFixture.failReceipt());
  await page.locator("#session-group-status").filter({ hasText: "whole-experiment completion is unconfirmed" }).waitFor();
  assert.equal(await page.locator("#workspace-run").isVisible(), true, "completion failures stay visible without leaving Run");
  await page.evaluate(() => window.sequenceFixture.publishReceipt());
  await page.locator("#session-group-status").filter({ hasText: "Experiment complete · 2 of 2 parts recorded" }).waitFor();
  assert.equal(await page.locator("#advance-session-part").isDisabled(), true);
  const beforeRotation = Number(await page.locator("#revision").innerText());
  await page.getByRole("button", { name: "Phone Remote", exact: true }).click();
  await page.locator("#rotate-pairing").click();
  await page.waitForFunction(revision => Number(document.getElementById("revision").textContent) > revision, beforeRotation);
  assert.equal(await page.locator("#session-id").innerText(), "fixture-part-2");
  await page.getByRole("button", { name: "Experiment Control", exact: true }).click();
  await page.getByRole("button", { name: "Package and parts", exact: true }).click();
  await page.locator("#session-group-status").scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(output, "runner-group-complete.png") });
  const geometry = await page.locator("#select-session-group, #advance-session-part, #prepare-first-audio-block, #session-group-status").evaluateAll(nodes => nodes.map(node => ({
    id: node.id, overflow: node.scrollWidth > node.clientWidth + 1, fontSize: getComputedStyle(node).fontSize,
    textLayout: node.dataset.pretextResult || null })));
  assert.ok(geometry.every(item => !item.overflow));
  assert.ok(geometry.every(item => ["fit", "reflow", "dom-fallback"].includes(item.textLayout)));
  await page.setViewportSize({ width: 760, height: 900 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.evaluate(() => window.sequenceFixture.choiceMode("left_right"));
  await page.locator('[data-workspace-open="package"]').click();
  await page.locator("#inspect-prepared-execution").click();
  await page.locator("#prepare-first-audio-block").click();
  await page.locator('[data-workspace-open="run"]').click();
  await page.evaluate(() => window.sequenceFixture.startResponses());
  await page.locator("#participant-response-left:enabled").waitFor();
  await page.locator("#participant-response-left").click();
  await page.locator("#participant-response-right").focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("ArrowLeft");
  assert.deepEqual(await page.evaluate(() => window.sequenceCalls.filter(call => call.command === "runner_record_response").slice(-3).map(call => call.args.request.choice)), ["left", "right", "left"]);
  for (const [width, zoom] of [[320, 1], [1280, 1], [1280, 2]]) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(value => document.documentElement.style.zoom = String(value), zoom);
    await page.waitForTimeout(180);
    const bounds = await page.locator("#participant-response-left, #participant-response-right").evaluateAll(nodes => nodes.map(node => {
      const box = node.getBoundingClientRect(); return { left: box.left, right: box.right, top: box.top, bottom: box.bottom, overflow: node.scrollWidth > node.clientWidth + 1 };
    }));
    assert.ok(bounds.every(box => !box.overflow && box.left >= 0 && box.right <= width));
    assert.ok(bounds[0].right <= bounds[1].left || bounds[0].bottom <= bounds[1].top);
    await page.screenshot({ path: resolve(output, `runner-choices-${width}-${zoom}.png`), fullPage: true });
  }
  await page.evaluate(() => document.documentElement.style.zoom = "");
  assert.deepEqual(errors, []);
  await writeFile(resolve(output, "runner-native-sequence-report.json"), JSON.stringify({ browser: browser.version(),
    scope: "compiled DOM, mocked native IPC; no hardware output", checks: ["instruction preload", "click and keyboard gate", "button gate identity", "native delay wait", "read-only result assessment", "revision-bound next part", "stale part detail retired", "whole experiment completion"], geometry }, null, 2));
  console.log("Runner compiled UI: instruction gates, result assessment and ordered two-part progression passed.");
} finally { await browser.close(); await new Promise(done => server.close(done)); }
