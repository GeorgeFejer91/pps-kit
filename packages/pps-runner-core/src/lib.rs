//! Pure target-authoritative state machine for PPS runners.
//!
//! This crate deliberately owns no UI, transport, filesystem, audio, or Android
//! types. Native targets call the same reducer for local and authenticated remote
//! operations; platform adapters remain responsible for precise media timing.

use std::collections::{BTreeMap, BTreeSet, VecDeque};

use pps_contracts::{
    Action, ActiveBlockSnapshot, Applied, AppliedStatus, ClockStamp, CommandRequest,
    IdentitySnapshot, InstructionGateSnapshot, PartSnapshot, RunSnapshot, RunnerPhase,
    RunnerSnapshot, SafetySnapshot, Scope, SetupSnapshot, TimingTier, BRSP_PROTOCOL,
    JSON_MAX_SAFE_INTEGER, MAX_STATE_BYTES, SNAPSHOT_SCHEMA,
};
use serde::Deserialize;
use serde_json::Value;

const DEDUPE_LIMIT: usize = 256;
const MIN_COMMAND_ID_BYTES: usize = 8;
const MAX_COMMAND_ID_BYTES: usize = 96;
const MAX_NOTE_BYTES: usize = 512;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DispatchOrigin {
    Local,
    Remote {
        controller_id: String,
        granted_scopes: BTreeSet<Scope>,
        lease_valid: bool,
    },
}

impl DispatchOrigin {
    fn is_remote(&self) -> bool {
        matches!(self, Self::Remote { .. })
    }

    fn dedupe_principal(&self) -> DedupePrincipal {
        match self {
            Self::Local => DedupePrincipal::Local,
            Self::Remote { controller_id, .. } => DedupePrincipal::Remote(controller_id.clone()),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum DedupePrincipal {
    Local,
    Remote(String),
}

#[derive(Debug, Clone)]
struct DedupeEntry {
    principal: DedupePrincipal,
    command_id: String,
    fingerprint: Vec<u8>,
    result: Applied,
}

#[derive(Debug, Clone)]
pub struct RunnerCore {
    snapshot: RunnerSnapshot,
    dedupe: VecDeque<DedupeEntry>,
    local_sequence: u64,
}

impl RunnerCore {
    pub fn new(
        target_id: impl Into<String>,
        target_kind: impl Into<String>,
        epoch: u64,
        timing_tier: TimingTier,
        now: ClockStamp,
    ) -> Self {
        let mut part_labels = BTreeMap::new();
        part_labels.insert("1".to_owned(), "Part 01".to_owned());
        part_labels.insert("2".to_owned(), "Part 02".to_owned());
        let mut core = Self {
            snapshot: RunnerSnapshot {
                schema: SNAPSHOT_SCHEMA.to_owned(),
                protocol: BRSP_PROTOCOL.to_owned(),
                target_id: target_id.into(),
                target_kind: target_kind.into(),
                epoch,
                revision: 0,
                server_unix_ms: now.unix_ms.min(JSON_MAX_SAFE_INTEGER),
                server_monotonic_ns: now.monotonic_ns.min(JSON_MAX_SAFE_INTEGER),
                connection_state: "local_only".to_owned(),
                timing_tier,
                package_verified: false,
                package_label: "No prepared package".to_owned(),
                allowed_actions: Vec::new(),
                identity: IdentitySnapshot {
                    participant_id: String::new(),
                    selected_participant_id: "P001".to_owned(),
                    session_id: String::new(),
                    session_group_id: String::new(),
                    part_session_id: String::new(),
                },
                setup: SetupSnapshot {
                    submitted: false,
                    ready: false,
                    required_missing: vec![
                        "participant_code".to_owned(),
                        "age".to_owned(),
                        "handedness".to_owned(),
                        "gender".to_owned(),
                    ],
                    participant_code: "P001".to_owned(),
                    participant_name_present: false,
                    name_sharing_opt_in: false,
                    age: None,
                    handedness: String::new(),
                    gender: String::new(),
                    part_labels,
                    part_label_options: vec![
                        "Same condition".to_owned(),
                        "Different condition".to_owned(),
                        "Baseline".to_owned(),
                        "Experimental".to_owned(),
                    ],
                    part_label_controls_visible: true,
                },
                part: PartSnapshot {
                    available_parts: vec![1, 2],
                    selected_part: None,
                    current_package_part: None,
                    pending_start_part: None,
                },
                run: RunSnapshot {
                    phase: RunnerPhase::Idle,
                    state_label: "Idle".to_owned(),
                    progress_label: "Prepare a validated session package".to_owned(),
                    event_label: "Waiting for setup".to_owned(),
                    thread_alive: false,
                    complete: false,
                },
                instruction_gate: InstructionGateSnapshot {
                    waiting: false,
                    gate_id: String::new(),
                    part2_start_gate: false,
                    instruction_label: String::new(),
                    button_label: "Continue".to_owned(),
                    next_action: String::new(),
                },
                active_block: ActiveBlockSnapshot {
                    active: false,
                    part_number: None,
                    phase_label: String::new(),
                    block_index: None,
                    block_label: String::new(),
                    display_block_index: None,
                    duration_s: None,
                    elapsed_s: None,
                    last_anchor_server_monotonic_ns: None,
                    running: false,
                    paused: false,
                    instruction_waiting: false,
                },
                safety: SafetySnapshot {
                    controller_lease_id: String::new(),
                    lease_expires_at_unix_ms: None,
                    local_override: true,
                    local_armed: false,
                    audio_route_ready: false,
                    publication_ready: false,
                    lsl_ready: false,
                    capture_started: false,
                },
                audit_event_count: 0,
                last_note: String::new(),
            },
            dedupe: VecDeque::new(),
            local_sequence: 0,
        };
        core.refresh_derived();
        core
    }

    pub fn snapshot(&self) -> RunnerSnapshot {
        self.snapshot.clone()
    }

    pub fn epoch(&self) -> u64 {
        self.snapshot.epoch
    }

    pub fn revision(&self) -> u64 {
        self.snapshot.revision
    }

    pub fn set_connection_state(&mut self, state: &str, now: ClockStamp) -> RunnerSnapshot {
        let normalized = if state.len() <= 48 && state.chars().all(is_safe_token_char) {
            state
        } else {
            "unknown"
        };
        if self.snapshot.connection_state != normalized {
            self.snapshot.connection_state = normalized.to_owned();
            self.bump_revision(&now);
        } else {
            self.stamp(&now);
        }
        self.snapshot()
    }

    pub fn set_controller_lease(
        &mut self,
        controller_id: Option<&str>,
        expires_at_unix_ms: Option<u64>,
        now: ClockStamp,
    ) -> RunnerSnapshot {
        let lease_id = controller_id.unwrap_or_default();
        // Lease freshness is transport state, not a scientific state transition.
        // Only ownership changes advance the CAS revision; keepalive extensions do
        // not invalidate an otherwise current controller command.
        let changed = self.snapshot.safety.controller_lease_id != lease_id;
        self.snapshot.safety.controller_lease_id = lease_id.to_owned();
        self.snapshot.safety.lease_expires_at_unix_ms = expires_at_unix_ms;
        if changed {
            self.bump_revision(&now);
        } else {
            self.stamp(&now);
        }
        self.snapshot()
    }

    pub fn rotate_epoch(&mut self, new_epoch: u64, now: ClockStamp) -> RunnerSnapshot {
        if self.snapshot.epoch != new_epoch {
            self.snapshot.epoch = new_epoch;
            self.dedupe.clear();
            self.bump_revision(&now);
        } else {
            self.stamp(&now);
        }
        self.snapshot()
    }

    pub fn dispatch_local(&mut self, action: Action, args: Value, now: ClockStamp) -> Applied {
        self.local_sequence = self.local_sequence.saturating_add(1);
        let command = CommandRequest {
            id: format!("local-{}-{}", self.snapshot.epoch, self.local_sequence),
            epoch: self.snapshot.epoch,
            sequence: self.local_sequence,
            expected_revision: Some(self.snapshot.revision),
            scope: action.required_scope().unwrap_or(Scope::SessionRead),
            action,
            args,
        };
        self.dispatch(DispatchOrigin::Local, command, now)
    }

    pub fn dispatch(
        &mut self,
        origin: DispatchOrigin,
        command: CommandRequest,
        now: ClockStamp,
    ) -> Applied {
        self.stamp(&now);
        // BRSP retries keep the command body identical but wrap it in a fresh
        // control envelope sequence. Dedupe therefore binds commandId to the
        // application command body and authenticated authority principal, not
        // transport/session replay metadata. Local and remote identifiers must
        // never share a namespace: otherwise a controller could pre-seed a
        // predictable local command ID and suppress a later operator action.
        let principal = origin.dedupe_principal();
        let fingerprint = serde_json::to_vec(&serde_json::json!({
            "scope": command.scope,
            "action": command.action,
            "args": command.args,
            "expectedRevision": command.expected_revision,
        }))
        .unwrap_or_default();
        if let Some(previous) = self
            .dedupe
            .iter()
            .find(|entry| entry.principal == principal && entry.command_id == command.id)
        {
            if previous.fingerprint != fingerprint {
                return self.rejected(&command, "command_id_reused_with_different_payload");
            }
            // BRSP retries rewrap this identical logical result in a fresh
            // transport envelope. Do not rewrite rejection into success (or
            // update its revision/snapshot) merely to annotate a duplicate.
            return previous.result.clone();
        }

        let accepted_revision = self.snapshot.revision;
        let rejection = self.validate_command(&origin, &command).err();
        let result = if let Some(reason) = rejection {
            self.rejected(&command, reason)
        } else {
            match self.apply_action(&origin, &command.action, &command.args, &now) {
                Ok(changed) => {
                    if changed {
                        self.snapshot.audit_event_count =
                            self.snapshot.audit_event_count.saturating_add(1);
                        self.bump_revision(&now);
                    } else {
                        self.refresh_derived();
                    }
                    Applied {
                        id: command.id.clone(),
                        action: command.action,
                        status: AppliedStatus::Accepted,
                        reason: if changed {
                            "applied".to_owned()
                        } else {
                            "already_in_requested_state".to_owned()
                        },
                        accepted_revision,
                        resulting_revision: self.snapshot.revision,
                        snapshot: self.snapshot(),
                    }
                }
                Err(reason) => self.rejected(&command, reason),
            }
        };
        self.remember(principal, command.id, fingerprint, result.clone());
        result
    }

    fn validate_command(
        &self,
        origin: &DispatchOrigin,
        command: &CommandRequest,
    ) -> Result<(), &'static str> {
        if !(MIN_COMMAND_ID_BYTES..=MAX_COMMAND_ID_BYTES).contains(&command.id.len())
            || !is_safe_command_id(&command.id)
        {
            return Err("invalid_command_id");
        }
        if command.epoch != self.snapshot.epoch {
            return Err("stale_epoch");
        }
        let invalid_sequence = match origin {
            DispatchOrigin::Local => {
                command.sequence == 0 || command.sequence > JSON_MAX_SAFE_INTEGER
            }
            // A fresh BRSP uint32 control sequence may canonically wrap from
            // 0xffff_ffff to zero. Preserve that exact wire value while still
            // rejecting callers that bypass the envelope's uint32 boundary.
            DispatchOrigin::Remote { .. } => command.sequence > u64::from(u32::MAX),
        };
        if command.epoch > JSON_MAX_SAFE_INTEGER
            || invalid_sequence
            || command
                .expected_revision
                .is_some_and(|revision| revision > JSON_MAX_SAFE_INTEGER)
        {
            return Err("json_integer_out_of_range");
        }
        if command.action.mutates_state()
            && command.expected_revision != Some(self.snapshot.revision)
        {
            return Err("revision_conflict");
        }
        if serde_json::to_vec(&command.args)
            .map(|bytes| bytes.len() > MAX_STATE_BYTES)
            .unwrap_or(true)
        {
            return Err("args_too_large_or_invalid");
        }
        validate_json_shape(&command.args, 0)?;
        if let DispatchOrigin::Remote {
            granted_scopes,
            lease_valid,
            ..
        } = origin
        {
            let required = command
                .action
                .required_scope()
                .ok_or("action_is_local_only")?;
            if required != command.scope {
                return Err("scope_action_mismatch");
            }
            if !granted_scopes.contains(&required) {
                return Err("scope_not_granted");
            }
            if command.action.mutates_state() && !lease_valid {
                return Err("controller_lease_expired");
            }
        }
        Ok(())
    }

    fn apply_action(
        &mut self,
        origin: &DispatchOrigin,
        action: &Action,
        args: &Value,
        now: &ClockStamp,
    ) -> Result<bool, &'static str> {
        match action {
            Action::SystemSnapshot => {
                expect_empty_args(args)?;
                Ok(false)
            }
            Action::PackagePrepareDemo => self.prepare_demo(args),
            Action::SetupSubmit => self.submit_setup(args),
            Action::TargetArm => {
                expect_empty_args(args)?;
                if origin.is_remote() {
                    return Err("local_arm_required");
                }
                if !self.snapshot.setup.ready || !self.snapshot.package_verified {
                    return Err("setup_or_package_not_ready");
                }
                if matches!(
                    self.snapshot.run.phase,
                    RunnerPhase::Running | RunnerPhase::Paused | RunnerPhase::InstructionGate
                ) {
                    return Err("run_already_active");
                }
                if self.snapshot.safety.local_armed && self.snapshot.run.phase == RunnerPhase::Ready
                {
                    return Ok(false);
                }
                self.snapshot.safety.local_armed = true;
                self.snapshot.run.phase = RunnerPhase::Ready;
                Ok(true)
            }
            Action::TargetDisarm => {
                expect_empty_args(args)?;
                if origin.is_remote() {
                    return Err("local_disarm_required");
                }
                if matches!(
                    self.snapshot.run.phase,
                    RunnerPhase::Running | RunnerPhase::Paused | RunnerPhase::InstructionGate
                ) {
                    return Err("cannot_disarm_active_run");
                }
                if !self.snapshot.safety.local_armed {
                    return Ok(false);
                }
                self.snapshot.safety.local_armed = false;
                self.snapshot.run.phase = RunnerPhase::Prepared;
                Ok(true)
            }
            Action::PartStart => self.start_part(args, now),
            Action::InstructionContinue => self.continue_instruction(args),
            Action::RunPause => {
                expect_empty_args(args)?;
                if self.snapshot.run.phase == RunnerPhase::Paused {
                    return Ok(false);
                }
                if self.snapshot.run.phase != RunnerPhase::Running {
                    return Err("run_is_not_running");
                }
                self.snapshot.run.phase = RunnerPhase::Paused;
                self.snapshot.active_block.running = false;
                self.snapshot.active_block.paused = true;
                Ok(true)
            }
            Action::RunResume => {
                expect_empty_args(args)?;
                if self.snapshot.run.phase == RunnerPhase::Running {
                    return Ok(false);
                }
                if self.snapshot.run.phase != RunnerPhase::Paused {
                    return Err("run_is_not_paused");
                }
                if !self.snapshot.safety.local_armed {
                    return Err("target_not_locally_armed");
                }
                self.snapshot.run.phase = RunnerPhase::Running;
                self.snapshot.active_block.running = true;
                self.snapshot.active_block.paused = false;
                self.snapshot.active_block.last_anchor_server_monotonic_ns = Some(now.monotonic_ns);
                Ok(true)
            }
            Action::RunStop | Action::RunCompleteDemo => {
                expect_empty_args(args)?;
                if *action == Action::RunCompleteDemo && origin.is_remote() {
                    return Err("action_is_local_only");
                }
                if matches!(
                    self.snapshot.run.phase,
                    RunnerPhase::Idle | RunnerPhase::Completed
                ) {
                    return Ok(false);
                }
                self.snapshot.run.phase = RunnerPhase::Completed;
                self.snapshot.run.complete = true;
                self.snapshot.run.thread_alive = false;
                self.snapshot.active_block.active = false;
                self.snapshot.active_block.running = false;
                self.snapshot.active_block.paused = false;
                self.snapshot.safety.capture_started = false;
                self.snapshot.safety.local_armed = false;
                Ok(true)
            }
            Action::RunAbort => {
                expect_empty_args(args)?;
                if matches!(
                    self.snapshot.run.phase,
                    RunnerPhase::Idle | RunnerPhase::Completed | RunnerPhase::Interrupted
                ) {
                    return Ok(false);
                }
                self.snapshot.run.phase = RunnerPhase::Interrupted;
                self.snapshot.run.complete = false;
                self.snapshot.run.thread_alive = false;
                self.snapshot.active_block.active = false;
                self.snapshot.active_block.running = false;
                self.snapshot.active_block.paused = false;
                self.snapshot.safety.capture_started = false;
                self.snapshot.safety.local_armed = false;
                Ok(true)
            }
            Action::SessionNote => {
                let note: NoteArgs = parse_args(args)?;
                let text = note.text.trim();
                if text.is_empty() || text.len() > MAX_NOTE_BYTES {
                    return Err("invalid_note");
                }
                if self.snapshot.last_note == text {
                    return Ok(false);
                }
                self.snapshot.last_note = text.to_owned();
                Ok(true)
            }
        }
    }

    fn prepare_demo(&mut self, args: &Value) -> Result<bool, &'static str> {
        let parsed: PrepareDemoArgs = parse_args(args)?;
        if matches!(
            self.snapshot.run.phase,
            RunnerPhase::Running | RunnerPhase::Paused | RunnerPhase::InstructionGate
        ) {
            return Err("cannot_replace_active_package");
        }
        let label = parsed
            .label
            .unwrap_or_else(|| "Deterministic PPS compatibility demo".to_owned());
        let label = label.trim();
        if label.is_empty() || label.len() > 120 {
            return Err("invalid_package_label");
        }
        let already = self.snapshot.package_verified
            && self.snapshot.package_label == label
            && self.snapshot.run.phase == RunnerPhase::Prepared;
        self.snapshot.package_verified = true;
        self.snapshot.package_label = label.to_owned();
        self.snapshot.run.phase = RunnerPhase::Prepared;
        self.snapshot.run.complete = false;
        self.snapshot.safety.local_armed = false;
        self.snapshot.identity.session_id = format!("demo-session-{}", self.snapshot.epoch);
        self.snapshot.identity.session_group_id = format!("demo-group-{}", self.snapshot.epoch);
        self.snapshot.setup.ready = self.snapshot.setup.submitted;
        Ok(!already)
    }

    fn submit_setup(&mut self, args: &Value) -> Result<bool, &'static str> {
        if matches!(
            self.snapshot.run.phase,
            RunnerPhase::Running | RunnerPhase::Paused | RunnerPhase::InstructionGate
        ) {
            return Err("setup_locked_during_run");
        }
        let parsed: SetupArgs = parse_args(args)?;
        if parsed.part_labels.len() != 2
            || !parsed.part_labels.contains_key("1")
            || !parsed.part_labels.contains_key("2")
        {
            return Err("invalid_part_labels");
        }
        let participant_code = parsed.participant_code.trim();
        if participant_code.is_empty()
            || participant_code.len() > 32
            || !participant_code.chars().all(is_safe_participant_char)
        {
            return Err("invalid_participant_code");
        }
        if !(1..=120).contains(&parsed.age) {
            return Err("invalid_age");
        }
        if !matches!(
            parsed.handedness.as_str(),
            "right" | "left" | "ambidextrous" | "prefer_not_to_say"
        ) {
            return Err("invalid_handedness");
        }
        if !matches!(
            parsed.gender.as_str(),
            "male" | "female" | "other" | "prefer_not_to_say"
        ) {
            return Err("invalid_gender");
        }
        let part_one = required_part_label(&parsed.part_labels, "1")?;
        let part_two = required_part_label(&parsed.part_labels, "2")?;
        let changed = !self.snapshot.setup.submitted
            || self.snapshot.setup.participant_code != participant_code
            || self.snapshot.setup.age != Some(parsed.age)
            || self.snapshot.setup.handedness != parsed.handedness
            || self.snapshot.setup.gender != parsed.gender
            || self.snapshot.setup.name_sharing_opt_in != parsed.name_sharing_opt_in
            || self.snapshot.setup.participant_name_present
                != parsed
                    .participant_name
                    .as_deref()
                    .map(str::trim)
                    .is_some_and(|name| !name.is_empty())
            || self.snapshot.setup.part_labels.get("1").map(String::as_str) != Some(part_one)
            || self.snapshot.setup.part_labels.get("2").map(String::as_str) != Some(part_two);
        self.snapshot.setup.submitted = true;
        self.snapshot.setup.required_missing.clear();
        self.snapshot.setup.participant_code = participant_code.to_owned();
        self.snapshot.setup.participant_name_present = parsed
            .participant_name
            .as_deref()
            .map(str::trim)
            .is_some_and(|name| !name.is_empty());
        self.snapshot.setup.name_sharing_opt_in = parsed.name_sharing_opt_in;
        self.snapshot.setup.age = Some(parsed.age);
        self.snapshot.setup.handedness = parsed.handedness;
        self.snapshot.setup.gender = parsed.gender;
        self.snapshot
            .setup
            .part_labels
            .insert("1".to_owned(), part_one.to_owned());
        self.snapshot
            .setup
            .part_labels
            .insert("2".to_owned(), part_two.to_owned());
        self.snapshot.identity.participant_id = participant_code.to_owned();
        self.snapshot.identity.selected_participant_id = participant_code.to_owned();
        self.snapshot.setup.ready = self.snapshot.package_verified;
        if changed {
            // Participant/condition metadata is part of the operator's safety
            // decision. Any material setup change revokes the prior local arm
            // so a remote controller cannot start under newly substituted
            // metadata without a fresh target-local acknowledgement.
            self.snapshot.safety.local_armed = false;
            if self.snapshot.package_verified {
                self.snapshot.run.phase = RunnerPhase::Prepared;
            }
        } else if self.snapshot.run.phase == RunnerPhase::Idle {
            self.snapshot.run.phase = RunnerPhase::Prepared;
        }
        Ok(changed)
    }

    fn start_part(&mut self, args: &Value, now: &ClockStamp) -> Result<bool, &'static str> {
        let parsed: PartArgs = parse_args(args)?;
        if !self
            .snapshot
            .part
            .available_parts
            .contains(&parsed.part_number)
        {
            return Err("part_not_available");
        }
        if !self.snapshot.safety.local_armed {
            return Err("target_not_locally_armed");
        }
        if !self.snapshot.setup.ready || !self.snapshot.package_verified {
            return Err("setup_or_package_not_ready");
        }
        if self.snapshot.run.phase != RunnerPhase::Ready {
            return Err("target_not_ready");
        }
        self.snapshot.part.selected_part = Some(parsed.part_number);
        self.snapshot.part.current_package_part = Some(parsed.part_number);
        self.snapshot.part.pending_start_part = None;
        self.snapshot.identity.part_session_id = format!(
            "{}-part-{:02}",
            self.snapshot.identity.session_id, parsed.part_number
        );
        self.snapshot.run.phase = RunnerPhase::Running;
        self.snapshot.run.complete = false;
        self.snapshot.run.thread_alive = true;
        self.snapshot.active_block.active = true;
        self.snapshot.active_block.part_number = Some(parsed.part_number);
        self.snapshot.active_block.phase_label = "Demo block".to_owned();
        self.snapshot.active_block.block_index = Some(1);
        self.snapshot.active_block.display_block_index = Some(1);
        self.snapshot.active_block.block_label = "Compatibility block 01".to_owned();
        self.snapshot.active_block.duration_s = Some(3.0);
        self.snapshot.active_block.elapsed_s = Some(0.0);
        self.snapshot.active_block.last_anchor_server_monotonic_ns = Some(now.monotonic_ns);
        self.snapshot.active_block.running = true;
        self.snapshot.active_block.paused = false;
        self.snapshot.safety.capture_started = true;
        Ok(true)
    }

    fn continue_instruction(&mut self, args: &Value) -> Result<bool, &'static str> {
        let parsed: GateArgs = parse_args(args)?;
        if self.snapshot.run.phase != RunnerPhase::InstructionGate
            || !self.snapshot.instruction_gate.waiting
        {
            return Err("instruction_gate_not_waiting");
        }
        if parsed.gate_id != self.snapshot.instruction_gate.gate_id {
            return Err("stale_instruction_gate");
        }
        self.snapshot.instruction_gate.waiting = false;
        self.snapshot.instruction_gate.gate_id.clear();
        self.snapshot.run.phase = RunnerPhase::Running;
        self.snapshot.active_block.instruction_waiting = false;
        self.snapshot.active_block.running = true;
        Ok(true)
    }

    fn rejected(&self, command: &CommandRequest, reason: impl Into<String>) -> Applied {
        Applied {
            id: command.id.clone(),
            action: command.action,
            status: AppliedStatus::Rejected,
            reason: reason.into(),
            accepted_revision: self.snapshot.revision,
            resulting_revision: self.snapshot.revision,
            snapshot: self.snapshot(),
        }
    }

    fn remember(
        &mut self,
        principal: DedupePrincipal,
        command_id: String,
        fingerprint: Vec<u8>,
        result: Applied,
    ) {
        self.dedupe.push_back(DedupeEntry {
            principal,
            command_id,
            fingerprint,
            result,
        });
        while self.dedupe.len() > DEDUPE_LIMIT {
            self.dedupe.pop_front();
        }
    }

    fn stamp(&mut self, now: &ClockStamp) {
        self.snapshot.server_unix_ms = now.unix_ms.min(JSON_MAX_SAFE_INTEGER);
        self.snapshot.server_monotonic_ns = now.monotonic_ns.min(JSON_MAX_SAFE_INTEGER);
    }

    fn bump_revision(&mut self, now: &ClockStamp) {
        self.snapshot.revision = self
            .snapshot
            .revision
            .saturating_add(1)
            .min(JSON_MAX_SAFE_INTEGER);
        self.stamp(now);
        self.refresh_derived();
    }

    fn refresh_derived(&mut self) {
        let phase = self.snapshot.run.phase;
        self.snapshot.run.complete = phase == RunnerPhase::Completed;
        self.snapshot.run.thread_alive = matches!(
            phase,
            RunnerPhase::Running | RunnerPhase::Paused | RunnerPhase::InstructionGate
        );
        self.snapshot.run.state_label = match phase {
            RunnerPhase::Idle => "Idle",
            RunnerPhase::Prepared => "Prepared",
            RunnerPhase::Ready => "Ready — locally armed",
            RunnerPhase::InstructionGate => "Waiting for instruction",
            RunnerPhase::Running => "Running",
            RunnerPhase::Paused => "Paused",
            RunnerPhase::Stopping => "Stopping",
            RunnerPhase::Completed => "Complete",
            RunnerPhase::Interrupted => "Interrupted",
            RunnerPhase::Error => "Error",
        }
        .to_owned();
        self.snapshot.run.progress_label = match phase {
            RunnerPhase::Idle => "Prepare a validated session package",
            RunnerPhase::Prepared => "Submit setup and arm on this target",
            RunnerPhase::Ready => "Start Part 01 or Part 02",
            RunnerPhase::InstructionGate => "Instruction acknowledgement required",
            RunnerPhase::Running => "Block 1 / 1",
            RunnerPhase::Paused => "Playback paused at target",
            RunnerPhase::Stopping => "Finalizing artifacts",
            RunnerPhase::Completed => "Session artifacts finalized",
            RunnerPhase::Interrupted => "Run stopped before completion",
            RunnerPhase::Error => "Inspect target logs",
        }
        .to_owned();
        self.snapshot.run.event_label = match phase {
            RunnerPhase::Running => "Target owns media timing",
            RunnerPhase::Paused => "Remote/local resume available",
            RunnerPhase::Ready => "Remote start requires this local arm",
            _ => "Authoritative target state",
        }
        .to_owned();
        self.snapshot.active_block.running = phase == RunnerPhase::Running;
        self.snapshot.active_block.paused = phase == RunnerPhase::Paused;
        self.snapshot.active_block.instruction_waiting = phase == RunnerPhase::InstructionGate;
        self.snapshot.allowed_actions = self.compute_allowed_actions();
    }

    fn compute_allowed_actions(&self) -> Vec<Action> {
        let mut actions = vec![Action::SystemSnapshot];
        let phase = self.snapshot.run.phase;
        if !matches!(
            phase,
            RunnerPhase::Running | RunnerPhase::Paused | RunnerPhase::InstructionGate
        ) {
            actions.push(Action::PackagePrepareDemo);
            actions.push(Action::SetupSubmit);
        }
        if self.snapshot.package_verified && self.snapshot.setup.ready {
            if self.snapshot.safety.local_armed {
                actions.push(Action::TargetDisarm);
            } else if !matches!(phase, RunnerPhase::Running | RunnerPhase::Paused) {
                actions.push(Action::TargetArm);
            }
        }
        match phase {
            RunnerPhase::Ready => actions.push(Action::PartStart),
            RunnerPhase::InstructionGate => actions.push(Action::InstructionContinue),
            RunnerPhase::Running => actions.push(Action::RunPause),
            RunnerPhase::Paused => actions.push(Action::RunResume),
            _ => {}
        }
        if matches!(
            phase,
            RunnerPhase::Prepared
                | RunnerPhase::Ready
                | RunnerPhase::InstructionGate
                | RunnerPhase::Running
                | RunnerPhase::Paused
        ) {
            actions.push(Action::RunStop);
            actions.push(Action::RunAbort);
        }
        actions.push(Action::SessionNote);
        actions
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct PrepareDemoArgs {
    #[serde(default)]
    label: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct SetupArgs {
    participant_code: String,
    #[serde(default)]
    participant_name: Option<String>,
    age: u8,
    handedness: String,
    gender: String,
    #[serde(default)]
    name_sharing_opt_in: bool,
    part_labels: BTreeMap<String, String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct PartArgs {
    part_number: u8,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct GateArgs {
    gate_id: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct NoteArgs {
    text: String,
}

fn parse_args<T: for<'de> Deserialize<'de>>(value: &Value) -> Result<T, &'static str> {
    serde_json::from_value(value.clone()).map_err(|_| "invalid_action_args")
}

fn expect_empty_args(value: &Value) -> Result<(), &'static str> {
    match value {
        Value::Object(fields) if fields.is_empty() => Ok(()),
        _ => Err("invalid_action_args"),
    }
}

fn validate_json_shape(value: &Value, depth: usize) -> Result<(), &'static str> {
    if depth > 8 {
        return Err("args_too_deep");
    }
    match value {
        Value::Null | Value::Bool(_) | Value::String(_) | Value::Number(_) => Ok(()),
        Value::Array(values) => {
            if values.len() > 256 {
                return Err("args_array_too_large");
            }
            for value in values {
                validate_json_shape(value, depth + 1)?;
            }
            Ok(())
        }
        Value::Object(fields) => {
            if fields.len() > 128 {
                return Err("args_object_too_large");
            }
            for (key, value) in fields {
                if key.is_empty()
                    || key.len() > 96
                    || matches!(key.as_str(), "__proto__" | "prototype" | "constructor")
                {
                    return Err("args_unsafe_field");
                }
                validate_json_shape(value, depth + 1)?;
            }
            Ok(())
        }
    }
}

fn required_part_label<'a>(
    labels: &'a BTreeMap<String, String>,
    key: &str,
) -> Result<&'a str, &'static str> {
    let label = labels
        .get(key)
        .map(String::as_str)
        .unwrap_or_default()
        .trim();
    if label.is_empty() || label.len() > 80 {
        return Err("invalid_part_label");
    }
    Ok(label)
}

fn is_safe_command_id(value: &str) -> bool {
    let mut characters = value.chars();
    characters
        .next()
        .is_some_and(|character| character.is_ascii_alphanumeric())
        && characters.all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | ':' | '.')
        })
}

fn is_safe_participant_char(character: char) -> bool {
    character.is_ascii_alphanumeric() || matches!(character, '-' | '_')
}

fn is_safe_token_char(character: char) -> bool {
    character.is_ascii_alphanumeric() || matches!(character, '-' | '_')
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn clock(step: u64) -> ClockStamp {
        ClockStamp {
            unix_ms: 1_800_000_000_000 + step,
            monotonic_ns: step * 1_000_000,
        }
    }

    fn ready_core() -> RunnerCore {
        let mut core = RunnerCore::new(
            "target-test",
            "desktop",
            7,
            TimingTier::DesktopPreview,
            clock(0),
        );
        assert_eq!(
            core.dispatch_local(
                Action::PackagePrepareDemo,
                json!({"label": "Fixture"}),
                clock(1),
            )
            .status,
            AppliedStatus::Accepted
        );
        assert_eq!(
            core.dispatch_local(
                Action::SetupSubmit,
                json!({
                    "participant_code": "P001",
                    "participant_name": "Private Name",
                    "age": 30,
                    "handedness": "right",
                    "gender": "prefer_not_to_say",
                    "name_sharing_opt_in": false,
                    "part_labels": {"1": "Near", "2": "Far"}
                }),
                clock(2),
            )
            .status,
            AppliedStatus::Accepted
        );
        assert_eq!(
            core.dispatch_local(Action::TargetArm, json!({}), clock(3))
                .status,
            AppliedStatus::Accepted
        );
        core
    }

    #[test]
    fn happy_path_requires_local_arm_and_redacts_name() {
        let mut core = ready_core();
        let result = core.dispatch_local(Action::PartStart, json!({"part_number": 1}), clock(4));
        assert_eq!(result.status, AppliedStatus::Accepted);
        assert_eq!(result.snapshot.run.phase, RunnerPhase::Running);
        assert!(result.snapshot.setup.participant_name_present);
        let wire = serde_json::to_string(&result.snapshot).unwrap();
        assert!(!wire.contains("Private Name"));

        assert_eq!(
            core.dispatch_local(Action::RunPause, json!({}), clock(5))
                .snapshot
                .run
                .phase,
            RunnerPhase::Paused
        );
        assert_eq!(
            core.dispatch_local(Action::RunResume, json!({}), clock(6))
                .snapshot
                .run
                .phase,
            RunnerPhase::Running
        );
    }

    #[test]
    fn remote_start_is_denied_without_local_arm() {
        let mut core = RunnerCore::new(
            "target-test",
            "desktop",
            9,
            TimingTier::DesktopPreview,
            clock(0),
        );
        core.dispatch_local(Action::PackagePrepareDemo, json!({}), clock(1));
        core.dispatch_local(
            Action::SetupSubmit,
            json!({
                "participant_code": "P001",
                "age": 30,
                "handedness": "right",
                "gender": "other",
                "name_sharing_opt_in": false,
                "part_labels": {"1": "A", "2": "B"}
            }),
            clock(2),
        );
        let command = CommandRequest {
            id: "cmd-start".to_owned(),
            epoch: 9,
            sequence: 1,
            expected_revision: Some(core.revision()),
            scope: Scope::SessionTransport,
            action: Action::PartStart,
            args: json!({"part_number": 1}),
        };
        let result = core.dispatch(
            DispatchOrigin::Remote {
                controller_id: "phone".to_owned(),
                granted_scopes: BTreeSet::from([Scope::SessionTransport]),
                lease_valid: true,
            },
            command,
            clock(3),
        );
        assert_eq!(result.status, AppliedStatus::Rejected);
        assert_eq!(result.reason, "target_not_locally_armed");
    }

    #[test]
    fn application_arguments_are_exact_and_structurally_bounded() {
        let mut core = RunnerCore::new(
            "target-test",
            "desktop",
            9,
            TimingTier::DesktopPreview,
            clock(0),
        );
        let unexpected = core.dispatch_local(
            Action::SystemSnapshot,
            json!({"unexpected": true}),
            clock(1),
        );
        assert_eq!(unexpected.status, AppliedStatus::Rejected);
        assert_eq!(unexpected.reason, "invalid_action_args");

        core.dispatch_local(Action::PackagePrepareDemo, json!({}), clock(2));
        let labels = core.dispatch_local(
            Action::SetupSubmit,
            json!({
                "participant_code": "P001",
                "age": 30,
                "handedness": "right",
                "gender": "other",
                "part_labels": {"1": "A", "2": "B", "3": "unexpected"}
            }),
            clock(3),
        );
        assert_eq!(labels.status, AppliedStatus::Rejected);
        assert_eq!(labels.reason, "invalid_part_labels");

        let mut nested = json!({});
        for _ in 0..10 {
            nested = json!({"child": nested});
        }
        let too_deep = core.dispatch_local(Action::PackagePrepareDemo, nested, clock(4));
        assert_eq!(too_deep.status, AppliedStatus::Rejected);
        assert_eq!(too_deep.reason, "args_too_deep");
    }

    #[test]
    fn revision_scope_epoch_and_dedupe_are_enforced() {
        let mut core = ready_core();
        let revision = core.revision();
        let command = CommandRequest {
            id: "command-1".to_owned(),
            epoch: core.epoch(),
            sequence: 1,
            expected_revision: Some(revision),
            scope: Scope::SessionTransport,
            action: Action::PartStart,
            args: json!({"part_number": 1}),
        };
        let origin = DispatchOrigin::Remote {
            controller_id: "controller".to_owned(),
            granted_scopes: BTreeSet::from([Scope::SessionTransport]),
            lease_valid: true,
        };
        let first = core.dispatch(origin.clone(), command.clone(), clock(10));
        assert_eq!(first.status, AppliedStatus::Accepted);
        let duplicate = core.dispatch(
            origin.clone(),
            CommandRequest {
                sequence: 2,
                ..command
            },
            clock(11),
        );
        assert_eq!(duplicate, first);

        let reused = core.dispatch(
            origin.clone(),
            CommandRequest {
                id: "command-1".to_owned(),
                epoch: core.epoch(),
                sequence: 3,
                expected_revision: Some(revision),
                scope: Scope::SessionTransport,
                action: Action::RunPause,
                args: json!({}),
            },
            clock(11),
        );
        assert_eq!(reused.status, AppliedStatus::Rejected);
        assert_eq!(reused.reason, "command_id_reused_with_different_payload");

        let stale_command = CommandRequest {
            id: "command-2".to_owned(),
            epoch: core.epoch(),
            sequence: 4,
            expected_revision: Some(revision),
            scope: Scope::SessionTransport,
            action: Action::RunPause,
            args: json!({}),
        };
        let stale = core.dispatch(origin.clone(), stale_command.clone(), clock(12));
        assert_eq!(stale.status, AppliedStatus::Rejected);
        assert_eq!(stale.reason, "revision_conflict");
        let retried_stale = core.dispatch(
            origin,
            CommandRequest {
                sequence: 5,
                ..stale_command
            },
            clock(13),
        );
        assert_eq!(retried_stale, stale);
        assert!(!pps_contracts::AppliedBody::from(&retried_stale).ok);
    }

    #[test]
    fn remote_uint32_sequence_wrap_zero_is_valid() {
        let mut core = ready_core();
        let origin = DispatchOrigin::Remote {
            controller_id: "controller".to_owned(),
            granted_scopes: BTreeSet::from([Scope::SessionRead]),
            lease_valid: true,
        };
        let wrapped = core.dispatch(
            origin.clone(),
            CommandRequest {
                id: "wrapped-sequence-zero".to_owned(),
                epoch: core.epoch(),
                sequence: 0,
                expected_revision: None,
                scope: Scope::SessionRead,
                action: Action::SystemSnapshot,
                args: json!({}),
            },
            clock(10),
        );
        assert_eq!(wrapped.status, AppliedStatus::Accepted);

        let outside_wire_range = core.dispatch(
            origin,
            CommandRequest {
                id: "sequence-over-uint32".to_owned(),
                epoch: core.epoch(),
                sequence: u64::from(u32::MAX) + 1,
                expected_revision: None,
                scope: Scope::SessionRead,
                action: Action::SystemSnapshot,
                args: json!({}),
            },
            clock(11),
        );
        assert_eq!(outside_wire_range.status, AppliedStatus::Rejected);
        assert_eq!(outside_wire_range.reason, "json_integer_out_of_range");
    }

    #[test]
    fn remote_command_ids_cannot_preseed_the_local_operator_namespace() {
        let mut core = ready_core();
        let next_local_id = format!("local-{}-4", core.epoch());
        let preseed = core.dispatch(
            DispatchOrigin::Remote {
                controller_id: "controller".to_owned(),
                granted_scopes: BTreeSet::from([Scope::SessionTransport]),
                lease_valid: false,
            },
            CommandRequest {
                id: next_local_id,
                epoch: core.epoch(),
                sequence: 1,
                expected_revision: Some(core.revision()),
                scope: Scope::SessionTransport,
                action: Action::PartStart,
                args: json!({"part_number": 1}),
            },
            clock(4),
        );
        assert_eq!(preseed.status, AppliedStatus::Rejected);
        assert_eq!(preseed.reason, "controller_lease_expired");

        let local = core.dispatch_local(Action::PartStart, json!({"part_number": 1}), clock(5));
        assert_eq!(local.status, AppliedStatus::Accepted);
        assert_eq!(local.snapshot.run.phase, RunnerPhase::Running);
    }

    #[test]
    fn remote_dedupe_is_scoped_to_the_authenticated_controller() {
        let mut core = ready_core();
        let first = core.dispatch(
            DispatchOrigin::Remote {
                controller_id: "controller-a".to_owned(),
                granted_scopes: BTreeSet::from([Scope::SessionTransport]),
                lease_valid: false,
            },
            CommandRequest {
                id: "shared-command-id".to_owned(),
                epoch: core.epoch(),
                sequence: 1,
                expected_revision: Some(core.revision()),
                scope: Scope::SessionTransport,
                action: Action::PartStart,
                args: json!({"part_number": 1}),
            },
            clock(4),
        );
        assert_eq!(first.reason, "controller_lease_expired");

        let second = core.dispatch(
            DispatchOrigin::Remote {
                controller_id: "controller-b".to_owned(),
                granted_scopes: BTreeSet::from([Scope::SessionTransport]),
                lease_valid: true,
            },
            CommandRequest {
                id: "shared-command-id".to_owned(),
                epoch: core.epoch(),
                sequence: 1,
                expected_revision: Some(core.revision()),
                scope: Scope::SessionTransport,
                action: Action::PartStart,
                args: json!({"part_number": 1}),
            },
            clock(5),
        );
        assert_eq!(second.status, AppliedStatus::Accepted);
        assert_eq!(second.snapshot.run.phase, RunnerPhase::Running);
    }

    #[test]
    fn changing_setup_revokes_local_arm_before_remote_start() {
        let mut core = ready_core();
        let changed = core.dispatch_local(
            Action::SetupSubmit,
            json!({
                "participant_code": "P002",
                "age": 31,
                "handedness": "left",
                "gender": "prefer_not_to_say",
                "name_sharing_opt_in": false,
                "part_labels": {"1": "Near", "2": "Far"}
            }),
            clock(4),
        );
        assert_eq!(changed.status, AppliedStatus::Accepted);
        assert!(!changed.snapshot.safety.local_armed);
        assert_eq!(changed.snapshot.run.phase, RunnerPhase::Prepared);

        let start = core.dispatch(
            DispatchOrigin::Remote {
                controller_id: "controller".to_owned(),
                granted_scopes: BTreeSet::from([Scope::SessionTransport]),
                lease_valid: true,
            },
            CommandRequest {
                id: "start-after-setup-change".to_owned(),
                epoch: core.epoch(),
                sequence: 1,
                expected_revision: Some(core.revision()),
                scope: Scope::SessionTransport,
                action: Action::PartStart,
                args: json!({"part_number": 1}),
            },
            clock(5),
        );
        assert_eq!(start.status, AppliedStatus::Rejected);
        assert_eq!(start.reason, "target_not_locally_armed");
    }

    #[test]
    fn stop_requires_abort_scope() {
        let mut core = ready_core();
        core.dispatch_local(Action::PartStart, json!({"part_number": 1}), clock(4));
        let result = core.dispatch(
            DispatchOrigin::Remote {
                controller_id: "controller".to_owned(),
                granted_scopes: BTreeSet::from([Scope::SessionTransport]),
                lease_valid: true,
            },
            CommandRequest {
                id: "cmd-stop".to_owned(),
                epoch: core.epoch(),
                sequence: 1,
                expected_revision: Some(core.revision()),
                scope: Scope::SessionAbort,
                action: Action::RunStop,
                args: json!({}),
            },
            clock(5),
        );
        assert_eq!(result.status, AppliedStatus::Rejected);
        assert_eq!(result.reason, "scope_not_granted");
    }
}
