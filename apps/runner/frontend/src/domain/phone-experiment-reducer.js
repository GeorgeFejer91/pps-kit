import { SNAPSHOT_SCHEMA } from "./runner-contract.js";

const ACTIVE_PHASES = new Set(["instruction_gate", "running", "paused", "stopping"]);
const PARTICIPANT_CODE = /^[A-Za-z0-9_-]{1,64}$/u;

function clone(value) {
  return structuredClone(value);
}

function safeString(value, maximum) {
  const text = String(value ?? "").trim();
  if (text.length > maximum || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(text)) {
    throw new TypeError(`Text must be display-safe and at most ${maximum} characters.`);
  }
  return text;
}

function stamp(snapshot, clock) {
  const value = clock();
  if (!Number.isSafeInteger(value.unixMs) || !Number.isSafeInteger(value.monotonicNs)) {
    throw new TypeError("Browser target clocks must remain JavaScript-safe integers.");
  }
  snapshot.server_unix_ms = value.unixMs;
  snapshot.server_monotonic_ns = value.monotonicNs;
}

function advance(snapshot, clock) {
  snapshot.revision += 1;
  snapshot.audit_event_count += 1;
  stamp(snapshot, clock);
}

export function allowedPhoneActions(snapshot) {
  const actions = ["system.snapshot", "session.note"];
  if (!ACTIVE_PHASES.has(snapshot.run.phase)) actions.push("setup.submit");
  if (["idle", "prepared", "ready", "completed", "interrupted"].includes(snapshot.run.phase)) {
    actions.push("package.prepare_demo");
  }
  if (snapshot.package_verified && snapshot.setup.ready && !snapshot.safety.local_armed) actions.push("target.arm");
  if (snapshot.safety.local_armed) actions.push("target.disarm");
  if (snapshot.run.phase === "ready") actions.push("part.start");
  if (snapshot.run.phase === "instruction_gate") actions.push("instruction.continue", "run.stop", "run.abort");
  if (snapshot.run.phase === "running") actions.push("run.pause", "run.stop", "run.abort", "run.complete_demo");
  if (snapshot.run.phase === "paused") actions.push("run.resume", "run.stop", "run.abort");
  return [...new Set(actions)];
}

function updateDerived(snapshot) {
  const phase = snapshot.run.phase;
  snapshot.run.thread_alive = ACTIVE_PHASES.has(phase);
  snapshot.run.complete = phase === "completed";
  snapshot.run.state_label = phase.replaceAll("_", " ").replace(/\b\w/gu, (value) => value.toUpperCase());
  snapshot.active_block.running = phase === "running";
  snapshot.active_block.paused = phase === "paused";
  snapshot.active_block.instruction_waiting = phase === "instruction_gate";
  snapshot.instruction_gate.waiting = phase === "instruction_gate";
  snapshot.allowed_actions = allowedPhoneActions(snapshot);
}

export function createPhoneExperimentSnapshot({
  targetId,
  epoch,
  clock = () => ({
    unixMs: Date.now(),
    monotonicNs: Math.floor(performance.now() * 1_000_000),
  }),
} = {}) {
  const snapshot = {
    schema: SNAPSHOT_SCHEMA,
    protocol: "brsp",
    target_id: targetId,
    target_kind: "browser_phone",
    epoch,
    revision: 0,
    server_unix_ms: 0,
    server_monotonic_ns: 0,
    connection_state: "local_only",
    timing_tier: "browser_exploratory",
    package_verified: false,
    package_label: "No demo prepared",
    allowed_actions: [],
    identity: {
      participant_id: "",
      selected_participant_id: "",
      session_id: `phone-${epoch}`,
      session_group_id: "browser-exploratory",
      part_session_id: "phone-demo-part-1",
    },
    setup: {
      submitted: false,
      ready: false,
      required_missing: ["participant_code"],
      participant_code: "",
      participant_name_present: false,
      name_sharing_opt_in: false,
      age: null,
      handedness: "unspecified",
      gender: "unspecified",
      part_labels: { "1": "Phone demo" },
      part_label_options: ["Phone demo"],
      part_label_controls_visible: false,
    },
    part: {
      available_parts: [1],
      selected_part: 1,
      current_package_part: 1,
      pending_start_part: null,
    },
    run: {
      phase: "idle",
      state_label: "Idle",
      progress_label: "Prepare the exploratory demo and submit setup.",
      event_label: "Waiting for local setup",
      thread_alive: false,
      complete: false,
    },
    instruction_gate: {
      waiting: false,
      gate_id: "",
      part2_start_gate: false,
      instruction_label: "",
      button_label: "Continue",
      next_action: "instruction.continue",
    },
    active_block: {
      active: false,
      part_number: null,
      phase_label: "Exploratory phone demo",
      block_index: null,
      block_label: "",
      display_block_index: null,
      duration_s: null,
      elapsed_s: null,
      last_anchor_server_monotonic_ns: null,
      running: false,
      paused: false,
      instruction_waiting: false,
    },
    safety: {
      controller_lease_id: "",
      lease_expires_at_unix_ms: null,
      local_override: false,
      local_armed: false,
      audio_route_ready: false,
      publication_ready: false,
      lsl_ready: false,
      capture_started: false,
    },
    audit_event_count: 0,
    last_note: "",
  };
  stamp(snapshot, clock);
  updateDerived(snapshot);
  return snapshot;
}

function accepted(snapshot, previousRevision, action, clock, effects = []) {
  advance(snapshot, clock);
  updateDerived(snapshot);
  return {
    status: "accepted",
    reason: "applied",
    acceptedRevision: previousRevision,
    resultingRevision: snapshot.revision,
    snapshot,
    effects,
    event: { action, revision: snapshot.revision, unix_ms: snapshot.server_unix_ms },
  };
}

function rejected(current, action, reason, clock) {
  const snapshot = clone(current);
  stamp(snapshot, clock);
  return {
    status: "rejected",
    reason,
    acceptedRevision: current.revision,
    resultingRevision: current.revision,
    snapshot,
    effects: [],
    event: { action, revision: current.revision, unix_ms: snapshot.server_unix_ms, rejected: true, reason },
  };
}

export function applyPhoneAction(current, action, args = {}, {
  clock = () => ({ unixMs: Date.now(), monotonicNs: Math.floor(performance.now() * 1_000_000) }),
  expectedRevision = null,
} = {}) {
  if (expectedRevision !== null && expectedRevision !== current.revision) {
    return rejected(current, action, "revision_conflict", clock);
  }
  if (!current.allowed_actions.includes(action)) return rejected(current, action, "invalid_transition", clock);
  if (action === "system.snapshot") {
    const snapshot = clone(current);
    stamp(snapshot, clock);
    return {
      status: "accepted",
      reason: "snapshot",
      acceptedRevision: current.revision,
      resultingRevision: current.revision,
      snapshot,
      effects: [],
      event: { action, revision: current.revision, unix_ms: snapshot.server_unix_ms },
    };
  }

  const snapshot = clone(current);
  const previousRevision = current.revision;
  const effects = [];
  try {
    switch (action) {
      case "package.prepare_demo": {
        if (snapshot.safety.local_armed) effects.push({ type: "outputs.stop" });
        snapshot.package_verified = true;
        snapshot.package_label = "Phone looming demo • exploratory timing";
        snapshot.safety.local_armed = false;
        snapshot.safety.audio_route_ready = false;
        snapshot.run.phase = "prepared";
        snapshot.run.progress_label = "Demo assets generated in this browser.";
        snapshot.run.event_label = "Demo prepared";
        break;
      }
      case "setup.submit": {
        const participantCode = String(args.participant_code ?? "").trim();
        if (!PARTICIPANT_CODE.test(participantCode)) return rejected(current, action, "invalid_participant_code", clock);
        const age = args.age === null || args.age === "" || args.age === undefined ? null : Number(args.age);
        if (age !== null && (!Number.isInteger(age) || age < 0 || age > 120)) return rejected(current, action, "invalid_age", clock);
        const participantName = safeString(args.participant_name, 80);
        snapshot.setup = {
          ...snapshot.setup,
          submitted: true,
          ready: true,
          required_missing: [],
          participant_code: participantCode,
          participant_name_present: participantName.length > 0,
          name_sharing_opt_in: Boolean(args.name_sharing_opt_in),
          age,
          handedness: safeString(args.handedness || "unspecified", 32),
          gender: safeString(args.gender || "unspecified", 32),
        };
        snapshot.identity.participant_id = participantCode;
        snapshot.identity.selected_participant_id = participantCode;
        if (snapshot.safety.local_armed) effects.push({ type: "outputs.stop" });
        snapshot.safety.local_armed = false;
        snapshot.safety.audio_route_ready = false;
        snapshot.run.phase = snapshot.package_verified ? "prepared" : "idle";
        snapshot.run.event_label = "Participant setup stored in browser memory";
        break;
      }
      case "target.arm": {
        snapshot.safety.local_armed = true;
        snapshot.safety.audio_route_ready = Boolean(args.audio_enabled);
        snapshot.run.phase = snapshot.package_verified && snapshot.setup.ready ? "ready" : snapshot.run.phase;
        snapshot.run.event_label = "Phone outputs armed by local gesture";
        effects.push({ type: "outputs.arm" });
        break;
      }
      case "target.disarm": {
        snapshot.safety.local_armed = false;
        snapshot.safety.audio_route_ready = false;
        snapshot.safety.local_override = ACTIVE_PHASES.has(snapshot.run.phase);
        if (ACTIVE_PHASES.has(snapshot.run.phase)) snapshot.run.phase = "interrupted";
        else if (snapshot.package_verified) snapshot.run.phase = "prepared";
        snapshot.active_block.active = false;
        snapshot.run.event_label = "Phone outputs disarmed locally";
        effects.push({ type: "outputs.stop" });
        break;
      }
      case "part.start": {
        snapshot.run.phase = "running";
        snapshot.run.progress_label = "Exploratory looming demo running";
        snapshot.run.event_label = "Looming audio and tactile demo started";
        snapshot.active_block = {
          ...snapshot.active_block,
          active: true,
          part_number: 1,
          block_index: 0,
          block_label: "Phone demo",
          display_block_index: 1,
          duration_s: 3,
          elapsed_s: 0,
          last_anchor_server_monotonic_ns: snapshot.server_monotonic_ns,
        };
        effects.push({ type: "demo.start" });
        break;
      }
      case "instruction.continue": {
        snapshot.run.phase = "running";
        snapshot.instruction_gate.gate_id = "";
        snapshot.instruction_gate.instruction_label = "";
        snapshot.run.event_label = "Instruction gate continued";
        effects.push({ type: "demo.start" });
        break;
      }
      case "run.pause": {
        snapshot.run.phase = "paused";
        snapshot.run.event_label = "Paused by semantic command";
        effects.push({ type: "demo.pause" });
        break;
      }
      case "run.resume": {
        snapshot.run.phase = "running";
        snapshot.run.event_label = "Resumed; exploratory demo restarts locally";
        effects.push({ type: "demo.start" });
        break;
      }
      case "run.stop": {
        snapshot.run.phase = "completed";
        snapshot.run.progress_label = "Exploratory demo stopped";
        snapshot.run.event_label = "Stopped cleanly";
        snapshot.active_block.active = false;
        effects.push({ type: "demo.stop" });
        break;
      }
      case "run.abort": {
        snapshot.run.phase = "interrupted";
        snapshot.run.progress_label = "Exploratory demo aborted";
        snapshot.run.event_label = "Abort applied";
        snapshot.active_block.active = false;
        snapshot.safety.local_override = true;
        effects.push({ type: "demo.stop" });
        break;
      }
      case "run.complete_demo": {
        snapshot.run.phase = "completed";
        snapshot.run.progress_label = "Exploratory phone trial complete";
        snapshot.run.event_label = "Browser demo completed locally";
        snapshot.active_block.active = false;
        snapshot.active_block.elapsed_s = snapshot.active_block.duration_s;
        effects.push({ type: "demo.stop" });
        break;
      }
      case "session.note": {
        const note = safeString(args.text ?? args.note, 500);
        if (!note) return rejected(current, action, "empty_note", clock);
        snapshot.last_note = note;
        snapshot.run.event_label = "Session note recorded";
        break;
      }
      default: return rejected(current, action, "unknown_action", clock);
    }
  } catch {
    return rejected(current, action, "invalid_arguments", clock);
  }
  return accepted(snapshot, previousRevision, action, clock, effects);
}

export function expirePhoneLease(current, {
  clock = () => ({ unixMs: Date.now(), monotonicNs: Math.floor(performance.now() * 1_000_000) }),
} = {}) {
  const snapshot = clone(current);
  const previousRevision = current.revision;
  snapshot.safety.controller_lease_id = "";
  snapshot.safety.lease_expires_at_unix_ms = null;
  if (snapshot.run.phase === "running") {
    snapshot.run.phase = "paused";
    snapshot.run.event_label = "Controller lease expired; target paused locally";
  }
  return accepted(snapshot, previousRevision, "system.lease_expired", clock, [{ type: "demo.pause" }]);
}

export function setPhoneConnectionMetadata(current, {
  connectionState,
  controllerId = "",
  leaseExpiresAtUnixMs = null,
  clock = () => ({ unixMs: Date.now(), monotonicNs: Math.floor(performance.now() * 1_000_000) }),
} = {}) {
  const snapshot = clone(current);
  snapshot.connection_state = connectionState;
  snapshot.safety.controller_lease_id = controllerId;
  snapshot.safety.lease_expires_at_unix_ms = leaseExpiresAtUnixMs;
  stamp(snapshot, clock);
  updateDerived(snapshot);
  return snapshot;
}
