import { DEFAULT_REMOTE_SCOPES } from "../domain/runner-contract.js";

const TOKEN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/u;
const BASE64URL_SECRET = /^[A-Za-z0-9_-]{43}$/u;
const ROOM = /^[A-Za-z0-9_-]{8,64}$/u;
const COMMON_KEYS = new Set(["mode", "transport", "target_id", "session_id", "secret", "scopes"]);

function assertToken(value, label) {
  if (typeof value !== "string" || !TOKEN.test(value)) throw new TypeError(`${label} is invalid.`);
  return value;
}

function assertRoom(value) {
  if (typeof value !== "string" || !ROOM.test(value)) throw new TypeError("room is invalid.");
  return value;
}

export function parseInvitation(href) {
  const url = new URL(href);
  for (const key of url.searchParams.keys()) {
    if (key.toLowerCase() === "secret") throw new TypeError("Pairing secrets are forbidden in URL queries.");
  }
  const fragment = new URLSearchParams(url.hash.slice(1));
  if (fragment.size === 0) return null;

  const transport = fragment.get("transport");
  const allowedKeys = new Set(COMMON_KEYS);
  if (transport === "relay" || transport === "vdo") allowedKeys.add("room");
  for (const key of fragment.keys()) {
    if (!allowedKeys.has(key)) throw new TypeError(`Unknown invitation field: ${key}.`);
    if (fragment.getAll(key).length !== 1) throw new TypeError(`Invitation field ${key} is duplicated.`);
  }

  if (transport !== "desktop" && transport !== "relay" && transport !== "vdo") {
    throw new TypeError("Unknown invitation transport.");
  }
  if (fragment.get("mode") !== "controller") throw new TypeError("Invitation mode must be controller.");
  const secret = fragment.get("secret") || "";
  if (!BASE64URL_SECRET.test(secret)) throw new TypeError("Invitation pairing secret is invalid.");
  const targetId = assertToken(fragment.get("target_id") || "", "target_id");
  const sessionId = assertToken(fragment.get("session_id") || "", "session_id");
  const room = transport === "relay" || transport === "vdo"
    ? assertRoom(fragment.get("room") || "")
    : null;
  const requestedScopes = (fragment.get("scopes") || DEFAULT_REMOTE_SCOPES.join(","))
    .split(",")
    .map((scope) => scope.trim())
    .filter(Boolean);
  if (requestedScopes.length === 0 || requestedScopes.length > 16 || new Set(requestedScopes).size !== requestedScopes.length) {
    throw new TypeError("Invitation scopes are invalid or duplicated.");
  }
  requestedScopes.forEach((scope) => assertToken(scope, "scope"));

  return {
    mode: "controller",
    transport,
    targetId,
    sessionId,
    room,
    secret,
    requestedScopes: [...new Set(requestedScopes)].sort(),
  };
}

export function createRelayInvitation({ pageUrl, room, targetId, secret, scopes = DEFAULT_REMOTE_SCOPES }) {
  assertRoom(room);
  assertToken(targetId, "target_id");
  if (!BASE64URL_SECRET.test(secret)) throw new TypeError("Pairing secret is invalid.");
  const url = new URL(pageUrl);
  url.search = "";
  const fragment = new URLSearchParams({
    mode: "controller",
    transport: "relay",
    room,
    target_id: targetId,
    session_id: room,
    secret,
    scopes: [...new Set(scopes)].sort().join(","),
  });
  url.hash = fragment.toString();
  return url.toString();
}

export function createVdoInvitation({ pageUrl, room, targetId, secret, scopes = DEFAULT_REMOTE_SCOPES }) {
  assertRoom(room);
  assertToken(targetId, "target_id");
  if (!BASE64URL_SECRET.test(secret)) throw new TypeError("Pairing secret is invalid.");
  const url = new URL(pageUrl);
  url.search = "";
  const fragment = new URLSearchParams({
    mode: "controller",
    transport: "vdo",
    room,
    target_id: targetId,
    session_id: room,
    secret,
    scopes: [...new Set(scopes)].sort().join(","),
  });
  url.hash = fragment.toString();
  return url.toString();
}

export function webSocketUrl({ locationUrl, transport, room, role = "controller" }) {
  const url = new URL(locationUrl);
  const protocol = url.protocol === "https:" ? "wss:" : "ws:";
  if (transport === "desktop") return `${protocol}//${url.host}/ws/desktop`;
  if (transport === "vdo") throw new TypeError("VDO invitations use a WebRTC transport, not a WebSocket URL.");
  assertRoom(room);
  if (role !== "controller" && role !== "target") throw new TypeError("Relay role is invalid.");
  return `${protocol}//${url.host}/ws/relay/${encodeURIComponent(room)}/${role}`;
}

export function sanitizedInvitationLocation(href) {
  const url = new URL(href);
  for (const key of [...url.searchParams.keys()]) {
    if (key.toLowerCase() === "secret") url.searchParams.delete(key);
  }
  url.hash = "";
  return `${url.pathname}${url.search}`;
}

export function stripInvitationMaterial() {
  if (!globalThis.history || !globalThis.location) return;
  history.replaceState(null, "", sanitizedInvitationLocation(location.href));
}
