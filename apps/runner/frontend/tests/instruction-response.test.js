import assert from "node:assert/strict";
import test from "node:test";
import { bindParticipantResponse } from "../src/ui/participant-response.js";

test("click instruction gates accept semantic input without enabling trial capture or delay/button gates", async () => {
  const oldDocument = globalThis.document;
  globalThis.document = { visibilityState: "visible", addEventListener() {} };
  try {
    const handlers = {}, requests = [];
    const target = { addEventListener(name, handler) { handlers[name] = handler; },
      getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 100 }; } };
    const input = bindParticipantResponse({ target, api: { kind: "tauri-native", async recordResponse(request) { requests.push(request); } },
      liveState: () => true, onError: error => { throw error; } });
    const gate = next_action => ({ run: { phase: "instruction_gate", participant_capture_ready: false },
      instruction_gate: { waiting: next_action !== "continue-delay", next_action } });
    input.refresh(gate("continue-click"));
    assert.equal(target.disabled, false);
    assert.equal(target.textContent, "Continue instruction");
    handlers.click({ detail: 0 });
    assert.deepEqual(requests, [{ choice: "", x: 0.5, y: 0.5 }]);
    for (const action of ["continue-button", "continue-delay"]) {
      input.refresh(gate(action));
      assert.equal(target.disabled, true);
      handlers.click({ detail: 0 });
    }
    input.refresh({ run: { phase: "running", participant_capture_ready: false } });
    assert.equal(target.disabled, true);
    assert.equal(requests.length, 1);
    input.refresh({ run: { phase: "running", participant_capture_ready: true } });
    handlers.click({ detail: 0 });
    assert.deepEqual(requests[1], { choice: "", x: null, y: null });
    globalThis.document.visibilityState = "hidden";
    input.refresh(gate("continue-click"));
    assert.equal(target.disabled, true);
  } finally { globalThis.document = oldDocument; }
});

test("native left/right controls preserve distinct pointer and keyboard choices without exposing answer keys", () => {
  const oldDocument = globalThis.document;
  globalThis.document = { visibilityState: "visible", addEventListener() {} };
  try {
    const button = () => ({ handlers: {}, addEventListener(name, fn) { this.handlers[name] = fn; } });
    const target = button(), left = button(), right = button(), choices = {}, help = {}, requests = [];
    const input = bindParticipantResponse({ target, choiceControls: choices, choiceButtons: { left, right }, help,
      api: { kind: "tauri-native", async recordResponse(request) { requests.push(request); } }, liveState: () => true,
      onError: error => { throw error; } });
    const snapshot = phase => ({ identity: { session_id: "test" }, run: { phase, participant_capture_ready: phase === "running" } });
    input.refresh(snapshot("prepared"));
    input.setPreparedMedia({ responseMode: "left_right", responseChoices: ["left", "right"] });
    assert.equal(left.disabled, true);
    input.refresh(snapshot("running"));
    input.setPreparedMedia(null); // Native PCM plan is retired at playback; its response policy remains active.
    assert.equal(target.hidden, true);
    assert.equal(choices.hidden, false);
    assert.equal(left.disabled, false);
    left.handlers.pointerdown({ isPrimary: true, button: 0 });
    left.handlers.click({ detail: 1, pointerType: "mouse" });
    right.handlers.click({ detail: 0 });
    const key = (button, value, repeat = false) => button.handlers.keydown({ key: value, repeat, preventDefault() {} });
    key(left, "ArrowRight"); key(right, "ArrowLeft"); key(left, "ArrowRight", true);
    target.handlers.click({ detail: 0 });
    assert.deepEqual(requests, ["left", "right", "right", "left"].map(choice => ({ choice, x: null, y: null })));
    input.refresh(snapshot("paused"));
    right.handlers.click({ detail: 0 });
    assert.equal(requests.length, 4);
    input.refresh(snapshot("prepared"));
    assert.equal(target.hidden, false);
    assert.equal(choices.hidden, true);
    input.setPreparedMedia({ responseMode: "unsupported", responseChoices: [] });
    input.refresh(snapshot("running"));
    target.handlers.click({ detail: 0 });
    assert.equal(requests.length, 4);
    assert.match(help.textContent, /does not support/);
    input.refresh({ ...snapshot("prepared"), identity: { session_id: "replacement" } });
    input.setPreparedMedia({ responseMode: "go", responseChoices: [] });
    input.refresh({ ...snapshot("running"), identity: { session_id: "replacement" } });
    target.handlers.click({ detail: 0 });
    assert.deepEqual(requests.at(-1), { choice: "", x: null, y: null });
  } finally { globalThis.document = oldDocument; }
});
