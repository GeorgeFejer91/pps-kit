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
