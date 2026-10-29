import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const resources = new URL("../../../../packages/pps-resources/", import.meta.url);
const functions = (start, end) => app.slice(app.indexOf(`function ${start}(`), app.indexOf(`function ${end}(`));
const inventory = JSON.parse(await readFile(new URL("assets/preloads/preload_inventory.json", resources), "utf8"));
function context() {
  const result = vm.createContext({ clone: structuredClone, staticPreloadInventory: inventory,
    staticInventoryProfile: (id, source) => source.profiles.find(profile => profile.template_id === id),
    staticResourceUrl: path => `https://example.test/${path}`,
  });
  vm.runInContext(functions("staticPremadeProvenance", "staticTemplatePayload")
    + functions("hydrateStaticSourceAssets", "staticProjectPayload")
    + functions("normalizeSourceKey", "renderSourceCounts")
    + functions("staticSourceInventory", "staticVariantNoiseType"), result);
  return result;
}
const emptyDesign = () => ({ noises: [], custom_looming_files: [], protocol: {} });

function wavDuration(bytes) {
  assert.equal(bytes.toString("ascii", 0, 4), "RIFF");
  assert.equal(bytes.toString("ascii", 8, 12), "WAVE");
  let byteRate, dataBytes;
  for (let offset = 12; offset + 8 <= bytes.length;) {
    const kind = bytes.toString("ascii", offset, offset + 4), size = bytes.readUInt32LE(offset + 4);
    if (kind === "fmt ") byteRate = bytes.readUInt32LE(offset + 16);
    if (kind === "data") dataBytes = size;
    offset += 8 + size + size % 2;
  }
  assert.ok(byteRate > 0 && dataBytes > 0);
  return dataBytes / byteRate;
}

test("premade noise and custom source durations follow the matching actual WAV in hosted and native projection", async () => {
  for (const id of ["canzoneri_2012_dynamic_sounds", "biggio_2017_common_racket"]) {
    const template = JSON.parse(await readFile(new URL(`study_templates/${id}.json`, resources), "utf8"));
    const ctx = context();
    for (const resourceUrl of [path => `https://example.test/${path}`, path => `pps-resource://localhost/${path}`]) {
      ctx.staticResourceUrl = resourceUrl;
      const status = ctx.staticProfileAssetStatus(id);
      const design = structuredClone(template.design);
      design.custom_looming_files ||= [];
      ctx.hydrateStaticSourceAssets(design, status);
      const sources = ctx.staticSourceInventory(design);
      for (const asset of status.assets) {
        const actual = wavDuration(await readFile(new URL(asset.path, resources)));
        assert.equal(actual, asset.duration_s, `${id}: checked-in metadata matches PCM duration`);
        assert.equal(sources.get(asset.label).duration_ms, Math.round(actual * 1000), `${id}: ${asset.label}`);
      }
      if (id === "canzoneri_2012_dynamic_sounds") {
        assert.equal(ctx.staticVariantDurationMs([{ kind: "jitter", value: 1000 },
          { kind: "audio", label: "Pink moving sound" }, { kind: "jitter", value: 1000 }], sources), 5000);
      }
    }
  }
});

test("hydration does not borrow duration from a same-label file that is not selected", () => {
  const ctx = context(), design = emptyDesign();
  design.noises = [{ label: "Noise", prebaked_path: "custom.wav", duration_s: 2 }];
  design.custom_looming_files = [{ label: "Audio", path: "custom2.wav", target_duration_s: 5 }];
  ctx.hydrateStaticSourceAssets(design, { assets: [
    { label: "Noise", path: "premade.wav", duration_s: 3 }, { label: "Audio", path: "premade2.wav", duration_s: 3 },
  ] });
  assert.equal(ctx.staticSourceInventory(design).get("Noise").duration_ms, 2000);
  assert.equal(ctx.staticSourceInventory(design).get("Audio").duration_ms, 5000);
});

test("matching media duration overrides recipe defaults; absent or invalid metadata preserves the existing fallback", () => {
  const ctx = context();
  for (const duration of [0.1, 1.14, 2.667, 5.714]) {
    const design = emptyDesign();
    design.noises = [{ label: "Noise", duration_s: 4 }];
    design.custom_looming_files = [{ label: "Audio", target_duration_s: 4 }];
    ctx.hydrateStaticSourceAssets(design, { assets: ["Noise", "Audio", "Appended"].map(label =>
      ({ label, path: `${label}.wav`, duration_s: duration })) });
    for (const source of ctx.staticSourceInventory(design).values()) assert.equal(source.duration_ms, Math.round(duration * 1000));
  }
  for (const duration of [undefined, null, "", 0, -1, NaN, Infinity]) {
    const design = emptyDesign();
    design.noises = [{ label: "Noise" }];
    ctx.hydrateStaticSourceAssets(design, { assets: [{ label: "Noise", path: "noise.wav", duration_s: duration }] });
    assert.equal(ctx.staticSourceInventory(design).get("Noise").duration_ms, 4000);
  }
});
