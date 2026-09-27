import assert from "node:assert/strict";
import test from "node:test";
import { installBrowserLifecycle } from "../src/remote/browser-lifecycle.js";
import { publicRunnerSnapshot } from "../src/domain/runner-contract.js";
import { createPhoneExperimentSnapshot } from "../src/domain/phone-experiment-reducer.js";

test("screen lock, freeze, BFCache, and offline recovery each suspend once without replaying a command", () => {
  const windowObject = new EventTarget();
  const documentObject = new EventTarget();
  documentObject.visibilityState = "visible";
  const navigatorObject = { onLine: true };
  let suspended = 0;
  let resumed = 0;
  installBrowserLifecycle({ windowObject, documentObject, navigatorObject,
    suspend: () => { suspended += 1; }, resume: () => { resumed += 1; } });
  for (let cycle = 0; cycle < 3; cycle += 1) {
    documentObject.visibilityState = "hidden";
    documentObject.dispatchEvent(new Event("visibilitychange"));
    documentObject.dispatchEvent(new Event("freeze"));
    windowObject.dispatchEvent(new Event("pagehide"));
    windowObject.dispatchEvent(new Event("pageshow"));
    assert.equal(suspended, cycle + 1);
    assert.equal(resumed, cycle, "a still-hidden BFCache restore cannot recover controls");
    navigatorObject.onLine = false;
    documentObject.visibilityState = "visible";
    documentObject.dispatchEvent(new Event("resume"));
    assert.equal(resumed, cycle, "offline resumption cannot recover controls");
    navigatorObject.onLine = true;
    windowObject.dispatchEvent(new Event("online"));
    windowObject.dispatchEvent(new Event("pageshow"));
    assert.equal(resumed, cycle + 1, "overlapping resume events initiate one recovery");
  }
});

test("phone observers receive the same public shape without participant details, paths, or notes", () => {
  const local = createPhoneExperimentSnapshot({ targetId: "phone-alpha", epoch: 8,
    clock: () => ({ unixMs: 1700000000000, monotonicNs: 1 }) });
  local.setup.participant_code = "PRIVATE_CODE";
  local.setup.age = 54;
  local.setup.gender = "female";
  local.identity.participant_id = "PRIVATE_ID";
  local.last_note = "PRIVATE_NOTE";
  local.allowed_actions = ["setup.submit", "target.arm", "run.pause"];
  const remote = publicRunnerSnapshot(local);
  assert.deepEqual(remote.allowed_actions, ["run.pause"]);
  assert.deepEqual(Object.keys(remote.setup).sort(), ["ready", "required_missing", "submitted"]);
  assert.doesNotMatch(JSON.stringify(remote), /PRIVATE_|"participant_id":|"participant_code":|"gender":|"last_note":/u);
  remote.part.available_parts.push(77);
  assert(!local.part.available_parts.includes(77), "projection cannot mutate target-owned state");
});
