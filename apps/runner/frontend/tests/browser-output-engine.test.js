import assert from "node:assert/strict";
import test from "node:test";
import * as output from "../src/phone/browser-output-engine.js";

test("scheduled cues map to the audio output clock, with a fallback before rendering", () => {
  const context = {
    currentTime: 4,
    baseLatency: 0.01,
    outputLatency: 0.09,
    getOutputTimestamp: () => ({ contextTime: 3.9, performanceTime: 5100 }),
  };
  assert.equal(output.audioOutputTime(context, 4.1, 5120), 5300);
  context.getOutputTimestamp = () => ({ contextTime: 0, performanceTime: 0 });
  assert.equal(output.audioOutputTime(context, 4.1, 5120), 5320);
});

test("a refused vibration leaves the phone disarmed", async () => {
  const engine = new output.BrowserOutputEngine({ navigatorObject: { vibrate: () => false } });
  await assert.rejects(engine.arm({ audioEnabled: false, vibrationEnabled: true }), /refused a vibration/u);
  assert.equal(engine.armed, false);
});
