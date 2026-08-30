const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });

export const BEACON_PROTOCOL = "pps.beacon";
export const BEACON_VERSION = 1;
export const BEACON_MAX_BYTES = 2_048;
export const BEACON_MAX_SCOPES = 16;
export const BEACON_TYPES = Object.freeze([
  "pairing.request",
  "pairing.accept",
  "pairing.reject",
  "pairing.cancel",
]);

const TYPE_SET = new Set(BEACON_TYPES);
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/u;
const ROOM = /^[A-Za-z0-9_]{8,96}$/u;
const BASE64URL = /^[A-Za-z0-9_-]+$/u;
const PRIVATE_SECRET = /^[A-Za-z0-9_-]{43}$/u;
const BASE64URL_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
const CONTROL_CHARACTERS = /[\p{Cc}\p{Cf}\p{Cs}]/u;

function isPlainObject(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function exactKeys(value, expectedKeys, label) {
  if (!isPlainObject(value)) throw new TypeError(`${label} must be a plain object.`);
  const actualKeys = Reflect.ownKeys(value);
  if (actualKeys.some((key) => typeof key !== "string")) {
    throw new TypeError(`${label} fields are invalid.`);
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (actualKeys.some((key) => !descriptors[key].enumerable || !("value" in descriptors[key]))) {
    throw new TypeError(`${label} fields must be enumerable data properties.`);
  }
  const actual = actualKeys.sort();
  const expected = [...expectedKeys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new TypeError(`${label} fields are invalid.`);
  }
}

function strictArray(value, label) {
  if (!Array.isArray(value) || Object.getPrototypeOf(value) !== Array.prototype) {
    throw new TypeError(`${label} must be an array.`);
  }
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const expectedKeys = Array.from({ length: value.length }, (_unused, index) => String(index));
  const actualKeys = Reflect.ownKeys(value).filter((key) => key !== "length");
  if (actualKeys.some((key) => typeof key !== "string")
    || actualKeys.length !== expectedKeys.length
    || actualKeys.some((key, index) => key !== expectedKeys[index])
    || expectedKeys.some((key) => !descriptors[key]?.enumerable || !("value" in descriptors[key]))) {
    throw new TypeError(`${label} must be a dense array of data properties.`);
  }
}

function token(value, label, minimum = 1, maximum = 96) {
  if (typeof value !== "string" || value.length < minimum || value.length > maximum || !TOKEN.test(value)) {
    throw new TypeError(`${label} must be a bounded protocol token.`);
  }
  return value;
}

function uint32(value, label) {
  if (!Number.isInteger(value) || value < 0 || value > 0xffff_ffff) {
    throw new TypeError(`${label} must be an unsigned 32-bit integer.`);
  }
  return value;
}

function safeInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new TypeError(`${label} must be a non-negative safe integer.`);
  }
  return value;
}

function nonce(value, label) {
  if (typeof value !== "string" || value.length < 20 || value.length > 64 || !BASE64URL.test(value)) {
    throw new TypeError(`${label} must be bounded base64url material.`);
  }
  return value;
}

function label(value) {
  if (typeof value !== "string" || value.length < 1 || value.length > 64
    || value.trim() !== value || CONTROL_CHARACTERS.test(value)) {
    throw new TypeError("controller label must be trimmed display-safe text of at most 64 characters.");
  }
  return value;
}

function scopes(value, field) {
  strictArray(value, field);
  if (value.length < 1 || value.length > BEACON_MAX_SCOPES) {
    throw new TypeError(`${field} must contain between 1 and ${BEACON_MAX_SCOPES} scopes.`);
  }
  value.forEach((scope) => token(scope, field, 1, 64));
  if (new Set(value).size !== value.length) throw new TypeError(`${field} must not contain duplicates.`);
  const sorted = [...value].sort();
  if (value.some((scope, index) => scope !== sorted[index])) {
    throw new TypeError(`${field} must be sorted.`);
  }
  return value;
}

function validateBody(type, body) {
  switch (type) {
    case "pairing.request":
      exactKeys(body, ["requestId", "controllerNonce", "label", "requestedScopes"], "pairing.request body");
      token(body.requestId, "requestId", 8);
      nonce(body.controllerNonce, "controllerNonce");
      label(body.label);
      scopes(body.requestedScopes, "requestedScopes");
      break;
    case "pairing.accept":
      exactKeys(
        body,
        [
          "requestId",
          "controllerId",
          "controllerNonce",
          "targetId",
          "room",
          "sessionId",
          "secret",
          "acceptedScopes",
          "expiresUnixMs",
        ],
        "pairing.accept body",
      );
      token(body.requestId, "requestId", 8);
      token(body.controllerId, "controllerId", 8);
      nonce(body.controllerNonce, "controllerNonce");
      token(body.targetId, "targetId", 8);
      if (typeof body.room !== "string" || !ROOM.test(body.room)) {
        throw new TypeError("room must be a bounded VDO.Ninja room token.");
      }
      token(body.sessionId, "sessionId", 8);
      if (typeof body.secret !== "string" || !PRIVATE_SECRET.test(body.secret)
        || BASE64URL_ALPHABET.indexOf(body.secret.at(-1)) % 4 !== 0) {
        throw new TypeError("secret must contain exactly 32 bytes of unpadded base64url material.");
      }
      scopes(body.acceptedScopes, "acceptedScopes");
      safeInteger(body.expiresUnixMs, "expiresUnixMs");
      break;
    case "pairing.reject":
      exactKeys(body, ["requestId", "controllerId", "controllerNonce", "reason"], "pairing.reject body");
      token(body.requestId, "requestId", 8);
      token(body.controllerId, "controllerId", 8);
      nonce(body.controllerNonce, "controllerNonce");
      token(body.reason, "reason", 1, 64);
      break;
    case "pairing.cancel":
      exactKeys(body, ["requestId", "controllerId", "controllerNonce"], "pairing.cancel body");
      token(body.requestId, "requestId", 8);
      token(body.controllerId, "controllerId", 8);
      nonce(body.controllerNonce, "controllerNonce");
      break;
    default:
      throw new TypeError("Unsupported public beacon frame type.");
  }
}

export function validateBeaconEnvelope(value) {
  exactKeys(
    value,
    ["protocol", "version", "type", "senderId", "senderEpoch", "sequence", "body"],
    "public beacon envelope",
  );
  if (value.protocol !== BEACON_PROTOCOL || value.version !== BEACON_VERSION || !TYPE_SET.has(value.type)) {
    throw new TypeError("Unsupported public beacon protocol, version, or type.");
  }
  token(value.senderId, "senderId", 8);
  uint32(value.senderEpoch, "senderEpoch");
  uint32(value.sequence, "sequence");
  validateBody(value.type, value.body);
  return value;
}

export function makeBeaconEnvelope({ type, senderId, senderEpoch, sequence, body }) {
  return validateBeaconEnvelope({
    protocol: BEACON_PROTOCOL,
    version: BEACON_VERSION,
    type,
    senderId,
    senderEpoch,
    sequence,
    body,
  });
}

function frameBytes(value) {
  if (typeof value === "string") return encoder.encode(value);
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  throw new TypeError("Public beacon frames must be UTF-8 text or bytes.");
}

export function encodeBeaconFrame(value) {
  const encoded = JSON.stringify(validateBeaconEnvelope(value));
  if (encoder.encode(encoded).byteLength > BEACON_MAX_BYTES) {
    throw new TypeError(`Public beacon frames must not exceed ${BEACON_MAX_BYTES} UTF-8 bytes.`);
  }
  return encoded;
}

export function decodeBeaconFrame(value) {
  const bytes = frameBytes(value);
  if (bytes.byteLength === 0 || bytes.byteLength > BEACON_MAX_BYTES) {
    throw new TypeError(`Public beacon frames must contain 1-${BEACON_MAX_BYTES} UTF-8 bytes.`);
  }
  let parsed;
  try {
    parsed = JSON.parse(decoder.decode(bytes));
  } catch {
    throw new TypeError("Public beacon frame is not valid UTF-8 JSON.");
  }
  return validateBeaconEnvelope(parsed);
}
