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

test("static trial timing includes instruction and jitter prefixes without inventing tactile catch events", () => {
  const functions = app.slice(app.indexOf("function staticVariantLoomingOnsetMs("), app.indexOf("function staticTrialFileBakePayload("));
  const context = vm.createContext({ slugify: value => value, previewVariantKey: () => "variant" });
  vm.runInContext(functions, context);
  const inventory = new Map([["Instruction", { kind: "prestimulus", duration_ms: 4000 }], ["Noise", { kind: "generated_noise", duration_ms: 4000 }]]);
  const variant = [{ kind: "audio", label: "Instruction" }, { kind: "jitter", value: 250 }, { kind: "audio", label: "Noise" }];
  assert.equal(context.staticVariantLoomingOnsetMs(variant, inventory), 4250);
  const base = { templateId: "test", rowIndex: 0, rowLabel: "Row", family: "audio_tactile", folderName: "target", variant, variantIndex: 1, durationMs: 8250, loomingOnsetMs: 4250, soaMs: 0 };
  assert.equal(context.staticTrialFileRow(base).tactile_onset_s, 4.25);
  assert.equal(context.staticTrialFileRow({ ...base, soaMs: 500 }).tactile_onset_s, 4.75);
  assert.equal(context.staticTrialFileRow({ ...base, family: "catch" }).tactile_onset_s, "");
  assert.equal(context.staticBaselineMode({ baseline_strategy: "stationary_burst", baseline_custom_trial_mode: "tactile_only" }), "stationary_burst");
  assert.equal(context.staticBaselineMode({ baseline_strategy: "min_max", baseline_custom_trial_mode: "tactile_only" }), "audio_tactile");
  assert.equal(context.staticBaselineMode({ baseline_strategy: "custom", baseline_custom_trial_mode: "tactile_only" }), "tactile_only");
});

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
  const shell = { inert: false };
  const context = vm.createContext({
    state: { design: { study_profile_reference_parameters: {} }, custom_workflow: { is_custom: true, is_finalized: false } },
    staticModeActive: true, editModeActive: true, workflowSaveInFlight: false, hostedFinalizationInFlight: false, templateLoadInFlight: false,
    runSequencePreviewRequestId: 0, runSequencePreviewTimer: null,
    WORKFLOW_STEPS: ["study", "stimulus", "run"],
    normalizedDesignerProgress: () => ({ edit_step: "run", confirmed_steps: ["study", "stimulus"], needs_review_steps: [] }),
    getWorkflowStep: () => ({ complete: true }), refreshHostedWorkflowSteps() {},
    clone: structuredClone, window: { clearTimeout() {}, PPSDesigner: { drafts: { save } } },
    document: { querySelector: () => shell }, $: () => ({ focus() {} }),
    markDesignerSaved() {}, renderAll() {}, renderRun() {}, renderWorkflow() {}, showToast() {},
  });
  vm.runInContext(`function collectPayload() { return { design: structuredClone(state.design) }; }
    ${handler("savePreparedStudyProfile", "function openSaveProfileModal")}`, Object.assign(context, { structuredClone }));
  return { context, shell, save: () => vm.runInContext("savePreparedStudyProfile()", context) };
}

test("audio imports already pending cannot mutate a finalizing or replaced hosted profile", async () => {
  for (const boundary of ["saving", "replaced", "locked"]) {
    const storage = deferred();
    const original = { design: { name: "original" } };
    const context = vm.createContext({
      state: original, staticModeActive: true, editModeActive: true, workflowSaveInFlight: false,
      pendingAudioImportMode: "instruction", pendingInstructionSlot: "welcome", showToast() {},
      $: () => ({ files: [{ name: "welcome.wav" }], value: "" }),
      window: { PPSDesigner: { drafts: { storeAudio: () => storage.promise } } },
    });
    vm.runInContext(handler("importAudioFromPicker", "function fileToBase64"), context);
    const pending = vm.runInContext("importAudioFromPicker()", context);
    if (boundary === "saving") context.workflowSaveInFlight = true;
    if (boundary === "replaced") context.state = { design: { name: "other" } };
    if (boundary === "locked") context.editModeActive = false;
    storage.resolve({ id: "clip", url: "blob:clip" });
    await pending;
    assert.deepEqual(original, { design: { name: "original" } });
  }
});

test("storage failure leaves finalization editable and retryable", async () => {
  const storage = deferred();
  const { context, shell, save } = finalizationHarness(() => storage.promise);
  const pending = save();
  assert.equal(context.state.custom_workflow.is_finalized, false, "not locked before persistence");
  assert.equal(context.editModeActive, true);
  assert.equal(shell.inert, true, "authoring controls cannot mutate a pending finalization");
  storage.reject(new Error("Quota exceeded"));
  await assert.rejects(pending, /Quota exceeded/);
  assert.equal(context.state.custom_workflow.is_finalized, false);
  assert.equal(context.state.design.study_profile_reference_parameters.profile_status, undefined);
  assert.equal(context.editModeActive, true);
  assert.equal(context.workflowSaveInFlight, false);
  assert.equal(shell.inert, false);
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

test("premade audio is fetched by inventory identity, verified and embedded for offline import", async () => {
  const audio = new Uint8Array([82, 73, 70, 70, 8, 7, 6, 5]);
  const digest = Buffer.from(await webcrypto.subtle.digest("SHA-256", audio)).toString("hex");
  const path = "assets/preloads/study/stimulus.wav";
  const calls = [];
  const context = vm.createContext({ window: { PPSDesignerApp: { preloadAssetUrl: value => `https://fixture.invalid/${value}` } },
    Blob, TextEncoder, Uint8Array, structuredClone, crypto: webcrypto,
    fetch: async url => { calls.push(url); return new Response(audio); } });
  vm.runInContext(chrome.replace(/initializeChrome\(\);\s*$/, ""), context);
  vm.runInContext("saveProfileDownload = async blob => { globalThis.download = blob; };", context);
  const snapshot = { preload_inventory: { assets: [{ path, sha256: digest }] }, design: { name: "Premade",
    noises: [{ label: "Noise", prebaked_path: path }], custom_looming_files: [{ label: "Reused", path }] } };
  await context.window.PPSDesigner.exportBundle(snapshot);
  assert.equal(calls.length, 1);
  const files = zipEntries(new Uint8Array(await context.download.arrayBuffer()));
  const profile = JSON.parse(new TextDecoder().decode(files.get("profile.json")));
  assert.deepEqual(files.get(`assets/${digest}.wav`), audio);
  assert.equal(profile.design.noises[0].prebaked_path, `browser-asset:${digest}.wav`);
  assert.equal(profile.design.custom_looming_files[0].path, `browser-asset:${digest}.wav`);
  assert.equal(snapshot.design.noises[0].prebaked_path, path, "export does not mutate the live profile");
  snapshot.preload_inventory.assets[0].sha256 = "0".repeat(64);
  context.download = null;
  await assert.rejects(context.window.PPSDesigner.exportBundle(snapshot), /checksum mismatch/);
  assert.equal(context.download, null);
  snapshot.preload_inventory.assets = [];
  await assert.rejects(context.window.PPSDesigner.exportBundle(snapshot), /not in the verified preload inventory/);
});

test("stopped source preview cannot start after its delayed audio decode finishes", async () => {
  const decode = deferred();
  let starts = 0;
  const context = vm.createContext({ sourcePreviewRequestId: 1, sourcePreviewAbort: null, activeSourcePreviewNode: null,
    AbortController, button: { isConnected: true }, armSourcePreviewCleanup() {},
    fetch: async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(4) }),
    audioContext: { decodeAudioData: () => decode.promise,
      createBufferSource: () => ({ connect() {}, addEventListener() {}, start() { starts++; } }) },
  });
  const end = app.indexOf("\nfunction ", app.indexOf("async function playSourcePreviewAudio("));
  vm.runInContext(app.slice(app.indexOf("async function playSourcePreviewAudio("), end), context);
  const pending = vm.runInContext('playSourcePreviewAudio("/audio.wav", button, audioContext, null, 4, 1)', context);
  context.sourcePreviewRequestId = 2;
  decode.resolve({});
  assert.equal(await pending, false);
  assert.equal(starts, 0);
});
