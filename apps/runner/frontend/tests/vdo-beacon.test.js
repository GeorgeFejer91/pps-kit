import assert from "node:assert/strict";
import test from "node:test";

import { decodeBeaconFrame, encodeBeaconFrame, makeBeaconEnvelope } from "../src/remote/beacon-contract.js";
import {
  PPS_PUBLIC_BEACON_CHANNEL,
  PPS_PUBLIC_BEACON_MAX_PEERS,
  PPS_PUBLIC_BEACON_MAX_PENDING_REQUESTS,
  PPS_PUBLIC_BEACON_MAX_TARGETS,
  PPS_PUBLIC_BEACON_NAMESPACE_KEY,
  PPS_PUBLIC_BEACON_ROOM,
  PPS_PUBLIC_BEACON_SALT,
  PpsPublicBeacon,
} from "../src/remote/vdo-beacon.js";

function detailEvent(type, detail) {
  const event = new Event(type);
  Object.defineProperty(event, "detail", { value: detail });
  return event;
}

function messageEvent(data) {
  const event = new Event("message");
  Object.defineProperty(event, "data", { value: data });
  return event;
}

class MockChannel extends EventTarget {
  constructor(label = PPS_PUBLIC_BEACON_CHANNEL) {
    super();
    this.label = `x-${label}`;
    this.readyState = "open";
    this.bufferedAmount = 0;
    this.sent = [];
  }

  send(data) {
    if (this.readyState !== "open") throw new Error("Channel is closed.");
    this.sent.push(data);
  }

  receive(data) {
    this.dispatchEvent(messageEvent(data));
  }

  close() {
    if (this.readyState === "closed") return;
    this.readyState = "closed";
    this.dispatchEvent(new Event("close"));
  }
}

class MockSdk extends EventTarget {
  constructor({ listing = [], connect = null } = {}) {
    super();
    this.listing = listing;
    this.connectImplementation = connect;
    this.calls = [];
    this.channels = [];
  }

  async connect() {
    this.calls.push(["connect"]);
    if (this.connectImplementation) await this.connectImplementation();
  }

  async joinRoom(options) {
    this.calls.push(["joinRoom", options]);
    if (this.listing.length > 0) {
      this.dispatchEvent(detailEvent("listing", { list: this.listing }));
    }
  }

  async announce(options) { this.calls.push(["announce", options]); }

  async view(streamId, options) { this.calls.push(["view", streamId, options]); }

  async openChannel(peerKey, label, options) {
    this.calls.push(["openChannel", peerKey, label, options]);
    const channel = new MockChannel(label);
    this.channels.push(channel);
    return channel;
  }

  async disconnect() { this.calls.push(["disconnect"]); }
}

function tokenSource(prefix = "T") {
  let counter = 0;
  return (byteLength) => {
    counter += 1;
    const length = Math.ceil((byteLength * 4) / 3);
    return `${prefix}${String(counter).padStart(4, "0")}${"A".repeat(64)}`.slice(0, length);
  };
}

function beaconOptions(role, sdk, now = () => 1_700_000_000_000) {
  return {
    role,
    label: role === "target" ? "Browser target" : "Browser controller",
    sdkFactory: () => sdk,
    now,
    randomEpochFn: () => 41,
    randomTokenFn: tokenSource(role === "target" ? "T" : "C"),
  };
}

async function settleMicrotasks(turns = 8) {
  for (let turn = 0; turn < turns; turn += 1) await Promise.resolve();
}

function publicTarget(index) {
  return {
    streamID: `pps_beacon_target_${String(index).padStart(4, "0")}`,
    UUID: `target-peer-${index}`,
    label: index === 0 ? "Target\u0000 zero" : `Target ${index}`,
  };
}

function pairingRequest({ sequence, requestId, senderId = "controller_public_test", senderEpoch = 3 }) {
  return makeBeaconEnvelope({
    type: "pairing.request",
    senderId,
    senderEpoch,
    sequence,
    body: {
      requestId,
      controllerNonce: "N".repeat(32),
      label: "Study controller",
      requestedScopes: ["session.read", "session.transport"],
    },
  });
}

test("construction is inert and browsing bounds listings without auto-viewing", async () => {
  const listing = Array.from({ length: PPS_PUBLIC_BEACON_MAX_TARGETS + 8 }, (_unused, index) => publicTarget(index));
  const sdk = new MockSdk({ listing });
  let constructions = 0;
  const beacon = new PpsPublicBeacon({
    ...beaconOptions("controller", sdk),
    sdkFactory: (options) => {
      constructions += 1;
      assert.deepEqual(options, {
        password: PPS_PUBLIC_BEACON_NAMESPACE_KEY,
        salt: PPS_PUBLIC_BEACON_SALT,
        forceTURN: false,
      });
      return sdk;
    },
  });

  assert.equal(constructions, 0);
  assert.equal(beacon.snapshot().phase, "idle");
  assert.deepEqual(beacon.targets(), []);
  await beacon.stop();
  assert.equal(constructions, 0, "even an idle stop creates no network object");
  await assert.rejects(() => beacon.startAdvertising(), /Only a target/u);
  await beacon.startBrowsing();
  assert.equal(constructions, 1);
  assert.equal(beacon.snapshot().phase, "browsing");
  assert.equal(beacon.targets().length, PPS_PUBLIC_BEACON_MAX_TARGETS);
  assert.equal(beacon.targets()[0].label, "Target  zero");
  assert.deepEqual(sdk.calls.filter(([name]) => name === "view"), []);
  assert.deepEqual(sdk.calls.find(([name]) => name === "joinRoom")[1], {
    room: PPS_PUBLIC_BEACON_ROOM,
    password: PPS_PUBLIC_BEACON_NAMESPACE_KEY,
  });

  await beacon.stop();
  assert.equal(beacon.snapshot().phase, "closed");
  assert.equal(sdk.calls.filter(([name]) => name === "disconnect").length, 1);
});

test("selection binds the exact target peer and accepts only the reliable data-only channel", async () => {
  const source = publicTarget(7);
  const sdk = new MockSdk({ listing: [source] });
  const beacon = new PpsPublicBeacon(beaconOptions("controller", sdk));
  await beacon.startBrowsing();
  await beacon.selectTarget(source.streamID);
  assert.deepEqual(sdk.calls.find(([name]) => name === "view").slice(1), [
    source.streamID,
    {
      audio: false,
      video: false,
      downloads: false,
      allowresources: false,
      label: "Browser controller",
    },
  ]);

  const wrongPeer = new MockChannel();
  sdk.dispatchEvent(detailEvent("channelOpen", {
    uuid: "attacker-peer",
    streamID: source.streamID,
    label: `x-${PPS_PUBLIC_BEACON_CHANNEL}`,
    channel: wrongPeer,
  }));
  const wrongLabel = new MockChannel("wrong_channel");
  sdk.dispatchEvent(detailEvent("channelOpen", {
    uuid: source.UUID,
    streamID: source.streamID,
    label: wrongLabel.label,
    channel: wrongLabel,
  }));
  assert.equal(beacon.snapshot().phase, "connecting-peer");

  const channel = new MockChannel();
  sdk.dispatchEvent(detailEvent("channelOpen", {
    uuid: source.UUID,
    streamID: source.streamID,
    label: channel.label,
    channel,
  }));
  assert.equal(beacon.snapshot().phase, "peer-open");
  channel.close();
  assert.equal(beacon.snapshot().phase, "browsing");
  assert.equal(beacon.snapshot().selectedStreamId, "");
  await beacon.stop();
});

test("advertising opens one ordered public channel per bounded peer only after explicit activation", async () => {
  const sdk = new MockSdk();
  let constructions = 0;
  const beacon = new PpsPublicBeacon({
    ...beaconOptions("target", sdk),
    sdkFactory: () => {
      constructions += 1;
      return sdk;
    },
  });
  assert.equal(constructions, 0);
  await assert.rejects(() => beacon.startBrowsing(), /Only a controller/u);
  await beacon.startAdvertising();
  assert.equal(constructions, 1);
  const announced = sdk.calls.find(([name]) => name === "announce");
  assert.equal(announced[1].streamID.startsWith("pps_beacon_target_"), true);

  sdk.dispatchEvent(detailEvent("dataChannelOpen", { uuid: "controller-peer" }));
  await settleMicrotasks();
  assert.deepEqual(sdk.calls.find(([name]) => name === "openChannel").slice(1), [
    "controller-peer",
    PPS_PUBLIC_BEACON_CHANNEL,
    { ordered: true },
  ]);
  sdk.dispatchEvent(detailEvent("dataChannelOpen", { uuid: "controller-peer" }));
  await settleMicrotasks();
  assert.equal(sdk.calls.filter(([name]) => name === "openChannel").length, 1);
  for (let index = 1; index < PPS_PUBLIC_BEACON_MAX_PEERS + 3; index += 1) {
    sdk.dispatchEvent(detailEvent("dataChannelOpen", { uuid: `controller-peer-${index}` }));
  }
  await settleMicrotasks();
  assert.equal(sdk.calls.filter(([name]) => name === "openChannel").length, PPS_PUBLIC_BEACON_MAX_PEERS);
  await beacon.stop();
  assert(sdk.channels.every((channel) => channel.readyState === "closed"));
});

test("a target emits private pairing material only after local approval and the controller event redacts it", async () => {
  const now = 1_700_000_000_000;
  const targetSdk = new MockSdk();
  const target = new PpsPublicBeacon(beaconOptions("target", targetSdk, () => now));
  await target.startAdvertising();
  targetSdk.dispatchEvent(detailEvent("dataChannelOpen", { uuid: "controller-peer" }));
  await settleMicrotasks();
  const targetChannel = targetSdk.channels[0];

  const source = { streamID: target.streamId, UUID: "target-peer", label: "Browser target" };
  const controllerSdk = new MockSdk({ listing: [source] });
  const controller = new PpsPublicBeacon(beaconOptions("controller", controllerSdk, () => now));
  await controller.startBrowsing();
  await controller.selectTarget(source.streamID);
  const controllerChannel = new MockChannel();
  controllerSdk.dispatchEvent(detailEvent("channelOpen", {
    uuid: source.UUID,
    streamID: source.streamID,
    label: controllerChannel.label,
    channel: controllerChannel,
  }));

  const requestId = controller.requestPairing({
    requestedScopes: ["session.transport", "session.read"],
  });
  targetChannel.receive(controllerChannel.sent[0]);
  await settleMicrotasks();
  assert.equal(target.pendingPairingRequests().length, 1);
  assert.equal(targetChannel.sent.length, 0, "receiving a request cannot auto-accept it");

  const approval = {
    targetId: "phone_target_test",
    acceptedScopes: ["session.read"],
    expiresUnixMs: now + 60_000,
  };
  assert.throws(
    () => target.approvePairing(requestId, { ...approval, acceptedScopes: ["session.admin"] }),
    /subset/u,
  );
  assert.throws(
    () => target.approvePairing(requestId, { ...approval, secret: "caller_supplied_material" }),
    /fields are invalid/u,
  );
  const offer = target.approvePairing(requestId, {
    ...approval,
    sessionId: "desktop_native_session_01",
  });
  const secret = offer.secret;
  assert.equal(offer.room.startsWith("brsp_private_"), true);
  assert.equal(offer.sessionId, "desktop_native_session_01");
  assert.equal(secret.length, 43);
  assert.equal(targetChannel.sent.length, 1);
  assert.equal(decodeBeaconFrame(targetChannel.sent[0]).type, "pairing.accept");

  let eventDetail;
  controller.addEventListener("pairingoffer", (event) => { eventDetail = event.detail; }, { once: true });
  controllerChannel.receive(targetChannel.sent[0]);
  await settleMicrotasks();
  assert.equal(Object.hasOwn(eventDetail, "secret"), false);
  assert.equal(JSON.stringify(eventDetail).includes(secret), false);
  assert.deepEqual(controller.takePrivateOffer(requestId), {
    targetId: offer.targetId,
    room: offer.room,
    sessionId: offer.sessionId,
    secret,
    acceptedScopes: ["session.read"],
    expiresUnixMs: offer.expiresUnixMs,
  });
  assert.equal(controller.takePrivateOffer(requestId), null, "private offers are one-shot");

  const secondRequestId = controller.requestPairing({ requestedScopes: ["session.read"] });
  targetChannel.receive(controllerChannel.sent.at(-1));
  await settleMicrotasks();
  const secondOffer = target.approvePairing(secondRequestId, approval);
  assert.notEqual(secondOffer.room, offer.room);
  assert.notEqual(secondOffer.secret, offer.secret);
  assert.equal(secondOffer.sessionId, secondOffer.room, "browser targets default the BRSP session to the private room");
  controllerChannel.receive(targetChannel.sent.at(-1));
  await settleMicrotasks();
  assert.equal(controller.snapshot().privateOfferCount, 1);
  await controller.stop();
  assert.equal(controller.snapshot().privateOfferCount, 0);
  assert.equal(controller.takePrivateOffer(secondRequestId), null, "stop destroys untaken private material");
  await target.stop();
});

test("target request handling enforces replay, identity, pending, and per-peer rate caps", async () => {
  const sdk = new MockSdk();
  const target = new PpsPublicBeacon(beaconOptions("target", sdk));
  await target.startAdvertising();
  sdk.dispatchEvent(detailEvent("dataChannelOpen", { uuid: "controller-peer" }));
  await settleMicrotasks();
  const channel = sdk.channels[0];
  let protocolErrors = 0;
  target.addEventListener("protocolerror", () => { protocolErrors += 1; });

  for (let index = 0; index < 5; index += 1) {
    channel.receive(encodeBeaconFrame(pairingRequest({
      sequence: index,
      requestId: `request_${String(index).padStart(8, "0")}`,
    })));
    await settleMicrotasks();
  }
  assert.equal(target.pendingPairingRequests().length, PPS_PUBLIC_BEACON_MAX_PENDING_REQUESTS);
  assert.deepEqual(channel.sent.map((frame) => decodeBeaconFrame(frame).body.reason), [
    "target_busy",
    "rate_limited",
  ]);

  channel.receive(encodeBeaconFrame(pairingRequest({ sequence: 4, requestId: "request_00000004" })));
  await settleMicrotasks();
  assert.equal(channel.sent.length, 2, "a replay does not receive a second response");
  channel.receive(encodeBeaconFrame(pairingRequest({
    sequence: 5,
    requestId: "request_99999999",
    senderId: "different_controller",
  })));
  await settleMicrotasks();
  assert(protocolErrors >= 2);
  assert.equal(target.pendingPairingRequests().length, PPS_PUBLIC_BEACON_MAX_PENDING_REQUESTS);
  await target.stop();
});

test("stop wins an in-flight start and clears channels, requests, and private material", async () => {
  let resolveConnect;
  const sdk = new MockSdk({
    connect: () => new Promise((resolve) => { resolveConnect = resolve; }),
  });
  const beacon = new PpsPublicBeacon(beaconOptions("target", sdk));
  const starting = beacon.startAdvertising();
  await settleMicrotasks();
  assert.equal(beacon.snapshot().phase, "connecting");
  const stopping = beacon.stop();
  resolveConnect();
  await Promise.all([starting, stopping]);
  assert.equal(beacon.snapshot().phase, "closed");
  assert.equal(beacon.snapshot().pendingRequestCount, 0);
  assert.equal(beacon.snapshot().privateOfferCount, 0);
  assert.equal(sdk.calls.some(([name]) => name === "announce"), false);
  assert.equal(sdk.calls.filter(([name]) => name === "disconnect").length, 1);
});

test("SDK construction failure is reported without leaving a half-started beacon", async () => {
  const beacon = new PpsPublicBeacon({
    ...beaconOptions("controller", new MockSdk()),
    sdkFactory: () => { throw new Error("factory unavailable"); },
  });
  await assert.rejects(() => beacon.startBrowsing(), /factory unavailable/u);
  assert.equal(beacon.snapshot().phase, "error");
  assert.equal(beacon.sdk, null);
  await beacon.stop();
  assert.equal(beacon.snapshot().phase, "closed");
});
