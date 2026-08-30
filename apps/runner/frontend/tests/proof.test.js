import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  createProofMac,
  proofMaterial,
  proofTranscript,
} from "../src/remote/proof.js";

const fixtureUrl = new URL("../../../../packages/pps-brsp/test-vectors/brsp1-proof.json", import.meta.url);
const fixture = JSON.parse(await readFile(fixtureUrl, "utf8"));
const { secret, targetHello, controllerHello } = fixture;

test("canonical proof transcript is complete, role ordered, and independent of arrival order", () => {
  const forward = proofTranscript(targetHello, controllerHello);
  const reverse = proofTranscript(controllerHello, targetHello);
  assert.equal(forward, reverse);
  assert.equal(forward, fixture.canonicalTranscript);
  assert.equal(
    proofMaterial({ localHello: controllerHello, remoteHello: targetHello }),
    `BRSP/1 proof\ncontroller\n${forward}`,
  );
  assert.match(forward, /^\{"controllerHello":/u);
  assert.match(forward, /"protocol":"brsp"/u);
  assert.match(forward, /"targetHello":/u);
});

test("proof uses UTF-8 invitation text as key and emits unpadded base64url", async () => {
  const material = proofMaterial({ localHello: controllerHello, remoteHello: targetHello });
  const independent = createHmac("sha256", Buffer.from(secret, "utf8"))
    .update(material, "utf8")
    .digest("base64url");
  const actual = await createProofMac(secret, {
    localHello: controllerHello,
    remoteHello: targetHello,
  });
  assert.equal(actual, independent);
  assert.equal(actual, fixture.controllerProof);
  assert.match(actual, /^[A-Za-z0-9_-]{43}$/u);
  assert(!actual.includes("="));
});

test("proof is bound to sender role and the complete hello transcript", async () => {
  const controller = await createProofMac(secret, {
    localHello: controllerHello,
    remoteHello: targetHello,
  });
  const target = await createProofMac(secret, {
    localHello: targetHello,
    remoteHello: controllerHello,
  });
  assert.equal(target, fixture.targetProof);
  assert.notEqual(controller, target);
  const altered = structuredClone(controllerHello);
  altered.body.requestedScopes.reverse();
  const alteredProof = await createProofMac(secret, {
    localHello: altered,
    remoteHello: targetHello,
  });
  assert.notEqual(controller, alteredProof, "received hello array order is authenticated");
});
