export const PROTOCOL = "brsp";
export const PROTOCOL_VERSION = 1;
export const SNAPSHOT_SCHEMA = "pps-runner-authority-snapshot.v1";
export const MAX_CONTROL_BYTES = 16 * 1024;

export const SCOPES = Object.freeze({
  READ: "session.read",
  PREPARE: "session.prepare",
  TRANSPORT: "session.transport",
  ANNOTATE: "session.annotate",
  ABORT: "session.abort",
});

export const DEFAULT_REMOTE_SCOPES = Object.freeze([
  SCOPES.READ,
  SCOPES.PREPARE,
  SCOPES.TRANSPORT,
]);

export const ACTION_SCOPE = Object.freeze({
  "system.snapshot": SCOPES.READ,
  "package.prepare_demo": SCOPES.PREPARE,
  "setup.submit": SCOPES.PREPARE,
  "part.start": SCOPES.TRANSPORT,
  "instruction.continue": SCOPES.TRANSPORT,
  "run.pause": SCOPES.TRANSPORT,
  "run.resume": SCOPES.TRANSPORT,
  "run.stop": SCOPES.ABORT,
  "run.abort": SCOPES.ABORT,
  "session.note": SCOPES.ANNOTATE,
});

export const LOCAL_ONLY_ACTIONS = Object.freeze([
  "target.arm",
  "target.disarm",
  "run.complete_demo",
]);

export const ALL_ACTIONS = Object.freeze([
  "system.snapshot",
  "package.prepare_demo",
  "setup.submit",
  "target.arm",
  "target.disarm",
  "part.start",
  "instruction.continue",
  "run.pause",
  "run.resume",
  "run.stop",
  "run.abort",
  "run.complete_demo",
  "session.note",
]);

export function requiredScope(action) {
  return ACTION_SCOPE[action] ?? null;
}

export function isKnownAction(action) {
  return ALL_ACTIONS.includes(action);
}

export function isRemoteAction(action) {
  return Object.hasOwn(ACTION_SCOPE, action);
}

export function intersectScopes(requested, available) {
  const availableSet = new Set(available);
  return [...new Set(requested)].filter((scope) => availableSet.has(scope)).sort();
}

export function actionsForScopes(actions, grantedScopes) {
  const granted = new Set(grantedScopes);
  return actions.filter((action) => {
    const scope = requiredScope(action);
    return scope !== null && granted.has(scope);
  });
}

const RUNNER_PHASES = new Set([
  "idle", "prepared", "ready", "instruction_gate", "running", "paused",
  "stopping", "completed", "interrupted", "error",
]);
const TIMING_TIERS = new Set([
  "desktop_preview", "browser_exploratory", "native_quest_unqualified", "native_qualified",
]);
const SNAPSHOT_TOKEN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$/u;

function plainObject(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(`${label} must be an object.`);
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    throw new TypeError(`${label} must be a plain object.`);
  }
  return value;
}

function exactObject(value, fields, label) {
  const object = plainObject(value, label);
  const actual = Object.keys(object).sort();
  const expected = [...fields].sort();
  if (actual.length !== expected.length || actual.some((field, index) => field !== expected[index])) {
    throw new TypeError(`${label} fields are invalid.`);
  }
  return object;
}

function snapshotString(value, label, maximum = 512) {
  if (typeof value !== "string" || value.length > maximum) {
    throw new TypeError(`${label} must be a bounded string.`);
  }
  return value;
}

function snapshotBoolean(value, label) {
  if (typeof value !== "boolean") throw new TypeError(`${label} must be boolean.`);
  return value;
}

function snapshotUint(value, label, maximum = Number.MAX_SAFE_INTEGER) {
  if (!Number.isSafeInteger(value) || value < 0 || value > maximum) {
    throw new TypeError(`${label} must be a bounded unsigned integer.`);
  }
  return value;
}

function nullable(value, validate) {
  if (value !== null) validate(value);
}

function stringArray(value, label, maximum = 256) {
  if (!Array.isArray(value) || value.length > maximum) {
    throw new TypeError(`${label} must be a bounded array.`);
  }
  value.forEach((entry, index) => snapshotString(entry, `${label}[${index}]`));
  return value;
}

function validateIdentity(value) {
  const identity = exactObject(value, [
    "participant_id", "selected_participant_id", "session_id", "session_group_id", "part_session_id",
  ], "snapshot.identity");
  Object.entries(identity).forEach(([field, entry]) => snapshotString(entry, `snapshot.identity.${field}`));
}

function validateSetup(value) {
  const setup = exactObject(value, [
    "submitted", "ready", "required_missing", "participant_code", "participant_name_present",
    "name_sharing_opt_in", "age", "handedness", "gender", "part_labels", "part_label_options",
    "part_label_controls_visible",
  ], "snapshot.setup");
  snapshotBoolean(setup.submitted, "snapshot.setup.submitted");
  snapshotBoolean(setup.ready, "snapshot.setup.ready");
  stringArray(setup.required_missing, "snapshot.setup.required_missing", 32);
  snapshotString(setup.participant_code, "snapshot.setup.participant_code", 32);
  snapshotBoolean(setup.participant_name_present, "snapshot.setup.participant_name_present");
  snapshotBoolean(setup.name_sharing_opt_in, "snapshot.setup.name_sharing_opt_in");
  nullable(setup.age, (age) => snapshotUint(age, "snapshot.setup.age", 255));
  snapshotString(setup.handedness, "snapshot.setup.handedness", 32);
  snapshotString(setup.gender, "snapshot.setup.gender", 32);
  const labels = plainObject(setup.part_labels, "snapshot.setup.part_labels");
  if (Object.keys(labels).length > 32) throw new TypeError("snapshot.setup.part_labels is too large.");
  for (const [key, label] of Object.entries(labels)) {
    if (!SNAPSHOT_TOKEN.test(key)) throw new TypeError("snapshot.setup.part_labels has an invalid key.");
    snapshotString(label, `snapshot.setup.part_labels.${key}`, 80);
  }
  stringArray(setup.part_label_options, "snapshot.setup.part_label_options", 32);
  snapshotBoolean(setup.part_label_controls_visible, "snapshot.setup.part_label_controls_visible");
}

function validatePart(value) {
  const part = exactObject(value, [
    "available_parts", "selected_part", "current_package_part", "pending_start_part",
  ], "snapshot.part");
  if (!Array.isArray(part.available_parts) || part.available_parts.length > 256) {
    throw new TypeError("snapshot.part.available_parts must be a bounded array.");
  }
  part.available_parts.forEach((entry, index) => snapshotUint(entry, `snapshot.part.available_parts[${index}]`, 255));
  if (new Set(part.available_parts).size !== part.available_parts.length) {
    throw new TypeError("snapshot.part.available_parts must not contain duplicates.");
  }
  for (const field of ["selected_part", "current_package_part", "pending_start_part"]) {
    nullable(part[field], (entry) => snapshotUint(entry, `snapshot.part.${field}`, 255));
  }
}

function validateRun(value) {
  const run = exactObject(value, [
    "phase", "state_label", "progress_label", "event_label", "thread_alive", "complete",
  ], "snapshot.run");
  if (!RUNNER_PHASES.has(run.phase)) throw new TypeError("snapshot.run.phase is invalid.");
  snapshotString(run.state_label, "snapshot.run.state_label");
  snapshotString(run.progress_label, "snapshot.run.progress_label");
  snapshotString(run.event_label, "snapshot.run.event_label");
  snapshotBoolean(run.thread_alive, "snapshot.run.thread_alive");
  snapshotBoolean(run.complete, "snapshot.run.complete");
}

function validateInstructionGate(value) {
  const gate = exactObject(value, [
    "waiting", "gate_id", "part2_start_gate", "instruction_label", "button_label", "next_action",
  ], "snapshot.instruction_gate");
  snapshotBoolean(gate.waiting, "snapshot.instruction_gate.waiting");
  snapshotString(gate.gate_id, "snapshot.instruction_gate.gate_id", 96);
  snapshotBoolean(gate.part2_start_gate, "snapshot.instruction_gate.part2_start_gate");
  snapshotString(gate.instruction_label, "snapshot.instruction_gate.instruction_label");
  snapshotString(gate.button_label, "snapshot.instruction_gate.button_label");
  snapshotString(gate.next_action, "snapshot.instruction_gate.next_action", 64);
  if (gate.next_action && !isKnownAction(gate.next_action)) {
    throw new TypeError("snapshot.instruction_gate.next_action is unknown.");
  }
}

function validateActiveBlock(value) {
  const block = exactObject(value, [
    "active", "part_number", "phase_label", "block_index", "block_label", "display_block_index",
    "duration_s", "elapsed_s", "last_anchor_server_monotonic_ns", "running", "paused",
    "instruction_waiting",
  ], "snapshot.active_block");
  snapshotBoolean(block.active, "snapshot.active_block.active");
  nullable(block.part_number, (entry) => snapshotUint(entry, "snapshot.active_block.part_number", 255));
  snapshotString(block.phase_label, "snapshot.active_block.phase_label");
  nullable(block.block_index, (entry) => snapshotUint(entry, "snapshot.active_block.block_index", 0xffff_ffff));
  snapshotString(block.block_label, "snapshot.active_block.block_label");
  nullable(block.display_block_index, (entry) => snapshotUint(entry, "snapshot.active_block.display_block_index", 0xffff_ffff));
  for (const field of ["duration_s", "elapsed_s"]) {
    nullable(block[field], (entry) => {
      if (typeof entry !== "number" || !Number.isFinite(entry) || entry < 0) {
        throw new TypeError(`snapshot.active_block.${field} must be a finite non-negative number.`);
      }
    });
  }
  nullable(block.last_anchor_server_monotonic_ns, (entry) => snapshotUint(entry, "snapshot.active_block.last_anchor_server_monotonic_ns"));
  snapshotBoolean(block.running, "snapshot.active_block.running");
  snapshotBoolean(block.paused, "snapshot.active_block.paused");
  snapshotBoolean(block.instruction_waiting, "snapshot.active_block.instruction_waiting");
}

function validateSafety(value) {
  const safety = exactObject(value, [
    "controller_lease_id", "lease_expires_at_unix_ms", "local_override", "local_armed",
    "audio_route_ready", "publication_ready", "lsl_ready", "capture_started",
  ], "snapshot.safety");
  snapshotString(safety.controller_lease_id, "snapshot.safety.controller_lease_id", 96);
  nullable(safety.lease_expires_at_unix_ms, (entry) => snapshotUint(entry, "snapshot.safety.lease_expires_at_unix_ms"));
  for (const field of [
    "local_override", "local_armed", "audio_route_ready", "publication_ready", "lsl_ready", "capture_started",
  ]) snapshotBoolean(safety[field], `snapshot.safety.${field}`);
}

/** Validate the complete versioned PPS authority snapshot before UI adoption. */
export function validateRunnerSnapshot(value) {
  const snapshot = exactObject(value, [
    "schema", "protocol", "target_id", "target_kind", "epoch", "revision", "server_unix_ms",
    "server_monotonic_ns", "connection_state", "timing_tier", "package_verified", "package_label",
    "allowed_actions", "identity", "setup", "part", "run", "instruction_gate", "active_block",
    "safety", "audit_event_count", "last_note",
  ], "snapshot");
  if (snapshot.schema !== SNAPSHOT_SCHEMA || snapshot.protocol !== PROTOCOL) {
    throw new TypeError("snapshot schema or protocol is unsupported.");
  }
  if (typeof snapshot.target_id !== "string" || !SNAPSHOT_TOKEN.test(snapshot.target_id)) {
    throw new TypeError("snapshot.target_id is invalid.");
  }
  snapshotString(snapshot.target_kind, "snapshot.target_kind", 96);
  snapshotUint(snapshot.epoch, "snapshot.epoch");
  snapshotUint(snapshot.revision, "snapshot.revision");
  snapshotUint(snapshot.server_unix_ms, "snapshot.server_unix_ms");
  snapshotUint(snapshot.server_monotonic_ns, "snapshot.server_monotonic_ns");
  snapshotString(snapshot.connection_state, "snapshot.connection_state", 64);
  if (!TIMING_TIERS.has(snapshot.timing_tier)) throw new TypeError("snapshot.timing_tier is invalid.");
  snapshotBoolean(snapshot.package_verified, "snapshot.package_verified");
  snapshotString(snapshot.package_label, "snapshot.package_label", 256);
  if (!Array.isArray(snapshot.allowed_actions) || snapshot.allowed_actions.length > ALL_ACTIONS.length
    || new Set(snapshot.allowed_actions).size !== snapshot.allowed_actions.length
    || snapshot.allowed_actions.some((action) => !isKnownAction(action))) {
    throw new TypeError("snapshot.allowed_actions is invalid.");
  }
  validateIdentity(snapshot.identity);
  validateSetup(snapshot.setup);
  validatePart(snapshot.part);
  validateRun(snapshot.run);
  validateInstructionGate(snapshot.instruction_gate);
  validateActiveBlock(snapshot.active_block);
  validateSafety(snapshot.safety);
  snapshotUint(snapshot.audit_event_count, "snapshot.audit_event_count");
  snapshotString(snapshot.last_note, "snapshot.last_note", 512);
  return snapshot;
}
