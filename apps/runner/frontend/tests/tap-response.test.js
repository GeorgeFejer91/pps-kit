import assert from "node:assert/strict";
import test from "node:test";
import { TapResponseWindow } from "../src/phone/tap-response.js";

const touch = (pointerId, timeStamp, clientX = 10, clientY = 10) =>
  ({ pointerId, timeStamp, clientX, clientY });

test("records only the first isolated tap in the local 100–2,000 ms window", () => {
  const capture = new TapResponseWindow();
  capture.open(1_000);
  capture.down(touch(1, 1_099));
  assert.equal(capture.up(touch(1, 1_110)), null);
  capture.down(touch(1, 1_750));
  capture.move(touch(1, 1_760, 55));
  assert.equal(capture.up(touch(1, 1_800)), null);
  capture.down(touch(1, 1_950));
  capture.down(touch(2, 1_960));
  assert.equal(capture.up(touch(1, 1_980)), null);
  assert.equal(capture.up(touch(2, 1_990)), null);
  capture.down(touch(1, 2_980));
  assert.deepEqual(capture.up(touch(1, 3_000)), { atMs: 2_980, reactionTimeMs: 1_980 });
  capture.down(touch(1, 2_995));
  assert.equal(capture.up(touch(1, 3_000)), null);
  capture.open(4_000);
  capture.down(touch(1, 6_001));
  assert.equal(capture.up(touch(1, 6_008)), null);
  capture.down(touch(1, 5_000));
  capture.close();
  assert.equal(capture.up(touch(1, 5_050)), null);
});

test("overlap uses the most recent eligible cue and discards repeated taps", () => {
  const capture = new TapResponseWindow();
  capture.open(1_000, 1);
  capture.open(1_500, 2);
  capture.down(touch(1, 1_550));
  assert.deepEqual(capture.up(touch(1, 1_580)), { atMs: 1_550, reactionTimeMs: 550, trialNumber: 1 });
  capture.open(1_700, 3);
  capture.down(touch(1, 1_900));
  assert.deepEqual(capture.up(touch(1, 1_930)), { atMs: 1_900, reactionTimeMs: 200, trialNumber: 3 });
  capture.down(touch(1, 1_940));
  assert.equal(capture.up(touch(1, 1_975)), null);
});

test("uses contact onset at the deadline and confirms the tap on release", () => {
  const capture = new TapResponseWindow();
  capture.open(1_000, 1);
  capture.down(touch(1, 3_000));
  assert.deepEqual(capture.up(touch(1, 3_140)), {
    atMs: 3_000, reactionTimeMs: 2_000, trialNumber: 1,
  });

  capture.open(4_000, 2);
  capture.down(touch(1, 5_950));
  assert.equal(capture.up(touch(1, 6_451)), null);
});
