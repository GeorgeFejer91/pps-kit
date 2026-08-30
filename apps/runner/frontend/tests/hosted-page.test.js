import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { fileURLToPath } from "node:url";


const companionHtml = await readFile(
  fileURLToPath(new URL("../companion/index.html", import.meta.url)),
  "utf8",
);
const companionCss = await readFile(
  fileURLToPath(new URL("../src/styles/app.css", import.meta.url)),
  "utf8",
);

test("hosted companion declares a restrictive browser-only document policy", () => {
  assert.match(companionHtml, /<title>PPS Experiment Runner Companion<\/title>/u);
  assert.match(companionHtml, /name="referrer" content="no-referrer"/u);
  assert.match(companionHtml, /Content-Security-Policy/u);
  assert.match(companionHtml, /connect-src 'self'/u);
  assert.match(companionHtml, /This page supplies the interface, not a network relay/u);
  assert.doesNotMatch(companionHtml, /https?:\/\/.*(?:\.js|\.css)|__TAURI_INTERNALS__|getUserMedia/u);
  assert.match(companionCss, /\.target-pairing\[hidden\]\s*\{\s*display:\s*none;/u);
});
