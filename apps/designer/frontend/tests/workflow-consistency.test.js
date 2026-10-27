import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";
import { webcrypto } from "node:crypto";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const chrome = (await readFile(new URL("../designer_main.js", import.meta.url), "utf8"))
  .replace('import { nativeDesigner } from "./native_designer.js";', 'const nativeDesigner = { enabled: false };');
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

test("instruction preview debounce preserves form values while native review invalidates immediately", async () => {
  let timer, invalidated = 0, previewed = 0;
  const context = vm.createContext({ state: { native_execution_review: { accepted: true } }, editModeActive: true,
    nativePreparedResult: { path: "prior-output" }, nativeExecutionMessage: "", designerDirty: true,
    runSequencePreviewRequestId: 0, runSequencePreviewTimer: null,
    nativeDesigner: { enabled: true, invalidate: () => invalidated++ },
    window: { clearTimeout() {}, setTimeout(callback) { timer = callback; return 1; } },
    stopActiveSourcePreview() {}, renderNativeExecution() {}, renderRun() { throw new Error("would discard current form"); },
    isCustomMode: () => true, isProfileReadonlyMode: () => false, reportError: error => { throw error; },
    previewRunSequence: async () => { assert.equal(context.state.native_execution_review, null); previewed++; },
  });
  vm.runInContext(app.slice(app.indexOf("function invalidateNativeAuthoring("), app.indexOf("function markDesignerSaved(")), context);
  vm.runInContext(app.slice(app.indexOf("function scheduleRunSequencePreview("), app.indexOf("async function previewRunSequence(")), context);
  // Input reaches its local preview listener, then the document dirty listener.
  context.scheduleRunSequencePreview();
  context.markDesignerDirty();
  assert.equal(invalidated, 1);
  assert.equal(context.state.native_execution_review, null);
  assert.equal(context.nativePreparedResult, null);
  assert.equal(previewed, 0);
  timer();
  assert.equal(previewed, 1);
});

test("only the explicit V1 loopback dashboard enables companion controls", () => {
  const nodes = [{ hidden: false }, { hidden: false }];
  const context = vm.createContext({
    window: { location: { hostname: "example.org", pathname: "/dashboard/" } },
    nativeDesigner: { enabled: false }, forced: false,
    forceStaticPreviewEnabled: () => context.forced,
    document: { querySelectorAll: () => nodes },
  });
  vm.runInContext(app.slice(app.indexOf("function isLocalDashboardOrigin("), app.indexOf("function loadApiBase(")), context);
  const cases = [
    ["example.org", "/dashboard/", false, false, false],
    ["127.0.0.1", "/apps/designer/frontend/compiled/index.html", false, false, false],
    ["127.0.0.1", "/dashboard/", false, false, true],
    ["127.0.0.1", "/dashboard/", true, false, false],
    ["127.0.0.1", "/dashboard/", false, true, false],
  ];
  for (const [hostname, pathname, native, forced, expected] of cases) {
    Object.assign(context.window.location, { hostname, pathname });
    context.nativeDesigner.enabled = native;
    context.forced = forced;
    assert.equal(context.companionModeEnabled(), expected);
    context.renderAdapterChrome();
    assert.ok(nodes.every(node => node.hidden === !expected));
  }
});

test("hosted startup never probes HTTP and a native failure never falls back", async () => {
  const calls = [];
  const context = vm.createContext({
    state: null, staticModeActive: false, staticModeReason: "", DEFAULT_STUDY_TEMPLATE_ID: "default",
    nativeDesigner: { enabled: false, load: async () => { calls.push("native"); throw new Error("native unavailable"); } },
    companionModeEnabled: () => false, forceStaticPreviewEnabled: () => false,
    designerApi: { state: async () => { calls.push("http"); return { templates: [] }; } },
    loadStaticState: async () => calls.push("hosted"), resetEditMode() {},
    pendingInitialTemplateRequest: () => ({}), applyStaticProfileInspectionPreview: async () => {},
    renderAll() {}, updateViewer() {},
  });
  vm.runInContext(handler("loadState", "function renderAll"), context);
  await context.loadState();
  assert.deepEqual(calls, ["hosted"]);
  calls.length = 0;
  context.nativeDesigner.enabled = true;
  await assert.rejects(context.loadState(), /native unavailable/);
  assert.deepEqual(calls, ["native"]);
  calls.length = 0;
  context.nativeDesigner.enabled = false;
  context.companionModeEnabled = () => true;
  await context.loadState();
  assert.deepEqual(calls, ["http"]);
});

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

test("hosted instruction selection replaces old media in both design and form without dropping continuation settings", async () => {
  const old = { slot: "before_experiment", label: "Old", path: "old.wav", enabled: true,
    continue_mode: "button", delay_s: 2.5, button_label: "Begin", duration_s: 85.7, sample_rate: 44100, channels: 2, sha256: "old-hash" };
  const original = { design: { study_profile_reference_parameters: {} }, run_sequence_setup: { instruction_profile: { slots: [old] } } };
  let rendered, dirty = 0, previews = 0;
  const context = vm.createContext({
    state: original, staticModeActive: true, editModeActive: true, workflowSaveInFlight: false,
    pendingAudioImportMode: "instruction", pendingInstructionSlot: "before_experiment", pendingDisplayColorHex: "#112233",
    $: () => ({ files: [{ name: "New.wav" }], value: "" }),
    window: { PPSDesigner: { drafts: { storeAudio: async () => ({ id: "new.wav", url: "blob:new", sha256: "new-hash" }) } } },
    collectRunInstructionProfile: () => ({ slots: [structuredClone(old)] }),
    renderRunInstructions: profile => { rendered = profile; }, markDesignerDirty: () => dirty++,
    scheduleRunSequencePreview: () => previews++, showToast() {}, renderBakePanel() { throw new Error("Instruction import must not stage an ingredient"); },
  });
  vm.runInContext(handler("importAudioFromPicker", "function fileToBase64"), context);
  await vm.runInContext("importAudioFromPicker()", context);
  const profile = original.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile;
  assert.equal(profile, rendered);
  assert.equal(profile, original.run_sequence_setup.instruction_profile);
  assert.deepEqual(JSON.parse(JSON.stringify(profile.slots[0])), { ...old, label: "New", path: "browser-asset:new.wav",
    browser_asset_id: "new.wav", sha256: "new-hash", duration_s: 0, sample_rate: 0, channels: 0, source: "browser_upload" });
  assert.equal(dirty, 1);
  assert.equal(previews, 1);
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

test("portable stationary controls retain distinct bytes and never replace the moving source identity", async () => {
  const moving = new Uint8Array([82,73,70,70,1,2,3]);
  const control = new Uint8Array([82,73,70,70,8,9,10]);
  const hash = bytes => webcrypto.subtle.digest("SHA-256", bytes).then(value => Buffer.from(value).toString("hex"));
  const controlHash = await hash(control);
  const context = vm.createContext({window:{}, Blob, TextEncoder, Uint8Array, structuredClone, crypto:webcrypto});
  vm.runInContext(chrome.replace(/initializeChrome\(\);\s*$/, ""), context);
  vm.runInContext("saveProfileDownload = async blob => { globalThis.download = blob; };", context);
  context.window.PPSDesigner.drafts.asset = async id => ({bytes:id === "moving.wav" ? moving : control, type:"audio/wav", name:id});
  const snapshot = {design:{name:"Distinct controls",noises:[{label:"Moving",prebaked_path:"browser-asset:moving.wav",browser_asset_id:"moving.wav",native_stationary_baseline_asset:"browser-asset:control.wav",native_stationary_baseline_sha256:controlHash,native_stationary_baseline_provenance:{qualification:"unqualified"}}]}};
  await context.window.PPSDesigner.exportBundle(snapshot);
  const files = zipEntries(new Uint8Array(await context.download.arrayBuffer()));
  const source = JSON.parse(new TextDecoder().decode(files.get("profile.json"))).design.noises[0];
  assert.equal(source.browser_asset_id,"moving.wav");
  assert.equal(source.prebaked_path,"browser-asset:moving.wav");
  assert.equal(source.native_stationary_baseline_asset,"browser-asset:control.wav");
  assert.equal(source.native_stationary_baseline_sha256,controlHash);
  assert.deepEqual(files.get("assets/moving.wav"),moving);
  assert.deepEqual(files.get("assets/control.wav"),control);
  context.window.PPSDesigner.drafts.asset = async id => id === "moving.wav" ? {bytes:moving,type:"audio/wav",name:id} : null;
  context.download = null;
  await assert.rejects(context.window.PPSDesigner.exportBundle(snapshot),/audio is missing: control.wav/);
  assert.equal(context.download,null);
});

test("collecting rendered sources retains native comparator, hash and loudness receipts", () => {
  const original={label:"Pink",noise_type:"pink",gain:1,prebaked_path:"native-assets/moving.wav",native_stationary_baseline_asset:"native-assets/control.wav",native_stationary_baseline_sha256:"c".repeat(64),loudness_policy:{kind:"linear_db_ramp"},native_stationary_baseline_provenance:{qualification:"unqualified"}};
  const fields={label:"Pink",noise_type:"pink",gain:"1",prebaked_path:original.prebaked_path};
  const card={dataset:{selectIngredient:"Pink"},querySelector(selector){const name=selector.match(/data-field="([^"]+)"/)[1];return {value:fields[name] || ""};}};
  const context=vm.createContext({state:{design:{noises:[original]}},clone:structuredClone,$:()=>({querySelectorAll:()=>[card]}),readJsonField:()=>null,GOLD_STANDARD_SOURCE_PROFILE:"gaussian"});
  const start=app.indexOf("function collectNoises(");
  vm.runInContext(app.slice(start,app.indexOf("\nfunction ",start+1)),context);
  const result=vm.runInContext("collectNoises()[0]",context);
  assert.equal(result.native_stationary_baseline_asset,original.native_stationary_baseline_asset);
  assert.equal(result.native_stationary_baseline_sha256,original.native_stationary_baseline_sha256);
  assert.equal(result.loudness_policy.kind,"linear_db_ramp");
  assert.notEqual(result.native_stationary_baseline_provenance,original.native_stationary_baseline_provenance);
});
