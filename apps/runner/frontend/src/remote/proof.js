import {
  canonicalStringify,
  createProofEnvelope,
  proofTranscript,
  verifyProofEnvelope,
} from "browser-remote-sync-protocol/src/brsp.js";
import { hmac } from "@noble/hashes/hmac";
import { sha256 } from "@noble/hashes/sha256";

const encoder = new TextEncoder();
const FALLBACK_KEY = Symbol("brsp-hmac-key");

function asBytes(value) {
  if (value instanceof Uint8Array) return new Uint8Array(value);
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  throw new TypeError("BRSP HMAC input must be bytes.");
}

function nobleHmacSubset() {
  return Object.freeze({
    async importKey(format, keyData, algorithm, extractable, usages) {
      if (format !== "raw" || algorithm?.name !== "HMAC" || algorithm?.hash !== "SHA-256"
        || extractable !== false || !Array.isArray(usages) || usages.length !== 1 || usages[0] !== "sign") {
        throw new TypeError("Only the BRSP HMAC-SHA-256 import profile is supported.");
      }
      return Object.freeze({ [FALLBACK_KEY]: asBytes(keyData) });
    },
    async sign(algorithm, key, data) {
      if (algorithm !== "HMAC" || !(key?.[FALLBACK_KEY] instanceof Uint8Array)) {
        throw new TypeError("Only BRSP HMAC signing is supported.");
      }
      const signature = hmac(sha256, key[FALLBACK_KEY], asBytes(data));
      return signature.buffer.slice(signature.byteOffset, signature.byteOffset + signature.byteLength);
    },
  });
}

/**
 * BRSP's upstream core uses Web Crypto. LAN HTTP pages still have secure random
 * bytes but may not expose `crypto.subtle`; install only the two HMAC operations
 * the normative proof needs, backed by the pinned noble implementation.
 */
export function installBrspProofCrypto(globalObject = globalThis) {
  const cryptoObject = globalObject.crypto;
  if (!cryptoObject || typeof cryptoObject.getRandomValues !== "function") {
    throw new Error("Cryptographically secure random bytes are unavailable.");
  }
  if (typeof cryptoObject.subtle?.importKey === "function" && typeof cryptoObject.subtle?.sign === "function") {
    return () => {};
  }
  const subset = nobleHmacSubset();
  const ownDescriptor = Object.getOwnPropertyDescriptor(cryptoObject, "subtle");
  try {
    Object.defineProperty(cryptoObject, "subtle", {
      configurable: true,
      enumerable: false,
      value: subset,
    });
    return () => {
      if (ownDescriptor) Object.defineProperty(cryptoObject, "subtle", ownDescriptor);
      else delete cryptoObject.subtle;
    };
  } catch {
    const globalDescriptor = Object.getOwnPropertyDescriptor(globalObject, "crypto");
    const replacement = Object.create(cryptoObject);
    Object.defineProperty(replacement, "subtle", { value: subset });
    Object.defineProperty(replacement, "getRandomValues", {
      value: cryptoObject.getRandomValues.bind(cryptoObject),
    });
    Object.defineProperty(globalObject, "crypto", {
      configurable: true,
      value: replacement,
    });
    return () => {
      if (globalDescriptor) Object.defineProperty(globalObject, "crypto", globalDescriptor);
      else delete globalObject.crypto;
    };
  }
}

export function proofMaterial({ localHello, remoteHello }) {
  const role = localHello?.body?.role;
  if (role !== "target" && role !== "controller") throw new TypeError("A proof requires a local hello role.");
  return `BRSP/1 proof\n${role}\n${proofTranscript(localHello, remoteHello)}`;
}

export async function createProofMac(secret, { localHello, remoteHello, sequence = 1 }) {
  const proof = await createProofEnvelope({ localHello, remoteHello, secret, sequence });
  return proof.body.value;
}

export function constantTimeEqual(left, right) {
  const a = encoder.encode(String(left));
  const b = encoder.encode(String(right));
  const length = Math.max(a.length, b.length);
  let difference = a.length ^ b.length;
  for (let index = 0; index < length; index += 1) {
    difference |= (a[index] ?? 0) ^ (b[index] ?? 0);
  }
  return difference === 0;
}

export { canonicalStringify, createProofEnvelope, proofTranscript, verifyProofEnvelope };
