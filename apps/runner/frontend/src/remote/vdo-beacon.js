import { randomEpoch, randomToken } from "browser-remote-sync-protocol/src/brsp.js";

import {
  BEACON_MAX_BYTES,
  decodeBeaconFrame,
  encodeBeaconFrame,
  makeBeaconEnvelope,
} from "./beacon-contract.js";

export const PPS_PUBLIC_BEACON_ROOM = "pps_kit_public_beacon_v1";
export const PPS_PUBLIC_BEACON_NAMESPACE_KEY = "pps-kit-public-beacon-v1-public-namespace";
export const PPS_PUBLIC_BEACON_SALT = "pps-kit-public-beacon-v1";
export const PPS_PUBLIC_BEACON_CHANNEL = "pps_beacon_control_v1";
export const PPS_PUBLIC_BEACON_STREAM_PREFIX = "pps_beacon_target_";
export const PPS_PUBLIC_BEACON_MAX_TARGETS = 32;
export const PPS_PUBLIC_BEACON_MAX_PEERS = 8;
export const PPS_PUBLIC_BEACON_MAX_PENDING_REQUESTS = 3;

const RELIABLE_BACKLOG_MAX_BYTES = 32_768;
const REQUEST_RATE_MAX = 4;
const REQUEST_RATE_WINDOW_MS = 60_000;
const REQUEST_TTL_MS = 60_000;
const PRIVATE_OFFER_MAX_LIFETIME_MS = 120_000;
const PRIVATE_ROOM_PREFIX = "brsp_private_";
const CONSUMED_REQUEST_LIMIT = 64;
const SAFE_STREAM = /^[A-Za-z0-9_]{8,96}$/u;
const SAFE_PEER = /^[A-Za-z0-9_-]{1,128}$/u;
const CONTROL_CHARACTERS = /[\p{Cc}\p{Cf}\p{Cs}]/gu;

function detailEvent(type, detail) {
  const event = new Event(type);
  Object.defineProperty(event, "detail", { value: detail, enumerable: true });
  return event;
}

function defaultSdkFactory(options) {
  if (typeof globalThis.VDONinjaSDK !== "function") {
    throw new Error("The pinned VDO.Ninja SDK has not been loaded.");
  }
  return new globalThis.VDONinjaSDK(options);
}

function sanitizeLabel(value, fallback) {
  const normalized = String(value ?? "").replace(CONTROL_CHARACTERS, " ").trim().slice(0, 64);
  return normalized || fallback;
}

function normalizeChannelLabel(value) {
  const label = String(value ?? "");
  return label.startsWith("x-") ? label.slice(2) : label;
}

function normalizeSource(value) {
  const streamId = String(value?.streamID ?? value?.streamId ?? (typeof value === "string" ? value : ""));
  const peerKey = String(value?.UUID ?? value?.uuid ?? "");
  if (!streamId.startsWith(PPS_PUBLIC_BEACON_STREAM_PREFIX) || !SAFE_STREAM.test(streamId)) return null;
  if (peerKey && !SAFE_PEER.test(peerKey)) return null;
  return Object.freeze({
    streamId,
    peerKey,
    label: sanitizeLabel(value?.label ?? value?.streamLabel ?? value?.name, "Unverified PPS target"),
  });
}

function openChannel(channel) {
  return channel?.readyState === "open";
}

function newerSequence(candidate, previous) {
  if (previous === null || previous === undefined) return true;
  const distance = ((candidate >>> 0) - (previous >>> 0)) >>> 0;
  return distance > 0 && distance < 0x8000_0000;
}

function sortedScopes(value) {
  if (!Array.isArray(value)) throw new TypeError("Scopes must be an array.");
  return [...new Set(value)].sort();
}

function isSubset(values, available) {
  const permitted = new Set(available);
  return values.every((value) => permitted.has(value));
}

function cloneOffer(offer) {
  return {
    targetId: offer.targetId,
    room: offer.room,
    sessionId: offer.sessionId,
    secret: offer.secret,
    acceptedScopes: [...offer.acceptedScopes],
    expiresUnixMs: offer.expiresUnixMs,
  };
}

function privateRoom(randomTokenFn) {
  return `${PRIVATE_ROOM_PREFIX}${randomTokenFn(18)}`.replace(/[^A-Za-z0-9_]/gu, "_");
}

function validateApproval(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)
    || (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null)) {
    throw new TypeError("Pairing approval must be a plain object.");
  }
  const expected = value.sessionId === undefined
    ? ["acceptedScopes", "expiresUnixMs", "targetId"]
    : ["acceptedScopes", "expiresUnixMs", "sessionId", "targetId"];
  const keys = Reflect.ownKeys(value).sort();
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])
    || keys.some((key) => typeof key !== "string" || !descriptors[key].enumerable || !("value" in descriptors[key]))) {
    throw new TypeError("Pairing approval fields are invalid.");
  }
  return value;
}

export class PpsPublicBeacon extends EventTarget {
  constructor({
    role,
    label,
    sdkFactory = defaultSdkFactory,
    now = () => Date.now(),
    randomTokenFn = randomToken,
    randomEpochFn = randomEpoch,
    forceTurn = false,
  }) {
    super();
    if (role !== "controller" && role !== "target") throw new TypeError("Beacon role must be controller or target.");
    if (typeof sdkFactory !== "function" || typeof now !== "function"
      || typeof randomTokenFn !== "function" || typeof randomEpochFn !== "function") {
      throw new TypeError("Beacon dependencies must be functions.");
    }
    this.role = role;
    this.label = sanitizeLabel(label, role === "target" ? "PPS browser target" : "PPS browser controller");
    this.sdkFactory = sdkFactory;
    this.now = now;
    this.randomToken = randomTokenFn;
    this.randomEpoch = randomEpochFn;
    this.forceTurn = Boolean(forceTurn);

    this.phase = "idle";
    this.sdk = null;
    this.listeners = [];
    this.lifecycleGeneration = 0;
    this.stopPromise = null;
    this.senderId = "";
    this.senderEpoch = 0;
    this.sequence = 0;
    this.streamId = "";

    this.sources = new Map();
    this.selectedStreamId = "";
    this.selectedPeerKey = "";
    this.selectedChannel = null;
    this.targetPeers = new Map();
    this.openingPeers = new Set();
    this.pendingRequests = new Map();
    this.controllerRequests = new Map();
    this.privateOffers = new Map();
    this.consumedRequestIds = new Set();
    this.consumedRequestOrder = [];
  }

  snapshot() {
    return {
      phase: this.phase,
      role: this.role,
      room: PPS_PUBLIC_BEACON_ROOM,
      senderId: this.senderId,
      streamId: this.streamId,
      selectedStreamId: this.selectedStreamId,
      targets: this.targets(),
      pendingRequestCount: this.pendingRequests.size,
      outstandingRequestCount: this.controllerRequests.size,
      privateOfferCount: this.privateOffers.size,
      forceTurnRequested: this.forceTurn,
    };
  }

  targets() {
    return [...this.sources.values()].map((source) => ({ ...source }));
  }

  pendingPairingRequests() {
    this.pruneExpiredRequests();
    return [...this.pendingRequests.values()].map((request) => ({
      requestId: request.requestId,
      controllerId: request.controllerId,
      label: request.label,
      requestedScopes: [...request.requestedScopes],
      receivedUnixMs: request.receivedUnixMs,
    }));
  }

  emitStatus(message, error = false) {
    this.dispatchEvent(detailEvent("status", { ...this.snapshot(), message, error }));
  }

  initializeIdentity() {
    this.senderId = `${this.role}_${this.randomToken(12)}`;
    this.senderEpoch = this.randomEpoch() >>> 0;
    this.sequence = 0;
    this.streamId = this.role === "target"
      ? `${PPS_PUBLIC_BEACON_STREAM_PREFIX}${this.randomToken(12)}`.replace(/[^A-Za-z0-9_]/gu, "_")
      : "";
  }

  nextSequence() {
    const sequence = this.sequence;
    this.sequence = (this.sequence + 1) >>> 0;
    return sequence;
  }

  isCurrentSdk(sdk, generation) {
    return this.sdk === sdk && this.lifecycleGeneration === generation && this.phase !== "stopping";
  }

  listen(sdk, generation, type, handler) {
    const guarded = (event) => {
      if (this.isCurrentSdk(sdk, generation)) handler(event);
    };
    sdk.addEventListener(type, guarded);
    this.listeners.push([sdk, type, guarded]);
  }

  removeListeners(sdk) {
    const retained = [];
    for (const [listenerSdk, type, handler] of this.listeners) {
      if (listenerSdk !== sdk) {
        retained.push([listenerSdk, type, handler]);
        continue;
      }
      try { listenerSdk.removeEventListener(type, handler); } catch { /* best-effort SDK cleanup */ }
    }
    this.listeners = retained;
  }

  installSdkListeners(sdk, generation) {
    this.listen(sdk, generation, "listing", (event) => this.addListing(event.detail));
    this.listen(sdk, generation, "videoaddedtoroom", (event) => this.addSource(event.detail));
    this.listen(sdk, generation, "userLeft", (event) => this.removePeerOrSource(event.detail));
    this.listen(sdk, generation, "dataChannelOpen", (event) => {
      if (this.role === "target") void this.openTargetChannel(event.detail?.uuid);
    });
    this.listen(sdk, generation, "channelOpen", (event) => {
      if (this.role === "controller") this.acceptControllerChannel(event.detail);
    });
    this.listen(sdk, generation, "dataChannelClose", (event) => this.closePeer(
      String(event.detail?.uuid ?? ""),
      "Public beacon data channel closed.",
    ));
    this.listen(sdk, generation, "connectionFailed", (event) => this.closePeer(
      String(event.detail?.uuid ?? ""),
      "Public beacon peer connection failed.",
    ));
    this.listen(sdk, generation, "error", (event) => {
      const message = event.detail?.error?.message ?? event.detail?.message ?? "VDO.Ninja public beacon error.";
      this.emitStatus(String(message).slice(0, 256), true);
    });
  }

  async startBrowsing() {
    if (this.role !== "controller") throw new Error("Only a controller can browse the public beacon.");
    return this.start("browsing");
  }

  async startAdvertising() {
    if (this.role !== "target") throw new Error("Only a target can advertise on the public beacon.");
    return this.start("advertising");
  }

  async start(readyPhase) {
    if (!new Set(["idle", "closed", "error"]).has(this.phase)) {
      throw new Error("The public beacon is already active.");
    }
    const generation = ++this.lifecycleGeneration;
    this.stopPromise = null;
    this.resetSessionState();
    this.initializeIdentity();
    this.phase = "connecting";
    this.emitStatus("Connecting to the explicitly requested public discovery beacon.");
    let sdk;
    try {
      sdk = this.sdkFactory({
        password: PPS_PUBLIC_BEACON_NAMESPACE_KEY,
        salt: PPS_PUBLIC_BEACON_SALT,
        forceTURN: this.forceTurn,
      });
      this.sdk = sdk;
      this.installSdkListeners(sdk, generation);
      await sdk.connect();
      if (!this.isCurrentSdk(sdk, generation)) return this.snapshot();
      await sdk.joinRoom({
        room: PPS_PUBLIC_BEACON_ROOM,
        password: PPS_PUBLIC_BEACON_NAMESPACE_KEY,
      });
      if (!this.isCurrentSdk(sdk, generation)) return this.snapshot();
      if (this.role === "target") {
        await sdk.announce({ streamID: this.streamId, label: this.label });
        if (!this.isCurrentSdk(sdk, generation)) return this.snapshot();
      }
      this.phase = readyPhase;
      this.emitStatus(this.role === "target"
        ? "Target is publicly discoverable; every request still needs local approval."
        : "Public target listings are available; select one explicitly before requesting access.");
      return this.snapshot();
    } catch (error) {
      const currentLifecycle = this.lifecycleGeneration === generation && this.phase !== "stopping";
      if (!currentLifecycle || (sdk && this.sdk !== sdk)) return this.snapshot();
      this.removeListeners(sdk);
      this.resetSessionState();
      this.phase = "error";
      this.emitStatus(error instanceof Error ? error.message : String(error), true);
      await this.stopSdk(sdk);
      throw error;
    }
  }

  addListing(detail) {
    if (this.role !== "controller") return;
    if (Array.isArray(detail?.list)) detail.list.forEach((source) => this.addSource(source));
    else this.addSource(detail);
  }

  addSource(value) {
    if (this.role !== "controller") return false;
    const source = normalizeSource(value);
    if (!source) return false;
    if (!this.sources.has(source.streamId) && this.sources.size >= PPS_PUBLIC_BEACON_MAX_TARGETS) {
      this.dispatchEvent(detailEvent("targetlimit", { maximum: PPS_PUBLIC_BEACON_MAX_TARGETS }));
      return false;
    }
    this.sources.set(source.streamId, source);
    this.dispatchEvent(detailEvent("targetschange", { targets: this.targets() }));
    return true;
  }

  async selectTarget(streamId) {
    if (this.role !== "controller" || this.phase !== "browsing") {
      throw new Error("Start browsing before selecting a public target.");
    }
    if (this.selectedStreamId) throw new Error("Stop before selecting a different public target.");
    const source = this.sources.get(String(streamId));
    if (!source) throw new Error("The selected public target is not present in the bounded listing.");
    const sdk = this.sdk;
    const generation = this.lifecycleGeneration;
    this.selectedStreamId = source.streamId;
    this.selectedPeerKey = source.peerKey;
    this.phase = "connecting-peer";
    try {
      await sdk.view(source.streamId, {
        audio: false,
        video: false,
        downloads: false,
        allowresources: false,
        label: this.label,
      });
      if (!this.isCurrentSdk(sdk, generation)) return this.snapshot();
      this.dispatchEvent(detailEvent("targetselected", { ...source }));
      return this.snapshot();
    } catch (error) {
      if (this.isCurrentSdk(sdk, generation)) {
        const channel = this.selectedChannel;
        this.selectedChannel = null;
        this.selectedStreamId = "";
        this.selectedPeerKey = "";
        this.controllerRequests.clear();
        this.privateOffers.clear();
        this.phase = "browsing";
        try { channel?.close(); } catch { /* partially opened channel */ }
      }
      throw error;
    }
  }

  async openTargetChannel(peerKeyValue) {
    const peerKey = String(peerKeyValue ?? "");
    if (!SAFE_PEER.test(peerKey) || this.openingPeers.has(peerKey) || this.targetPeers.has(peerKey)) return;
    if (this.targetPeers.size + this.openingPeers.size >= PPS_PUBLIC_BEACON_MAX_PEERS) {
      this.dispatchEvent(detailEvent("peerlimit", { maximum: PPS_PUBLIC_BEACON_MAX_PEERS }));
      return;
    }
    const sdk = this.sdk;
    const generation = this.lifecycleGeneration;
    this.openingPeers.add(peerKey);
    try {
      const channel = await sdk.openChannel(peerKey, PPS_PUBLIC_BEACON_CHANNEL, { ordered: true });
      if (!this.isCurrentSdk(sdk, generation)) {
        try { channel?.close(); } catch { /* stale channel */ }
        return;
      }
      if (!this.attachTargetChannel(peerKey, channel)) {
        try { channel?.close(); } catch { /* invalid channel */ }
      }
    } catch (error) {
      if (this.isCurrentSdk(sdk, generation)) {
        this.emitStatus(error instanceof Error ? error.message : String(error), true);
      }
    } finally {
      this.openingPeers.delete(peerKey);
    }
  }

  attachTargetChannel(peerKey, channel) {
    if (!openChannel(channel) || normalizeChannelLabel(channel.label) !== PPS_PUBLIC_BEACON_CHANNEL) return false;
    const previous = this.targetPeers.get(peerKey);
    const peer = {
      peerKey,
      channel,
      controllerId: "",
      controllerEpoch: null,
      lastSequence: null,
      rateStartedAt: this.now(),
      rateCount: 0,
    };
    this.targetPeers.set(peerKey, peer);
    try { previous?.channel?.close(); } catch { /* superseded channel */ }
    channel.addEventListener("message", (event) => {
      if (this.targetPeers.get(peerKey)?.channel !== channel) return;
      void this.receiveTargetFrame(peer, event.data);
    });
    channel.addEventListener("close", () => {
      if (this.targetPeers.get(peerKey)?.channel === channel) this.closePeer(peerKey, "Public controller left.");
    }, { once: true });
    this.dispatchEvent(detailEvent("peeropen", { peerKey, role: "controller" }));
    return true;
  }

  acceptControllerChannel(detail = {}) {
    if (normalizeChannelLabel(detail.label) !== PPS_PUBLIC_BEACON_CHANNEL || !openChannel(detail.channel)
      || normalizeChannelLabel(detail.channel.label) !== PPS_PUBLIC_BEACON_CHANNEL) return;
    const peerKey = String(detail.uuid ?? "");
    if (!SAFE_PEER.test(peerKey) || !this.selectedStreamId) return;
    if (detail.streamID && detail.streamID !== this.selectedStreamId) return;
    if (this.selectedPeerKey && peerKey !== this.selectedPeerKey) return;
    if (!this.selectedPeerKey && !detail.streamID) return;
    const previous = this.selectedChannel;
    this.selectedPeerKey = peerKey;
    this.selectedChannel = detail.channel;
    try { previous?.close(); } catch { /* superseded channel */ }
    this.phase = "peer-open";
    const channel = detail.channel;
    channel.addEventListener("message", (event) => {
      if (this.selectedChannel !== channel || this.selectedPeerKey !== peerKey) return;
      void this.receiveControllerFrame(peerKey, event.data);
    });
    channel.addEventListener("close", () => {
      if (this.selectedChannel === channel) this.closePeer(peerKey, "Public target left.");
    }, { once: true });
    this.dispatchEvent(detailEvent("peeropen", { peerKey, role: "target" }));
  }

  sendFrame(channel, envelope) {
    if (!openChannel(channel)) return false;
    const encoded = encodeBeaconFrame(envelope);
    const byteLength = new TextEncoder().encode(encoded).byteLength;
    const bufferedAmount = Number(channel.bufferedAmount);
    if (byteLength > BEACON_MAX_BYTES || !Number.isFinite(bufferedAmount) || bufferedAmount < 0
      || bufferedAmount + byteLength > RELIABLE_BACKLOG_MAX_BYTES) {
      return false;
    }
    try {
      channel.send(encoded);
      return true;
    } catch {
      return false;
    }
  }

  requestPairing({ requestedScopes, label = this.label } = {}) {
    if (this.role !== "controller" || this.phase !== "peer-open" || !this.selectedChannel) {
      throw new Error("Select and open a public target before requesting private access.");
    }
    if (this.controllerRequests.size > 0) throw new Error("A pairing request is already pending.");
    const requestId = `request_${this.randomToken(12)}`;
    const controllerNonce = this.randomToken(24);
    const sortedRequestedScopes = sortedScopes(requestedScopes);
    const envelope = makeBeaconEnvelope({
      type: "pairing.request",
      senderId: this.senderId,
      senderEpoch: this.senderEpoch,
      sequence: this.nextSequence(),
      body: {
        requestId,
        controllerNonce,
        label: sanitizeLabel(label, "PPS browser controller"),
        requestedScopes: sortedRequestedScopes,
      },
    });
    const request = {
      requestId,
      controllerNonce,
      requestedScopes: sortedRequestedScopes,
      peerKey: this.selectedPeerKey,
      createdUnixMs: this.now(),
    };
    this.controllerRequests.set(requestId, request);
    if (!this.sendFrame(this.selectedChannel, envelope)) {
      this.controllerRequests.delete(requestId);
      throw new Error("The public beacon reliable queue is unavailable.");
    }
    this.dispatchEvent(detailEvent("pairingrequested", {
      requestId,
      requestedScopes: [...sortedRequestedScopes],
    }));
    return requestId;
  }

  cancelPairing(requestId) {
    if (this.role !== "controller") throw new Error("Only a controller can cancel its pairing request.");
    const request = this.controllerRequests.get(requestId);
    if (!request) return false;
    const envelope = makeBeaconEnvelope({
      type: "pairing.cancel",
      senderId: this.senderId,
      senderEpoch: this.senderEpoch,
      sequence: this.nextSequence(),
      body: {
        requestId: request.requestId,
        controllerId: this.senderId,
        controllerNonce: request.controllerNonce,
      },
    });
    this.sendFrame(this.selectedChannel, envelope);
    this.controllerRequests.delete(requestId);
    this.dispatchEvent(detailEvent("pairingcancelled", { requestId, source: "local" }));
    return true;
  }

  requestWithinRate(peer) {
    const now = this.now();
    if (now - peer.rateStartedAt >= REQUEST_RATE_WINDOW_MS) {
      peer.rateStartedAt = now;
      peer.rateCount = 0;
    }
    peer.rateCount += 1;
    return peer.rateCount <= REQUEST_RATE_MAX;
  }

  validPeerEnvelope(peer, envelope) {
    if (!peer.controllerId) {
      peer.controllerId = envelope.senderId;
      peer.controllerEpoch = envelope.senderEpoch;
    }
    if (peer.controllerId !== envelope.senderId || peer.controllerEpoch !== envelope.senderEpoch) return false;
    if (!newerSequence(envelope.sequence, peer.lastSequence)) return false;
    peer.lastSequence = envelope.sequence;
    return true;
  }

  async receiveTargetFrame(peer, data) {
    let envelope;
    try {
      envelope = decodeBeaconFrame(data);
    } catch (error) {
      this.dispatchEvent(detailEvent("protocolerror", {
        peerKey: peer.peerKey,
        message: error instanceof Error ? error.message : String(error),
      }));
      return;
    }
    if (!new Set(["pairing.request", "pairing.cancel"]).has(envelope.type) || !this.validPeerEnvelope(peer, envelope)) {
      this.dispatchEvent(detailEvent("protocolerror", {
        peerKey: peer.peerKey,
        message: "Public controller frame direction, identity, epoch, or sequence was rejected.",
      }));
      return;
    }
    this.pruneExpiredRequests();
    if (envelope.type === "pairing.cancel") {
      const request = this.pendingRequests.get(envelope.body.requestId);
      if (!request || request.peerKey !== peer.peerKey || request.controllerId !== envelope.body.controllerId
        || request.controllerNonce !== envelope.body.controllerNonce) return;
      this.pendingRequests.delete(request.requestId);
      this.rememberConsumed(request.requestId);
      this.dispatchEvent(detailEvent("pairingcancelled", { requestId: request.requestId, source: "remote" }));
      return;
    }

    const { requestId, controllerNonce, label, requestedScopes } = envelope.body;
    if (this.pendingRequests.has(requestId) || this.consumedRequestIds.has(requestId)) {
      this.dispatchEvent(detailEvent("protocolerror", {
        peerKey: peer.peerKey,
        message: "Duplicate or replayed public pairing request was rejected.",
      }));
      return;
    }
    if (!this.requestWithinRate(peer)) {
      this.sendDirectRejection(peer, envelope, "rate_limited");
      this.rememberConsumed(requestId);
      return;
    }
    if (this.pendingRequests.size >= PPS_PUBLIC_BEACON_MAX_PENDING_REQUESTS) {
      this.sendDirectRejection(peer, envelope, "target_busy");
      this.rememberConsumed(requestId);
      return;
    }
    const request = {
      requestId,
      peerKey: peer.peerKey,
      controllerId: envelope.senderId,
      controllerNonce,
      label,
      requestedScopes: [...requestedScopes],
      receivedUnixMs: this.now(),
    };
    this.pendingRequests.set(requestId, request);
    this.dispatchEvent(detailEvent("pairingrequest", {
      requestId,
      controllerId: request.controllerId,
      label: request.label,
      requestedScopes: [...request.requestedScopes],
      receivedUnixMs: request.receivedUnixMs,
    }));
  }

  sendDirectRejection(peer, requestEnvelope, reason) {
    const response = makeBeaconEnvelope({
      type: "pairing.reject",
      senderId: this.senderId,
      senderEpoch: this.senderEpoch,
      sequence: this.nextSequence(),
      body: {
        requestId: requestEnvelope.body.requestId,
        controllerId: requestEnvelope.senderId,
        controllerNonce: requestEnvelope.body.controllerNonce,
        reason,
      },
    });
    this.sendFrame(peer.channel, response);
  }

  approvePairing(requestId, approvalValue) {
    if (this.role !== "target") throw new Error("Only a target can approve a pairing request.");
    this.pruneExpiredRequests();
    const request = this.pendingRequests.get(requestId);
    if (!request) throw new Error("The pairing request is missing, expired, or already consumed.");
    const approval = validateApproval(approvalValue);
    const acceptedScopes = sortedScopes(approval.acceptedScopes);
    if (!isSubset(acceptedScopes, request.requestedScopes)) {
      throw new TypeError("Approved scopes must be a subset of the controller request.");
    }
    const expiresUnixMs = Number(approval.expiresUnixMs);
    const now = this.now();
    if (!Number.isSafeInteger(expiresUnixMs) || expiresUnixMs <= now
      || expiresUnixMs - now > PRIVATE_OFFER_MAX_LIFETIME_MS) {
      throw new TypeError("Private pairing offers must expire within two minutes.");
    }
    const room = privateRoom(this.randomToken);
    const privateOffer = {
      targetId: approval.targetId,
      room,
      sessionId: approval.sessionId ?? room,
      secret: this.randomToken(32),
      acceptedScopes,
      expiresUnixMs,
    };
    const envelope = makeBeaconEnvelope({
      type: "pairing.accept",
      senderId: this.senderId,
      senderEpoch: this.senderEpoch,
      sequence: this.nextSequence(),
      body: {
        requestId: request.requestId,
        controllerId: request.controllerId,
        controllerNonce: request.controllerNonce,
        ...privateOffer,
      },
    });
    const peer = this.targetPeers.get(request.peerKey);
    if (!peer || !this.sendFrame(peer.channel, envelope)) {
      throw new Error("The approved controller's reliable discovery channel is unavailable.");
    }
    this.pendingRequests.delete(requestId);
    this.rememberConsumed(requestId);
    this.dispatchEvent(detailEvent("pairingapproved", {
      requestId,
      controllerId: request.controllerId,
      acceptedScopes: [...acceptedScopes],
      expiresUnixMs,
    }));
    return cloneOffer(privateOffer);
  }

  rejectPairing(requestId, reason = "target_denied") {
    if (this.role !== "target") throw new Error("Only a target can reject a pairing request.");
    this.pruneExpiredRequests();
    const request = this.pendingRequests.get(requestId);
    if (!request) return false;
    const peer = this.targetPeers.get(request.peerKey);
    const envelope = makeBeaconEnvelope({
      type: "pairing.reject",
      senderId: this.senderId,
      senderEpoch: this.senderEpoch,
      sequence: this.nextSequence(),
      body: {
        requestId: request.requestId,
        controllerId: request.controllerId,
        controllerNonce: request.controllerNonce,
        reason,
      },
    });
    this.sendFrame(peer?.channel, envelope);
    this.pendingRequests.delete(requestId);
    this.rememberConsumed(requestId);
    this.dispatchEvent(detailEvent("pairingrejected", { requestId, reason, source: "local" }));
    return true;
  }

  async receiveControllerFrame(peerKey, data) {
    let envelope;
    try {
      envelope = decodeBeaconFrame(data);
    } catch (error) {
      this.dispatchEvent(detailEvent("protocolerror", {
        peerKey,
        message: error instanceof Error ? error.message : String(error),
      }));
      return;
    }
    if (!new Set(["pairing.accept", "pairing.reject"]).has(envelope.type)) return;
    const request = this.controllerRequests.get(envelope.body.requestId);
    if (!request || request.peerKey !== peerKey || envelope.body.controllerId !== this.senderId
      || envelope.body.controllerNonce !== request.controllerNonce) return;
    if (!this.remoteTargetId) {
      this.remoteTargetId = envelope.senderId;
      this.remoteTargetEpoch = envelope.senderEpoch;
      this.remoteTargetSequence = null;
    }
    if (this.remoteTargetId !== envelope.senderId || this.remoteTargetEpoch !== envelope.senderEpoch
      || !newerSequence(envelope.sequence, this.remoteTargetSequence)) return;
    this.remoteTargetSequence = envelope.sequence;

    this.controllerRequests.delete(request.requestId);
    if (envelope.type === "pairing.reject") {
      this.rememberConsumed(request.requestId);
      this.dispatchEvent(detailEvent("pairingrejected", {
        requestId: request.requestId,
        reason: envelope.body.reason,
        source: "remote",
      }));
      return;
    }
    const now = this.now();
    if (envelope.body.expiresUnixMs <= now || envelope.body.expiresUnixMs - now > PRIVATE_OFFER_MAX_LIFETIME_MS
      || !isSubset(envelope.body.acceptedScopes, request.requestedScopes)) {
      this.rememberConsumed(request.requestId);
      this.dispatchEvent(detailEvent("protocolerror", {
        peerKey,
        message: "Private pairing offer is expired or exceeds the requested scopes.",
      }));
      return;
    }
    this.privateOffers.set(request.requestId, {
      targetId: envelope.body.targetId,
      room: envelope.body.room,
      sessionId: envelope.body.sessionId,
      secret: envelope.body.secret,
      acceptedScopes: [...envelope.body.acceptedScopes],
      expiresUnixMs: envelope.body.expiresUnixMs,
    });
    this.rememberConsumed(request.requestId);
    this.dispatchEvent(detailEvent("pairingoffer", {
      requestId: request.requestId,
      targetId: envelope.body.targetId,
      acceptedScopes: [...envelope.body.acceptedScopes],
      expiresUnixMs: envelope.body.expiresUnixMs,
    }));
  }

  takePrivateOffer(requestId) {
    const offer = this.privateOffers.get(requestId);
    if (!offer) return null;
    this.privateOffers.delete(requestId);
    if (offer.expiresUnixMs <= this.now()) return null;
    return cloneOffer(offer);
  }

  rememberConsumed(requestId) {
    if (this.consumedRequestIds.has(requestId)) return;
    this.consumedRequestIds.add(requestId);
    this.consumedRequestOrder.push(requestId);
    while (this.consumedRequestOrder.length > CONSUMED_REQUEST_LIMIT) {
      this.consumedRequestIds.delete(this.consumedRequestOrder.shift());
    }
  }

  pruneExpiredRequests() {
    const cutoff = this.now() - REQUEST_TTL_MS;
    for (const [requestId, request] of this.pendingRequests) {
      if (request.receivedUnixMs > cutoff) continue;
      this.pendingRequests.delete(requestId);
      this.rememberConsumed(requestId);
      this.dispatchEvent(detailEvent("pairingrejected", {
        requestId,
        reason: "request_expired",
        source: "target",
      }));
    }
  }

  removePeerOrSource(detail = {}) {
    const identifier = String(detail.UUID ?? detail.uuid ?? detail.streamID ?? detail.streamId ?? "");
    if (!identifier) return;
    const peersToClose = new Set();
    let listingChanged = false;
    for (const [streamId, source] of this.sources) {
      if (streamId !== identifier && source.peerKey !== identifier) continue;
      this.sources.delete(streamId);
      listingChanged = true;
      if (source.peerKey) peersToClose.add(source.peerKey);
    }
    if (this.targetPeers.has(identifier) || this.selectedPeerKey === identifier) peersToClose.add(identifier);
    if (this.selectedStreamId === identifier && this.selectedPeerKey) peersToClose.add(this.selectedPeerKey);
    if (listingChanged) this.dispatchEvent(detailEvent("targetschange", { targets: this.targets() }));
    for (const peerKey of peersToClose) this.closePeer(peerKey, "Public beacon peer left.");
  }

  closePeer(peerKey, reason) {
    if (!peerKey) return;
    let closed = false;
    const targetPeer = this.targetPeers.get(peerKey);
    if (targetPeer) {
      this.targetPeers.delete(peerKey);
      closed = true;
      for (const [requestId, request] of this.pendingRequests) {
        if (request.peerKey !== peerKey) continue;
        this.pendingRequests.delete(requestId);
        this.rememberConsumed(requestId);
      }
      try { targetPeer.channel?.close(); } catch { /* already closed */ }
    }
    if (this.selectedPeerKey === peerKey) {
      const channel = this.selectedChannel;
      this.selectedChannel = null;
      this.selectedPeerKey = "";
      this.selectedStreamId = "";
      this.controllerRequests.clear();
      this.privateOffers.clear();
      this.remoteTargetId = "";
      this.remoteTargetEpoch = null;
      this.remoteTargetSequence = null;
      closed = true;
      if (this.phase !== "stopping" && this.phase !== "closed") this.phase = "browsing";
      try { channel?.close(); } catch { /* already closed */ }
    }
    if (closed) this.dispatchEvent(detailEvent("peerclose", { peerKey, reason }));
  }

  resetSessionState() {
    const channels = [this.selectedChannel, ...[...this.targetPeers.values()].map((peer) => peer.channel)];
    this.sources.clear();
    this.selectedStreamId = "";
    this.selectedPeerKey = "";
    this.selectedChannel = null;
    this.targetPeers.clear();
    this.openingPeers.clear();
    this.pendingRequests.clear();
    this.controllerRequests.clear();
    this.privateOffers.clear();
    this.consumedRequestIds.clear();
    this.consumedRequestOrder = [];
    this.remoteTargetId = "";
    this.remoteTargetEpoch = null;
    this.remoteTargetSequence = null;
    for (const channel of channels) {
      try { channel?.close(); } catch { /* best-effort channel cleanup */ }
    }
  }

  async stopSdk(sdk) {
    if (this.sdk === sdk) this.sdk = null;
    if (!sdk) return;
    try { await sdk.disconnect?.(); } catch { /* signaling may already be gone */ }
  }

  stop() {
    if (this.stopPromise) return this.stopPromise;
    if (this.phase === "idle" || this.phase === "closed") return Promise.resolve(this.snapshot());
    this.stopPromise = this.performStop();
    return this.stopPromise;
  }

  async performStop() {
    ++this.lifecycleGeneration;
    this.phase = "stopping";
    const sdk = this.sdk;
    if (sdk) this.removeListeners(sdk);
    this.resetSessionState();
    await this.stopSdk(sdk);
    this.senderId = "";
    this.senderEpoch = 0;
    this.sequence = 0;
    this.streamId = "";
    this.phase = "closed";
    this.emitStatus("Public beacon stopped and private offer material cleared.");
    return this.snapshot();
  }
}
