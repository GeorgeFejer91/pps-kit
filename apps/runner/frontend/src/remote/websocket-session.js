import {
  BRSPConnection,
  BRSP_CONTROL_MAX_BYTES,
  BRSP_STATE_TYPES,
  canonicalStringify,
} from "browser-remote-sync-protocol/src/brsp.js";

import {
  SCOPES,
  actionsForScopes,
  isRemoteAction,
  requiredScope,
  validateRunnerSnapshot,
} from "../domain/runner-contract.js";
import {
  createProtocolIdentity,
  encodeControlMessage,
  makeEnvelope,
  parseControlFrame,
} from "./protocol.js";
import { installBrspProofCrypto } from "./proof.js";

const CAPABILITIES = Object.freeze([
  "command-ack",
  "latest-state",
  "pps-runner-v1",
  "state-snapshot",
]);
const PEER_KEY = "websocket-peer";
const CONTROL_QUEUE_MAX_BYTES = 262_144;
const CONTROLLER_HEARTBEAT_MS = 2_000;
const CONTROLLER_LEASE_MS = 5_000;
const STATE_HEARTBEAT_MS = 250;

function boundedMilliseconds(value, label, { minimum = 50, maximum = 60_000 } = {}) {
  if (!Number.isFinite(value) || value < minimum || value > maximum) {
    throw new TypeError(`${label} must be between ${minimum} and ${maximum} milliseconds.`);
  }
  return value;
}

function detailEvent(type, detail) {
  const event = new Event(type);
  Object.defineProperty(event, "detail", { value: detail, enumerable: true });
  return event;
}

function openSocket(socket) {
  return socket?.readyState === 1;
}

async function normalizeFrameData(value) {
  if (typeof value === "string" || value instanceof ArrayBuffer || ArrayBuffer.isView(value)) return value;
  if (typeof Blob !== "undefined" && value instanceof Blob) return value.arrayBuffer();
  throw new TypeError("Unsupported WebSocket frame type.");
}

/**
 * BRSP adapter for the lab WebSocket transport. WebSocket is reliable and
 * ordered, so the two BRSP lanes are logical: control is never dropped, while
 * state is coalesced before entering the socket queue and receivers still use
 * an independent uint32 state sequence.
 */
class BrspWebSocketTransport extends EventTarget {
  constructor({ url, role, socketFactory }) {
    super();
    this.url = String(url);
    this.role = role;
    this.socketFactory = socketFactory ?? ((socketUrl) => new WebSocket(socketUrl));
    this.socket = null;
    this.peerOpen = false;
    this.stopped = false;
    this.pendingState = null;
    this.drainTimer = null;
    this.isRelay = /\/ws\/relay\//u.test(new URL(this.url, "ws://localhost").pathname);
  }

  start() {
    if (this.socket) throw new Error("The transport is already active.");
    this.stopped = false;
    const socket = this.socketFactory(this.url);
    this.socket = socket;
    socket.addEventListener("open", () => {
      this.dispatchEvent(detailEvent("transportopen", {}));
      if (!this.isRelay) this.openPeer();
    });
    socket.addEventListener("message", (event) => {
      void this.receive(event.data).catch((error) => this.fail(error));
    });
    socket.addEventListener("close", () => this.closed("WebSocket closed."));
    socket.addEventListener("error", () => this.fail(new Error("The WebSocket transport reported an error.")));
  }

  openPeer() {
    if (this.peerOpen || !openSocket(this.socket)) return;
    this.peerOpen = true;
    this.dispatchEvent(detailEvent("peeropen", { peerKey: PEER_KEY }));
  }

  async receive(data) {
    const message = parseControlFrame(await normalizeFrameData(data));
    if (message.kind === "relay.peer") {
      const peerRole = this.role === "target" ? "controller" : "target";
      const detail = {
        ...message,
        message: `${message.role} relay peer ${message.present ? "connected" : "disconnected"}.`,
      };
      this.dispatchEvent(detailEvent("relaypeer", detail));
      if (message.role === peerRole) {
        if (message.present) this.openPeer();
        else this.closed("Relay peer disconnected.", false);
      }
      return;
    }
    if (message.kind === "relay.error") {
      this.dispatchEvent(detailEvent("relayerror", message));
      return;
    }
    if (!this.peerOpen) throw new TypeError("BRSP data arrived before the selected peer opened.");
    const eventType = BRSP_STATE_TYPES.includes(message.type) ? "statemessage" : "controlmessage";
    this.dispatchEvent(detailEvent(eventType, {
      peerKey: PEER_KEY,
      data: encodeControlMessage(message),
    }));
  }

  sendControl(peerKey, data) {
    if (peerKey !== PEER_KEY || !this.peerOpen || !openSocket(this.socket)) return false;
    const byteLength = new TextEncoder().encode(data).byteLength;
    if (byteLength > BRSP_CONTROL_MAX_BYTES || this.socket.bufferedAmount + byteLength > CONTROL_QUEUE_MAX_BYTES) {
      return false;
    }
    this.socket.send(data);
    return true;
  }

  sendState(peerKey, data) {
    if (peerKey !== PEER_KEY || !this.peerOpen || !openSocket(this.socket)) return false;
    if (this.socket.bufferedAmount > 0) {
      this.pendingState = data;
      this.scheduleDrain();
      return false;
    }
    this.socket.send(data);
    return true;
  }

  scheduleDrain() {
    if (this.drainTimer !== null) return;
    const drain = () => {
      this.drainTimer = null;
      if (!this.pendingState || !this.peerOpen || !openSocket(this.socket)) return;
      if (this.socket.bufferedAmount > 0) {
        this.scheduleDrain();
        return;
      }
      const newest = this.pendingState;
      this.pendingState = null;
      this.socket.send(newest);
    };
    this.drainTimer = setTimeout(drain, 16);
  }

  closePeer(peerKey) {
    if (peerKey !== PEER_KEY) return;
    this.stop();
  }

  closed(reason, closeSocket = false) {
    const wasOpen = this.peerOpen;
    this.peerOpen = false;
    this.pendingState = null;
    clearTimeout(this.drainTimer);
    this.drainTimer = null;
    if (wasOpen) this.dispatchEvent(detailEvent("peerclose", { peerKey: PEER_KEY, reason }));
    if (closeSocket && openSocket(this.socket)) this.socket.close(1002, "Protocol error");
  }

  fail(error) {
    this.dispatchEvent(detailEvent("transporterror", {
      message: error instanceof Error ? error.message : String(error),
    }));
    this.closed("Transport protocol error.", true);
  }

  async stop() {
    if (this.stopped) return;
    this.stopped = true;
    const socket = this.socket;
    this.socket = null;
    this.closed("Transport stopped.");
    if (openSocket(socket)) socket.close(1000, "User stopped remote control");
  }
}

/**
 * PPS adds an application-level read boundary and target-owned controller
 * liveness to the transport-neutral BRSP state machine. These checks remain
 * outside the pinned upstream package because `session.read` and the
 * controller deadman are PPS profile rules rather than BRSP/1 wire fields.
 */
class PpsBrspConnection extends BRSPConnection {
  constructor({ onAcceptedControllerControl, ...options }) {
    super(options);
    this.onAcceptedControllerControl = onAcceptedControllerControl;
  }

  hasReadScope() {
    return this.acceptedScopes.includes(SCOPES.READ);
  }

  requestSnapshot() {
    if (this.role !== "controller" || this.phase !== "ready") return false;
    if (!this.hasReadScope()) return false;
    return this.sendControlEnvelope(makeEnvelope({
      type: "snapshot-request",
      sessionId: this.sessionId,
      senderId: this.peerId,
      senderEpoch: this.epoch,
      sequence: this.nextControlSequence(),
      body: {},
    }));
  }

  publishSnapshot(...args) {
    if (this.role === "target" && !this.hasReadScope()) return false;
    return super.publishSnapshot(...args);
  }

  publishState(...args) {
    if (this.role === "target" && !this.hasReadScope()) return false;
    return super.publishState(...args);
  }

  queueCommand(envelope) {
    // The WebSocket transport has already run the exact PPS body validator,
    // but repeat it here before a command is allowed to renew authority.
    encodeControlMessage(envelope);
    const command = envelope.body;
    if (!this.acceptedScopes.includes(command.scope)) {
      throw new TypeError("Command uses a scope that was not negotiated.");
    }
    const cached = this.commandResults.get(command.commandId);
    if (cached && cached.request !== canonicalStringify(command)) {
      throw new TypeError("A commandId was reused with a different command body.");
    }
    if (this.onAcceptedControllerControl?.(envelope) === false) {
      throw new TypeError("The target-owned controller lease expired.");
    }
    return super.queueCommand(envelope);
  }

  handleSnapshotRequest(envelope) {
    // Validate the exact empty body before treating this standard BRSP control
    // as a liveness signal. A target without session.read renews the peer lease
    // but deliberately publishes no snapshot.
    encodeControlMessage(envelope);
    if (this.onAcceptedControllerControl?.(envelope) === false) {
      throw new TypeError("The target-owned controller lease expired.");
    }
    return super.handleSnapshotRequest(envelope);
  }

  handleSnapshot(envelope) {
    if (this.role === "controller" && !this.hasReadScope()) {
      throw new TypeError("session.read is required to receive a PPS snapshot.");
    }
    return super.handleSnapshot(envelope);
  }

  receiveState(detail) {
    if (this.role === "controller" && this.phase === "ready" && !this.hasReadScope()) {
      throw new TypeError("session.read is required to receive PPS state.");
    }
    return super.receiveState(detail);
  }

  async receiveControl(detail) {
    const inspectForLiveness = this.role === "target" && this.phase === "ready"
      && detail?.peerKey === this.peerKey;
    const envelope = inspectForLiveness ? parseControlFrame(detail?.data) : undefined;
    const previousSequence = this.remoteControlSequence;
    await super.receiveControl(detail);
    // Commands and snapshot requests renew inside their exact validators above.
    // A bounded authenticated diagnostic is the only other non-closing control
    // a ready controller may send, so count it after the core accepts its fresh
    // sequence. `bye` revokes authority and must never extend the lease.
    if (envelope?.type === "error" && this.phase === "ready"
      && this.remoteControlSequence !== previousSequence
      && this.onAcceptedControllerControl?.(envelope) === false) {
      throw new TypeError("The target-owned controller lease expired.");
    }
  }
}

class BrspSocketSession extends EventTarget {
  constructor({
    url,
    role,
    sessionId,
    secret,
    peerId,
    scopes,
    socketFactory,
    getState,
    applyCommand,
    now,
    onAcceptedControllerControl,
  }) {
    super();
    installBrspProofCrypto();
    this.phase = "idle";
    this.transport = new BrspWebSocketTransport({ url, role, socketFactory });
    this.connection = new PpsBrspConnection({
      transport: this.transport,
      role,
      sessionId,
      sharedSecret: secret,
      peerId,
      capabilities: CAPABILITIES,
      requestedScopes: role === "controller" ? scopes : [],
      grantedScopes: role === "target" ? scopes : [],
      getState,
      applyCommand,
      now,
      onAcceptedControllerControl,
    });
    this.transport.addEventListener("transportopen", () => this.setPhase("authenticating", "Transport open; completing BRSP hello, proof, and ready."));
    this.transport.addEventListener("relaypeer", (event) => this.dispatchEvent(detailEvent("relaypeer", event.detail)));
    this.transport.addEventListener("relayerror", (event) => this.dispatchEvent(detailEvent("remoteerror", event.detail)));
    this.transport.addEventListener("transporterror", (event) => this.dispatchEvent(detailEvent("protocolerror", event.detail)));
    this.connection.addEventListener("phasechange", (event) => this.setPhase(event.detail.phase, event.detail.message));
    this.connection.addEventListener("protocolerror", (event) => this.dispatchEvent(detailEvent("protocolerror", event.detail)));
    this.connection.addEventListener("remoteerror", (event) => this.dispatchEvent(detailEvent("remoteerror", event.detail)));
  }

  setPhase(phase, message) {
    this.phase = phase;
    this.dispatchEvent(detailEvent("phasechange", { phase, message }));
  }

  connect() {
    if (!["idle", "closed", "error"].includes(this.phase)) throw new Error("The session is already active.");
    this.setPhase("connecting", "Opening the explicitly requested connection…");
    this.transport.start();
  }

  stop() {
    this.beforeStop();
    void this.connection.close().catch((error) => {
      this.dispatchEvent(detailEvent("protocolerror", { message: error.message }));
    });
  }

  beforeStop() {}
}

export class BrspControllerSession extends BrspSocketSession {
  constructor({
    url,
    secret,
    targetId,
    sessionId,
    requestedScopes,
    controllerId = createProtocolIdentity("controller"),
    socketFactory,
    controllerHeartbeatMs = CONTROLLER_HEARTBEAT_MS,
    setIntervalFn = (handler, milliseconds) => setInterval(handler, milliseconds),
    clearIntervalFn = (timer) => clearInterval(timer),
    now,
  }) {
    super({
      url,
      role: "controller",
      sessionId,
      secret,
      peerId: controllerId,
      scopes: [...new Set(requestedScopes)].sort(),
      socketFactory,
      now,
    });
    this.expectedTargetId = targetId;
    this.controllerId = controllerId;
    this.grantedScopes = [];
    this.snapshot = null;
    this.pendingActions = new Map();
    this.controllerHeartbeatMs = boundedMilliseconds(controllerHeartbeatMs, "controllerHeartbeatMs");
    this.setIntervalFn = setIntervalFn;
    this.clearIntervalFn = clearIntervalFn;
    this.snapshotHeartbeat = null;
    this.connection.addEventListener("ready", () => {
      const status = this.connection.snapshot();
      this.grantedScopes = [...status.acceptedScopes];
      this.startSnapshotHeartbeat();
      this.dispatchEvent(detailEvent("ready", this.status()));
    });
    this.connection.addEventListener("peerclose", () => this.stopSnapshotHeartbeat());
    this.connection.addEventListener("phasechange", (event) => {
      if (event.detail.phase !== "ready") this.stopSnapshotHeartbeat();
    });
    this.connection.addEventListener("snapshot", (event) => this.acceptState(event.detail, "snapshot"));
    this.connection.addEventListener("state", (event) => this.acceptState(event.detail, "state"));
    this.connection.addEventListener("commandapplied", (event) => this.acceptApplied(event.detail));
  }

  status() {
    return {
      phase: this.phase,
      targetId: this.snapshot?.target_id ?? this.expectedTargetId,
      controllerId: this.controllerId,
      senderEpoch: this.connection.epoch,
      grantedScopes: [...this.grantedScopes],
      capabilities: [...this.connection.negotiatedCapabilities],
      pendingCommands: this.connection.pendingCommands.size,
      snapshot: this.snapshot,
    };
  }

  acceptState({ revision, state }, source) {
    let validated;
    try {
      if (!this.grantedScopes.includes(SCOPES.READ)) {
        throw new TypeError("session.read is required before adopting PPS target state.");
      }
      validated = validateRunnerSnapshot(state);
      if (revision !== validated.revision) {
        throw new TypeError("BRSP state revision does not match its PPS snapshot revision.");
      }
      if (validated.target_id !== this.expectedTargetId) {
        throw new TypeError("Target snapshot identity does not match the invitation.");
      }
    } catch (error) {
      this.connection.protocolError(error);
      return;
    }
    if (this.snapshot && revision < this.snapshot.revision) return;
    this.snapshot = validated;
    this.dispatchEvent(detailEvent("snapshot", { revision, snapshot: validated, source }));
  }

  requestSnapshot() {
    if (this.phase !== "ready") throw new Error("Authenticate before requesting target state.");
    if (!this.grantedScopes.includes(SCOPES.READ)) {
      throw new Error("The target did not grant session.read.");
    }
    return this.connection.requestSnapshot();
  }

  startSnapshotHeartbeat() {
    this.stopSnapshotHeartbeat();
    if (!this.grantedScopes.includes(SCOPES.READ)) return;
    this.snapshotHeartbeat = this.setIntervalFn(() => {
      if (this.phase !== "ready") return;
      try {
        this.connection.requestSnapshot();
      } catch (error) {
        this.stopSnapshotHeartbeat();
        this.connection.protocolError(error);
      }
    }, this.controllerHeartbeatMs);
  }

  stopSnapshotHeartbeat() {
    if (this.snapshotHeartbeat === null) return;
    this.clearIntervalFn(this.snapshotHeartbeat);
    this.snapshotHeartbeat = null;
  }

  sendCommand(action, args = {}, { expectedRevision = this.snapshot?.revision ?? null } = {}) {
    if (this.phase !== "ready") throw new Error("Authenticate before sending commands.");
    const scope = requiredScope(action);
    if (!scope || !isRemoteAction(action)) throw new Error(`${action} is target-local and cannot be sent remotely.`);
    if (!this.grantedScopes.includes(scope)) throw new Error(`The target did not grant ${scope}.`);
    if (!this.snapshot?.allowed_actions?.includes(action)) throw new Error(`The target does not currently allow ${action}.`);
    const commandId = this.connection.sendCommand(scope, action, args, { expectedRevision });
    this.pendingActions.set(commandId, action);
    this.dispatchEvent(detailEvent("pendingchange", this.status()));
    return commandId;
  }

  acceptApplied(applied) {
    const result = applied.result && typeof applied.result === "object" ? applied.result : {};
    const action = result.action ?? this.pendingActions.get(applied.commandId) ?? "unknown";
    this.pendingActions.delete(applied.commandId);
    this.dispatchEvent(detailEvent("commandapplied", {
      ...applied,
      id: applied.commandId,
      action,
      status: result.status ?? (applied.ok ? "accepted" : "rejected"),
      reason: result.reason ?? applied.error ?? "applied",
      accepted_revision: result.acceptedRevision ?? applied.revision,
      resulting_revision: result.resultingRevision ?? applied.revision,
      snapshot: this.snapshot,
    }));
    this.dispatchEvent(detailEvent("pendingchange", this.status()));
  }

  beforeStop() {
    this.stopSnapshotHeartbeat();
    this.pendingActions.clear();
  }
}

function applicationErrorToken(reason) {
  const normalized = String(reason || "command_rejected").replace(/[^A-Za-z0-9_.:-]/gu, "_").slice(0, 64);
  return normalized || "command_rejected";
}

export class BrspTargetSession extends BrspSocketSession {
  constructor({
    url,
    secret,
    targetId,
    sessionId,
    availableScopes,
    actions,
    getSnapshot,
    applyCommand,
    onLeaseExpired,
    socketFactory,
    controllerLeaseMs = CONTROLLER_LEASE_MS,
    stateHeartbeatMs = STATE_HEARTBEAT_MS,
    now = () => performance.now(),
    setTimeoutFn = (handler, milliseconds) => setTimeout(handler, milliseconds),
    clearTimeoutFn = (timer) => clearTimeout(timer),
    setIntervalFn = (handler, milliseconds) => setInterval(handler, milliseconds),
    clearIntervalFn = (timer) => clearInterval(timer),
  }) {
    const targetPeerId = createProtocolIdentity("target");
    const advertisedActions = new Set(actions);
    let controllerLeaseIsValid = () => false;
    let renewControllerLease = () => false;
    const validatedSnapshot = () => {
      const current = validateRunnerSnapshot(getSnapshot());
      if (current.target_id !== targetId) {
        throw new TypeError("The browser target snapshot does not match its advertised target ID.");
      }
      return current;
    };
    const rejectedCommand = (command, reason, current = validatedSnapshot()) => ({
      ok: false,
      revision: current.revision,
      result: {
        action: command.action,
        status: "rejected",
        reason,
        acceptedRevision: current.revision,
        resultingRevision: current.revision,
      },
      error: applicationErrorToken(reason),
    });
    const adaptCommand = async (command) => {
      const current = validatedSnapshot();
      if (!controllerLeaseIsValid()) return rejectedCommand(command, "controller_lease_expired", current);
      const required = requiredScope(command.action);
      if (!isRemoteAction(command.action)) return rejectedCommand(command, "action_is_local_only", current);
      if (required !== command.scope) return rejectedCommand(command, "scope_action_mismatch", current);
      if (!advertisedActions.has(command.action)) return rejectedCommand(command, "action_not_advertised", current);
      if (!current.allowed_actions.includes(command.action)) return rejectedCommand(command, "invalid_transition", current);
      const outcome = await applyCommand({
        id: command.commandId,
        action: command.action,
        args: command.args,
        scope: command.scope,
        expected_revision: command.expectedRevision,
      });
      const resultingSnapshot = validatedSnapshot();
      const ok = outcome?.status !== "rejected";
      return {
        ok,
        revision: outcome?.resultingRevision ?? outcome?.snapshot?.revision ?? resultingSnapshot.revision,
        result: {
          action: command.action,
          status: outcome?.status ?? (ok ? "accepted" : "rejected"),
          reason: outcome?.reason ?? (ok ? "applied" : "command_rejected"),
          acceptedRevision: outcome?.acceptedRevision ?? current.revision,
          resultingRevision: outcome?.resultingRevision ?? resultingSnapshot.revision,
        },
        error: ok ? null : applicationErrorToken(outcome?.reason),
      };
    };
    super({
      url,
      role: "target",
      sessionId,
      secret,
      peerId: targetPeerId,
      scopes: [...new Set(availableScopes)].sort(),
      socketFactory,
      getState: validatedSnapshot,
      applyCommand: adaptCommand,
      now,
      onAcceptedControllerControl: () => renewControllerLease(),
    });
    this.targetId = targetId;
    this.actions = [...advertisedActions].sort();
    this.getSnapshot = validatedSnapshot;
    this.onLeaseExpired = onLeaseExpired;
    this.now = now;
    this.controllerLeaseMs = boundedMilliseconds(controllerLeaseMs, "controllerLeaseMs", { minimum: 100 });
    this.stateHeartbeatMs = boundedMilliseconds(stateHeartbeatMs, "stateHeartbeatMs");
    this.setTimeoutFn = setTimeoutFn;
    this.clearTimeoutFn = clearTimeoutFn;
    this.setIntervalFn = setIntervalFn;
    this.clearIntervalFn = clearIntervalFn;
    this.controller = null;
    this.leaseDeadline = null;
    this.leaseTimer = null;
    this.stateHeartbeat = null;
    this.leaseMs = this.controllerLeaseMs;
    controllerLeaseIsValid = () => this.hasValidControllerLease();
    renewControllerLease = () => this.refreshControllerLease();
    this.connection.addEventListener("ready", () => {
      this.controller = { id: this.connection.snapshot().remotePeerId };
      this.refreshControllerLease();
      this.startStateHeartbeat();
      this.dispatchEvent(detailEvent("ready", this.status()));
    });
    this.connection.addEventListener("command", (event) => this.dispatchEvent(detailEvent("commandapplied", event.detail)));
    this.connection.addEventListener("peerclose", () => this.expireController({ reason: "controller_disconnected" }));
    this.connection.addEventListener("phasechange", (event) => {
      if (event.detail.phase !== "ready") this.stopStateHeartbeat();
    });
  }

  status() {
    const status = this.connection.snapshot();
    return {
      phase: this.phase,
      targetId: this.targetId,
      controllerId: this.controller?.id,
      senderEpoch: this.connection.epoch,
      grantedScopes: [...status.acceptedScopes],
      capabilities: [...status.capabilities],
      leaseRemainingMs: this.leaseDeadline === null
        ? 0
        : Math.max(0, Math.ceil(this.leaseDeadline - this.now())),
    };
  }

  publishState(snapshot = this.getSnapshot()) {
    const validated = validateRunnerSnapshot(snapshot);
    if (validated.target_id !== this.targetId) {
      throw new TypeError("The browser target cannot publish another target's snapshot.");
    }
    return this.connection.publishState(validated, { revision: validated.revision });
  }

  hasValidControllerLease(at = this.now()) {
    return Boolean(this.controller) && this.leaseDeadline !== null && at < this.leaseDeadline;
  }

  refreshControllerLease() {
    if (!this.controller || this.connection.phase !== "ready") return false;
    const acceptedAt = this.now();
    if (this.leaseDeadline !== null && acceptedAt >= this.leaseDeadline) {
      this.expireController({ reason: "controller_lease_expired", closeConnection: true });
      return false;
    }
    this.leaseDeadline = acceptedAt + this.controllerLeaseMs;
    this.scheduleLeaseExpiry(this.controllerLeaseMs);
    this.dispatchEvent(detailEvent("leaserenewed", this.status()));
    return true;
  }

  scheduleLeaseExpiry(milliseconds) {
    if (this.leaseTimer !== null) this.clearTimeoutFn(this.leaseTimer);
    this.leaseTimer = this.setTimeoutFn(() => {
      this.leaseTimer = null;
      if (!this.controller || this.leaseDeadline === null) return;
      const remaining = this.leaseDeadline - this.now();
      if (remaining > 0) {
        this.scheduleLeaseExpiry(remaining);
        return;
      }
      this.expireController({ reason: "controller_lease_expired", closeConnection: true });
    }, milliseconds);
  }

  startStateHeartbeat() {
    this.stopStateHeartbeat();
    if (!this.connection.acceptedScopes.includes(SCOPES.READ)) return;
    this.stateHeartbeat = this.setIntervalFn(() => {
      if (this.phase !== "ready") return;
      try {
        this.publishState();
      } catch (error) {
        this.stopStateHeartbeat();
        this.connection.protocolError(error);
      }
    }, this.stateHeartbeatMs);
  }

  stopStateHeartbeat() {
    if (this.stateHeartbeat === null) return;
    this.clearIntervalFn(this.stateHeartbeat);
    this.stateHeartbeat = null;
  }

  expireController({ reason = "controller_lease_expired", closeConnection = false } = {}) {
    if (!this.controller) return;
    const expiredControllerId = this.controller.id;
    this.controller = null;
    this.leaseDeadline = null;
    if (this.leaseTimer !== null) this.clearTimeoutFn(this.leaseTimer);
    this.leaseTimer = null;
    this.stopStateHeartbeat();
    let callbackError;
    try {
      this.onLeaseExpired?.({ controllerId: expiredControllerId, reason });
    } catch (error) {
      callbackError = error;
    }
    this.dispatchEvent(detailEvent("leaseexpired", {
      ...this.status(),
      controllerId: expiredControllerId,
      reason,
    }));
    if (closeConnection) {
      void this.connection.close().catch((error) => {
        this.dispatchEvent(detailEvent("protocolerror", { message: error.message }));
      });
    }
    if (callbackError) {
      this.dispatchEvent(detailEvent("protocolerror", {
        message: callbackError instanceof Error ? callbackError.message : String(callbackError),
      }));
    }
    return true;
  }

  beforeStop() {
    this.expireController({ reason: "local_stop" });
    this.stopStateHeartbeat();
  }
}

export function remoteActionsForTarget(actions, grantedScopes) {
  return actionsForScopes(actions, grantedScopes);
}
