import assert from "node:assert/strict";
import test from "node:test";

import {
  BEACON_MAX_BYTES,
  decodeBeaconFrame,
  encodeBeaconFrame,
  makeBeaconEnvelope,
  validateBeaconEnvelope,
} from "../src/remote/beacon-contract.js";

const encoder = new TextEncoder();

function requestEnvelope(overrides = {}) {
  return {
    protocol: "pps.beacon",
    version: 1,
    type: "pairing.request",
    senderId: "controller_test",
    senderEpoch: 7,
    sequence: 0,
    body: {
      requestId: "request_abcdefgh",
      controllerNonce: "A".repeat(32),
      label: "PPS controller",
      requestedScopes: ["session.read", "session.transport"],
    },
    ...overrides,
  };
}

test("public beacon frames round-trip at the exact 2 KiB boundary", () => {
  const envelope = makeBeaconEnvelope({
    type: "pairing.request",
    senderId: "controller_test",
    senderEpoch: 7,
    sequence: 0,
    body: requestEnvelope().body,
  });
  const encoded = encodeBeaconFrame(envelope);
  assert.deepEqual(decodeBeaconFrame(encoded), envelope);

  const encodedBytes = encoder.encode(encoded).byteLength;
  const exactLimit = `${encoded}${" ".repeat(BEACON_MAX_BYTES - encodedBytes)}`;
  assert.equal(encoder.encode(exactLimit).byteLength, BEACON_MAX_BYTES);
  assert.deepEqual(decodeBeaconFrame(exactLimit), envelope);
  assert.throws(() => decodeBeaconFrame(`${exactLimit} `), /1-2048 UTF-8 bytes/u);
});

test("public beacon contract rejects commands, unknown fields, malformed arrays, and accessors", () => {
  assert.throws(
    () => validateBeaconEnvelope({ ...requestEnvelope(), type: "command" }),
    /Unsupported public beacon/u,
  );
  assert.throws(
    () => validateBeaconEnvelope({ ...requestEnvelope(), relayUrl: "wss://attacker.example" }),
    /fields are invalid/u,
  );
  assert.throws(
    () => validateBeaconEnvelope({
      ...requestEnvelope(),
      body: { ...requestEnvelope().body, requestedScopes: ["session.transport", "session.read"] },
    }),
    /must be sorted/u,
  );
  assert.throws(
    () => validateBeaconEnvelope({
      ...requestEnvelope(),
      body: { ...requestEnvelope().body, requestedScopes: ["session.read", "session.read"] },
    }),
    /must not contain duplicates/u,
  );
  const scopesWithExtraField = ["session.read"];
  scopesWithExtraField.metadata = "not-on-the-wire";
  assert.throws(
    () => validateBeaconEnvelope({
      ...requestEnvelope(),
      body: { ...requestEnvelope().body, requestedScopes: scopesWithExtraField },
    }),
    /dense array/u,
  );
  const accessorBody = {};
  for (const [key, value] of Object.entries(requestEnvelope().body)) {
    Object.defineProperty(accessorBody, key, {
      enumerable: true,
      get: () => value,
    });
  }
  assert.throws(
    () => validateBeaconEnvelope({ ...requestEnvelope(), body: accessorBody }),
    /data properties/u,
  );
});

test("private offers require canonical 32-byte base64url secrets and exact fields", () => {
  const body = {
    requestId: "request_abcdefgh",
    controllerId: "controller_test",
    controllerNonce: "A".repeat(32),
    targetId: "target_test",
    room: "private_room_abcdefgh",
    sessionId: "session_abcdefgh",
    secret: Buffer.alloc(32, 17).toString("base64url"),
    acceptedScopes: ["session.read"],
    expiresUnixMs: 1_700_000_010_000,
  };
  const envelope = makeBeaconEnvelope({
    type: "pairing.accept",
    senderId: "target_public_test",
    senderEpoch: 9,
    sequence: 2,
    body,
  });
  assert.deepEqual(decodeBeaconFrame(encodeBeaconFrame(envelope)), envelope);
  assert.throws(
    () => validateBeaconEnvelope({
      ...envelope,
      body: { ...body, secret: `${body.secret.slice(0, -1)}_` },
    }),
    /exactly 32 bytes/u,
  );
  assert.throws(
    () => validateBeaconEnvelope({
      ...envelope,
      body: { ...body, controllerUrl: "https://attacker.example" },
    }),
    /fields are invalid/u,
  );
});

test("decoder rejects empty, invalid UTF-8, and non-JSON public frames", () => {
  assert.throws(() => decodeBeaconFrame(""), /1-2048 UTF-8 bytes/u);
  assert.throws(() => decodeBeaconFrame(Uint8Array.of(0xc3, 0x28)), /valid UTF-8 JSON/u);
  assert.throws(() => decodeBeaconFrame("not-json"), /valid UTF-8 JSON/u);
});
