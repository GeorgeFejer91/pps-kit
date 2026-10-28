import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";
import { ROW_CONTRACT_FIELDS, rowContractMetadata, trialFamilyContract } from "../row_contract.js";
import { countStripVariants, iterateStripVariants, assertSequenceLimit, assertCountLimit } from "../sequence_variants.js";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const resources = new URL("../../../../packages/pps-resources/", import.meta.url);
const functions = (start, end) => app.slice(app.indexOf(`function ${start}(`), app.indexOf(`function ${end}(`));
function single(name) {
  const start = app.indexOf(`function ${name}(`);
  assert.ok(start >= 0, name);
  return app.slice(start, app.indexOf("\nfunction ", start + 1));
}
function context() {
  const ctx = vm.createContext({ ROW_CONTRACT_FIELDS, rowContractMetadata, trialFamilyContract,
    countStripVariants, iterateStripVariants, assertSequenceLimit, assertCountLimit,
    DEFAULT_STUDY_TEMPLATE_ID: "fixture", TRIAL_FAMILY_COLORS: {},
    familyDisplayName: value => value, sourceColor: () => "#000", clone: structuredClone,
  });
  vm.runInContext(functions("staticSourceInventory", "staticCountBy") + single("staticBlockPreviewRow") + single("staticSoaColor")
    + ["normalizedRandomizationSeed", "slugify", "normalizeRepetitionValue", "trialPoolFamilyKey", "stableHashInt",
      "trialPoolSourceLineage", "trialPoolFractionalStratum", "trialPoolFractionalParentStratum", "previewVariantKey",
      "csvEscape", "rowsToCsv"].map(single).join("\n"), ctx);
  return ctx;
}

test("row contract allowlist matches V1 and retains typed nonempty values without arbitrary metadata", async () => {
  const python = await readFile(new URL("../../../../packages/pps-runtime/src/peripersonal_space_toolkit/dashboard_app.py", import.meta.url), "utf8");
  const fields = [...python.match(/ROW_CONTRACT_FIELDS = \(([\s\S]*?)\n\)/)[1].matchAll(/"([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(ROW_CONTRACT_FIELDS, fields);
  assert.deepEqual(rowContractMetadata({ iti_ms: 0, primary_analysis_included: false, response_choice_set: ["left", "right"],
    body_part: "", body_side: null, secret: "never export", duration_ms: 999 }),
    { response_choice_set: ["left", "right"], primary_analysis_included: false, iti_ms: 0 });
  assert.deepEqual(trialFamilyContract({ expected_response: "respond" }, "catch"), {
    expected_response: "withhold", target_role: "catch_no_target", response_rule: "withhold_response_to_audio_only_catch",
  });
  assert.equal(trialFamilyContract({}, "auditory_only").expected_response, "respond");
});

test("saved Collignon left/right and Biggio timing contracts survive file, pool, block and CSV projection", async () => {
  const ctx = context();
  for (const id of ["tajadura_jimenez_2009_uncrossed_visual_deprivation", "tajadura_jimenez_2009_crossed_visual_deprivation", "biggio_2017_common_racket"]) {
    const { design } = JSON.parse(await readFile(new URL(`study_templates/${id}.json`, resources), "utf8"));
    const files = ctx.staticTrialFileBakePayload(design, {}).files;
    const pool = ctx.staticTrialPoolBakePayload(design, { files }).preview_rows;
    const blocks = pool.map((row, index) => ctx.staticBlockPreviewRow(row, 1, index + 1, 0, 1000));
    assert.ok(files.length && pool.length);
    for (const rows of [files, pool, blocks]) for (const row of rows) {
      const strip = design.protocol.trial_strips.find(strip => strip.label === row.row_label);
      assert.deepEqual(rowContractMetadata(row), trialFamilyContract(strip.metadata, row.family), `${id}: ${row.row_label}/${row.family}`);
    }
    if (id.startsWith("tajadura")) {
      assert.equal(blocks.length, 300);
      assert.deepEqual(new Set(blocks.map(row => row.correct_response)), new Set(["left", "right"]));
      assert.ok(blocks.every(row => row.response_choice_set === "left,right" && row.expected_response === "respond" && row.iti_ms === "1950"));
      const csv = ctx.rowsToCsv(blocks, ["response_choice_set", "correct_response", "iti_ms"]);
      assert.match(csv, /"left,right",left,1950/);
      assert.match(csv, /"left,right",right,1950/);
    }
  }
  assert.equal(ctx.rowsToCsv([{ response_choice_set: ["left", "right"], primary_analysis_included: false }],
    ["response_choice_set", "primary_analysis_included"]),
    'response_choice_set,primary_analysis_included\r\n"[""left"",""right""]",false\r\n');
});

test("collecting edited or reordered strip controls preserves saved protocol identity and hidden contract", () => {
  const ctx = context();
  ctx.state = { design: { protocol: { trial_strips: [
    { strip_id: "left", metadata: { correct_response: "left", iti_ms: 1950 }, soa_values_ms: [0], elements: [] },
    { strip_id: "right", metadata: { correct_response: "right", iti_ms: 1950 }, soa_values_ms: [30], elements: [] },
  ] } } };
  ctx.$ = () => ({ querySelectorAll: () => [1, 0].map(index => ({ dataset: { stripIndex: String(index) },
    querySelectorAll: () => [], querySelector: selector => ({ value: selector.includes('"label"') ? `Edited ${index}` : "0" }),
  })) });
  vm.runInContext(single("collectTrialStrips"), ctx);
  const strips = ctx.collectTrialStrips();
  assert.equal(strips[0].strip_id, "right");
  assert.equal(strips[0].metadata.correct_response, "right");
  assert.deepEqual(strips[0].soa_values_ms, [30]);
  assert.equal(strips[1].strip_id, "left");
  assert.equal(strips[1].metadata.correct_response, "left");
  strips[0].metadata.correct_response = "changed";
  assert.equal(ctx.state.design.protocol.trial_strips[1].metadata.correct_response, "right");
});
