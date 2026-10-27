import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";
import { webcrypto } from "node:crypto";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const chrome = await readFile(new URL("../designer_main.js", import.meta.url), "utf8");
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

// Exercise the existing non-exported browser handlers without initializing the whole page.
function handler(name, next) {
  return app.slice(app.indexOf(`async function ${name}(`), app.indexOf(`\n${next}`));
}

function previewHarness() {
  const requests = [];
  const initial = { design: { name: "Current project" } };
  const context = vm.createContext({
    state: initial, staticModeActive: false, editModeActive: true,
    workflowSaveInFlight: false, templateLoadInFlight: false,
    runSequencePreviewRequestId: 0, input: 1, renders: 0,
    ensureEditableProject: () => true,
    designerApi: { previewRunSequence(payload) {
      const request = { ...deferred(), payload };
      requests.push(request);
      return request.promise;
    } },
  });
  vm.runInContext(`function collectPayload() { return { participants: input }; }
    function renderAll() { renders++; }
    ${handler("previewRunSequence", "async function regenerateRunSequence")}`, context);
  return { context, requests, preview: () => vm.runInContext("previewRunSequence()", context), initial };
}

test("only the current preview may replace the current design snapshot", async () => {
  const { context, requests, preview } = previewHarness();
  const first = preview();
  context.input = 2;
  const second = preview();
  const latest = { design: { name: "Newest preview" } };
  requests[1].resolve(latest);
  await second;
  requests[0].resolve({ design: { name: "Obsolete preview" } });
  await first;
  assert.equal(context.state, latest);
  assert.equal(context.renders, 1);
});

test("a changed form or project rejects a pending preview, including stale failures", async () => {
  for (const change of ["input", "project", "edit mode"]) {
    const { context, requests, preview, initial } = previewHarness();
    const pending = preview();
    if (change === "input") context.input = 2;
    if (change === "project") context.state = { design: { name: "Other project" } };
    if (change === "edit mode") context.editModeActive = false;
    const current = context.state;
    requests[0].resolve({ design: { name: "Old response" } });
    await pending;
    assert.equal(context.state, current, change);
    assert.equal(context.renders, 0, change);
    assert.equal(initial.design.name, "Current project");
  }
  const { context, requests, preview } = previewHarness();
  const old = preview();
  context.input = 2;
  const current = preview();
  requests[0].reject(new Error("obsolete request failed"));
  await old;
  requests[1].reject(new Error("current request failed"));
  await assert.rejects(current, /current request failed/);
});

function finalizationHarness(save) {
  const context = vm.createContext({
    state: { design: { study_profile_reference_parameters: {} }, custom_workflow: { is_custom: true, is_finalized: false } },
    staticModeActive: true, editModeActive: true, workflowSaveInFlight: false,
    WORKFLOW_STEPS: ["study", "stimulus", "run"],
    normalizedDesignerProgress: () => ({ edit_step: "run", confirmed_steps: ["study", "stimulus"], needs_review_steps: [] }),
    getWorkflowStep: () => ({ complete: true }), refreshHostedWorkflowSteps() {},
    clone: structuredClone, window: { PPSDesigner: { drafts: { save } } },
    markDesignerSaved() {}, renderAll() {}, renderRun() {}, renderWorkflow() {}, showToast() {},
  });
  vm.runInContext(`function collectPayload() { return { design: structuredClone(state.design) }; }
    ${handler("savePreparedStudyProfile", "function openSaveProfileModal")}`, Object.assign(context, { structuredClone }));
  return { context, save: () => vm.runInContext("savePreparedStudyProfile()", context) };
}

test("storage failure leaves finalization editable and retryable", async () => {
  const storage = deferred();
  const { context, save } = finalizationHarness(() => storage.promise);
  const pending = save();
  assert.equal(context.state.custom_workflow.is_finalized, false, "not locked before persistence");
  assert.equal(context.editModeActive, true);
  storage.reject(new Error("Quota exceeded"));
  await assert.rejects(pending, /Quota exceeded/);
  assert.equal(context.state.custom_workflow.is_finalized, false);
  assert.equal(context.state.design.study_profile_reference_parameters.profile_status, undefined);
  assert.equal(context.editModeActive, true);
  assert.equal(context.workflowSaveInFlight, false);
  context.window.PPSDesigner.drafts.save = async snapshot => {
    assert.equal(snapshot.custom_workflow.is_finalized, true);
  };
  await save();
  assert.equal(context.state.custom_workflow.is_finalized, true);
  assert.equal(context.editModeActive, false);
});

function zipEntries(bytes) {
  const files = new Map();
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = 0;
  while (view.getUint32(offset, true) === 0x04034b50) {
    const size = view.getUint32(offset + 18, true);
    const nameSize = view.getUint16(offset + 26, true);
    const extraSize = view.getUint16(offset + 28, true);
    const start = offset + 30 + nameSize + extraSize;
    files.set(new TextDecoder().decode(bytes.subarray(offset + 30, offset + 30 + nameSize)), bytes.slice(start, start + size));
    offset = start + size;
  }
  return files;
}

test("portable bundle contains instruction audio once with verified inventory and stable references", async () => {
  const context = vm.createContext({ window: {}, Blob, TextEncoder, Uint8Array, structuredClone, crypto: webcrypto });
  vm.runInContext(chrome.replace(/initializeChrome\(\);\s*$/, ""), context);
  const audio = new Uint8Array([82, 73, 70, 70, 1, 2, 3, 4]);
  context.window.PPSDesigner.drafts.asset = async id => id === "instruction.wav"
    ? { bytes: audio, name: "Welcome.wav", type: "audio/wav" } : null;
  vm.runInContext("saveProfileDownload = async blob => { globalThis.download = blob; };", context);
  const snapshot = { design: { name: "Portable", custom_looming_files: [], prestimulus_files: [],
    study_profile_reference_parameters: { dashboard_run_setup: { instruction_profile: { slots: [
      { slot: "welcome", path: "browser-asset:instruction.wav", browser_asset_id: "instruction.wav" },
      { slot: "break", path: "browser-asset:instruction.wav" },
    ] } } } } };
  await context.window.PPSDesigner.exportBundle(snapshot);
  const files = zipEntries(new Uint8Array(await context.download.arrayBuffer()));
  assert.deepEqual([...files.keys()].sort(), ["assets/instruction.wav", "manifest.json", "profile.json"]);
  assert.deepEqual(files.get("assets/instruction.wav"), audio);
  const profile = JSON.parse(new TextDecoder().decode(files.get("profile.json")));
  assert.equal(profile.assets.length, 1);
  assert.equal(profile.assets[0].logical_id, "instruction.wav");
  assert.equal(profile.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots[1].path, "browser-asset:instruction.wav");
  const manifest = JSON.parse(new TextDecoder().decode(files.get("manifest.json")));
  for (const entry of manifest.files) {
    assert.equal(entry.bytes, files.get(entry.path).length);
    assert.equal(entry.sha256, Buffer.from(await webcrypto.subtle.digest("SHA-256", files.get(entry.path))).toString("hex"));
  }
  context.window.PPSDesigner.drafts.asset = async () => null;
  context.download = null;
  await assert.rejects(context.window.PPSDesigner.exportBundle(snapshot), /Local browser audio is missing/);
  assert.equal(context.download, null);
});
