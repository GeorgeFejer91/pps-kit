import assert from "node:assert/strict";
import test from "node:test";

import {
  applyPhoneAction,
  createPhoneExperimentSnapshot,
  expirePhoneLease,
} from "../src/domain/phone-experiment-reducer.js";

let tick;
let clock;

function resetClock() {
  tick = 0;
  clock = () => ({ unixMs: 1_700_000_000_000 + tick, monotonicNs: 1_000_000 + tick++ });
}

test("phone target requires local arm before starting and advances one revision per mutation", () => {
  resetClock();
  let snapshot = createPhoneExperimentSnapshot({ targetId: "phone_target_test", epoch: 7, clock });
  assert.equal(snapshot.run.phase, "idle");
  assert(!snapshot.allowed_actions.includes("part.start"));

  let outcome = applyPhoneAction(snapshot, "package.prepare_demo", {}, { clock });
  assert.equal(outcome.status, "accepted");
  snapshot = outcome.snapshot;
  assert.equal(snapshot.revision, 1);

  outcome = applyPhoneAction(snapshot, "setup.submit", { participant_code: "P001" }, { clock });
  snapshot = outcome.snapshot;
  assert.equal(snapshot.run.phase, "prepared");
  assert(snapshot.allowed_actions.includes("target.arm"));
  assert(!snapshot.allowed_actions.includes("part.start"));

  outcome = applyPhoneAction(snapshot, "part.start", {}, { clock });
  assert.equal(outcome.status, "rejected");
  assert.equal(outcome.resultingRevision, snapshot.revision);

  outcome = applyPhoneAction(snapshot, "target.arm", { audio_enabled: true }, { clock });
  snapshot = outcome.snapshot;
  assert.equal(snapshot.run.phase, "ready");
  assert(snapshot.allowed_actions.includes("part.start"));

  outcome = applyPhoneAction(snapshot, "part.start", {}, { clock });
  snapshot = outcome.snapshot;
  assert.equal(snapshot.run.phase, "running");
  assert.deepEqual(outcome.effects, [{ type: "demo.start" }]);
  assert.equal(snapshot.revision, 4);
  assert(!snapshot.allowed_actions.includes("setup.submit"));
});

test("expected revision conflicts preserve authority state", () => {
  resetClock();
  const snapshot = createPhoneExperimentSnapshot({ targetId: "phone_target_test", epoch: 7, clock });
  const outcome = applyPhoneAction(snapshot, "setup.submit", { participant_code: "P001" }, {
    clock,
    expectedRevision: 99,
  });
  assert.equal(outcome.status, "rejected");
  assert.equal(outcome.reason, "revision_conflict");
  assert.equal(outcome.snapshot.revision, 0);
});

test("changing phone setup revokes local arm before any remote start", () => {
  resetClock();
  let snapshot = createPhoneExperimentSnapshot({ targetId: "phone_target_test", epoch: 19, clock });
  snapshot = applyPhoneAction(snapshot, "package.prepare_demo", {}, { clock }).snapshot;
  snapshot = applyPhoneAction(snapshot, "setup.submit", { participant_code: "P001" }, { clock }).snapshot;
  snapshot = applyPhoneAction(snapshot, "target.arm", { audio_enabled: true }, { clock }).snapshot;
  assert.equal(snapshot.safety.local_armed, true);
  assert.equal(snapshot.run.phase, "ready");

  const changed = applyPhoneAction(snapshot, "setup.submit", { participant_code: "P002" }, { clock });
  assert.equal(changed.status, "accepted");
  assert.equal(changed.snapshot.safety.local_armed, false);
  assert.equal(changed.snapshot.safety.audio_route_ready, false);
  assert.equal(changed.snapshot.run.phase, "prepared");
  assert(!changed.snapshot.allowed_actions.includes("part.start"));
  assert.deepEqual(changed.effects, [{ type: "outputs.stop" }]);
});

test("lease expiry pauses a running browser target locally", () => {
  resetClock();
  let snapshot = createPhoneExperimentSnapshot({ targetId: "phone_target_test", epoch: 7, clock });
  for (const [action, args] of [
    ["package.prepare_demo", {}],
    ["setup.submit", { participant_code: "P001" }],
    ["target.arm", { audio_enabled: true }],
    ["part.start", {}],
  ]) snapshot = applyPhoneAction(snapshot, action, args, { clock }).snapshot;
  const expired = expirePhoneLease(snapshot, { clock });
  assert.equal(expired.snapshot.run.phase, "paused");
  assert.equal(expired.effects[0].type, "demo.pause");
  assert.equal(expired.snapshot.revision, snapshot.revision + 1);
});

test("snapshot action refreshes clocks without changing semantic revision", () => {
  resetClock();
  const snapshot = createPhoneExperimentSnapshot({ targetId: "phone_target_test", epoch: 7, clock });
  const outcome = applyPhoneAction(snapshot, "system.snapshot", {}, { clock });
  assert.equal(outcome.status, "accepted");
  assert.equal(outcome.snapshot.revision, snapshot.revision);
  assert.notEqual(outcome.snapshot.server_monotonic_ns, snapshot.server_monotonic_ns);
});
