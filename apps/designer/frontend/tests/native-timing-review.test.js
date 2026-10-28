import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";
import { ROW_CONTRACT_FIELDS } from "../row_contract.js";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const source = app.slice(app.indexOf("function renderNativeItiTiming("), app.indexOf("function coloredPreviewCell("));
const context = vm.createContext({ escapeHtml: value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;"),
  formatDurationMs: value => `${value} ms`, ROW_CONTRACT_FIELDS });
vm.runInContext(source, context);
const row = { iti_ms: "1000-1500", iti_policy: "paper_randomized_1000_to_1500_ms",
  native_iti_materialization_policy: "toolkit_uniform_integer_ms_std_rng_0_8_8.v1", native_iti_anchor: "after_trial_audio_end",
  native_iti_seed_sha256: "a".repeat(64), native_iti_range_min_ms: 1000, native_iti_range_max_ms: 1500,
  native_resolved_iti_ms: 1234, native_iti_frames: 54419, native_session_duration_ms: 6234,
  native_iti_source_distribution_reported: false, native_iti_source_anchor_reported: false, native_iti_legacy_compatible: false };

test("native timing review distinguishes the saved range from the selected toolkit delay and provenance", () => {
  const original = structuredClone(row), html = context.renderNativeItiTiming(row);
  for (const text of ["Toolkit ITI: 1234 ms", "Reported range: 1000-1500 ms", row.iti_policy,
    "Toolkit uniform whole-millisecond sampling", "after trial audio ends", "54419 frames", "6234 ms", row.native_iti_seed_sha256,
    "Source distribution and anchor are unreported", "not source or legacy equivalence"]) assert.ok(html.includes(text), text);
  assert.deepEqual(row, original, "presentation never replaces source evidence or selected timing");
  assert.equal(context.renderNativeItiTiming({ iti_ms: 1950 }), "", "numeric legacy timing remains unchanged");
  assert.equal(context.nativeItiReviewDisclosure({ blocks: [{ preview_rows: [{ iti_ms: 1950 }] }] }), "");
  const summary = context.nativeItiReviewDisclosure({ blocks: [{ preview_rows: [row, row] }, { preview_rows: [row] }] });
  assert.match(summary, /3 reviewed rows/);
  assert.match(summary, /source does not report this distribution, anchor or seed/);
  assert.match(summary, /before accepting/);
  assert.ok(context.renderNativeItiTiming({ ...row, iti_policy: "<script>" }).includes("&lt;script&gt;"));
});

test("Segment 5 CSV allowlist retains all native timing receipt fields alongside the source contract", () => {
  const definition = app.slice(app.indexOf("const BLOCK_CSV_DOWNLOAD_COLUMNS ="), app.indexOf("const DEFAULT_LOUDNESS_POLICY ="));
  vm.runInContext(`${definition}\nthis.columns = BLOCK_CSV_DOWNLOAD_COLUMNS;`, context);
  for (const key of Object.keys(row)) assert.ok(context.columns.includes(key), key);
});
