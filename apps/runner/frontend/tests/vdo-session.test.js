import assert from "node:assert/strict";
import test from "node:test";

import {
  VDO_BRSP_CONTROL_CHANNEL,
  VDO_BRSP_STATE_CHANNEL,
} from "browser-remote-sync-protocol/src/vdo-ninja-transport.js";

import { createPhoneExperimentSnapshot } from "../src/domain/phone-experiment-reducer.js";
import { BrspControllerSession, BrspTargetSession } from "../src/remote/websocket-session.js";
import { PpsVdoTransport } from "../src/remote/vdo-transport.js";

function detailEvent(type, detail) {
  const event = new Event(type);
  Object.defineProperty(event, "detail", { value: detail });
  return event;
}

class LinkedChannel extends EventTarget {
  constructor(label, options) {
    super();
    this.label = `x-${label}`;
    this.options = options;
    this.readyState = "open";
    this.bufferedAmount = 0;
    this.peer = null;
    this.messageListeners = 0;
    this.pendingMessages = [];
  }

  send(data) {
    queueMicrotask(() => this.peer?.receive(data));
  }

  addEventListener(type, listener, options) {
    super.addEventListener(type, listener, options);
    if (type !== "message") return;
    this.messageListeners += 1;
    const pending = this.pendingMessages.splice(0);
    pending.forEach((data) => queueMicrotask(() => this.receive(data)));
  }

  receive(data) {
    if (this.messageListeners === 0) {
      this.pendingMessages.push(data);
      return;
    }
    const event = new Event("message");
    Object.defineProperty(event, "data", { value: data });
    this.dispatchEvent(event);
  }

  close() {
    if (this.readyState === "closed") return;
    this.readyState = "closed";
    this.dispatchEvent(new Event("close"));
  }
}

class FakeVdoNetwork {
  constructor() {
    this.target = null;
    this.controller = null;
    this.streamId = "";
    this.targetOptions = null;
    this.controllerOptions = null;
    this.viewOptions = null;
  }

  sdkFactory(role) {
    return (options) => {
      if (role === "target") this.targetOptions = options;
      else this.controllerOptions = options;
      return new FakeVdoSdk(this, role);
    };
  }

  listing() {
    return this.streamId
      ? [{ streamID: this.streamId, UUID: "target-vdo-peer", label: "PPS test target" }]
      : [];
  }

  openTargetChannel(label, options) {
    const target = new LinkedChannel(label, options);
    const controller = new LinkedChannel(label, options);
    target.peer = controller;
    controller.peer = target;
    setTimeout(() => this.controller?.dispatchEvent(detailEvent("channelOpen", {
      uuid: "target-vdo-peer",
      streamID: this.streamId,
      label: `x-${label}`,
      channel: controller,
    })), 0);
    return target;
  }
}

class FakeVdoSdk extends EventTarget {
  constructor(network, role) {
    super();
    this.network = network;
    this.role = role;
    this.calls = [];
    network[role] = this;
  }

  async connect() { this.calls.push(["connect"]); }

  async joinRoom(options) {
    this.calls.push(["joinRoom", options]);
    if (this.role === "controller") {
      this.dispatchEvent(detailEvent("listing", { list: this.network.listing() }));
    }
  }

  async announce(options) {
    this.calls.push(["announce", options]);
    this.network.streamId = options.streamID;
  }

  async view(_streamId, options) {
    this.calls.push(["view", options]);
    this.network.viewOptions = options;
    queueMicrotask(() => this.network.target?.dispatchEvent(detailEvent("dataChannelOpen", {
      uuid: "controller-vdo-peer",
    })));
  }

  async openChannel(_peerKey, label, options) {
    this.calls.push(["openChannel", label, options]);
    return this.network.openTargetChannel(label, options);
  }

  async getPeerQuality() { return { relayed: false, rttMs: 12 }; }

  async disconnect() { this.calls.push(["disconnect"]); }
}

function eventOnce(target, type) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(
      `Timed out waiting for ${type}; phase=${target.phase}; error=${target.testError || "none"}; `
      + `connection=${JSON.stringify({
        phase: target.connection?.phase,
        peerKey: target.connection?.peerKey,
        remoteHello: target.connection?.remoteHello?.senderId,
        localProofSent: target.connection?.localProofSent,
        remoteProofValid: target.connection?.remoteProofValid,
        localReadySent: target.connection?.localReadySent,
        remoteReady: target.connection?.remoteReady,
      })}.`,
    )), 2_000);
    target.addEventListener(type, (event) => {
      clearTimeout(timeout);
      resolve(event);
    }, { once: true });
  });
}

test("private VDO transport stays inert until Connect and carries canonical BRSP authority", async (context) => {
  const network = new FakeVdoNetwork();
  const secret = Buffer.alloc(32, 17).toString("base64url");
  const room = "brsp_private_session_test";
  let snapshot = {
    ...createPhoneExperimentSnapshot({
      targetId: "phone-target-vdo",
      epoch: 41,
      clock: () => ({ unixMs: 1_700_000_000_000, monotonicNs: 42_000 }),
    }),
    allowed_actions: ["package.prepare_demo"],
  };
  const targetTransport = new PpsVdoTransport({
    role: "target",
    room,
    sharedSecret: secret,
    sdkFactory: network.sdkFactory("target"),
  });
  const controllerTransport = new PpsVdoTransport({
    role: "controller",
    room,
    sharedSecret: secret,
    sdkFactory: network.sdkFactory("controller"),
  });
  const target = new BrspTargetSession({
    transport: targetTransport,
    secret,
    targetId: snapshot.target_id,
    sessionId: room,
    availableScopes: ["session.read", "session.prepare"],
    actions: ["package.prepare_demo"],
    getSnapshot: () => snapshot,
    applyCommand: async (command) => {
      snapshot = { ...snapshot, revision: snapshot.revision + 1, package_verified: true };
      return {
        status: "accepted",
        reason: "applied",
        acceptedRevision: command.expected_revision,
        resultingRevision: snapshot.revision,
        snapshot,
      };
    },
  });
  const controller = new BrspControllerSession({
    transport: controllerTransport,
    secret,
    targetId: snapshot.target_id,
    sessionId: room,
    requestedScopes: ["session.read", "session.prepare"],
    controllerId: "controller-vdo-test",
  });
  target.addEventListener("protocolerror", (event) => { target.testError = event.detail.message; });
  controller.addEventListener("protocolerror", (event) => { controller.testError = event.detail.message; });
  context.after(async () => {
    await controller.connection.close();
    await target.connection.close();
  });

  assert.equal(network.target, null);
  assert.equal(network.controller, null);
  const targetReady = eventOnce(target, "ready");
  const controllerReady = eventOnce(controller, "ready");
  const initialSnapshot = eventOnce(controller, "snapshot");
  target.connect();
  await Promise.resolve();
  controller.connect();
  try {
    await Promise.all([targetReady, controllerReady]);
  } catch (error) {
    throw new Error(`${error.message} controller=${JSON.stringify({
      phase: controller.connection.phase,
      peerKey: controller.connection.peerKey,
      remoteHello: controller.connection.remoteHello?.senderId,
      localProofSent: controller.connection.localProofSent,
      remoteProofValid: controller.connection.remoteProofValid,
      localReadySent: controller.connection.localReadySent,
      remoteReady: controller.connection.remoteReady,
      error: controller.testError,
    })}`, { cause: error });
  }
  assert.equal((await initialSnapshot).detail.snapshot.package_verified, false);
  assert.deepEqual(network.viewOptions, {
    audio: false,
    video: false,
    downloads: false,
    allowresources: false,
    label: "BRSP controller",
  });
  assert.equal(network.targetOptions.password, secret);
  assert.equal(network.controllerOptions.password, secret);
  assert.deepEqual(
    network.target.calls.filter(([name]) => name === "openChannel").map(([, label, options]) => [label, options]),
    [
      [VDO_BRSP_CONTROL_CHANNEL, { ordered: true }],
      [VDO_BRSP_STATE_CHANNEL, { ordered: false, maxRetransmits: 0 }],
    ],
  );

  const applied = eventOnce(controller, "commandapplied");
  const returned = new Promise((resolve) => {
    const listener = (event) => {
      if (event.detail.snapshot.package_verified) {
        controller.removeEventListener("snapshot", listener);
        resolve(event);
      }
    };
    controller.addEventListener("snapshot", listener);
  });
  controller.sendCommand("package.prepare_demo");
  assert.equal((await applied).detail.status, "accepted");
  assert.equal((await returned).detail.snapshot.package_verified, true);
});
