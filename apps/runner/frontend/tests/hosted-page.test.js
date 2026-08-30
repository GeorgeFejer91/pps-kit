import assert from "node:assert/strict";
import { createHash } from "node:crypto";
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
const companionSource = await readFile(
  fileURLToPath(new URL("../src/companion-app.js", import.meta.url)),
  "utf8",
);
const vdoSdk = await readFile(
  fileURLToPath(new URL("../public/vendor/vdoninja/1.5.5/vdoninja-sdk.min.js", import.meta.url)),
);

test("hosted companion declares a restrictive browser-only document policy", () => {
  assert.match(companionHtml, /<title>PPS Experiment Runner Companion<\/title>/u);
  assert.match(companionHtml, /name="referrer" content="no-referrer"/u);
  assert.match(companionHtml, /Content-Security-Policy/u);
  assert.match(companionHtml, /connect-src 'self' wss:\/\/wss\.vdo\.ninja https:\/\/turnservers\.vdo\.ninja/u);
  assert.match(companionHtml, /This page carries a data-only connection beacon/u);
  assert.match(companionHtml, /id="beacon-browse"/u);
  assert.match(companionHtml, /id="target-beacon-start"/u);
  assert.match(companionHtml, /id="phone-response"[^>]*disabled>Tap response/u);
  assert.match(companionHtml, /id="embedding-warning"[^>]*role="alert"[^>]*hidden/u);
  assert.match(companionHtml, /After target-local approval, fresh credentials go only to that exact requester/u);
  assert.match(companionHtml, /\.\.\/vendor\/vdoninja\/1\.5\.5\/vdoninja-sdk\.min\.js/u);
  assert(
    companionHtml.indexOf("vdoninja-sdk.min.js") < companionHtml.indexOf('type="module"'),
    "the reviewed classic SDK must be defined before the companion module imports its adapter",
  );
  assert.doesNotMatch(companionHtml, /https?:\/\/.*(?:\.js|\.css)|__TAURI_INTERNALS__|getUserMedia/u);
  assert.match(companionCss, /\.target-pairing\[hidden\]\s*\{\s*display:\s*none;/u);
  assert.equal(
    createHash("sha256").update(vdoSdk).digest("hex"),
    "390ea6c8b1a4e57bf7fa18ff2b394f25cc79e637130f97e4a29ca958a90fac77",
  );
});

test("approved phone credentials cannot authenticate after their offer deadline", () => {
  assert.match(companionSource, /Date\.now\(\) >= phoneTarget\.offerExpiresUnixMs/u);
  assert.match(companionSource, /approved private offer expired before authentication completed/iu);
});

test("hosted approval and output controls fail closed inside an iframe", () => {
  assert.match(companionSource, /window\.top !== window\.self/u);
  assert.match(companionSource, /if \(isEmbeddedContext\(\)\)[\s\S]+blockEmbeddedContext\(\);[\s\S]+return;/u);
  assert.match(companionSource, /stripInvitationMaterial\(\);[\s\S]+querySelectorAll\("button, input, select, textarea"\)/u);
});
