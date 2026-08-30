import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const [html, source, styles] = await Promise.all([
  readFile(new URL("index.html", root), "utf8"),
  readFile(new URL("src/desktop-app.js", root), "utf8"),
  readFile(new URL("src/styles/app.css", root), "utf8"),
]);

test("desktop page exposes explicit inbound target and outbound controller roles", () => {
  assert.match(html, /Public rendezvous · private control/u);
  assert.match(html, /id="desktop-beacon-start"[^>]*>Advertise this runner</u);
  assert.match(html, /id="desktop-pairing-request"[^>]*hidden/u);
  assert.match(html, /id="desktop-request-approve"[^>]*disabled/u);
  assert.match(html, /Control a Browser Experiment/u);
  assert.match(html, /id="desktop-controller-browse"[^>]*>Browse public targets</u);
  assert.match(html, /id="desktop-controller-connect"[^>]*disabled/u);
  for (const action of ["package.prepare_demo", "part.start", "run.pause", "run.resume", "run.stop"]) {
    assert.match(html, new RegExp(`data-controller-action="${action.replace(".", "\\.")}"`));
  }
});

test("desktop loads only the pinned local VDO SDK before its module", () => {
  const sdk = "./vendor/vdoninja/1.5.5/vdoninja-sdk.min.js";
  assert.match(html, new RegExp(`<script src="${sdk.replaceAll(".", "\\.")}"></script>`));
  assert.ok(html.indexOf(sdk) < html.indexOf("./src/desktop-app.js"));
  assert.doesNotMatch(html, /https?:\/\/[^\s"']+vdoninja-sdk/iu);
  assert.doesNotMatch(source, /getUserMedia|publish\s*\(/u);
});

test("desktop inbound path uses Rust owner APIs and never local runner dispatch", () => {
  assert.match(source, /new PpsPublicBeacon\(\{ role: "target"/u);
  assert.match(source, /new BrspTargetSession\(/u);
  assert.match(source, /const sessionId = remoteSessionId\(\)[\s\S]+beacon\.approvePairing[\s\S]+sessionId,/u);
  assert.match(source, /snapshot\?\.safety\?\.local_armed/u);
  assert.match(source, /remoteSessionClaim\(/u);
  assert.match(source, /remoteSessionRenew\(/u);
  assert.match(source, /remoteSessionDispatch\(/u);
  assert.match(source, /remoteSessionRevoke\(/u);
  assert.match(source, /envelope\.type === "snapshot-request" \|\| envelope\.type === "error"/u);
  assert.match(source, /applicationOwnsTransitionValidation:\s*true/u);
  assert.match(source, /canPublishTargetState:\s*\(\) => nativePublicationAuthorized\(target\)/u);
  assert.match(source, /controller_lease_id === target\.nativeClaimReceipt\.controllerId/u);
  assert.match(source, /if \(remoteControllerConnected\(\)\) throw new Error/u);
  assert.match(source, /Date\.now\(\) >= target\.offerExpiresUnixMs[\s\S]+private_offer_expired/u);

  const inboundApply = source.slice(
    source.indexOf("async function applyInboundCommand"),
    source.indexOf("function bindInboundPrivateSession"),
  );
  assert.match(source, /function queueNativeControl[\s\S]+target\.nativeControlTail\.then/u);
  assert.match(source, /const operation = queueNativeControl[\s\S]+api\.remoteSessionDispatch/u);
  assert.match(source, /return operation;/u);
  assert.match(inboundApply, /takeCommandOperation/u);
  assert.doesNotMatch(inboundApply, /api\.dispatch\s*\(/u);
  const nativeQueue = source.slice(
    source.indexOf("function queueNativeControl"),
    source.indexOf("function takeCommandOperation"),
  );
  assert.equal((nativeQueue.match(/target !== inboundPrivateTarget/gu) ?? []).length, 2);
  assert.ok(nativeQueue.indexOf("await target.claimPromise") < nativeQueue.lastIndexOf("target !== inboundPrivateTarget"));
  assert.match(source, /lanListener:\s*false/u);
  assert.match(source, /lanListener:\s*true/u);
});

test("desktop outbound controller waits for approval and explicit private Connect", () => {
  assert.match(source, /new PpsPublicBeacon\(\{ role: "controller"/u);
  assert.match(source, /beacon\.takePrivateOffer/u);
  assert.match(source, /new BrspControllerSession\(/u);
  assert.match(source, /desktop-controller-connect.+addEventListener\("click"/su);
  assert.match(source, /session\.sendCommand\(button\.dataset\.controllerAction/u);
  assert.match(source, /renderOutboundSnapshot\(event\.detail\.snapshot\)/u);

  const outboundConnect = source.slice(
    source.indexOf("async function connectOutboundController"),
    source.indexOf("async function stopOutboundControllerSession"),
  );
  assert.doesNotMatch(outboundConnect, /remoteSession(?:Claim|Renew|Dispatch|Revoke)/u);
});

test("all desktop remote producers stop on pagehide and shared beacon CSS is accessible", () => {
  assert.match(source, /window\.addEventListener\("pagehide"[\s\S]+stopAllRemoteNetworking/u);
  assert.match(styles, /\.beacon-target-list\s*\{/u);
  assert.match(styles, /\.beacon-target-button\s*\{/u);
  assert.match(styles, /\.beacon-target-button\[aria-pressed="true"\]/u);
  assert.match(styles, /\.beacon-request-card\[hidden\][^{]*\{\s*display:\s*none;/u);
});
