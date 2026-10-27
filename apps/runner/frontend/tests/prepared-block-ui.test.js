import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import test from "node:test";

const source = await readFile(new URL("../src/desktop-app.js", import.meta.url), "utf8");
const extract = (name, next) => source.slice(source.indexOf(`function ${name}(`), source.indexOf(`\nfunction ${next}(`));
const prepared = ordinal => ({ schema: "pps-runner-prepared-audio-summary.v1", preparationScope: "pcm-and-output-plan-cache",
  outputQualification: "unqualified", executable: false, outputPlanPrepared: true, blockOrdinal: ordinal,
  sampleRateHz: 48000, sourceChannels: 3, sourceChannelLayout: "binaural-left-right-tactile", outputRoute: "canonical-three",
  scheduledEventCount: 5, frames: 48000, decodedBytes: 576000, cacheCapacityBlocks: 1, cacheByteBudget: 1280 * 1024 * 1024 });
const snapshot = (phase, revision, block = 1) => ({ epoch: 1, revision, run: { phase, complete: phase === "completed" },
  active_block: { active: phase === "running", display_block_index: block, elapsed_s: 5, duration_s: 5 },
  package_verified: true, identity: { session_id: "session" }, allowed_actions: [] });

function harness() {
  const nodes = {};
  const elements = new Proxy(nodes, { get(target, id) {
    return target[id] ||= { style: {}, dataset: {}, replaceChildren() {}, disabled: false, textContent: "" };
  } });
  const context = vm.createContext({ elements, snapshot: snapshot("prepared", 1, 0), preparedAudio: null,
    preparedExecution: { blockCount: 2 }, preparedPlan: { sessionId: "session" },
    api: { kind: "tauri-native" }, participantResponse: { refresh() {} }, participantSetupDraft: { refresh() {} },
    nativeOutputSetup: { update() {} }, updateInboundPolicyUi() {}, inboundPrivateTarget: null,
    sessionProgress: { update() {}, isBusy: () => false }, packageSelectionInFlight: false,
    document: { querySelectorAll: () => [], createElement: () => ({}) },
  });
  vm.runInContext([extract("text", "titleCase"), extract("titleCase", "formatDuration"), extract("formatDuration", "showToast"),
    extract("planValue", "renderPreparedAudio"), extract("renderPreparedAudio", "renderPreparedExecution"), extract("renderSnapshot", "readRemoteUrl")].join("\n"), context);
  return { context, elements, render: (value, adoptContext = false) => { context.next = value; context.adoptContext = adoptContext; return vm.runInContext("renderSnapshot(next, {adoptContext})", context); },
    prepare: value => { context.audio = value; return vm.runInContext("renderPreparedAudio(audio)", context); } };
}

test("next-block preparation accepts a bounded native ordinal and displays it", () => {
  const { prepare, elements } = harness();
  assert.equal(prepare(prepared(1)), true);
  assert.match(elements["prepared-audio-status"].textContent, /Block 2 prepared/);
  for (const ordinal of [-1, 2, 0.5]) assert.equal(prepare(prepared(ordinal)), false);
});

test("only explicit native adoption accepts a new lower epoch; retired-session responses cannot overwrite it", () => {
  const { context, render } = harness();
  context.snapshot = { ...snapshot("completed", 9), epoch: 900, identity: { session_id: "part-one" } };
  context.preparedPlan = null;
  const partTwo = { ...snapshot("prepared", 1), epoch: 2, identity: { session_id: "part-two" } };
  assert.equal(render(partTwo), false, "an unacknowledged event cannot adopt a new authority");
  assert.equal(render(partTwo, true), true);
  assert.equal(context.snapshot.identity.session_id, "part-two");
  assert.equal(render({ ...snapshot("completed", 99), epoch: 900, identity: { session_id: "part-one" } }), false);
  assert.equal(context.snapshot.identity.session_id, "part-two");
  assert.equal(render({ ...partTwo, revision: 0 }), false);
  assert.equal(render({ ...partTwo, epoch: 1, revision: 2 }), true, "pairing rotation advances revision within the same session");
  assert.equal(render({ ...partTwo, epoch: 2, revision: 2 }), false, "a same-revision random epoch is not a newer authority");
  assert.equal(render(partTwo), false, "a delayed old-epoch snapshot cannot roll back rotation");
});

test("native block completion retires prior media, clears progress and unlocks next preparation", () => {
  const { context, elements, render, prepare } = harness();
  prepare(prepared(0));
  render(snapshot("running", 2));
  assert.equal(context.preparedAudio, null);
  // A stale in-flight preparation cannot survive the completion boundary.
  prepare(prepared(0));
  render(snapshot("prepared", 3));
  assert.equal(context.preparedAudio, null);
  assert.equal(elements["prepare-first-audio-block"].disabled, false);
  assert.equal(elements["prepare-first-audio-block"].textContent, "Prepare next audio occurrence");
  assert.equal(elements["block-progress"].style.width, "0%");
  prepare(prepared(1));
  render(snapshot("prepared", 3));
  assert.equal(context.preparedAudio.blockOrdinal, 1, "repeat snapshot keeps newly prepared media");
  assert.equal(elements["prepare-first-audio-block"].disabled, true);
  render(snapshot("completed", 4, 2));
  assert.equal(context.preparedAudio, null);
  assert.equal(elements["prepare-first-audio-block"].disabled, true);
});

test("native instruction summaries require their own scope and retire at the waiting gate", () => {
  const { context, elements, render, prepare } = harness();
  const instruction = { ...prepared(2), mediaKind: "instruction", stageOrdinal: 7,
    preparationScope: "instruction-pcm-and-output-plan-cache", instructionLabel: "Post-block rest",
    instructionContinueMode: "delay", instructionNeedsContinue: true };
  assert.equal(prepare(instruction), true, "trailing instruction is not a nonexistent block");
  assert.match(elements["prepared-audio-status"].textContent, /Instruction: Post-block rest/);
  assert.match(elements["prepared-audio-detail"].textContent, /native timed wait/);
  render({ ...snapshot("instruction_gate", 2), instruction_gate: { waiting: false, next_action: "continue-delay" } });
  assert.equal(context.preparedAudio, null);
  assert.equal(elements["prepare-first-audio-block"].disabled, true);
  assert.match(elements["run-progress"].textContent, /native instruction timer/);
  assert.equal(prepare({ ...instruction, preparationScope: "pcm-and-output-plan-cache" }), false);
  assert.equal(prepare({ ...instruction, mediaKind: "unrecognized" }), false);
  assert.equal(prepare({ ...instruction, instructionContinueMode: "automatic" }), false);
});

test("native capability labels separate durable recording support, active capture and absent LSL", () => {
  const { context, elements, render } = harness();
  render(snapshot("prepared", 1, 0));
  assert.equal(elements["lsl-ready"].textContent, "Not supported in this preview");
  assert.equal(elements["native-recording-status"].textContent, "Trial-response recording not started.");
  render({ ...snapshot("running", 2), run: { phase: "running", participant_capture_ready: true }, safety: { lsl_ready: true } });
  assert.equal(elements["lsl-ready"].textContent, "Ready");
  assert.equal(elements["native-recording-status"].textContent, "Trial-response recording active.");
  context.api.kind = "browser-preview";
  render(snapshot("running", 3));
  assert.match(elements["native-recording-status"].textContent, /native result recording is unavailable/);
});
