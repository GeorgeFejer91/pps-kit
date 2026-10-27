import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { audioBoxLabels, countStripVariants, iterateStripVariants, previewStripVariants, assertSequenceLimit, assertCountLimit } from "../sequence_variants.js";

const app = readFileSync(new URL("../app.js", import.meta.url), "utf8");
const functions = (start, end) => app.slice(app.indexOf(`function ${start}(`), app.indexOf(`function ${end}(`));

const jitter = values => ({ kind: "jitter", label: "Delay", jitter_values_ms: values });
const audio = labels => ({ kind: "looming_stimulus", source_labels: labels });
const legacy = strip => {
  const factors = (strip.elements || []).map(element => element.kind === "jitter"
    ? (element.jitter_values_ms || []).filter(value => Number.isFinite(Number(value)))
      .map(value => ({ kind: "jitter", label: `${element.label || "Jitter"} (${value} ms)`, value }))
    : audioBoxLabels(element).map(label => ({ kind: "audio", label })));
  return !factors.length || factors.some(factor => !factor.length) ? []
    : factors.reduce((rows, factor) => rows.flatMap(row => factor.map(choice => [...row, choice])), [[]]);
};
const key = variant => variant.map(choice => choice.kind === "jitter" ? `jitter_${choice.value}ms` : choice.label).join(" + ");

test("counts and ordered variants preserve legacy choices, duplicates, keys and empty factors", () => {
  const cases = [
    {}, { elements: [] }, { elements: [audio([])] },
    { elements: [jitter([NaN, Infinity, "invalid"])] },
    { elements: [audio(["A", "A", "B", ""]), jitter([0, "50", 50, null, "invalid"]), audio(["C", "D"])] },
    { elements: [{ source_label: "Fallback" }, { label: "Named clip" }] },
    { elements: [{ label: "Audio box" }] },
  ];
  for (let dimensions = 1; dimensions <= 5; dimensions++) {
    cases.push({ elements: Array.from({ length: dimensions }, (_, index) => index % 2 ? audio(["A", "B"]) : jitter([0, 50, 100])) });
  }
  for (const strip of cases) {
    const expected = legacy(strip);
    assert.equal(countStripVariants(strip), expected.length);
    assert.deepEqual([...iterateStripVariants(strip)], expected);
    assert.deepEqual([...iterateStripVariants(strip)].map(key), expected.map(key));
    for (const limit of [0, 1, 7, 240]) assert.deepEqual(previewStripVariants(strip, limit), expected.slice(0, limit));
  }
});

test("six-by-six counting and bounded preview keep the full total without full expansion", () => {
  const strip = { elements: Array.from({ length: 6 }, () => jitter([0, 1, 2, 3, 4, 5])) };
  assert.equal(countStripVariants(strip), 46_656);
  const prefix = previewStripVariants(strip, 240);
  assert.equal(prefix.length, 240);
  assert.deepEqual(prefix[0].map(choice => choice.value), [0, 0, 0, 0, 0, 0]);
  assert.deepEqual(prefix.at(-1).map(choice => choice.value), [0, 0, 1, 0, 3, 5]);
  assert.throws(() => iterateStripVariants(strip, 10_000), /limit.*10000/i);
  assert.equal(assertSequenceLimit([strip]), 46_656, "legacy full enumeration does not inherit a native ceiling");
});

test("overflow stays explicit, bounded prefixes remain usable and empty factors dominate", () => {
  const strip = { elements: Array.from({ length: 54 }, () => jitter([0, 1])) };
  assert.equal(countStripVariants(strip), Infinity);
  assert.throws(() => iterateStripVariants(strip), /safe integer/i);
  assert.throws(() => assertSequenceLimit([strip]), /safe integer/i);
  assert.equal(previewStripVariants(strip, 3).length, 3);
  assert.equal(countStripVariants({ elements: [...strip.elements, audio([])] }), 0);
  assert.deepEqual([...iterateStripVariants({ elements: [...strip.elements, audio([])] })], []);
});

test("caller-supplied native limits reject the whole variant map before partial enumeration", () => {
  const strips = [{ elements: [jitter([0, 1, 2])] }, { elements: [audio(["A", "B"])] }];
  assert.equal(assertSequenceLimit(strips, 5), 5);
  assert.throws(() => assertSequenceLimit(strips, 4), /limit.*4/i);
  for (const count of [-1, NaN, Infinity, -Infinity, 0.5]) assert.throws(() => assertCountLimit(count), RangeError);
  assert.equal(assertCountLimit(0, 0), 0);
  for (const limit of [-1, NaN, Infinity, 0.5]) {
    assert.throws(() => previewStripVariants(strips[0], limit), /limit/i);
    assert.throws(() => assertSequenceLimit(strips, limit), /limit/i);
  }
});

test("scientific file enumeration preserves row order, global variant IDs and uncrossed families", () => {
  const context = vm.createContext({ countStripVariants, assertSequenceLimit, assertCountLimit, iterateStripVariants,
    staticSourceInventory: () => ({}), staticVariantDurationMs: () => 1000, staticVariantLoomingOnsetMs: () => 0,
    staticVariantNoiseType: () => "white", staticBaselineMode: () => "audio_tactile", staticTrialFileRow: row => row, DEFAULT_STUDY_TEMPLATE_ID: "fixture",
  });
  vm.runInContext(functions("staticTrialFileCount", "staticTrialPoolSettings"), context);
  const strips = [{ label: "First", elements: [audio(["A", "B"]), jitter([0, 50])] }, { label: "Second", elements: [audio(["C"])] }];
  const design = { protocol: { trial_strips: strips, soa_values_ms: [100, 200], include_baseline_trials: true,
    baseline_strategy: "custom", baseline_soa_values_ms: [0], include_catch_trials: true,
    catch_crosses_sequence_variants: false, include_auditory_only_trials: true } };
  const payload = context.staticTrialFileBakePayload(design, {});
  const actual = payload.files.map(row => [row.rowIndex, row.variantIndex, key(row.variant), row.family, row.soaMs ?? null]);
  let id = 0;
  const expected = strips.flatMap((strip, row) => legacy(strip).flatMap((variant, index) => {
    id++;
    const entry = (family, soa = null) => [row, id, key(variant), family, soa];
    return [entry("audio_tactile", 100), entry("audio_tactile", 200), entry("baseline", 0),
      ...(index === 0 ? [entry("catch")] : []), entry("auditory_only", 0)];
  }));
  assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected);
  assert.equal(context.staticTrialFileCount(design), expected.length);
  assert.throws(() => context.staticTrialFileBakePayload(design, {}, expected.length - 1), /limit/);
});

test("native review bounds precede source planning while audit examples disclose truncation", () => {
  const strips = [{ elements: Array.from({ length: 6 }, () => jitter([0, 1, 2, 3, 4, 5])) }];
  let sourceCountCalls = 0;
  const context = vm.createContext({ countStripVariants, previewStripVariants, assertSequenceLimit, assertCountLimit,
    TRIAL_PREVIEW_LIMIT: 240, nativeDesigner: { capabilities: { assembly: { max_rows: 10000, max_blocks: 128 } } },
    staticTrialFileCount: () => { sourceCountCalls++; return 1; },
  });
  vm.runInContext(functions("nativeAssemblyLimit", "previewVariantLabel"), context);
  assert.throws(() => context.nativeAssemblyLimit({ protocol: { trial_strips: strips } }), /limit.*10000/);
  assert.equal(sourceCountCalls, 0, "over-limit variants fail before source file work");
  vm.runInContext(functions("auditTrialStripSnapshot", "auditPoolRows"), context);
  const audit = context.auditTrialStripSnapshot(strips[0], 0);
  assert.equal(audit.variant_count, 46656);
  assert.equal(audit.variants.length, 240);
  assert.equal(audit.variants_truncated, true);
  const overflow = context.auditTrialStripSnapshot({ elements: Array.from({ length: 54 }, () => jitter([0, 1])) }, 0);
  assert.equal(overflow.variant_count, null);
  assert.equal(overflow.variant_count_overflow, true);
  assert.equal(overflow.variants.length, 240);
});

test("readiness reports overflow without throwing or replacing the editable draft", () => {
  const state = { custom_workflow: { is_custom: true }, design: { protocol: { trial_strips: [{
    elements: Array.from({ length: 54 }, () => jitter([0, 1])),
  }] } } };
  const context = vm.createContext({ state, staticModeActive: true, countStripVariants,
    WORKFLOW_STEPS: ["trials"], profileStepStatus: () => ({ complete: true }), SEGMENT_INFO: {}, humanize: value => value });
  vm.runInContext(functions("refreshHostedWorkflowSteps", "initializeHostedDesignerProgress"), context);
  context.refreshHostedWorkflowSteps();
  assert.equal(state.custom_workflow.steps[0].complete, false);
  assert.match(state.custom_workflow.steps[0].missing[0], /Too many variants.*draft is preserved/);
  assert.equal(state.design.protocol.trial_strips[0].elements.length, 54);
});
