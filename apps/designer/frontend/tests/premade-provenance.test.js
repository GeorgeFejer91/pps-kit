import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { webcrypto } from "node:crypto";
import vm from "node:vm";
import test from "node:test";

const app = await readFile(new URL("../app.js", import.meta.url), "utf8");
const chrome = (await readFile(new URL("../designer_main.js", import.meta.url), "utf8"))
  .replace('import { nativeDesigner } from "./native_designer.js";', 'const nativeDesigner = { enabled: false };')
  .replace(/initializeChrome\(\);\s*$/, "");
const hash = async bytes => Buffer.from(await webcrypto.subtle.digest("SHA-256", bytes)).toString("hex");

async function fixture() {
  const audio = new Uint8Array([82, 73, 70, 70, 1, 2, 3, 4]);
  const digest = await hash(audio);
  const text = `${JSON.stringify({ asset: { sha256: digest }, proxy_policy: "explicit-proxy.v2", provenance: { scientific_source_conformance: false } }, null, 2)}\r\n`;
  const receiptHash = await hash(new TextEncoder().encode(text));
  const path = "assets/preloads/study/audio.wav";
  const sidecar = "assets/preloads/study/audio.native_generation.json";
  const asset = { label: "Noise", path, sha256: digest, native_generation_provenance: sidecar, native_generation_provenance_sha256: receiptHash, proxy_policy: "explicit-proxy.v2" };
  const calls = [];
  const context = vm.createContext({ window: { PPSDesignerApp: { preloadAssetUrl: value => value } },
    Blob, TextEncoder, TextDecoder, Uint8Array, structuredClone, crypto: webcrypto, AbortSignal,
    fetch: async url => { calls.push(url); return new Response(url === path ? audio : text); } });
  vm.runInContext(chrome, context);
  vm.runInContext("saveProfileDownload = async blob => { globalThis.download = blob; };", context);
  const snapshot = { preload_inventory: { assets: [asset] }, design: { name: "Premade", noises: [{ ...asset, prebaked_path: path }] } };
  return { audio, digest, text, receiptHash, path, sidecar, asset, calls, context, snapshot };
}

function exportedProfile(context) {
  return context.download.arrayBuffer().then(buffer => {
    const bytes = new Uint8Array(buffer), view = new DataView(buffer), files = new Map();
    let offset = 0;
    while (view.getUint32(offset, true) === 0x04034b50) {
      const size = view.getUint32(offset + 18, true), nameSize = view.getUint16(offset + 26, true);
      const start = offset + 30 + nameSize + view.getUint16(offset + 28, true);
      files.set(new TextDecoder().decode(bytes.subarray(offset + 30, offset + 30 + nameSize)), bytes.slice(start, start + size));
      offset = start + size;
    }
    return { profile: JSON.parse(new TextDecoder().decode(files.get("profile.json"))), files };
  });
}

test("static premade projection and source hydration preserve receipt references", async () => {
  const { asset } = await fixture();
  const context = vm.createContext({ clone: structuredClone, staticInventoryProfile: () => ({ assets: [asset] }),
    staticPreloadInventory: {}, staticResourceUrl: value => value, normalizeSourceKey: value => value.toLowerCase(), expandStaticTrialStripSourceLabels() {} });
  for (const name of ["staticPremadeProvenance", "staticPremadeDuration", "staticProfileAssetStatus", "hydrateStaticSourceAssets", "staticRenderStatus"]) {
    const start = app.indexOf(`function ${name}(`);
    vm.runInContext(app.slice(start, app.indexOf("\nfunction ", start + 1)), context);
  }
  const status = context.staticProfileAssetStatus("test");
  assert.equal(context.staticRenderStatus(status).wavs[0].native_generation_provenance_sha256, asset.native_generation_provenance_sha256);
  for (const kind of ["noises", "custom_looming_files", "extra"]) {
    const design = { noises: [], custom_looming_files: [], protocol: {} };
    if (kind !== "extra") design[kind].push({ label: "Noise" });
    context.hydrateStaticSourceAssets(design, status);
    const source = [...design.noises, ...design.custom_looming_files][0];
    for (const field of ["native_generation_provenance", "native_generation_provenance_sha256", "proxy_policy"]) assert.equal(source[field], asset[field]);
  }
  const replaced = { noises: [{ label: "Noise", prebaked_path: "browser-asset:replacement.wav" }], custom_looming_files: [], protocol: {} };
  context.hydrateStaticSourceAssets(replaced, status);
  assert.equal(replaced.noises[0].native_generation_provenance, undefined, "matching labels do not bind receipts to replacement audio");
});

test("premade receipt stays byte-exact through export and network-free re-export", async () => {
  const f = await fixture();
  await f.context.window.PPSDesigner.exportBundle(f.snapshot);
  const { profile, files } = await exportedProfile(f.context);
  const receipt = profile.design.noises[0].native_premade_provenance;
  assert.deepEqual(receipt, { json_utf8: f.text, sha256: f.receiptHash });
  assert.equal(JSON.parse(receipt.json_utf8).provenance.scientific_source_conformance, false);
  assert.deepEqual(f.calls, [f.path, f.sidecar]);
  assert.equal(files.size, 3, "receipt is inline design metadata, not a new ZIP member");
  f.context.fetch = async () => { throw new Error("offline"); };
  f.context.window.PPSDesigner.drafts.asset = async () => ({ bytes: f.audio, type: "audio/wav", name: "audio.wav" });
  await f.context.window.PPSDesigner.exportBundle({ design: profile.design });
  assert.deepEqual((await exportedProfile(f.context)).profile.design.noises[0].native_premade_provenance, receipt);
  assert.equal(f.snapshot.design.noises[0].native_premade_provenance, undefined);
});

test("corrupt, stale, oversized, malformed and mismatched premade receipts prevent download", async () => {
  for (const failure of ["hash", "audio", "oversized", "json", "utf8", "policy", "missing hash", "unsafe path"]) {
    const f = await fixture();
    let bytes = new TextEncoder().encode(f.text);
    if (failure === "audio") bytes = new TextEncoder().encode(f.text.replace(f.digest, "0".repeat(64)));
    if (failure === "oversized") bytes = new Uint8Array(256 * 1024 + 1);
    if (failure === "json") bytes = new TextEncoder().encode("{broken");
    if (failure === "utf8") bytes = new Uint8Array([255]);
    if (failure !== "hash") f.snapshot.design.noises[0].native_generation_provenance_sha256 = await hash(bytes);
    if (failure === "hash") bytes[0] = 32;
    if (failure === "policy") f.snapshot.design.noises[0].proxy_policy = "another-policy";
    if (failure === "missing hash") f.snapshot.design.noises[0].native_generation_provenance_sha256 = "";
    if (failure === "unsafe path") f.snapshot.design.noises[0].native_generation_provenance = "assets/preloads/../secret.json";
    f.context.fetch = async url => new Response(url === f.path ? f.audio : bytes);
    await assert.rejects(f.context.window.PPSDesigner.exportBundle(f.snapshot), undefined, failure);
    assert.equal(f.context.download, undefined, failure);
  }
  const f = await fixture();
  f.snapshot.design.noises[0].native_premade_provenance = { json_utf8: f.text, sha256: f.receiptHash };
  f.context.fetch = async () => new Response(new Uint8Array([1, 2]));
  f.snapshot.design.noises[0].prebaked_path = "browser-asset:changed.wav";
  f.context.window.PPSDesigner.drafts.asset = async () => ({ bytes: new Uint8Array([1, 2]), type: "audio/wav", name: "changed.wav" });
  await assert.rejects(f.context.window.PPSDesigner.exportBundle(f.snapshot), /provenance/i);
  assert.equal(f.context.download, undefined);
  delete f.snapshot.design.noises[0].prebaked_path;
  await assert.rejects(f.context.window.PPSDesigner.exportBundle(f.snapshot), /no audio reference/);
});
