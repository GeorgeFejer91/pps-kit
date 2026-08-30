import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { assemblePages } from "./build_pages.mjs";


const scriptDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(scriptDir, "../../..");
const runnerCompiled = join(root, "apps", "runner", "compiled");
const companionAssets = ["companion.js", "qr-code.js", "style.css"];
const companionVendorHashes = new Map([
  ["LICENSE-MPL-2.0.txt", "3f3d9e0024b1921b067d6f7f88deb4a60cbe7a78e76c64e3f1d7fc3b779b9d04"],
  ["NOTICE.md", "e9a94c863d79032c0371bb2a207f2ecbc5d78108c0191d2484d8c2f58626aacb"],
  ["vdoninja-sdk.js", "8097d5420d7ed2426623d7ff08f6abd45f03f89e6540a6cc4b86bcdc057d841e"],
  ["vdoninja-sdk.min.js", "390ea6c8b1a4e57bf7fa18ff2b394f25cc79e637130f97e4a29ca958a90fac77"],
]);

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function exists(path) {
  return Boolean(await stat(path).catch(() => null));
}

test("Pages assembly publishes only the canonical browser companion bytes", async () => {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "pps-pages-"));
  const output = join(temporaryRoot, "pages");
  try {
    assert.equal(await assemblePages(output), resolve(output));

    for (const route of ["index.html", "documentation/index.html", "download/index.html", ".nojekyll"]) {
      assert.equal(await exists(join(output, route)), true, `missing existing Pages route ${route}`);
    }
    assert.equal((await readFile(join(output, "CNAME"), "utf8")).trim(), "ppskit.qzz.io");

    const sourceIndex = await readFile(join(runnerCompiled, "companion", "index.html"));
    const stagedIndex = await readFile(join(output, "experiment-runner", "index.html"));
    assert.deepEqual(stagedIndex, sourceIndex);
    for (const asset of companionAssets) {
      assert.deepEqual(
        await readFile(join(output, "assets", asset)),
        await readFile(join(runnerCompiled, "assets", asset)),
        `${asset} must remain byte-identical`,
      );
    }
    for (const [file, expectedHash] of companionVendorHashes) {
      const relative = join("vendor", "vdoninja", "1.5.5", file);
      const source = await readFile(join(runnerCompiled, relative));
      const staged = await readFile(join(output, relative));
      assert.deepEqual(staged, source, `${file} must remain byte-identical`);
      assert.equal(sha256(staged), expectedHash, `${file} must match the reviewed VDO.Ninja 1.5.5 hash`);
    }

    assert.equal(await exists(join(output, "assets", "desktop.js")), false);
    assert.equal(await exists(join(output, "experiment-runner", "src-tauri")), false);
    const html = stagedIndex.toString("utf8");
    for (const [base, expectedAssetsRoot] of [
      ["https://ppskit.qzz.io/experiment-runner/", "https://ppskit.qzz.io/assets/"],
      ["https://georgefejer91.github.io/pps-kit/experiment-runner/", "https://georgefejer91.github.io/pps-kit/assets/"],
    ]) {
      assert.equal(new URL("../assets/companion.js", base).href, `${expectedAssetsRoot}companion.js`);
      assert.equal(new URL("../assets/style.css", base).href, `${expectedAssetsRoot}style.css`);
      assert.equal(
        new URL("../vendor/vdoninja/1.5.5/vdoninja-sdk.min.js", base).href,
        new URL("vendor/vdoninja/1.5.5/vdoninja-sdk.min.js", new URL("../", base)).href,
      );
    }
    assert.match(html, /\.\.\/assets\/companion\.js/u);
    assert.match(html, /\.\.\/vendor\/vdoninja\/1\.5\.5\/vdoninja-sdk\.min\.js/u);
    assert.doesNotMatch(html, /desktop\.js|__TAURI_INTERNALS__/u);
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});
