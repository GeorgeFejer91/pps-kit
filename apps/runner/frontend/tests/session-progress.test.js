import assert from "node:assert/strict";
import test from "node:test";
import { bindSessionProgress, validGroupStatus, validResultsAssessment } from "../src/ui/session-progress.js";

const snap = (revision, phase = "completed", session = "part1") => ({ revision, epoch: 1, run: { phase, complete: false }, identity: { session_id: session } });
const group = (revision, completedParts = 1) => ({ revision, partCount: 2, currentPart: 1, completedParts, experimentComplete: false });
const flush = () => new Promise(resolve => setImmediate(resolve));
function harness(api) {
  const elements = new Proxy({}, { get(target, id) { return target[id] ||= { handlers: {}, disabled: false,
    addEventListener(name, fn) { this.handlers[name] = fn; }, replaceChildren(...children) { this.children = children; } }; } });
  const errors = [], advances = [];
  const progress = bindSessionProgress({ elements, api: { kind: "tauri-native", ...api },
    onError: error => errors.push(error), onAdvance: value => advances.push(value) });
  return { progress, elements, errors, advances };
}

test("group advancement uses the current native revision and does not infer experiment completion from part completion", async () => {
  const calls = [];
  const h = harness({ nativeGroupStatus: async () => group(5), advancePreparedGroupPart: async args => { calls.push(args); return snap(6, "prepared", "part2"); } });
  h.progress.update(snap(5));
  await flush();
  assert.equal(h.elements["advance-session-part"].disabled, false);
  assert.match(h.elements["session-group-status"].textContent, /Part 1 of 2 · 1 complete/);
  assert.doesNotMatch(h.elements["session-group-status"].textContent, /Experiment complete/);
  await h.elements["advance-session-part"].handlers.click();
  assert.deepEqual(calls, [{ expectedRevision: 5 }]);
  assert.equal(h.advances[0].identity.session_id, "part2");
  h.progress.update(snap(7, "running", "part2"));
  assert.equal(h.elements["advance-session-part"].disabled, true);
});

test("late group status cannot enable advancement for a replacement session", async () => {
  let resolveFirst, reads = 0;
  const h = harness({ nativeGroupStatus: () => ++reads === 1 ? new Promise(resolve => { resolveFirst = resolve; })
    : Promise.resolve({ revision: 8, partCount: 0, currentPart: 0, completedParts: 0, experimentComplete: false }) });
  h.progress.update(snap(5));
  h.progress.update(snap(8, "prepared", "single"));
  resolveFirst(group(5));
  await flush();
  assert.equal(h.elements["advance-session-part"].disabled, true);
  assert.equal(h.elements["advance-session-part"].hidden, true);
  assert.match(h.elements["session-group-status"].textContent, /Single prepared session/);
});

test("result assessment is bounded, path-free, paginated, and cleared when the selected part changes", () => {
  const oldDocument = globalThis.document;
  globalThis.document = { createElement: () => ({}) };
  try {
    const h = harness({ kind: "browser-preview" });
    const assessment = { schema: "pps.native-result-assessment.v1", inspectionScope: "read-only-file-prefix", timingQualification: "unqualified",
      completeScan: false, reason: "resource_limit", attempts: Array.from({ length: 9 }, (_, n) => ({
        attemptId: String(n).padStart(32, "0"), status: "interrupted", reason: "readable_prefix", commonEventSequence: 2, commonEventRecords: 3, commonDatasetRows: 1 })) };
    h.progress.setAssessment(assessment);
    assert.equal(h.elements["native-results-list"].children.length, 8);
    assert.match(h.elements["native-results-summary"].textContent, /not resumed/);
    h.elements["native-results-next"].handlers.click();
    assert.equal(h.elements["native-results-list"].children.length, 1);
    assert.match(h.elements["native-results-page"].textContent, /Page 2 of 2/);
    assert.equal(validResultsAssessment({ ...assessment, attempts: [{ ...assessment.attempts[0], attemptId: "C:/private/file" }] }), false);
    assert.equal(validResultsAssessment({ ...assessment, attempts: Array(257).fill(assessment.attempts[0]) }), false);
    h.progress.update(snap(9, "prepared", "part2"));
    assert.equal(h.elements["native-results-assessment"].hidden, true);
    assert.equal(validGroupStatus({ ...group(5), experimentComplete: true }), false);
    assert.equal(validGroupStatus({ ...group(5, 2), currentPart: 2, experimentComplete: false }), true,
      "all part receipts do not imply a durable group completion receipt");
  } finally { globalThis.document = oldDocument; }
});
