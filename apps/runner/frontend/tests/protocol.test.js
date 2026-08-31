import assert from "node:assert/strict";
import test from "node:test";

import { createPhoneExperimentSnapshot } from "../src/domain/phone-experiment-reducer.js";
import {
  PUBLIC_SNAPSHOT_SCHEMA,
  validatePublicRunnerSnapshot,
  validatePublishedRunnerSnapshot,
  validateRunnerSnapshot,
} from "../src/domain/runner-contract.js";
import {
  createVdoInvitation,
  parseInvitation,
  sanitizedInvitationLocation,
} from "../src/remote/invitation.js";
import { encodeControlMessage, parseControlFrame } from "../src/remote/protocol.js";
import {
  BrspControllerSession,
  BrspTargetSession,
  PPS_RELIABLE_COMMAND_BUSY_CODE,
  PPS_RELIABLE_COMMAND_LIMIT,
} from "../src/remote/websocket-session.js";

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

test("VDO invitation uses a fresh private room and keeps all pairing material in the fragment", () => {
  const secret = Buffer.alloc(32, 11).toString("base64url");
  const href = createVdoInvitation({
    pageUrl: "https://ppskit.qzz.io/experiment-runner/?ignored=1#old",
    room: "brsp_private_room_1234",
    targetId: "phone-target-alpha",
    secret,
    scopes: ["session.transport", "session.read"],
  });
  const url = new URL(href);
  assert.equal(url.search, "");
  assert.equal(url.hash.includes(secret), true);
  const parsed = parseInvitation(href);
  assert.equal(parsed.transport, "vdo");
  assert.equal(parsed.room, "brsp_private_room_1234");
  assert.equal(parsed.sessionId, "brsp_private_room_1234");
  assert.deepEqual(parsed.requestedScopes, ["session.read", "session.transport"]);
});

test("invitation cleanup strips fragments and forbidden query secrets", () => {
  assert.equal(
    sanitizedInvitationLocation("https://lab.example/companion/?view=phone&Secret=leaked#secret=fragment"),
    "/companion/?view=phone",
  );
  assert.equal(
    sanitizedInvitationLocation("https://lab.example/companion/?view=phone"),
    "/companion/?view=phone",
  );
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
  assert.equal(validateRunnerSnapshot({
    ...snapshot,
    setup: { ...snapshot.setup, participant_code: "P".repeat(64) },
  }).setup.participant_code.length, 64);
  assert.throws(() => validateRunnerSnapshot({
    ...snapshot,
    setup: { ...snapshot.setup, participant_code: "P".repeat(65) },
  }), /participant_code/u);
  assert.throws(() => validateRunnerSnapshot({ ...snapshot, setup: { ready: false } }), /setup.*fields/u);
  assert.throws(() => validateRunnerSnapshot({ ...snapshot, protocol: "BRSP/1" }), /unsupported/u);
  assert.throws(() => validateRunnerSnapshot({
    ...snapshot,
    active_block: { ...snapshot.active_block, elapsed_s: Number.NaN },
  }), /finite/u);
});

test("native public snapshots have a distinct exact PII-free schema", () => {
  const local = createPhoneExperimentSnapshot({
    targetId: "target-alpha",
    epoch: 7,
    clock: () => ({ unixMs: 1_700_000_000_000, monotonicNs: 123_000 }),
  });
  const remote = {
    schema: PUBLIC_SNAPSHOT_SCHEMA,
    protocol: local.protocol,
    target_id: local.target_id,
    target_kind: local.target_kind,
    epoch: local.epoch,
    revision: local.revision,
    server_unix_ms: local.server_unix_ms,
    server_monotonic_ns: local.server_monotonic_ns,
    connection_state: local.connection_state,
    timing_tier: local.timing_tier,
    package_verified: local.package_verified,
    allowed_actions: local.allowed_actions,
    setup: {
      submitted: local.setup.submitted,
      ready: local.setup.ready,
      required_missing: local.setup.required_missing,
    },
    part: local.part,
    run: local.run,
    instruction_gate: local.instruction_gate,
    active_block: local.active_block,
    safety: {
      lease_expires_at_unix_ms: local.safety.lease_expires_at_unix_ms,
      local_override: local.safety.local_override,
      local_armed: local.safety.local_armed,
      audio_route_ready: local.safety.audio_route_ready,
      publication_ready: local.safety.publication_ready,
      lsl_ready: local.safety.lsl_ready,
      capture_started: local.safety.capture_started,
    },
  };
  assert.equal(validatePublicRunnerSnapshot(remote), remote);
  assert.equal(validatePublishedRunnerSnapshot(remote), remote);
  assert.equal(validatePublishedRunnerSnapshot(local), local);
  for (const privateField of ["identity", "package_label", "last_note", "audit_event_count"]) {
    assert.throws(() => validatePublicRunnerSnapshot({ ...remote, [privateField]: "private" }), /fields are invalid/u);
  }
  assert.throws(() => validatePublicRunnerSnapshot({
    ...remote,
    setup: { ...remote.setup, participant_code: "P001" },
  }), /fields are invalid/u);
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

function publicSnapshot({ allowedActions = [] } = {}) {
  const local = phoneSnapshot({ allowedActions });
  return {
    schema: PUBLIC_SNAPSHOT_SCHEMA,
    protocol: local.protocol,
    target_id: local.target_id,
    target_kind: local.target_kind,
    epoch: local.epoch,
    revision: local.revision,
    server_unix_ms: local.server_unix_ms,
    server_monotonic_ns: local.server_monotonic_ns,
    connection_state: local.connection_state,
    timing_tier: local.timing_tier,
    package_verified: local.package_verified,
    allowed_actions: local.allowed_actions,
    setup: {
      submitted: local.setup.submitted,
      ready: local.setup.ready,
      required_missing: local.setup.required_missing,
    },
    part: local.part,
    run: local.run,
    instruction_gate: local.instruction_gate,
    active_block: local.active_block,
    safety: {
      lease_expires_at_unix_ms: local.safety.lease_expires_at_unix_ms,
      local_override: local.safety.local_override,
      local_armed: local.safety.local_armed,
      audio_route_ready: local.safety.audio_route_ready,
      publication_ready: local.safety.publication_ready,
      lsl_ready: local.safety.lsl_ready,
      capture_started: local.safety.capture_started,
    },
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
  const acceptedControls = [];
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
    onAcceptedControllerControl: (envelope) => {
      acceptedControls.push({ type: envelope.type, sequence: envelope.sequence });
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
  assert(acceptedControls.some(({ type }) => type === "snapshot-request"));
  assert(acceptedControls.some(({ type }) => type === "command"));
  assert.equal(new Set(acceptedControls.map(({ sequence }) => sequence)).size, acceptedControls.length);

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

test("native-backed targets can disable autonomous state heartbeats", async () => {
  const sockets = linkedSockets();
  const controllerIntervals = new ManualIntervals();
  const targetIntervals = new ManualIntervals();
  const secret = Buffer.alloc(32, 19).toString("base64url");
  const snapshot = publicSnapshot({ allowedActions: [] });
  const controller = new BrspControllerSession({
    url: "wss://lab.example/ws/native-no-heartbeat",
    secret,
    targetId: "target-alpha",
    sessionId: "session-native-no-heartbeat",
    requestedScopes: ["session.read"],
    controllerId: "controller-native-no-heartbeat",
    setIntervalFn: controllerIntervals.setInterval,
    clearIntervalFn: controllerIntervals.clearInterval,
    socketFactory: () => sockets.controller,
  });
  const target = new BrspTargetSession({
    url: "wss://lab.example/ws/native-no-heartbeat",
    secret,
    targetId: "target-alpha",
    sessionId: "session-native-no-heartbeat",
    availableScopes: ["session.read"],
    actions: [],
    getSnapshot: () => snapshot,
    applyCommand: async () => ({ status: "rejected", reason: "not_used", snapshot }),
    stateHeartbeatEnabled: false,
    setIntervalFn: targetIntervals.setInterval,
    clearIntervalFn: targetIntervals.clearInterval,
    socketFactory: () => sockets.target,
  });

  await connectSessions(controller, target, sockets);
  assert.equal(controllerIntervals.pending.size, 1, "controller still requests owner-fenced snapshots");
  assert.equal(targetIntervals.pending.size, 0, "target never publishes an unfenced periodic state");

  controller.stop();
  target.stop();
});

test("target command handling awaits an asynchronous native authority gate", async () => {
  const sockets = linkedSockets();
  const secret = Buffer.alloc(32, 13).toString("base64url");
  const snapshot = phoneSnapshot({ allowedActions: ["run.pause"] });
  let releaseNative;
  let applyCount = 0;
  const controller = new BrspControllerSession({
    url: "wss://lab.example/ws/native-gate",
    secret,
    targetId: "target-alpha",
    sessionId: "session-native-gate",
    requestedScopes: ["session.read", "session.transport"],
    controllerId: "controller-native-gate",
    socketFactory: () => sockets.controller,
  });
  const target = new BrspTargetSession({
    url: "wss://lab.example/ws/native-gate",
    secret,
    targetId: "target-alpha",
    sessionId: "session-native-gate",
    availableScopes: ["session.read", "session.transport"],
    actions: ["run.pause"],
    getSnapshot: () => snapshot,
    applyCommand: async () => {
      applyCount += 1;
      return {
        status: "accepted",
        reason: "applied",
        acceptedRevision: snapshot.revision,
        resultingRevision: snapshot.revision,
        snapshot,
      };
    },
    onAcceptedControllerControl: (envelope) => {
      if (envelope.type !== "command") return true;
      return new Promise((resolve) => { releaseNative = resolve; });
    },
    socketFactory: () => sockets.target,
  });

  await connectSessions(controller, target, sockets);
  const applied = eventOnce(controller, "commandapplied");
  controller.sendCommand("run.pause");
  await settleMicrotasks();
  assert.equal(applyCount, 0, "the application reducer waits for native authorization");
  assert.equal(controller.status().pendingCommands, 1);

  releaseNative(true);
  assert.equal((await applied).detail.status, "accepted");
  assert.equal(applyCount, 1);

  controller.stop();
  target.stop();
});

test("PPS controllers admit only one outstanding reliable command and recover after applied", async (context) => {
  const sockets = linkedSockets();
  const secret = Buffer.alloc(32, 23).toString("base64url");
  const snapshot = phoneSnapshot({ allowedActions: ["run.pause"] });
  let applyCount = 0;
  let releaseFirst;
  const accepted = () => ({
    status: "accepted",
    reason: "applied",
    acceptedRevision: snapshot.revision,
    resultingRevision: snapshot.revision,
    snapshot,
  });
  const controller = new BrspControllerSession({
    url: "wss://lab.example/ws/reliable-cap",
    secret,
    targetId: "target-alpha",
    sessionId: "session-reliable-cap",
    requestedScopes: ["session.read", "session.transport"],
    controllerId: "controller-reliable-cap",
    socketFactory: () => sockets.controller,
  });
  const target = new BrspTargetSession({
    url: "wss://lab.example/ws/reliable-cap",
    secret,
    targetId: "target-alpha",
    sessionId: "session-reliable-cap",
    availableScopes: ["session.read", "session.transport"],
    actions: ["run.pause"],
    getSnapshot: () => snapshot,
    applyCommand: () => {
      applyCount += 1;
      if (applyCount !== 1) return accepted();
      return new Promise((resolve) => { releaseFirst = () => resolve(accepted()); });
    },
    socketFactory: () => sockets.target,
  });
  context.after(() => {
    controller.stop();
    target.stop();
  });

  await connectSessions(controller, target, sockets);
  const firstApplied = eventOnce(controller, "commandapplied");
  const firstId = controller.sendCommand("run.pause");
  const admittedCommandFrames = sockets.controller.sent
    .filter((frame) => parseControlFrame(frame).type === "command").length;

  assert.match(firstId, /^cmd_/u);
  assert.equal(controller.status().pendingCommands, 1);
  assert.equal(controller.status().reliableCommandLimit, PPS_RELIABLE_COMMAND_LIMIT);
  assert.equal(controller.status().reliableCommandBusy, true);
  assert.equal(controller.connection.pendingCommands.size, 1);
  assert.equal(controller.pendingActions.size, 1);
  for (let attempt = 0; attempt < 100; attempt += 1) {
    assert.throws(
      () => controller.sendCommand("run.pause"),
      (error) => error?.code === PPS_RELIABLE_COMMAND_BUSY_CODE
        && error?.limit === PPS_RELIABLE_COMMAND_LIMIT,
    );
  }
  assert.equal(controller.connection.pendingCommands.size, 1, "rejected sends cannot grow BRSP pending state");
  assert.equal(controller.pendingActions.size, 1, "rejected sends cannot grow PPS action state");
  assert.equal(
    sockets.controller.sent.filter((frame) => parseControlFrame(frame).type === "command").length,
    admittedCommandFrames,
    "busy rejection occurs before command ID generation and transport send",
  );

  await settleMicrotasks();
  assert.equal(typeof releaseFirst, "function");
  releaseFirst();
  assert.equal((await firstApplied).detail.status, "accepted");
  assert.equal(controller.status().pendingCommands, 0);
  assert.equal(controller.status().reliableCommandBusy, false);
  assert.equal(controller.connection.pendingCommands.size, 0);
  assert.equal(controller.pendingActions.size, 0);

  const secondApplied = eventOnce(controller, "commandapplied");
  controller.sendCommand("run.pause");
  assert.equal((await secondApplied).detail.status, "accepted");
  assert.equal(applyCount, 2);
  assert.equal(controller.status().pendingCommands, 0);
});

test("controller pending state survives diagnostic remote errors and clears on terminal recovery", () => {
  const socket = new LinkedSocket();
  const controller = new BrspControllerSession({
    url: "wss://lab.example/ws/pending-lifecycle",
    secret: Buffer.alloc(32, 24).toString("base64url"),
    targetId: "target-alpha",
    sessionId: "session-pending-lifecycle",
    requestedScopes: ["session.read", "session.transport"],
    controllerId: "controller-pending-lifecycle",
    socketFactory: () => socket,
  });
  let pendingChanges = 0;
  controller.addEventListener("pendingchange", () => { pendingChanges += 1; });
  const seedPending = (id) => {
    controller.connection.pendingCommands.set(id, { action: "run.pause" });
    controller.pendingActions.set(id, "run.pause");
    assert.equal(controller.status().reliableCommandBusy, true);
  };

  seedPending("cmd_remote_error");
  const remoteError = new Event("remoteerror");
  Object.defineProperty(remoteError, "detail", { value: { message: "target error" } });
  controller.connection.dispatchEvent(remoteError);
  assert.equal(
    controller.status().pendingCommands,
    1,
    "a non-terminal BRSP error cannot reopen the command slot before a late applied frame",
  );
  controller.setPhase("error", "Operator must reconnect after an unresolved remote error.");
  assert.equal(controller.status().pendingCommands, 0);

  seedPending("cmd_protocol_error");
  controller.connection.protocolError(new Error("protocol failed"));
  assert.equal(controller.status().pendingCommands, 0);

  seedPending("cmd_reconnect");
  controller.connect();
  assert.equal(controller.status().pendingCommands, 0);

  seedPending("cmd_stop");
  controller.stop();
  assert.equal(controller.status().pendingCommands, 0);
  assert.equal(controller.connection.pendingCommands.size, 0);
  assert.equal(controller.pendingActions.size, 0);
  assert.equal(pendingChanges, 4, "every terminally abandoned pending command publishes a UI state change");
});

test("target publication stays private until application authority permits it", async () => {
  const sockets = linkedSockets();
  const secret = Buffer.alloc(32, 14).toString("base64url");
  const snapshot = phoneSnapshot({ allowedActions: [] });
  let publicationAllowed = false;
  const controller = new BrspControllerSession({
    url: "wss://lab.example/ws/publication-gate",
    secret,
    targetId: "target-alpha",
    sessionId: "session-publication-gate",
    requestedScopes: ["session.read"],
    controllerId: "controller-publication-gate",
    socketFactory: () => sockets.controller,
  });
  const target = new BrspTargetSession({
    url: "wss://lab.example/ws/publication-gate",
    secret,
    targetId: "target-alpha",
    sessionId: "session-publication-gate",
    availableScopes: ["session.read"],
    actions: [],
    getSnapshot: () => snapshot,
    applyCommand: async () => ({ status: "rejected", reason: "not_used", snapshot }),
    canPublishTargetState: () => publicationAllowed,
    socketFactory: () => sockets.target,
  });

  await connectSessions(controller, target, sockets);
  assert.equal(controller.snapshot, null);
  const blockedTypes = sockets.target.sent.map((frame) => parseControlFrame(frame).type);
  assert(!blockedTypes.includes("snapshot"));
  assert(!blockedTypes.includes("state"));

  publicationAllowed = true;
  const published = eventOnce(controller, "snapshot");
  assert.equal(target.publishState(snapshot), true);
  assert.equal((await published).detail.snapshot.target_id, "target-alpha");

  controller.stop();
  target.stop();
});

test("snapshot responses await asynchronous application lease renewal", async () => {
  const sockets = linkedSockets();
  const secret = Buffer.alloc(32, 15).toString("base64url");
  const snapshot = phoneSnapshot({ allowedActions: [] });
  let holdNextSnapshot = false;
  let releaseRenewal;
  const controller = new BrspControllerSession({
    url: "wss://lab.example/ws/snapshot-gate",
    secret,
    targetId: "target-alpha",
    sessionId: "session-snapshot-gate",
    requestedScopes: ["session.read"],
    controllerId: "controller-snapshot-gate",
    socketFactory: () => sockets.controller,
  });
  const target = new BrspTargetSession({
    url: "wss://lab.example/ws/snapshot-gate",
    secret,
    targetId: "target-alpha",
    sessionId: "session-snapshot-gate",
    availableScopes: ["session.read"],
    actions: [],
    getSnapshot: () => snapshot,
    applyCommand: async () => ({ status: "rejected", reason: "not_used", snapshot }),
    onAcceptedControllerControl: (envelope) => {
      if (envelope.type !== "snapshot-request" || !holdNextSnapshot) return true;
      holdNextSnapshot = false;
      return new Promise((resolve) => { releaseRenewal = resolve; });
    },
    socketFactory: () => sockets.target,
  });

  await connectSessions(controller, target, sockets);
  const before = sockets.target.sent.filter((frame) => parseControlFrame(frame).type === "snapshot").length;
  holdNextSnapshot = true;
  const renewedSnapshot = eventOnce(controller, "snapshot");
  controller.requestSnapshot();
  await settleMicrotasks();
  const blocked = sockets.target.sent.filter((frame) => parseControlFrame(frame).type === "snapshot").length;
  assert.equal(blocked, before, "the response is withheld while native renewal is unresolved");

  releaseRenewal(true);
  await renewedSnapshot;
  const after = sockets.target.sent.filter((frame) => parseControlFrame(frame).type === "snapshot").length;
  assert.equal(after, before + 1);

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
