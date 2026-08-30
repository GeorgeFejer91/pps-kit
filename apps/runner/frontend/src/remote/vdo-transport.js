import {
  BRSP_CONTROL_MAX_BYTES,
  BRSP_STATE_MAX_BYTES,
} from "browser-remote-sync-protocol/src/brsp.js";
import {
  VdoNinjaTransport,
  generateVdoRoomId,
} from "browser-remote-sync-protocol/src/vdo-ninja-transport.js";

const encoder = new TextEncoder();
const PREOPEN_CONTROL_MAX_FRAMES = 4;

function detailEvent(type, detail) {
  const event = new Event(type);
  Object.defineProperty(event, "detail", { value: detail, enumerable: true });
  return event;
}

function byteLength(value) {
  if (typeof value === "string") return encoder.encode(value).byteLength;
  if (value instanceof ArrayBuffer) return value.byteLength;
  if (ArrayBuffer.isView(value)) return value.byteLength;
  return Infinity;
}

/**
 * Application wrapper around the pinned VDO.Ninja adapter.
 *
 * VDO can report the first data channel before its sibling channel. A remote
 * hello may therefore reach the adapter just before it emits `peeropen`.
 * BRSP deliberately ignores data from an unattached peer, so this wrapper
 * retains a very small bounded pre-open control queue and the newest state
 * frame, emits `peeropen`, then flushes them. It does not change BRSP bytes or
 * authenticate anything; the normal BRSP connection remains the authority.
 */
export class PpsVdoTransport extends EventTarget {
  constructor(options) {
    super();
    this.inner = new VdoNinjaTransport(options);
    this.openPeers = new Set();
    this.pendingControl = new Map();
    this.pendingState = new Map();
    this.listeners = [];
    for (const type of ["status", "quality"]) this.forward(type);
    this.listen("controlmessage", (event) => this.receiveBeforeOpen("control", event.detail));
    this.listen("statemessage", (event) => this.receiveBeforeOpen("state", event.detail));
    this.listen("peeropen", (event) => this.openPeer(event.detail));
    this.listen("peerclose", (event) => this.closeObservedPeer(event.detail));
  }

  listen(type, handler) {
    this.inner.addEventListener(type, handler);
    this.listeners.push([type, handler]);
  }

  forward(type) {
    this.listen(type, (event) => this.dispatchEvent(detailEvent(type, event.detail)));
  }

  receiveBeforeOpen(lane, detail = {}) {
    const { peerKey, data } = detail;
    const limit = lane === "control" ? BRSP_CONTROL_MAX_BYTES : BRSP_STATE_MAX_BYTES;
    if (!peerKey || byteLength(data) === 0 || byteLength(data) > limit) {
      if (peerKey) this.closePeer(peerKey);
      return;
    }
    if (this.openPeers.has(peerKey)) {
      this.dispatchEvent(detailEvent(`${lane}message`, detail));
      return;
    }
    if (lane === "state") {
      this.pendingState.set(peerKey, detail);
      return;
    }
    const pending = this.pendingControl.get(peerKey) ?? [];
    if (pending.length >= PREOPEN_CONTROL_MAX_FRAMES) {
      this.closePeer(peerKey);
      return;
    }
    pending.push(detail);
    this.pendingControl.set(peerKey, pending);
  }

  openPeer(detail = {}) {
    if (!detail.peerKey || this.openPeers.has(detail.peerKey)) return;
    this.openPeers.add(detail.peerKey);
    this.dispatchEvent(detailEvent("peeropen", detail));
    const controls = this.pendingControl.get(detail.peerKey) ?? [];
    this.pendingControl.delete(detail.peerKey);
    for (const frame of controls) this.dispatchEvent(detailEvent("controlmessage", frame));
    const state = this.pendingState.get(detail.peerKey);
    this.pendingState.delete(detail.peerKey);
    if (state) this.dispatchEvent(detailEvent("statemessage", state));
  }

  closeObservedPeer(detail = {}) {
    if (detail.peerKey) {
      this.openPeers.delete(detail.peerKey);
      this.pendingControl.delete(detail.peerKey);
      this.pendingState.delete(detail.peerKey);
    }
    this.dispatchEvent(detailEvent("peerclose", detail));
  }

  start() { return this.inner.start(); }

  snapshot() { return this.inner.snapshot(); }

  selectTarget(streamId) { return this.inner.selectTarget(streamId); }

  sendControl(peerKey, data) { return this.inner.sendControl(peerKey, data); }

  sendState(peerKey, data) { return this.inner.sendState(peerKey, data); }

  closePeer(peerKey) {
    this.openPeers.delete(peerKey);
    this.pendingControl.delete(peerKey);
    this.pendingState.delete(peerKey);
    return this.inner.closePeer(peerKey);
  }

  async stop() {
    this.openPeers.clear();
    this.pendingControl.clear();
    this.pendingState.clear();
    return this.inner.stop();
  }
}

export function createPpsVdoTransport(options) {
  return new PpsVdoTransport(options);
}

export { generateVdoRoomId };
