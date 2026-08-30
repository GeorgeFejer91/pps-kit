import assert from "node:assert/strict";
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

    assert.equal(await exists(join(output, "assets", "desktop.js")), false);
    assert.equal(await exists(join(output, "experiment-runner", "src-tauri")), false);
    const html = stagedIndex.toString("utf8");
    for (const [base, expectedAssetsRoot] of [
      ["https://ppskit.qzz.io/experiment-runner/", "https://ppskit.qzz.io/assets/"],
      ["https://georgefejer91.github.io/pps-kit/experiment-runner/", "https://georgefejer91.github.io/pps-kit/assets/"],
    ]) {
      assert.equal(new URL("../assets/companion.js", base).href, `${expectedAssetsRoot}companion.js`);
      assert.equal(new URL("../assets/style.css", base).href, `${expectedAssetsRoot}style.css`);
    }
    assert.match(html, /\.\.\/assets\/companion\.js/u);
    assert.doesNotMatch(html, /desktop\.js|__TAURI_INTERNALS__/u);
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
});
