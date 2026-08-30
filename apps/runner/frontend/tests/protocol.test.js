import assert from "node:assert/strict";
import test from "node:test";

import { createPhoneExperimentSnapshot } from "../src/domain/phone-experiment-reducer.js";
import { validateRunnerSnapshot } from "../src/domain/runner-contract.js";
import { parseInvitation } from "../src/remote/invitation.js";
import { encodeControlMessage, parseControlFrame } from "../src/remote/protocol.js";
import { BrspControllerSession, BrspTargetSession } from "../src/remote/websocket-session.js";

const hello = {
  protocol: "brsp",
  version: 1,
  type: "hello",
  sessionId: "session_abcdefgh",
  senderId: "target_abcdefgh",
  senderEpoch: 42,
  sequence: 0,
  body: {
    role: "target",
    nonce: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    capabilities: ["command-ack", "latest-state", "pps-runner-v1", "state-snapshot"],
    requestedScopes: [],
    grantedScopes: ["session.read", "session.transport"],
  },
};

test("protocol parser accepts the canonical envelope and distinct relay metadata", () => {
  assert.deepEqual(parseControlFrame(JSON.stringify(hello)), hello);
  assert.equal(parseControlFrame('{"kind":"relay.peer","role":"target","present":true}').kind, "relay.peer");
  assert.equal(parseControlFrame('{"kind":"relay.error","code":"room_full","message":"Room is full."}').kind, "relay.error");
});

test("protocol parser rejects wrong fields, uint32 overflow, unknown types, and oversized state", () => {
  assert.throws(() => parseControlFrame(JSON.stringify({ ...hello, surprise: true })), /Malformed/u);
  assert.throws(() => parseControlFrame(JSON.stringify({ ...hello, senderEpoch: 0x1_0000_0000 })), /Malformed/u);
  assert.throws(() => parseControlFrame(JSON.stringify({ ...hello, type: "lease.keepalive" })), /Malformed/u);
  const oversizedState = {
    ...hello,
    type: "state",
    sequence: 1,
    body: { revision: 1, state: { padding: "x".repeat(8_200) } },
  };
  assert.throws(() => encodeControlMessage(oversizedState), /8192/u);
});

test("proof parser accepts normative base64url and rejects non-canonical body fields", () => {
  const proof = {
    ...hello,
    type: "proof",
    sequence: 1,
    body: { algorithm: "HMAC-SHA-256", role: "target", value: "A".repeat(43) },
  };
  assert.deepEqual(parseControlFrame(JSON.stringify(proof)), proof);
  assert.throws(() => parseControlFrame(JSON.stringify({ ...proof, body: { ...proof.body, mac: "ab".repeat(32) } })), /fields are invalid/u);
});

test("invitation keeps the secret and session in a strict fragment", () => {
  const secret = "A".repeat(43);
  const value = `https://lab.example/companion/#mode=controller&transport=desktop&target_id=target-alpha&session_id=session-alpha&secret=${secret}&scopes=session.read%2Csession.transport`;
  const parsed = parseInvitation(value);
  assert.equal(parsed.secret, secret);
  assert.equal(parsed.sessionId, "session-alpha");
  assert.equal(parsed.transport, "desktop");
  assert.throws(() => parseInvitation(`https://lab.example/companion/?secret=${secret}#mode=controller`), /forbidden/u);
  assert.throws(() => parseInvitation(`${value}&secret=${secret}`), /duplicated/u);
  assert.throws(() => parseInvitation(`${value}&debug=true`), /Unknown invitation field/u);
});

test("session construction and invitation parsing never auto-connect", () => {
  let socketCount = 0;
  const socketFactory = () => {
    socketCount += 1;
    throw new Error("Socket creation is observable.");
  };
  const secret = "A".repeat(43);
  const session = new BrspControllerSession({
    url: "wss://lab.example/ws/desktop",
    secret,
    targetId: "target-alpha",
    sessionId: "session-alpha",
    requestedScopes: ["session.read"],
    socketFactory,
  });
  parseInvitation(`https://lab.example/companion/#mode=controller&transport=desktop&target_id=target-alpha&session_id=session-alpha&secret=${secret}&scopes=session.read`);
  assert.equal(session.phase, "idle");
  assert.equal(socketCount, 0);
  assert.throws(() => session.connect(), /observable/u);
  assert.equal(socketCount, 1);
});

test("PPS snapshots require the complete versioned application schema", () => {
  const snapshot = createPhoneExperimentSnapshot({
    targetId: "target-alpha",
    epoch: 7,
    clock: () => ({ unixMs: 1_700_000_000_000, monotonicNs: 123_000 }),
  });
  assert.equal(validateRunnerSnapshot(snapshot), snapshot);
  assert.throws(() => validateRunnerSnapshot({ ...snapshot, setup: { ready: false } }), /setup.*fields/u);
  assert.throws(() => validateRunnerSnapshot({ ...snapshot, protocol: "BRSP/1" }), /unsupported/u);
  assert.throws(() => validateRunnerSnapshot({
    ...snapshot,
    active_block: { ...snapshot.active_block, elapsed_s: Number.NaN },
  }), /finite/u);
});

class LinkedSocket extends EventTarget {
  constructor() {
    super();
    this.readyState = 0;
    this.bufferedAmount = 0;
    this.peer = null;
    this.sent = [];
  }

  send(data) {
    this.sent.push(data);
    const event = new Event("message");
    Object.defineProperty(event, "data", { value: data });
    queueMicrotask(() => this.peer.dispatchEvent(event));
  }

  close() {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.dispatchEvent(new Event("close"));
  }
}

function linkedSockets() {
  const controller = new LinkedSocket();
  const target = new LinkedSocket();
  controller.peer = target;
  target.peer = controller;
  return { controller, target };
}

function openLinked(sockets) {
  sockets.controller.readyState = 1;
  sockets.target.readyState = 1;
  sockets.controller.dispatchEvent(new Event("open"));
  sockets.target.dispatchEvent(new Event("open"));
}

function eventOnce(target, type) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Timed out waiting for ${type}; phase=${target.phase}.`)), 2_000);
    target.addEventListener(type, (event) => {
      clearTimeout(timeout);
      resolve(event);
    }, { once: true });
  });
}

async function settleMicrotasks(turns = 12) {
  for (let turn = 0; turn < turns; turn += 1) await Promise.resolve();
}

class ManualTimeouts {
  constructor() {
    this.time = 0;
    this.nextId = 1;
    this.pending = new Map();
  }

  now = () => this.time;

  setTimeout = (handler, delay) => {
    const id = this.nextId;
    this.nextId += 1;
    this.pending.set(id, { at: this.time + delay, handler });
    return id;
  };

  clearTimeout = (id) => this.pending.delete(id);

  advance(milliseconds) {
    const destination = this.time + milliseconds;
    while (true) {
      const next = [...this.pending.entries()]
        .filter(([, timer]) => timer.at <= destination)
        .sort((left, right) => left[1].at - right[1].at || left[0] - right[0])[0];
      if (!next) break;
      const [id, timer] = next;
      this.pending.delete(id);
      this.time = timer.at;
      timer.handler();
    }
    this.time = destination;
  }
}

class ManualIntervals {
  constructor() {
    this.nextId = 1;
    this.pending = new Map();
  }

  setInterval = (handler, milliseconds) => {
    const id = this.nextId;
    this.nextId += 1;
    this.pending.set(id, { handler, milliseconds });
    return id;
  };

  clearInterval = (id) => this.pending.delete(id);

  tickAll() {
    for (const { handler } of [...this.pending.values()]) handler();
  }
}

function phoneSnapshot({ allowedActions = [] } = {}) {
  return {
    ...createPhoneExperimentSnapshot({
      targetId: "target-alpha",
      epoch: 42,
      clock: () => ({ unixMs: 1_700_000_000_000, monotonicNs: 123_000 }),
    }),
    allowed_actions: allowedActions,
  };
}

async function connectSessions(controller, target, sockets) {
  const controllerReady = eventOnce(controller, "ready");
  const targetReady = eventOnce(target, "ready");
  controller.connect();
  target.connect();
  openLinked(sockets);
  await Promise.all([controllerReady, targetReady]);
  await settleMicrotasks();
}

test("browser target deadman is renewed by canonical controller controls and expires a silent half-open session", async () => {
  const sockets = linkedSockets();
  const leaseClock = new ManualTimeouts();
  const controllerIntervals = new ManualIntervals();
  const targetIntervals = new ManualIntervals();
  const secret = Buffer.alloc(32, 7).toString("base64url");
  const snapshot = phoneSnapshot({ allowedActions: ["run.pause"] });
  const expirations = [];
  let commandCount = 0;
  const controller = new BrspControllerSession({
    url: "wss://lab.example/ws/desktop",
    secret,
    targetId: "target-alpha",
    sessionId: "session-alpha",
    requestedScopes: ["session.read", "session.transport"],
    controllerId: "controller-alpha",
    controllerHeartbeatMs: 2_000,
    setIntervalFn: controllerIntervals.setInterval,
    clearIntervalFn: controllerIntervals.clearInterval,
    now: leaseClock.now,
    socketFactory: () => sockets.controller,
  });
  const target = new BrspTargetSession({
    url: "wss://lab.example/ws/desktop",
    secret,
    targetId: "target-alpha",
    sessionId: "session-alpha",
    availableScopes: ["session.read", "session.transport"],
    actions: ["run.pause"],
    getSnapshot: () => snapshot,
    applyCommand: async () => {
      commandCount += 1;
      return {
        status: "accepted",
        reason: "applied",
        acceptedRevision: snapshot.revision,
        resultingRevision: snapshot.revision,
        snapshot,
      };
    },
    onLeaseExpired: (detail) => expirations.push(detail),
    controllerLeaseMs: 5_000,
    now: leaseClock.now,
    setTimeoutFn: leaseClock.setTimeout,
    clearTimeoutFn: leaseClock.clearTimeout,
    setIntervalFn: targetIntervals.setInterval,
    clearIntervalFn: targetIntervals.clearInterval,
    socketFactory: () => sockets.target,
  });

  await connectSessions(controller, target, sockets);
  assert.equal(target.status().leaseRemainingMs, 5_000);
  assert.equal(controllerIntervals.pending.size, 1);
  assert.equal(targetIntervals.pending.size, 1, "read-authorized state heartbeat is active");

  leaseClock.advance(2_000);
  controllerIntervals.tickAll();
  await settleMicrotasks();
  assert.equal(target.status().leaseRemainingMs, 5_000, "snapshot-request heartbeat renews receiver-local deadline");

  leaseClock.advance(4_000);
  const applied = eventOnce(controller, "commandapplied");
  controller.sendCommand("run.pause");
  assert.equal((await applied).detail.status, "accepted");
  assert.equal(commandCount, 1);
  assert.equal(target.status().leaseRemainingMs, 5_000, "accepted command renews the same target lease");

  const controllerTypes = sockets.controller.sent.map((frame) => parseControlFrame(frame).type);
  assert(controllerTypes.filter((type) => type === "snapshot-request").length >= 2);
  assert(!controllerTypes.includes("lease.keepalive"), "liveness uses only registered BRSP/1 controls");

  leaseClock.advance(4_999);
  assert.equal(expirations.length, 0);
  leaseClock.advance(1);
  await settleMicrotasks();
  assert.equal(expirations.length, 1);
  assert.equal(expirations[0].reason, "controller_lease_expired");
  assert.equal(expirations[0].controllerId, "controller-alpha");
  assert.equal(target.controller, null);
  assert.equal(target.phase, "closed");
  assert.equal(targetIntervals.pending.size, 0);

  controller.stop();
  target.stop();
});

test("session.read gates browser target publication and controller adoption for both snapshot lanes", async () => {
  for (const unsolicitedType of ["snapshot", "state"]) {
    const sockets = linkedSockets();
    const leaseClock = new ManualTimeouts();
    const controllerIntervals = new ManualIntervals();
    const targetIntervals = new ManualIntervals();
    const secret = Buffer.alloc(32, unsolicitedType === "snapshot" ? 5 : 6).toString("base64url");
    const snapshot = phoneSnapshot({ allowedActions: ["run.pause"] });
    const controller = new BrspControllerSession({
      url: "wss://lab.example/ws/desktop",
      secret,
      targetId: "target-alpha",
      sessionId: `session-${unsolicitedType}`,
      requestedScopes: ["session.transport"],
      controllerId: `controller-${unsolicitedType}`,
      setIntervalFn: controllerIntervals.setInterval,
      clearIntervalFn: controllerIntervals.clearInterval,
      now: leaseClock.now,
      socketFactory: () => sockets.controller,
    });
    const target = new BrspTargetSession({
      url: "wss://lab.example/ws/desktop",
      secret,
      targetId: "target-alpha",
      sessionId: `session-${unsolicitedType}`,
      availableScopes: ["session.transport"],
      actions: ["run.pause"],
      getSnapshot: () => snapshot,
      applyCommand: async () => ({ status: "rejected", reason: "not_used", snapshot }),
      controllerLeaseMs: 5_000,
      now: leaseClock.now,
      setTimeoutFn: leaseClock.setTimeout,
      clearTimeoutFn: leaseClock.clearTimeout,
      setIntervalFn: targetIntervals.setInterval,
      clearIntervalFn: targetIntervals.clearInterval,
      socketFactory: () => sockets.target,
    });

    await connectSessions(controller, target, sockets);
    assert.deepEqual(controller.grantedScopes, ["session.transport"]);
    assert.equal(controller.snapshot, null);
    assert.equal(controllerIntervals.pending.size, 0, "no snapshot-request heartbeat exists without session.read");
    assert.equal(targetIntervals.pending.size, 0, "no state heartbeat exists without session.read");
    assert.equal(target.publishState(snapshot), false);
    assert.equal(target.connection.publishSnapshot(), false);
    assert.throws(() => controller.requestSnapshot(), /session\.read/u);
    const publishedTypes = sockets.target.sent.map((frame) => parseControlFrame(frame).type);
    assert(!publishedTypes.includes("snapshot"));
    assert(!publishedTypes.includes("state"));

    const protocolError = eventOnce(controller, "protocolerror");
    const laneSequence = unsolicitedType === "state"
      ? (target.connection.stateSequence + 1) >>> 0
      : target.connection.nextControlSequence();
    sockets.target.send(encodeControlMessage({
      protocol: "brsp",
      version: 1,
      type: unsolicitedType,
      sessionId: `session-${unsolicitedType}`,
      senderId: target.connection.peerId,
      senderEpoch: target.connection.epoch,
      sequence: laneSequence,
      body: { revision: snapshot.revision, state: snapshot },
    }));
    assert.match((await protocolError).detail.message, /session\.read/u);
    assert.equal(controller.snapshot, null);

    controller.stop();
    target.stop();
  }
});

test("controller and browser target use mutual canonical proof and returned authority state without WebCrypto subtle", async () => {
  const originalCrypto = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  const nativeCrypto = globalThis.crypto;
  Object.defineProperty(globalThis, "crypto", {
    configurable: true,
    value: { getRandomValues: nativeCrypto.getRandomValues.bind(nativeCrypto) },
  });
  try {
    const sockets = linkedSockets();
    const secret = Buffer.alloc(32, 9).toString("base64url");
    let snapshot = createPhoneExperimentSnapshot({
      targetId: "target-alpha",
      epoch: 42,
      clock: () => ({ unixMs: 1_700_000_000_000, monotonicNs: 123_000 }),
    });
    snapshot = {
      ...snapshot,
      allowed_actions: ["run.pause"],
      run: {
        ...snapshot.run,
        phase: "running",
        state_label: "Running",
        progress_label: "Test",
        event_label: "Test",
        thread_alive: true,
      },
      active_block: {
        ...snapshot.active_block,
        active: true,
        elapsed_s: 0,
        duration_s: 3,
        running: true,
      },
    };
    let applyCount = 0;
    const controller = new BrspControllerSession({
      url: "wss://lab.example/ws/desktop",
      secret,
      targetId: "target-alpha",
      sessionId: "session-alpha",
      requestedScopes: ["session.prepare", "session.read", "session.transport"],
      controllerId: "controller-alpha",
      socketFactory: () => sockets.controller,
    });
    const target = new BrspTargetSession({
      url: "wss://lab.example/ws/desktop",
      secret,
      targetId: "target-alpha",
      sessionId: "session-alpha",
      availableScopes: ["session.prepare", "session.read", "session.transport"],
      actions: ["run.pause"],
      getSnapshot: () => snapshot,
      applyCommand: async (command) => {
        applyCount += 1;
        snapshot = {
          ...snapshot,
          revision: snapshot.revision + 1,
          run: { ...snapshot.run, phase: "paused", state_label: "Paused" },
        };
        return {
          status: "accepted",
          reason: "applied",
          acceptedRevision: command.expected_revision,
          resultingRevision: snapshot.revision,
          snapshot,
        };
      },
      socketFactory: () => sockets.target,
    });

    const ready = eventOnce(controller, "ready");
    const initialState = eventOnce(controller, "snapshot");
    controller.connect();
    target.connect();
    openLinked(sockets);
    await ready;
    await initialState;
    assert.equal(controller.phase, "ready");
    assert.deepEqual(controller.grantedScopes, ["session.prepare", "session.read", "session.transport"]);

    const applied = eventOnce(controller, "commandapplied");
    const returnedState = new Promise((resolve) => {
      const listener = (event) => {
        if (event.detail.snapshot.revision === 1) {
          controller.removeEventListener("snapshot", listener);
          resolve(event);
        }
      };
      controller.addEventListener("snapshot", listener);
    });
    controller.sendCommand("run.pause");
    assert.equal((await applied).detail.status, "accepted");
    const stateEvent = await returnedState;
    assert.equal(stateEvent.detail.snapshot.run.phase, "paused");
    assert.equal(controller.snapshot.revision, 1);

    for (const [scope, action, reason] of [
      ["session.transport", "target.arm", "action_is_local_only"],
      ["session.read", "run.pause", "scope_action_mismatch"],
      ["session.prepare", "package.prepare_demo", "action_not_advertised"],
    ]) {
      const rejected = eventOnce(controller, "commandapplied");
      controller.connection.sendCommand(scope, action, {}, { expectedRevision: snapshot.revision });
      const detail = (await rejected).detail;
      assert.equal(detail.ok, false);
      assert.equal(detail.status, "rejected");
      assert.equal(detail.reason, reason);
    }
    snapshot = { ...snapshot, allowed_actions: [] };
    const transitionRejected = eventOnce(controller, "commandapplied");
    controller.connection.sendCommand("session.transport", "run.pause", {}, { expectedRevision: snapshot.revision });
    assert.equal((await transitionRejected).detail.reason, "invalid_transition");
    assert.equal(applyCount, 1);

    const adopted = controller.snapshot;
    const protocolError = eventOnce(controller, "protocolerror");
    sockets.target.send(encodeControlMessage({
      protocol: "brsp",
      version: 1,
      type: "state",
      sessionId: "session-alpha",
      senderId: target.connection.peerId,
      senderEpoch: target.connection.epoch,
      sequence: (target.connection.stateSequence + 1) >>> 0,
      body: {
        revision: adopted.revision + 1,
        state: { target_id: "target-alpha", revision: adopted.revision + 1 },
      },
    }));
    await protocolError;
    assert.equal(controller.snapshot, adopted);
    controller.stop();
    target.stop();
  } finally {
    Object.defineProperty(globalThis, "crypto", originalCrypto);
  }
});
