import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";
import { webcrypto } from "node:crypto";
import { trialFamilyContract } from "../row_contract.js";

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
  const context = vm.createContext({ slugify: value => value, previewVariantKey: () => "variant", trialFamilyContract });
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
const instructionAdoption = app.slice(app.indexOf("function adoptInstructionAudio("), app.indexOf("async function importNativeAudio("));

test("startup draft restoration never replaces a new interaction or save, including during a pending read", async () => {
  for (const action of [null, "pointerdown", "keydown", "pps-designer-dirty", "pps-designer-saved"]) {
    for (const pendingRead of [false, true]) {
      const read = deferred(), startup = deferred(), started = deferred(), listeners = new Map();
      let loads = 0, restores = 0;
      const context = vm.createContext({
        document: { addEventListener: (type, fn) => listeners.set(type, fn), removeEventListener: type => listeners.delete(type) },
        window: { PPSDesignerApp: { ready: startup.promise, restoreHostedDraft: () => restores++ } },
        drafts: { load: async () => { loads++; started.resolve(); return read.promise; } },
      });
      vm.runInContext(chrome.slice(chrome.indexOf("function scheduleHostedDraftRestore("), chrome.indexOf("function initializeChrome(")), context);
      const done = context.scheduleHostedDraftRestore();
      assert.equal(loads, 0, "automatic restore waits for the initial template load to settle");
      if (action && !pendingRead) listeners.get(action)();
      startup.resolve();
      if (pendingRead) await started.promise;
      if (action && pendingRead) listeners.get(action)();
      read.resolve({ custom_workflow: { is_custom: true } });
      await done;
      assert.equal(loads, action && !pendingRead ? 0 : 1);
      assert.equal(restores, action ? 0 : 1);
      assert.equal(listeners.size, 0);
    }
  }
});

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

test("instruction rendering initializes defaults and replaces hidden metadata or lock state without leaving an old menu", () => {
  let html = "", renders = 0, closed = 0;
  const container = { children: [], dataset: {}, contains: () => true,
    get innerHTML() { return html; }, set innerHTML(value) { html = value; renders++; this.children = [{}]; } };
  const context = vm.createContext({ profile: {}, finalized: false, activeBoundedSelect: null,
    $: id => id === "run-instruction-slots" ? container : {},
    restoreFocusAfterRender: () => () => {}, isProfileFinalized: () => context.finalized,
    collectRunInstructionProfile: () => context.profile, upgradeBoundedSelects() {}, escapeHtml: value => String(value),
    closeBoundedSelect: () => { closed++; context.activeBoundedSelect = null; },
  });
  const constants = app.slice(app.indexOf("const RUN_INSTRUCTION_SLOTS ="), app.indexOf("const RUN_INSTRUCTION_CONTINUE_MODES ="));
  const modeStart = app.indexOf("const RUN_INSTRUCTION_CONTINUE_MODES =");
  vm.runInContext(constants + app.slice(modeStart, app.indexOf("\n];", modeStart) + 3)
    + app.slice(app.indexOf("function normalizedRunInstructionSlots("), app.indexOf("function collectRunInstructionProfile(")), context);
  context.renderRunInstructions({});
  assert.equal(renders, 1, "empty DOM renders even when defaults equal collected defaults");
  assert.equal((html.match(/<article /g) || []).length, context.normalizedRunInstructionSlots({}).length);
  context.activeBoundedSelect = {};
  context.renderRunInstructions({});
  assert.equal(renders, 1, "an identical profile preserves its active menu");
  assert.equal(closed, 0);
  context.profile = { slots: [{ slot: "before_experiment", path: "clip.wav", sha256: "old" }] };
  const changed = structuredClone(context.profile);
  changed.slots[0].sha256 = "new";
  context.renderRunInstructions(changed);
  assert.equal(renders, 2);
  assert.equal(closed, 1, "a changed hidden media identity closes the old menu");
  assert.match(html, /data-instruction-field="sha256"[^>]*value="new"/);
  context.profile = changed;
  context.finalized = true;
  context.renderRunInstructions(changed);
  assert.equal(renders, 3);
  assert.match(html, /data-instruction-field="label"[^>]*disabled/);
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
      pendingAudioImportMode: "instruction", pendingInstructionSlot: "welcome", pendingDisplayColorHex: "", showToast() {},
      audioImportRequestId: 0, audioImportHttpQueue: Promise.resolve(), URL: { revokeObjectURL() {} },
      $: () => ({ files: [{ name: "welcome.wav" }], value: "" }),
      window: { PPSDesigner: { drafts: { storeAudio: () => storage.promise } } },
    });
    vm.runInContext(instructionAdoption + handler("importAudioFromPicker", "function fileToBase64"), context);
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
    audioImportRequestId: 0, audioImportHttpQueue: Promise.resolve(), URL: { revokeObjectURL() {} },
    $: () => ({ files: [{ name: "New.wav" }], value: "" }),
    window: { PPSDesigner: { drafts: { storeAudio: async () => ({ id: "new.wav", url: "blob:new", sha256: "new-hash" }) } } },
    collectRunInstructionProfile: () => ({ slots: [structuredClone(old)] }),
    renderRunInstructions: profile => { rendered = profile; }, markDesignerDirty: () => dirty++,
    scheduleRunSequencePreview: () => previews++, showToast() {}, renderBakePanel() { throw new Error("Instruction import must not stage an ingredient"); },
  });
  vm.runInContext(instructionAdoption + handler("importAudioFromPicker", "function fileToBase64"), context);
  await vm.runInContext("importAudioFromPicker()", context);
  const profile = original.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile;
  assert.equal(profile, rendered);
  assert.equal(profile, original.run_sequence_setup.instruction_profile);
  assert.deepEqual(JSON.parse(JSON.stringify(profile.slots[0])), { ...old, label: "New", path: "browser-asset:new.wav",
    browser_asset_id: "new.wav", sha256: "new-hash", duration_s: 0, sample_rate: 0, channels: 0, source: "browser_upload" });
  assert.equal(dirty, 1);
  assert.equal(previews, 1);
});

function importHarness(hosted = true) {
  const pending = [], revoked = [], staged = [], calls = [];
  const state = { design: { study_profile_reference_parameters: { dashboard_run_setup: { instruction_profile: {
    slots: [{ slot: "before_experiment", path: "old.wav", enabled: true }, { slot: "after_experiment", path: "end.wav", enabled: true }],
  } } } }, preload_inventory: { assets: [] } };
  const context = vm.createContext({ state, staticModeActive: hosted, editModeActive: true, workflowSaveInFlight: false,
    audioImportRequestId: 0, audioImportHttpQueue: Promise.resolve(), pendingInstructionSlot: "before_experiment",
    pendingAudioImportMode: "instruction", pendingDisplayColorHex: "#123456", pendingBakeRecipe: null,
    file: { name: "First.wav" }, URL: { revokeObjectURL: url => revoked.push(url) },
    $: () => ({ files: [context.file], value: "" }), ensureEditableProject: () => true,
    window: { PPSDesigner: { drafts: { storeAudio: () => { const job = deferred(); pending.push(job); return job.promise; } } } },
    nativeDesigner: { pickAudio: () => { const job = deferred(); pending.push(job); return job.promise; } },
    designerApi: { importRunInstructions: args => { const job = deferred(); calls.push({ args, job }); return job.promise; },
      importAudio: args => { const job = deferred(); calls.push({ args, job }); return job.promise; } },
    fileToBase64: async file => file.name, collectRunInstructionProfile: () => structuredClone(context.state.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile),
    renderRunInstructions() {}, markDesignerDirty() {}, scheduleRunSequencePreview() {}, showToast() {},
    renderBakePanel() {}, markDesignerSaved() {}, renderAll() {}, stageImportedAudioForBake: (audio, mode) => staged.push({ audio, mode }),
  });
  vm.runInContext(instructionAdoption + handler("importNativeAudio", "async function importNativeProfile") + handler("importAudioFromPicker", "function fileToBase64"), context);
  return { context, pending, revoked, staged, calls, run: () => vm.runInContext("importAudioFromPicker()", context), native: () => vm.runInContext("importNativeAudio()", context) };
}

test("latest hosted selection wins reversed storage completion and unused URLs are revoked", async () => {
  const h = importHarness();
  const first = h.run();
  h.context.file = { name: "Second.wav" };
  const second = h.run();
  h.pending[1].resolve({ id: "second.wav", sha256: "second", url: "blob:second" });
  await second;
  h.pending[0].resolve({ id: "first.wav", sha256: "first", url: "blob:first" });
  await first;
  assert.equal(h.context.state.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots[0].path, "browser-asset:second.wav");
  assert.deepEqual(h.revoked, ["blob:second", "blob:first"]);
  const ingredient = importHarness();
  ingredient.context.pendingInstructionSlot = "";
  ingredient.context.pendingAudioImportMode = "preserve";
  const active = ingredient.run();
  ingredient.pending[0].resolve({ id: "live.wav", url: "blob:live" });
  await active;
  assert.deepEqual(ingredient.revoked, [], "live ingredient preview URL remains usable");
  assert.equal(ingredient.staged[0].audio.browser_preview_url, "blob:live");
  const changedRecipe = importHarness();
  changedRecipe.context.pendingInstructionSlot = "";
  changedRecipe.context.pendingAudioImportMode = "preserve";
  const obsolete = changedRecipe.run();
  changedRecipe.context.pendingBakeRecipe = { action: "create" };
  changedRecipe.pending[0].resolve({ id: "obsolete.wav", url: "blob:obsolete" });
  await obsolete;
  assert.equal(changedRecipe.staged.length, 0);
  assert.deepEqual(changedRecipe.revoked, ["blob:obsolete"]);
});

test("native picks capture their target and discard an older completion without publishing its asset", async () => {
  const h = importHarness();
  const first = h.native();
  h.context.pendingInstructionSlot = "";
  h.context.pendingAudioImportMode = "spatialize";
  const second = h.native();
  h.pending[1].resolve({ label: "Second", path: "native-assets/second.wav", duration_s: 1 });
  await second;
  h.pending[0].resolve({ label: "First", path: "native-assets/first.wav", duration_s: 1 });
  await first;
  assert.equal(h.staged.length, 1);
  assert.equal(h.staged[0].mode, "spatialize");
  assert.deepEqual(h.context.state.preload_inventory.assets.map(asset => asset.label), ["Second"]);
  const target = importHarness();
  const pick = target.native();
  target.context.pendingInstructionSlot = "after_experiment";
  target.pending[0].resolve({ label: "Selected", path: "native-assets/selected.wav", duration_s: 1 });
  await pick;
  const slots = target.context.state.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots;
  assert.equal(slots.find(slot => slot.slot === "before_experiment").path, "native-assets/selected.wav");
  assert.equal(slots.find(slot => slot.slot === "after_experiment").path, "end.wav");
  assert.equal(target.context.pendingInstructionSlot, "after_experiment", "an already opened different target is not cleared");
  for (const boundary of ["saving", "replaced", "locked"]) {
    const fenced = importHarness(), owner = fenced.context.state;
    const awaiting = fenced.native();
    if (boundary === "saving") fenced.context.workflowSaveInFlight = true;
    if (boundary === "replaced") fenced.context.state = { design: {} };
    if (boundary === "locked") fenced.context.editModeActive = false;
    fenced.pending[0].resolve({ label: "Late", path: "native-assets/late.wav", duration_s: 1 });
    await awaiting;
    assert.equal(owner.preload_inventory.assets.length, 0, boundary);
  }
});

test("native instruction replacement preserves continuation policy and publishes verified media to later run rendering", async () => {
  const h = importHarness();
  const old = h.context.state.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots[0];
  Object.assign(old, { label: "Old", path: "browser-asset:old.wav", browser_asset_id: "old.wav", sha256: "old-hash",
    duration_s: 85.7, sample_rate: 48000, channels: 2, source: "browser_upload", enabled: false,
    continue_mode: "click", delay_s: 0, button_label: "Continue" });
  h.context.state.run_sequence_setup = { message: "retained setup", instruction_profile: { slots: [structuredClone(old)] } };
  const formProfile = structuredClone(h.context.state.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile);
  Object.assign(formProfile.slots[0], { enabled: true, continue_mode: "button", delay_s: 2.5, button_label: "Begin" });
  h.context.collectRunInstructionProfile = () => structuredClone(formProfile);
  const older = h.native();
  const latest = h.native();
  const audio = { label: "Native clip", path: "native-assets/verified.wav", sha256: "a".repeat(64), duration_s: 0.1, sample_rate: 44100, channels: 1 };
  let dirty = 0, previews = 0, rendered;
  h.context.markDesignerDirty = () => dirty++;
  h.context.scheduleRunSequencePreview = () => previews++;
  h.context.renderRunInstructions = profile => { rendered = profile; };
  h.pending[1].resolve(structuredClone(audio));
  await latest;
  h.pending[0].resolve({ ...audio, label: "Obsolete", path: "native-assets/obsolete.wav" });
  await older;
  const profile = h.context.state.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile;
  assert.equal(profile, h.context.state.run_sequence_setup.instruction_profile);
  assert.equal(h.context.state.run_sequence_setup.message, "retained setup");
  assert.deepEqual(JSON.parse(JSON.stringify(profile.slots[0])), { ...formProfile.slots[0], ...audio, browser_asset_id: "", source: "native_import" });
  assert.equal(dirty, 1);
  assert.equal(previews, 1);
  assert.equal(h.context.state.preload_inventory.assets.length, 1);
  assert.equal(h.context.state.preload_inventory.assets[0].sha256, audio.sha256);
  Object.assign(h.context, { $: () => null, document: { querySelectorAll: () => [] }, getWorkflowStep: () => null,
    isProfileFinalized: () => false, renderProfileValidationChecklist() {}, renderRunSequenceTable() {}, renderProtocolSummary() {} });
  vm.runInContext(app.slice(app.indexOf("function renderRun()"), app.indexOf("function renderNativeExecution()")), h.context);
  rendered = null;
  h.context.renderRun();
  assert.equal(rendered, profile, "later run rendering sees the selected verified clip, never the old setup projection");
});

test("superseded storage errors stay obsolete while current failures remain retryable", async () => {
  const h = importHarness();
  const old = h.run(), latest = h.run();
  h.pending[1].resolve({ id: "latest.wav", url: "blob:latest" });
  await latest;
  h.pending[0].reject(new Error("Obsolete storage failure"));
  await old;
  h.context.pendingInstructionSlot = "before_experiment";
  const failed = h.run();
  h.pending[2].reject(new Error("Current quota failure"));
  await assert.rejects(failed, /Current quota failure/);
  const retry = h.run();
  h.pending[3].resolve({ id: "retry.wav", url: "blob:retry" });
  await retry;
  assert.equal(h.context.state.design.study_profile_reference_parameters.dashboard_run_setup.instruction_profile.slots[0].path, "browser-asset:retry.wav");
});

test("V1 import mutations serialize; stale replies and stale file reads never adopt or dispatch", async () => {
  const h = importHarness(false);
  const first = h.run();
  await new Promise(setImmediate);
  h.context.file = { name: "Second.wav" };
  const second = h.run();
  await new Promise(setImmediate);
  assert.equal(h.calls.length, 1, "the next server mutation waits for the prior import");
  h.calls[0].job.resolve({ marker: "old" });
  await first;
  await new Promise(setImmediate);
  assert.equal(h.context.state.marker, undefined);
  assert.equal(h.calls[1].args.filename, "Second.wav");
  h.calls[1].job.resolve({ marker: "latest" });
  await second;
  assert.equal(h.context.state.marker, "latest");
  const reads = importHarness(false), encodings = [];
  reads.context.fileToBase64 = () => { const job = deferred(); encodings.push(job); return job.promise; };
  const oldRead = reads.run();
  const latestRead = reads.run();
  encodings[1].resolve("new");
  await new Promise(setImmediate);
  encodings[0].resolve("old");
  await oldRead;
  assert.equal(reads.calls.length, 1);
  assert.equal(reads.calls[0].args.content_base64, "new");
  reads.calls[0].job.resolve({ marker: "new" });
  await latestRead;
});

test("browser audio checks the existing 64 MiB budget before reading and rejects changed byte lengths before hashing", async () => {
  let reads = 0, hashes = 0, writes = 0;
  const context = vm.createContext({ window: {}, Blob, TextEncoder, Uint8Array, structuredClone,
    crypto: { subtle: { digest: async () => { hashes++; return new ArrayBuffer(32); } } } });
  vm.runInContext(chrome.replace(/initializeChrome\(\);\s*$/, ""), context);
  context.write = () => writes++;
  vm.runInContext("put = async () => write();", context);
  await assert.rejects(context.window.PPSDesigner.drafts.storeAudio({ size: 64 * 1024 * 1024 + 1, arrayBuffer: async () => { reads++; } }), /64 MiB/);
  assert.deepEqual([reads, hashes, writes], [0, 0, 0]);
  await assert.rejects(context.window.PPSDesigner.drafts.storeAudio({ size: 1, arrayBuffer: async () => { reads++; return new ArrayBuffer(2); } }), /byte count/);
  assert.deepEqual([reads, hashes, writes], [1, 0, 0]);
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
