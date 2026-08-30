import {
  BRSP_CONTROL_MAX_BYTES,
  BRSP_CONTROL_TYPES,
  BRSP_STATE_MAX_BYTES,
  BRSP_STATE_TYPES,
  decodeEnvelope,
  encodeEnvelope,
  makeEnvelope,
  randomEpoch,
  randomToken,
  validateHelloBody,
} from "browser-remote-sync-protocol/src/brsp.js";

import { MAX_CONTROL_BYTES, PROTOCOL, PROTOCOL_VERSION } from "../domain/runner-contract.js";

const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", { fatal: true });
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/u;
const BASE64URL = /^[A-Za-z0-9_-]+$/u;
const CONTROL_TYPES = new Set(BRSP_CONTROL_TYPES);
const STATE_TYPES = new Set(BRSP_STATE_TYPES);

if (BRSP_CONTROL_MAX_BYTES !== MAX_CONTROL_BYTES || PROTOCOL !== "brsp" || PROTOCOL_VERSION !== 1) {
  throw new Error("Pinned BRSP/1 constants do not match the PPS profile.");
}

function isPlainObject(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function exactKeys(value, keys, label) {
  if (!isPlainObject(value)) throw new TypeError(`${label} must be a plain object.`);
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new TypeError(`${label} fields are invalid.`);
  }
}

function token(value, label, minimum = 1, maximum = 96) {
  if (typeof value !== "string" || value.length < minimum || value.length > maximum || !TOKEN.test(value)) {
    throw new TypeError(`${label} must be a bounded protocol token.`);
  }
}

function uint(value, label, maximum = Number.MAX_SAFE_INTEGER) {
  if (!Number.isInteger(value) || value < 0 || value > maximum) {
    throw new TypeError(`${label} must be a bounded non-negative integer.`);
  }
}

function tokenArray(value, label) {
  if (!Array.isArray(value) || value.length > 32) throw new TypeError(`${label} must be a bounded array.`);
  value.forEach((entry) => token(entry, label, 1, 64));
  if (new Set(value).size !== value.length) throw new TypeError(`${label} must not contain duplicates.`);
}

function jsonValue(value, label = "value", depth = 0) {
  if (depth > 8) throw new TypeError(`${label} exceeds the BRSP depth limit.`);
  if (value === null || typeof value === "string" || typeof value === "boolean") return;
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError(`${label} contains a non-finite number.`);
    return;
  }
  if (Array.isArray(value)) {
    if (value.length > 256) throw new TypeError(`${label} exceeds the BRSP array limit.`);
    value.forEach((entry, index) => jsonValue(entry, `${label}[${index}]`, depth + 1));
    return;
  }
  if (!isPlainObject(value)) throw new TypeError(`${label} must contain plain JSON data.`);
  const fields = Object.keys(value);
  if (fields.length > 128) throw new TypeError(`${label} exceeds the BRSP object-field limit.`);
  for (const key of fields) {
    if (!key || key.length > 96 || ["__proto__", "prototype", "constructor"].includes(key)) {
      throw new TypeError(`${label} contains an unsafe field.`);
    }
    jsonValue(value[key], `${label}.${key}`, depth + 1);
  }
}

function validateBody(envelope) {
  const { body, type } = envelope;
  switch (type) {
    case "hello":
      validateHelloBody(body);
      break;
    case "proof":
      exactKeys(body, ["algorithm", "role", "value"], "proof body");
      if (body.algorithm !== "HMAC-SHA-256" || !["target", "controller"].includes(body.role)
        || typeof body.value !== "string" || !BASE64URL.test(body.value)) {
        throw new TypeError("Proof body is invalid.");
      }
      break;
    case "ready":
      exactKeys(body, ["capabilities", "acceptedScopes"], "ready body");
      tokenArray(body.capabilities, "ready capabilities");
      tokenArray(body.acceptedScopes, "ready scopes");
      break;
    case "command":
      exactKeys(body, ["commandId", "scope", "action", "args", "expectedRevision"], "command body");
      token(body.commandId, "commandId", 8);
      token(body.scope, "command scope", 1, 64);
      token(body.action, "command action", 1, 64);
      if (body.expectedRevision !== null) uint(body.expectedRevision, "expectedRevision");
      jsonValue(body.args, "command args");
      break;
    case "applied":
      exactKeys(body, ["commandId", "ok", "revision", "result", "error"], "applied body");
      token(body.commandId, "commandId", 8);
      if (typeof body.ok !== "boolean") throw new TypeError("applied ok must be boolean.");
      uint(body.revision, "applied revision");
      jsonValue(body.result, "applied result");
      if (body.error !== null) token(body.error, "applied error", 1, 64);
      break;
    case "snapshot":
    case "state":
      exactKeys(body, ["revision", "state"], `${type} body`);
      uint(body.revision, `${type} revision`);
      jsonValue(body.state, `${type} state`);
      break;
    case "snapshot-request":
    case "bye":
      exactKeys(body, [], `${type} body`);
      break;
    case "intent":
      exactKeys(body, ["scope", "controls"], "intent body");
      token(body.scope, "intent scope", 1, 64);
      jsonValue(body.controls, "intent controls");
      break;
    case "error":
      exactKeys(body, ["code", "message"], "error body");
      token(body.code, "error code", 1, 64);
      if (typeof body.message !== "string" || body.message.length > 256) throw new TypeError("error message is invalid.");
      break;
    default:
      throw new TypeError(`Unknown BRSP message type: ${type}.`);
  }
  return envelope;
}

function bytes(value) {
  if (typeof value === "string") return encoder.encode(value);
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  throw new TypeError("BRSP frame must be UTF-8 text or bytes.");
}

function relayMetadata(value) {
  if (value.kind === "relay.peer") {
    exactKeys(value, ["kind", "role", "present"], "relay.peer");
    if (!["target", "controller"].includes(value.role) || typeof value.present !== "boolean") {
      throw new TypeError("relay.peer fields are invalid.");
    }
    return value;
  }
  if (value.kind === "relay.error") {
    exactKeys(value, ["kind", "code", "message"], "relay.error");
    token(value.code, "relay error code", 1, 64);
    if (typeof value.message !== "string" || value.message.length > 256) throw new TypeError("relay error message is invalid.");
    return value;
  }
  return undefined;
}

export function parseControlFrame(value) {
  const encoded = bytes(value);
  if (encoded.byteLength === 0 || encoded.byteLength > BRSP_CONTROL_MAX_BYTES) {
    throw new TypeError("BRSP frame has an invalid byte length.");
  }
  let parsed;
  try {
    parsed = JSON.parse(decoder.decode(encoded));
  } catch {
    throw new TypeError("BRSP frame is not valid UTF-8 JSON.");
  }
  if (isPlainObject(parsed) && typeof parsed.kind === "string") {
    const metadata = relayMetadata(parsed);
    if (metadata) return metadata;
  }
  const lane = STATE_TYPES.has(parsed?.type) ? "state" : "control";
  const envelope = decodeEnvelope(encoded, { lane });
  if (!envelope) throw new TypeError("Malformed, oversized, or unsupported BRSP/1 envelope.");
  return validateBody(envelope);
}

export function encodeControlMessage(message) {
  if (message?.kind === "relay.peer" || message?.kind === "relay.error") {
    relayMetadata(message);
    return JSON.stringify(message);
  }
  validateBody(message);
  return encodeEnvelope(message, { lane: STATE_TYPES.has(message.type) ? "state" : "control" });
}

export function createProtocolIdentity(prefix) {
  return `${prefix}_${randomToken(12)}`;
}

export function createProtocolNonce() {
  return randomToken(24);
}

export function createProtocolEpoch() {
  return randomEpoch();
}

export function createPairingSecret() {
  return randomToken(32);
}

export { BRSP_CONTROL_MAX_BYTES, BRSP_STATE_MAX_BYTES, CONTROL_TYPES, STATE_TYPES, makeEnvelope };
