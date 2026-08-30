use std::{
    collections::{BTreeSet, VecDeque},
    time::{Duration, Instant},
};

use pps_brsp::{
    canonical_json, create_proof_envelope, negotiate_session, random_epoch, random_nonce,
    ready_matches, valid_peer_id, valid_token, validate_common, validate_hello, NegotiatedSession,
    PairingSecret, SequenceDecision, SequenceGuard,
};
use pps_contracts::{
    Action, AppliedBody, BrspRole, CommandBody, CommandEnvelope, Envelope, ErrorBody, HelloBody,
    HelloEnvelope, ProofEnvelope, ReadyBody, ReadyEnvelope, RunnerPhase, RunnerSnapshot, Scope,
    SnapshotBody, StateBody, WireEnvelope, JSON_MAX_SAFE_INTEGER, MAX_CONTROL_BYTES,
    MAX_STATE_BYTES, PPS_REMOTE_CAPABILITIES,
};
use pps_runner_core::{DispatchOrigin, RunnerCore};
use serde::{de::DeserializeOwned, Serialize};

use crate::clock_stamp;

const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(12);
const CONTROLLER_LEASE: Duration = Duration::from_secs(5);
const STATE_HEARTBEAT: Duration = Duration::from_millis(250);
const COMMAND_DEDUPE_LIMIT: usize = 128;
const MAX_OUTBOUND_FRAMES: usize = 4;

#[derive(Debug)]
pub(crate) struct PairingMaterial {
    pub target_id: String,
    pub session_id: String,
    pub room: String,
    pub secret: String,
    pub invitation: String,
    pub scopes: Vec<Scope>,
}

#[derive(Debug)]
pub(crate) struct RelayOutcome {
    pub outbound: Vec<String>,
    pub refresh_ui: bool,
    pub close: bool,
    pub phase: String,
    pub message: String,
}

impl RelayOutcome {
    fn new(phase: &str, message: impl Into<String>) -> Self {
        Self {
            outbound: Vec::new(),
            refresh_ui: false,
            close: false,
            phase: phase.to_owned(),
            message: message.into(),
        }
    }

    fn terminal(phase: &str, message: impl Into<String>) -> Self {
        Self {
            close: true,
            ..Self::new(phase, message)
        }
    }
}

#[derive(Clone)]
struct PairingConfig {
    secret: PairingSecret,
    encoded_secret: String,
    session_id: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum HandshakePhase {
    AwaitingHello,
    AwaitingProof,
    AwaitingReady,
    Ready,
}

#[derive(Debug, Clone)]
struct CommandCacheEntry {
    command_id: String,
    fingerprint: String,
    applied: AppliedBody,
}

struct TargetSession {
    secret: PairingSecret,
    target_hello: HelloEnvelope,
    controller_hello: Option<HelloEnvelope>,
    negotiated: Option<NegotiatedSession>,
    phase: HandshakePhase,
    remote_control_sequence: Option<SequenceGuard>,
    target_control_sequence: u32,
    target_state_sequence: u32,
    handshake_deadline: Instant,
    lease_deadline: Option<Instant>,
    last_state_sent: Instant,
    last_state_revision: Option<u64>,
}

#[derive(Default)]
pub(crate) struct RelayAuthority {
    pairing: Option<PairingConfig>,
    session: Option<TargetSession>,
    command_cache: VecDeque<CommandCacheEntry>,
}

impl RelayAuthority {
    pub(crate) fn create_pairing(
        &mut self,
        core: &mut RunnerCore,
        companion_base_url: &str,
        room: &str,
    ) -> Result<PairingMaterial, String> {
        validate_companion_base(companion_base_url)?;
        validate_room(room)?;
        self.end_session(core, "Pairing rotated locally.", "remote_waiting");
        self.command_cache.clear();

        let secret = PairingSecret::generate();
        let encoded_secret = secret.expose_base64();
        let session_id = format!("quest_session_{}", &random_nonce()[..18]);
        let target_id = core.snapshot().target_id;
        let scopes = available_scopes();
        let scope_csv = scopes
            .iter()
            .map(|scope| scope.as_str())
            .collect::<Vec<_>>()
            .join(",");
        let invitation = format!(
            "{companion_base_url}#mode=controller&transport=relay&room={room}&target_id={target_id}&session_id={session_id}&secret={encoded_secret}&scopes={scope_csv}"
        );
        self.pairing = Some(PairingConfig {
            secret,
            encoded_secret: encoded_secret.clone(),
            session_id: session_id.clone(),
        });
        core.set_connection_state("remote_waiting", clock_stamp());
        Ok(PairingMaterial {
            target_id,
            session_id,
            room: room.to_owned(),
            secret: encoded_secret,
            invitation,
            scopes,
        })
    }

    pub(crate) fn begin(&mut self, core: &mut RunnerCore, supplied_secret: &str) -> RelayOutcome {
        self.end_session(core, "Fresh BRSP handshake requested.", "remote_waiting");
        let Some(pairing) = self.pairing.as_ref() else {
            return RelayOutcome::terminal("error", "Generate a local invitation first.");
        };
        let supplied_is_valid = PairingSecret::from_base64(supplied_secret).is_ok()
            && constant_time_equal(
                supplied_secret.as_bytes(),
                pairing.encoded_secret.as_bytes(),
            );
        if !supplied_is_valid {
            return RelayOutcome::terminal("error", "Pairing material was rejected.");
        }

        let target_sender_id = format!("target_{}", &random_nonce()[..18]);
        let target_sender_epoch = random_epoch();
        let target_hello = Envelope::new(
            "hello",
            pairing.session_id.clone(),
            target_sender_id,
            target_sender_epoch,
            0,
            HelloBody {
                role: BrspRole::Target,
                nonce: random_nonce(),
                capabilities: PPS_REMOTE_CAPABILITIES
                    .iter()
                    .map(|capability| (*capability).to_owned())
                    .collect(),
                requested_scopes: Vec::new(),
                granted_scopes: available_scopes(),
            },
        );
        if validate_hello(&target_hello).is_err() {
            return RelayOutcome::terminal("error", "Could not create a valid target hello.");
        }
        let encoded = match encode_bounded(&target_hello, MAX_CONTROL_BYTES) {
            Ok(encoded) => encoded,
            Err(message) => return RelayOutcome::terminal("error", message),
        };
        self.session = Some(TargetSession {
            secret: pairing.secret.clone(),
            target_hello,
            controller_hello: None,
            negotiated: None,
            phase: HandshakePhase::AwaitingHello,
            remote_control_sequence: None,
            target_control_sequence: 0,
            target_state_sequence: 0,
            handshake_deadline: Instant::now() + HANDSHAKE_TIMEOUT,
            lease_deadline: None,
            last_state_sent: Instant::now(),
            last_state_revision: None,
        });
        core.set_connection_state("remote_authenticating", clock_stamp());
        let mut outcome = RelayOutcome::new(
            "authenticating",
            "Target hello sent; mutual BRSP proof is required.",
        );
        outcome.outbound.push(encoded);
        outcome.refresh_ui = true;
        outcome
    }

    pub(crate) fn handle_frame(&mut self, core: &mut RunnerCore, frame: &str) -> RelayOutcome {
        if frame.len() > MAX_CONTROL_BYTES {
            return self.close_with_protocol_error(
                core,
                "frame_too_large",
                "Control frame exceeds 16 KiB.",
                "error",
            );
        }
        let Some(mut session) = self.session.take() else {
            return RelayOutcome::terminal("error", "No BRSP handshake is active.");
        };
        let had_authenticated_authority = session.phase == HandshakePhase::Ready;
        let outcome = session.handle_frame(core, frame, &mut self.command_cache);
        if outcome.close {
            let state = if outcome.phase == "lease_expired" {
                "remote_lease_expired"
            } else {
                "remote_waiting"
            };
            revoke_core(core, state, had_authenticated_authority);
        } else {
            self.session = Some(session);
        }
        outcome
    }

    pub(crate) fn poll(&mut self, core: &mut RunnerCore) -> RelayOutcome {
        let Some(mut session) = self.session.take() else {
            return RelayOutcome::new("waiting_controller", "Waiting for a controller peer.");
        };
        let had_authenticated_authority = session.phase == HandshakePhase::Ready;
        let outcome = session.poll(core);
        if outcome.close {
            let state = if outcome.phase == "lease_expired" {
                "remote_lease_expired"
            } else {
                "remote_waiting"
            };
            revoke_core(core, state, had_authenticated_authority);
        } else {
            self.session = Some(session);
        }
        outcome
    }

    pub(crate) fn end(&mut self, core: &mut RunnerCore, reason: &str) -> RelayOutcome {
        self.end_session(core, reason, "remote_waiting");
        let mut outcome = RelayOutcome::new("waiting_controller", bounded_message(reason));
        outcome.refresh_ui = true;
        outcome
    }

    fn close_with_protocol_error(
        &mut self,
        core: &mut RunnerCore,
        code: &str,
        message: &str,
        phase: &str,
    ) -> RelayOutcome {
        let had_authenticated_authority = self
            .session
            .as_ref()
            .is_some_and(|session| session.phase == HandshakePhase::Ready);
        let mut outcome = self
            .session
            .as_mut()
            .map(|session| session.protocol_error(code, message, phase, true))
            .unwrap_or_else(|| RelayOutcome::terminal(phase, message));
        self.session = None;
        revoke_core(core, "remote_waiting", had_authenticated_authority);
        outcome.refresh_ui = true;
        outcome
    }

    fn end_session(&mut self, core: &mut RunnerCore, _reason: &str, state: &str) {
        if let Some(session) = self.session.take() {
            revoke_core(core, state, session.phase == HandshakePhase::Ready);
        }
    }
}

impl TargetSession {
    fn handle_frame(
        &mut self,
        core: &mut RunnerCore,
        frame: &str,
        command_cache: &mut VecDeque<CommandCacheEntry>,
    ) -> RelayOutcome {
        if let Some(expired) = self.expiration(core) {
            return expired;
        }
        let wire: WireEnvelope = match serde_json::from_str(frame) {
            Ok(wire) => wire,
            Err(_) => {
                return self.protocol_error(
                    "malformed_envelope",
                    "Malformed canonical BRSP/1 envelope.",
                    "error",
                    true,
                )
            }
        };

        match self.phase {
            HandshakePhase::AwaitingHello => self.receive_hello(wire),
            HandshakePhase::AwaitingProof => self.receive_proof(wire),
            HandshakePhase::AwaitingReady => self.receive_ready(core, wire),
            HandshakePhase::Ready => self.receive_ready_control(core, wire, command_cache),
        }
    }

    fn poll(&mut self, core: &mut RunnerCore) -> RelayOutcome {
        if let Some(expired) = self.expiration(core) {
            return expired;
        }
        if self.phase != HandshakePhase::Ready {
            return RelayOutcome::new(
                "authenticating",
                "Waiting for the next mutual BRSP handshake envelope.",
            );
        }
        let mut outcome = RelayOutcome::new("ready", "Authenticated controller lease is active.");
        if self.can_read()
            && (self.last_state_revision != Some(core.revision())
                || self.last_state_sent.elapsed() >= STATE_HEARTBEAT)
        {
            if let Err(message) = self.push_state(&mut outcome, core) {
                return self.protocol_error("state_too_large", &message, "error", true);
            }
        }
        outcome
    }

    fn receive_hello(&mut self, wire: WireEnvelope) -> RelayOutcome {
        let controller_hello: HelloEnvelope = match typed_from_wire(wire, "hello") {
            Ok(hello) => hello,
            Err(message) => return self.protocol_error("invalid_hello", &message, "error", true),
        };
        if validate_hello(&controller_hello).is_err()
            || controller_hello.body.role != BrspRole::Controller
            || controller_hello.session_id != self.target_hello.session_id
            || !valid_peer_id(&controller_hello.sender_id)
        {
            return self.protocol_error(
                "invalid_hello",
                "Controller hello failed canonical validation.",
                "error",
                true,
            );
        }
        let proof =
            match create_proof_envelope(&self.secret, &self.target_hello, &controller_hello, 1) {
                Ok(proof) => proof,
                Err(_) => {
                    return self.protocol_error(
                        "invalid_hello_pair",
                        "Hello pair cannot form a proof transcript.",
                        "error",
                        true,
                    )
                }
            };
        self.controller_hello = Some(controller_hello);
        self.remote_control_sequence = Some(SequenceGuard::after(0));
        self.target_control_sequence = 1;
        self.phase = HandshakePhase::AwaitingProof;
        let mut outcome = RelayOutcome::new(
            "authenticating",
            "Controller hello accepted; target proof sent.",
        );
        if self
            .push_serialized(&mut outcome, &proof, MAX_CONTROL_BYTES)
            .is_err()
        {
            return self.protocol_error(
                "serialization_failed",
                "Target proof could not be encoded.",
                "error",
                true,
            );
        }
        outcome
    }

    fn receive_proof(&mut self, wire: WireEnvelope) -> RelayOutcome {
        if let Err(outcome) = self.validate_remote_control(&wire) {
            return outcome;
        }
        let proof: ProofEnvelope = match typed_from_wire(wire, "proof") {
            Ok(proof) => proof,
            Err(message) => return self.protocol_error("invalid_proof", &message, "error", true),
        };
        let controller_hello = self
            .controller_hello
            .as_ref()
            .expect("controller hello exists in AwaitingProof");
        if proof.sequence != 1
            || !self
                .secret
                .verify_proof(&proof, &self.target_hello, controller_hello)
        {
            return self.protocol_error(
                "proof_failed",
                "Controller pairing proof was rejected.",
                "error",
                true,
            );
        }
        let negotiated = match negotiate_session(&self.target_hello, controller_hello) {
            Ok(negotiated) => negotiated,
            Err(_) => {
                return self.protocol_error(
                    "negotiation_failed",
                    "BRSP capability/scope negotiation failed.",
                    "error",
                    true,
                )
            }
        };
        if negotiated.accepted_scopes.is_empty()
            || !negotiated
                .capabilities
                .iter()
                .any(|capability| capability == "pps-runner-v1")
            || !negotiated
                .capabilities
                .iter()
                .any(|capability| capability == "command-ack")
        {
            return self.protocol_error(
                "negotiation_failed",
                "No usable PPS command capability or scope was negotiated.",
                "error",
                true,
            );
        }
        self.target_control_sequence = 2;
        let ready = Envelope::new(
            "ready",
            self.target_hello.session_id.clone(),
            self.target_hello.sender_id.clone(),
            self.target_hello.sender_epoch,
            self.target_control_sequence,
            ReadyBody {
                capabilities: negotiated.capabilities.clone(),
                accepted_scopes: negotiated.accepted_scopes.clone(),
            },
        );
        self.negotiated = Some(negotiated);
        self.phase = HandshakePhase::AwaitingReady;
        let mut outcome = RelayOutcome::new(
            "authenticating",
            "Controller proof accepted; waiting for matching ready.",
        );
        if self
            .push_serialized(&mut outcome, &ready, MAX_CONTROL_BYTES)
            .is_err()
        {
            return self.protocol_error(
                "serialization_failed",
                "Target ready could not be encoded.",
                "error",
                true,
            );
        }
        outcome
    }

    fn receive_ready(&mut self, core: &mut RunnerCore, wire: WireEnvelope) -> RelayOutcome {
        if let Err(outcome) = self.validate_remote_control(&wire) {
            return outcome;
        }
        let ready: ReadyEnvelope = match typed_from_wire(wire, "ready") {
            Ok(ready) => ready,
            Err(message) => return self.protocol_error("invalid_ready", &message, "error", true),
        };
        let negotiated = self
            .negotiated
            .as_ref()
            .expect("negotiation exists in AwaitingReady");
        if ready.sequence != 2 || !ready_matches(&ready.body, negotiated) {
            return self.protocol_error(
                "ready_mismatch",
                "Controller ready did not match exact negotiation.",
                "error",
                true,
            );
        }

        self.phase = HandshakePhase::Ready;
        self.refresh_lease(core);
        core.set_connection_state("remote_connected", clock_stamp());
        let mut outcome = RelayOutcome::new("ready", "Authenticated controller lease is active.");
        outcome.refresh_ui = true;
        if self.can_read() {
            if let Err(message) = self.push_snapshot(&mut outcome, core) {
                return self.protocol_error("snapshot_too_large", &message, "error", true);
            }
            if let Err(message) = self.push_state(&mut outcome, core) {
                return self.protocol_error("state_too_large", &message, "error", true);
            }
        }
        outcome
    }

    fn receive_ready_control(
        &mut self,
        core: &mut RunnerCore,
        wire: WireEnvelope,
        command_cache: &mut VecDeque<CommandCacheEntry>,
    ) -> RelayOutcome {
        if let Err(outcome) = self.validate_remote_control(&wire) {
            return outcome;
        }
        match wire.message_type.as_str() {
            "command" => self.receive_command(core, wire, command_cache),
            "snapshot-request" => {
                if typed_from_wire::<pps_contracts::EmptyBody>(wire, "snapshot-request").is_err() {
                    return self.protocol_error(
                        "invalid_snapshot_request",
                        "Snapshot request body must be an empty object.",
                        "error",
                        true,
                    );
                }
                self.refresh_lease(core);
                if !self.can_read() {
                    return self.protocol_error(
                        "scope_required",
                        "session.read is required for snapshots.",
                        "ready",
                        false,
                    );
                }
                let mut outcome = RelayOutcome::new("ready", "Snapshot published.");
                if let Err(message) = self.push_snapshot(&mut outcome, core) {
                    return self.protocol_error("snapshot_too_large", &message, "error", true);
                }
                outcome
            }
            "error" => {
                let diagnostic = match typed_from_wire::<ErrorBody>(wire, "error") {
                    Ok(diagnostic) => diagnostic,
                    Err(_) => {
                        return self.protocol_error(
                            "invalid_error",
                            "Peer diagnostic body is invalid.",
                            "error",
                            true,
                        )
                    }
                };
                if !valid_protocol_error(&diagnostic.body) {
                    return self.protocol_error(
                        "invalid_error",
                        "Peer diagnostic is not bounded display-safe text.",
                        "error",
                        true,
                    );
                }
                self.refresh_lease(core);
                RelayOutcome::new("ready", "Bounded controller diagnostic received.")
            }
            "bye" => {
                if typed_from_wire::<pps_contracts::EmptyBody>(wire, "bye").is_err() {
                    return self.protocol_error(
                        "invalid_bye",
                        "Bye body must be an empty object.",
                        "error",
                        true,
                    );
                }
                RelayOutcome::terminal("waiting_controller", "Controller ended the BRSP session.")
            }
            _ => self.protocol_error(
                "unsupported_message",
                "Message type is not valid from a ready controller.",
                "ready",
                false,
            ),
        }
    }

    fn receive_command(
        &mut self,
        core: &mut RunnerCore,
        wire: WireEnvelope,
        command_cache: &mut VecDeque<CommandCacheEntry>,
    ) -> RelayOutcome {
        let frame: CommandEnvelope = match typed_from_wire(wire, "command") {
            Ok(frame) => frame,
            Err(message) => return self.protocol_error("invalid_command", &message, "error", true),
        };
        let fingerprint = match serde_json::to_value(&frame.body)
            .map_err(|_| "Command body could not be encoded.".to_owned())
            .and_then(|value| canonical_json(&value).map_err(|error| error.to_string()))
        {
            Ok(fingerprint) => fingerprint,
            Err(message) => return self.protocol_error("invalid_command", &message, "error", true),
        };
        if let Some(reason) = self.current_authorization_error(&frame.body) {
            let mut outcome = RelayOutcome::new("ready", "Command was not authorized.");
            let rejected = rejected_applied(&frame.body, core.revision(), reason);
            if self.push_applied(&mut outcome, rejected).is_err() {
                return self.protocol_error(
                    "serialization_failed",
                    "Applied rejection could not be encoded.",
                    "error",
                    true,
                );
            }
            return outcome;
        }
        if let Some(previous) = command_cache
            .iter()
            .find(|entry| entry.command_id == frame.body.command_id)
            .cloned()
        {
            if previous.fingerprint != fingerprint {
                return self.protocol_error(
                    "command_id_reused",
                    "commandId was reused with a different command body.",
                    "error",
                    true,
                );
            }
            self.refresh_lease(core);
            let applied = previous.applied.clone();
            let mut outcome = RelayOutcome::new("ready", "Duplicate command acknowledged.");
            if self.push_applied(&mut outcome, applied).is_err() {
                return self.protocol_error(
                    "serialization_failed",
                    "Applied acknowledgement could not be encoded.",
                    "error",
                    true,
                );
            }
            return outcome;
        }

        self.refresh_lease(core);
        let body = frame.body;
        let controller = self
            .controller_hello
            .as_ref()
            .expect("controller hello exists while ready");
        let granted_scopes = self.scope_set();
        let request = body.clone().into_request(core.epoch(), frame.sequence);
        let applied = core.dispatch(
            DispatchOrigin::Remote {
                controller_id: controller.sender_id.clone(),
                granted_scopes,
                lease_valid: self.lease_is_valid(),
            },
            request,
            clock_stamp(),
        );
        let applied_body = AppliedBody::from(&applied);
        remember_command(
            command_cache,
            body.command_id,
            fingerprint,
            applied_body.clone(),
        );
        let mut outcome = RelayOutcome::new("ready", "Command acknowledgement published.");
        outcome.refresh_ui = true;
        if self.push_applied(&mut outcome, applied_body).is_err() {
            return self.protocol_error(
                "serialization_failed",
                "Applied acknowledgement could not be encoded.",
                "error",
                true,
            );
        }
        if self.can_read() {
            if let Err(message) = self.push_state(&mut outcome, core) {
                return self.protocol_error("state_too_large", &message, "error", true);
            }
        }
        outcome
    }

    fn expiration(&mut self, _core: &mut RunnerCore) -> Option<RelayOutcome> {
        if self.phase == HandshakePhase::Ready {
            if self
                .lease_deadline
                .is_some_and(|deadline| Instant::now() >= deadline)
            {
                return Some(self.protocol_error(
                    "lease_expired",
                    "Controller heartbeat lease expired; authority was revoked.",
                    "lease_expired",
                    true,
                ));
            }
        } else if Instant::now() >= self.handshake_deadline {
            return Some(self.protocol_error(
                "handshake_timeout",
                "Mutual BRSP authentication timed out.",
                "error",
                true,
            ));
        }
        None
    }

    fn validate_remote_control(&mut self, wire: &WireEnvelope) -> Result<(), RelayOutcome> {
        if validate_common(wire, &wire.message_type).is_err() {
            return Err(self.protocol_error(
                "invalid_envelope",
                "BRSP common envelope validation failed.",
                "error",
                true,
            ));
        }
        let controller = self
            .controller_hello
            .as_ref()
            .expect("controller hello exists after AwaitingHello");
        if wire.session_id != controller.session_id
            || wire.sender_id != controller.sender_id
            || wire.sender_epoch != controller.sender_epoch
        {
            return Err(self.protocol_error(
                "sender_mismatch",
                "Envelope sender does not match the authenticated hello.",
                "error",
                true,
            ));
        }
        let decision = self
            .remote_control_sequence
            .as_mut()
            .expect("sequence guard exists after controller hello")
            .accept(wire.sequence);
        if decision != SequenceDecision::Fresh {
            return Err(self.protocol_error(
                "replayed_sequence",
                "Control sequence is duplicate, old, or half-range ambiguous.",
                if self.phase == HandshakePhase::Ready {
                    "ready"
                } else {
                    "authenticating"
                },
                false,
            ));
        }
        Ok(())
    }

    fn refresh_lease(&mut self, core: &mut RunnerCore) {
        let deadline = Instant::now() + CONTROLLER_LEASE;
        self.lease_deadline = Some(deadline);
        let controller_id = self
            .controller_hello
            .as_ref()
            .map(|hello| hello.sender_id.as_str());
        let now = clock_stamp();
        core.set_controller_lease(
            controller_id,
            Some(
                now.unix_ms
                    .saturating_add(CONTROLLER_LEASE.as_millis() as u64)
                    .min(JSON_MAX_SAFE_INTEGER),
            ),
            now,
        );
    }

    fn lease_is_valid(&self) -> bool {
        self.phase == HandshakePhase::Ready
            && self
                .lease_deadline
                .is_some_and(|deadline| Instant::now() < deadline)
    }

    fn can_read(&self) -> bool {
        self.scope_set().contains(&Scope::SessionRead)
    }

    fn scope_set(&self) -> BTreeSet<Scope> {
        self.negotiated
            .as_ref()
            .map(|session| session.accepted_scopes.iter().copied().collect())
            .unwrap_or_default()
    }

    fn current_authorization_error(&self, body: &CommandBody) -> Option<&'static str> {
        if !is_safe_remote_action(body.action) {
            return Some("action_not_exposed_by_quest_remote");
        }
        if body.action.required_scope() != Some(body.scope) {
            return Some("scope_action_mismatch");
        }
        if !self.scope_set().contains(&body.scope) {
            return Some("scope_not_granted");
        }
        None
    }

    fn push_applied(
        &mut self,
        outcome: &mut RelayOutcome,
        body: AppliedBody,
    ) -> Result<(), String> {
        let envelope = Envelope::new(
            "applied",
            self.target_hello.session_id.clone(),
            self.target_hello.sender_id.clone(),
            self.target_hello.sender_epoch,
            self.next_control_sequence(),
            body,
        );
        self.push_serialized(outcome, &envelope, MAX_CONTROL_BYTES)
    }

    fn push_snapshot(
        &mut self,
        outcome: &mut RelayOutcome,
        core: &RunnerCore,
    ) -> Result<(), String> {
        let state = self.remote_snapshot(core);
        let envelope = Envelope::new(
            "snapshot",
            self.target_hello.session_id.clone(),
            self.target_hello.sender_id.clone(),
            self.target_hello.sender_epoch,
            self.next_control_sequence(),
            SnapshotBody {
                revision: state.revision,
                state,
            },
        );
        self.push_serialized(outcome, &envelope, MAX_CONTROL_BYTES)
    }

    fn push_state(&mut self, outcome: &mut RelayOutcome, core: &RunnerCore) -> Result<(), String> {
        let state = self.remote_snapshot(core);
        self.target_state_sequence = self.target_state_sequence.wrapping_add(1);
        let envelope = Envelope::new(
            "state",
            self.target_hello.session_id.clone(),
            self.target_hello.sender_id.clone(),
            self.target_hello.sender_epoch,
            self.target_state_sequence,
            StateBody {
                revision: state.revision,
                state,
            },
        );
        self.push_serialized(outcome, &envelope, MAX_STATE_BYTES)?;
        self.last_state_revision = Some(core.revision());
        self.last_state_sent = Instant::now();
        Ok(())
    }

    fn remote_snapshot(&self, core: &RunnerCore) -> RunnerSnapshot {
        let scopes = self.scope_set();
        let mut snapshot = core.snapshot();
        snapshot.allowed_actions.retain(|action| {
            is_safe_remote_action(*action)
                && action
                    .required_scope()
                    .is_some_and(|required| scopes.contains(&required))
        });
        snapshot
    }

    fn push_serialized<T: Serialize>(
        &self,
        outcome: &mut RelayOutcome,
        value: &T,
        maximum: usize,
    ) -> Result<(), String> {
        if outcome.outbound.len() >= MAX_OUTBOUND_FRAMES {
            return Err("Native relay response exceeded four frames.".to_owned());
        }
        outcome.outbound.push(encode_bounded(value, maximum)?);
        Ok(())
    }

    fn protocol_error(
        &mut self,
        code: &str,
        message: &str,
        phase: &str,
        close: bool,
    ) -> RelayOutcome {
        let mut outcome = if close {
            RelayOutcome::terminal(phase, message)
        } else {
            RelayOutcome::new(phase, message)
        };
        let envelope = Envelope::new(
            "error",
            self.target_hello.session_id.clone(),
            self.target_hello.sender_id.clone(),
            self.target_hello.sender_epoch,
            self.next_control_sequence(),
            ErrorBody {
                code: bounded_token(code),
                message: bounded_message(message),
            },
        );
        if let Ok(encoded) = encode_bounded(&envelope, MAX_CONTROL_BYTES) {
            outcome.outbound.push(encoded);
        }
        outcome
    }

    fn next_control_sequence(&mut self) -> u32 {
        self.target_control_sequence = self.target_control_sequence.wrapping_add(1);
        self.target_control_sequence
    }
}

fn typed_from_wire<T: DeserializeOwned>(
    wire: WireEnvelope,
    expected_type: &str,
) -> Result<Envelope<T>, String> {
    if wire.message_type != expected_type {
        return Err(format!("Expected {expected_type} envelope."));
    }
    serde_json::from_value(serde_json::to_value(wire).map_err(|_| "Invalid envelope.".to_owned())?)
        .map_err(|_| format!("Invalid {expected_type} body."))
}

fn rejected_applied(body: &CommandBody, revision: u64, reason: &str) -> AppliedBody {
    AppliedBody {
        command_id: body.command_id.clone(),
        ok: false,
        revision,
        result: None,
        error: Some(reason.to_owned()),
    }
}

fn remember_command(
    cache: &mut VecDeque<CommandCacheEntry>,
    command_id: String,
    fingerprint: String,
    applied: AppliedBody,
) {
    cache.push_back(CommandCacheEntry {
        command_id,
        fingerprint,
        applied,
    });
    while cache.len() > COMMAND_DEDUPE_LIMIT {
        cache.pop_front();
    }
}

fn is_safe_remote_action(action: Action) -> bool {
    matches!(
        action,
        Action::SystemSnapshot
            | Action::PackagePrepareDemo
            | Action::SetupSubmit
            | Action::PartStart
            | Action::RunPause
            | Action::RunResume
            | Action::RunStop
            | Action::SessionNote
    )
}

fn valid_protocol_error(error: &ErrorBody) -> bool {
    valid_token(&error.code, 1, 64)
        && error.message.chars().count() <= 256
        && !error.message.chars().any(|character| {
            matches!(
                character,
                '\u{0000}'..='\u{0008}'
                    | '\u{000b}'
                    | '\u{000c}'
                    | '\u{000e}'..='\u{001f}'
                    | '\u{007f}'
            )
        })
}

fn available_scopes() -> Vec<Scope> {
    let mut scopes = vec![
        Scope::SessionRead,
        Scope::SessionPrepare,
        Scope::SessionTransport,
        Scope::SessionAnnotate,
        Scope::SessionAbort,
    ];
    scopes.sort();
    scopes
}

fn revoke_core(core: &mut RunnerCore, state: &str, pause_active_run: bool) {
    let now = clock_stamp();
    core.set_controller_lease(None, None, now.clone());
    core.set_connection_state(state, now.clone());
    if pause_active_run && core.snapshot().run.phase == RunnerPhase::Running {
        core.dispatch_local(Action::RunPause, serde_json::json!({}), now);
    }
}

fn validate_room(room: &str) -> Result<(), String> {
    if (8..=64).contains(&room.len())
        && room
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || matches!(character, '-' | '_'))
    {
        Ok(())
    } else {
        Err("Room must match [A-Za-z0-9_-]{8,64}.".to_owned())
    }
}

fn validate_companion_base(value: &str) -> Result<(), String> {
    let valid_scheme = value.starts_with("https://") || value.starts_with("http://");
    if value.len() <= 512
        && valid_scheme
        && !value.contains(['#', '?'])
        && !value.chars().any(char::is_whitespace)
    {
        Ok(())
    } else {
        Err(
            "Companion base URL must be a bounded http(s) URL without query or fragment."
                .to_owned(),
        )
    }
}

fn encode_bounded<T: Serialize>(value: &T, maximum: usize) -> Result<String, String> {
    let encoded =
        serde_json::to_string(value).map_err(|_| "JSON serialization failed.".to_owned())?;
    if encoded.len() > maximum {
        Err(format!("Serialized BRSP frame exceeds {maximum} bytes."))
    } else {
        Ok(encoded)
    }
}

fn constant_time_equal(left: &[u8], right: &[u8]) -> bool {
    let length = left.len().max(right.len());
    let mut difference = left.len() ^ right.len();
    for index in 0..length {
        difference |= usize::from(
            left.get(index).copied().unwrap_or_default()
                ^ right.get(index).copied().unwrap_or_default(),
        );
    }
    difference == 0
}

fn bounded_token(value: &str) -> String {
    value
        .chars()
        .filter(|character| character.is_ascii_alphanumeric() || matches!(character, '_' | '-'))
        .take(48)
        .collect()
}

fn bounded_message(value: &str) -> String {
    value.chars().take(160).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use pps_brsp::{create_proof_envelope, proof_transcript};
    use pps_contracts::{AppliedEnvelope, EmptyBody, ErrorEnvelope};
    use serde_json::{json, Value};

    fn core() -> RunnerCore {
        let mut core = RunnerCore::new(
            "pps-quest-local-preview",
            "native-quest-spatial-preview",
            7,
            pps_contracts::TimingTier::NativeQuestUnqualified,
            clock_stamp(),
        );
        core.dispatch_local(
            Action::PackagePrepareDemo,
            json!({"label": "Quest test"}),
            clock_stamp(),
        );
        core.dispatch_local(
            Action::SetupSubmit,
            json!({
                "participant_code": "QUEST_TEST",
                "age": 18,
                "handedness": "prefer_not_to_say",
                "gender": "prefer_not_to_say",
                "name_sharing_opt_in": false,
                "part_labels": {"1": "One", "2": "Two"}
            }),
            clock_stamp(),
        );
        core
    }

    struct Harness {
        relay: RelayAuthority,
        core: RunnerCore,
        secret: PairingSecret,
        target: HelloEnvelope,
        controller: HelloEnvelope,
        negotiated: NegotiatedSession,
    }

    fn authenticated(requested_scopes: Vec<Scope>) -> Harness {
        let mut relay = RelayAuthority::default();
        let mut core = core();
        let pairing = relay
            .create_pairing(&mut core, "https://lab.example/companion/", "quest_lab_01")
            .unwrap();
        let secret = PairingSecret::from_base64(&pairing.secret).unwrap();
        let begin = relay.begin(&mut core, &pairing.secret);
        let target: HelloEnvelope = serde_json::from_str(&begin.outbound[0]).unwrap();
        let controller = Envelope::new(
            "hello",
            pairing.session_id,
            "controller_abcdef",
            2,
            0,
            HelloBody {
                role: BrspRole::Controller,
                nonce: "Y29udHJvbGxlci1ub25jZS0xMjM0NTY".to_owned(),
                capabilities: PPS_REMOTE_CAPABILITIES
                    .iter()
                    .map(|value| (*value).to_owned())
                    .collect(),
                requested_scopes,
                granted_scopes: vec![],
            },
        );
        let proof_response =
            relay.handle_frame(&mut core, &serde_json::to_string(&controller).unwrap());
        assert_eq!(proof_response.phase, "authenticating");
        let controller_proof = create_proof_envelope(&secret, &controller, &target, 1).unwrap();
        let ready_response = relay.handle_frame(
            &mut core,
            &serde_json::to_string(&controller_proof).unwrap(),
        );
        let target_ready: ReadyEnvelope =
            serde_json::from_str(&ready_response.outbound[0]).unwrap();
        let negotiated = negotiate_session(&target, &controller).unwrap();
        let controller_ready = Envelope::new(
            "ready",
            controller.session_id.clone(),
            controller.sender_id.clone(),
            controller.sender_epoch,
            2,
            target_ready.body,
        );
        let accepted = relay.handle_frame(
            &mut core,
            &serde_json::to_string(&controller_ready).unwrap(),
        );
        assert_eq!(accepted.phase, "ready");
        Harness {
            relay,
            core,
            secret,
            target,
            controller,
            negotiated,
        }
    }

    fn reconnect(harness: &mut Harness, requested_scopes: Vec<Scope>) {
        harness.relay.end(&mut harness.core, "test reconnect");
        let begin = harness
            .relay
            .begin(&mut harness.core, &harness.secret.expose_base64());
        let target: HelloEnvelope = serde_json::from_str(&begin.outbound[0]).unwrap();
        let controller = Envelope::new(
            "hello",
            target.session_id.clone(),
            "controller_reconnect",
            29,
            0,
            HelloBody {
                role: BrspRole::Controller,
                nonce: "cmVjb25uZWN0LW5vbmNlLTEyMzQ1Njc4".to_owned(),
                capabilities: PPS_REMOTE_CAPABILITIES
                    .iter()
                    .map(|value| (*value).to_owned())
                    .collect(),
                requested_scopes,
                granted_scopes: vec![],
            },
        );
        harness.relay.handle_frame(
            &mut harness.core,
            &serde_json::to_string(&controller).unwrap(),
        );
        let proof = create_proof_envelope(&harness.secret, &controller, &target, 1).unwrap();
        let target_ready_result = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&proof).unwrap());
        let target_ready: ReadyEnvelope =
            serde_json::from_str(&target_ready_result.outbound[0]).unwrap();
        let negotiated = negotiate_session(&target, &controller).unwrap();
        let controller_ready = Envelope::new(
            "ready",
            controller.session_id.clone(),
            controller.sender_id.clone(),
            controller.sender_epoch,
            2,
            target_ready.body,
        );
        let result = harness.relay.handle_frame(
            &mut harness.core,
            &serde_json::to_string(&controller_ready).unwrap(),
        );
        assert_eq!(result.phase, "ready");
        harness.target = target;
        harness.controller = controller;
        harness.negotiated = negotiated;
    }

    fn command(
        harness: &Harness,
        sequence: u32,
        command_id: &str,
        scope: Scope,
        action: Action,
        args: Value,
        expected_revision: Option<u64>,
    ) -> CommandEnvelope {
        Envelope::new(
            "command",
            harness.controller.session_id.clone(),
            harness.controller.sender_id.clone(),
            harness.controller.sender_epoch,
            sequence,
            CommandBody {
                command_id: command_id.to_owned(),
                scope,
                action,
                args,
                expected_revision,
            },
        )
    }

    #[test]
    fn shared_cross_language_proof_fixture_is_exact() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../../../../packages/pps-brsp/test-vectors/brsp1-proof.json"
        ))
        .unwrap();
        let target: HelloEnvelope = serde_json::from_value(fixture["targetHello"].clone()).unwrap();
        let controller: HelloEnvelope =
            serde_json::from_value(fixture["controllerHello"].clone()).unwrap();
        let secret = PairingSecret::from_base64(fixture["secret"].as_str().unwrap()).unwrap();
        assert_eq!(
            proof_transcript(&target, &controller).unwrap(),
            fixture["canonicalTranscript"].as_str().unwrap()
        );
        assert_eq!(
            create_proof_envelope(&secret, &target, &controller, 1)
                .unwrap()
                .body
                .value,
            fixture["targetProof"].as_str().unwrap()
        );
    }

    #[test]
    fn pairing_secret_stays_in_fragment_and_session_is_explicit() {
        let mut relay = RelayAuthority::default();
        let mut core = core();
        let pairing = relay
            .create_pairing(&mut core, "https://lab.example/companion/", "quest_lab_01")
            .unwrap();
        let before_fragment = pairing.invitation.split('#').next().unwrap();
        assert!(!before_fragment.contains(&pairing.secret));
        assert!(pairing.invitation.contains("session_id=quest_session_"));
        assert!(pairing.invitation.contains("secret="));
        assert_eq!(pairing.secret.len(), 43);
    }

    #[test]
    fn read_scope_controls_all_snapshot_and_state_publication() {
        let mut harness = authenticated(vec![Scope::SessionTransport]);
        let request = Envelope::new(
            "snapshot-request",
            harness.controller.session_id.clone(),
            harness.controller.sender_id.clone(),
            harness.controller.sender_epoch,
            3,
            EmptyBody {},
        );
        let result = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&request).unwrap());
        assert_eq!(result.outbound.len(), 1);
        let error: ErrorEnvelope = serde_json::from_str(&result.outbound[0]).unwrap();
        assert_eq!(error.body.code, "scope_required");
        assert!(result
            .outbound
            .iter()
            .all(|frame| !frame.contains("participant_code")));
        assert!(harness.relay.poll(&mut harness.core).outbound.is_empty());
    }

    #[test]
    fn invalid_peer_diagnostic_cannot_refresh_the_lease() {
        let mut harness = authenticated(vec![Scope::SessionRead]);
        let invalid = Envelope::new(
            "error",
            harness.controller.session_id.clone(),
            harness.controller.sender_id.clone(),
            harness.controller.sender_epoch,
            3,
            ErrorBody {
                code: String::new(),
                message: "x".repeat(257),
            },
        );
        let result = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&invalid).unwrap());
        assert!(result.close);
        assert_eq!(result.phase, "error");
        assert!(harness
            .core
            .snapshot()
            .safety
            .controller_lease_id
            .is_empty());
        assert!(harness.relay.session.is_none());
    }

    #[test]
    fn local_arm_operations_never_cross_the_remote_boundary() {
        let mut harness = authenticated(available_scopes());
        let revision = harness.core.revision();
        let frame = command(
            &harness,
            3,
            "remote-arm-0001",
            Scope::SessionTransport,
            Action::TargetArm,
            json!({}),
            Some(revision),
        );
        let result = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&frame).unwrap());
        let applied: AppliedEnvelope = serde_json::from_str(&result.outbound[0]).unwrap();
        assert!(!applied.body.ok);
        assert_eq!(
            applied.body.error.as_deref(),
            Some("action_not_exposed_by_quest_remote")
        );
        assert!(!harness.core.snapshot().safety.local_armed);
    }

    #[test]
    fn replay_is_rejected_and_fresh_command_id_retry_is_deduped() {
        let mut harness = authenticated(vec![Scope::SessionRead]);
        let frame = command(
            &harness,
            3,
            "snapshot-command-01",
            Scope::SessionRead,
            Action::SystemSnapshot,
            json!({}),
            None,
        );
        let encoded = serde_json::to_string(&frame).unwrap();
        let first = harness.relay.handle_frame(&mut harness.core, &encoded);
        let first_applied: AppliedEnvelope = serde_json::from_str(&first.outbound[0]).unwrap();
        let replay = harness.relay.handle_frame(&mut harness.core, &encoded);
        let replay_error: ErrorEnvelope = serde_json::from_str(&replay.outbound[0]).unwrap();
        assert_eq!(replay_error.body.code, "replayed_sequence");

        let retry = command(
            &harness,
            4,
            "snapshot-command-01",
            Scope::SessionRead,
            Action::SystemSnapshot,
            json!({}),
            None,
        );
        let retried = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&retry).unwrap());
        let retried_applied: AppliedEnvelope = serde_json::from_str(&retried.outbound[0]).unwrap();
        assert_eq!(first_applied.body, retried_applied.body);
    }

    #[test]
    fn fresh_uint32_wrap_sequence_zero_reaches_the_shared_core() {
        let mut harness = authenticated(vec![Scope::SessionRead]);
        harness
            .relay
            .session
            .as_mut()
            .unwrap()
            .remote_control_sequence = Some(SequenceGuard::after(u32::MAX));
        let frame = command(
            &harness,
            0,
            "wrapped-command-zero",
            Scope::SessionRead,
            Action::SystemSnapshot,
            json!({}),
            None,
        );
        let result = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&frame).unwrap());
        let applied: AppliedEnvelope = serde_json::from_str(&result.outbound[0]).unwrap();
        assert!(applied.body.ok);
    }

    #[test]
    fn wrong_scope_is_rejected_by_shared_core() {
        let mut harness = authenticated(vec![Scope::SessionTransport]);
        let revision = harness.core.revision();
        let frame = command(
            &harness,
            3,
            "pause-wrong-scope",
            Scope::SessionRead,
            Action::RunPause,
            json!({}),
            Some(revision),
        );
        let result = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&frame).unwrap());
        let applied: AppliedEnvelope = serde_json::from_str(&result.outbound[0]).unwrap();
        assert!(!applied.body.ok);
        assert_eq!(applied.body.error.as_deref(), Some("scope_action_mismatch"));
    }

    #[test]
    fn stale_expected_revision_is_rejected_without_mutation() {
        let mut harness = authenticated(vec![Scope::SessionAnnotate]);
        let current_revision = harness.core.revision();
        let frame = command(
            &harness,
            3,
            "stale-session-note",
            Scope::SessionAnnotate,
            Action::SessionNote,
            json!({"text": "must not be applied"}),
            Some(current_revision.saturating_sub(1)),
        );
        let result = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&frame).unwrap());
        let applied: AppliedEnvelope = serde_json::from_str(&result.outbound[0]).unwrap();
        assert!(!applied.body.ok);
        assert_eq!(applied.body.error.as_deref(), Some("revision_conflict"));
        assert_eq!(harness.core.revision(), current_revision);
        assert!(harness.core.snapshot().last_note.is_empty());
    }

    #[test]
    fn malformed_and_oversize_frames_fail_closed() {
        let mut malformed = authenticated(vec![Scope::SessionRead]);
        let result = malformed.relay.handle_frame(&mut malformed.core, "{");
        assert!(result.close);
        assert!(malformed
            .core
            .snapshot()
            .safety
            .controller_lease_id
            .is_empty());

        let mut oversized = authenticated(vec![Scope::SessionRead]);
        let result = oversized
            .relay
            .handle_frame(&mut oversized.core, &"x".repeat(MAX_CONTROL_BYTES + 1));
        assert!(result.close);
        assert!(oversized
            .core
            .snapshot()
            .safety
            .controller_lease_id
            .is_empty());
    }

    #[test]
    fn unauthenticated_peer_cannot_pause_a_local_run() {
        let mut relay = RelayAuthority::default();
        let mut core = core();
        let pairing = relay
            .create_pairing(&mut core, "https://lab.example/companion/", "quest_lab_01")
            .unwrap();
        core.dispatch_local(Action::TargetArm, json!({}), clock_stamp());
        core.dispatch_local(Action::PartStart, json!({"part_number": 1}), clock_stamp());
        assert_eq!(core.snapshot().run.phase, RunnerPhase::Running);

        relay.begin(&mut core, &pairing.secret);
        let malformed = relay.handle_frame(&mut core, "{");
        assert!(malformed.close);
        assert_eq!(core.snapshot().run.phase, RunnerPhase::Running);

        relay.begin(&mut core, &pairing.secret);
        relay.end(&mut core, "pre-auth peer left");
        assert_eq!(core.snapshot().run.phase, RunnerPhase::Running);
        assert!(core.snapshot().safety.controller_lease_id.is_empty());
    }

    #[test]
    fn lease_expiry_pauses_without_disarming_or_aborting() {
        let mut harness = authenticated(vec![Scope::SessionTransport]);
        harness
            .core
            .dispatch_local(Action::TargetArm, json!({}), clock_stamp());
        let revision = harness.core.revision();
        let start = command(
            &harness,
            3,
            "start-part-one-01",
            Scope::SessionTransport,
            Action::PartStart,
            json!({"part_number": 1}),
            Some(revision),
        );
        harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&start).unwrap());
        assert_eq!(harness.core.snapshot().run.phase, RunnerPhase::Running);
        harness.relay.session.as_mut().unwrap().lease_deadline =
            Some(Instant::now() - Duration::from_millis(1));
        let expired = harness.relay.poll(&mut harness.core);
        assert!(expired.close);
        assert_eq!(expired.phase, "lease_expired");
        assert_eq!(harness.core.snapshot().run.phase, RunnerPhase::Paused);
        assert!(harness.core.snapshot().safety.local_armed);
        assert!(harness
            .core
            .snapshot()
            .safety
            .controller_lease_id
            .is_empty());
    }

    #[test]
    fn reconnect_requires_a_fresh_handshake_and_preserves_pairing() {
        let mut harness = authenticated(vec![Scope::SessionRead]);
        let old_sender_epoch = harness.target.sender_epoch;
        let secret = harness.secret.expose_base64();
        harness.relay.end(&mut harness.core, "test disconnect");
        let begin = harness.relay.begin(&mut harness.core, &secret);
        assert!(!begin.close);
        let new_target: HelloEnvelope = serde_json::from_str(&begin.outbound[0]).unwrap();
        assert_ne!(old_sender_epoch, new_target.sender_epoch);
        assert_eq!(new_target.sequence, 0);
        assert!(harness
            .core
            .snapshot()
            .safety
            .controller_lease_id
            .is_empty());
    }

    #[test]
    fn command_dedupe_survives_a_fresh_controller_identity_reconnect() {
        let mut harness = authenticated(vec![Scope::SessionRead]);
        let first = command(
            &harness,
            3,
            "reconnect-dedupe-command",
            Scope::SessionRead,
            Action::SystemSnapshot,
            json!({}),
            None,
        );
        let first_result = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&first).unwrap());
        let first_applied: AppliedEnvelope =
            serde_json::from_str(&first_result.outbound[0]).unwrap();

        reconnect(&mut harness, vec![Scope::SessionTransport]);
        let narrowed = command(
            &harness,
            3,
            "reconnect-dedupe-command",
            Scope::SessionRead,
            Action::SystemSnapshot,
            json!({}),
            None,
        );
        let narrowed_result = harness.relay.handle_frame(
            &mut harness.core,
            &serde_json::to_string(&narrowed).unwrap(),
        );
        let narrowed_applied: AppliedEnvelope =
            serde_json::from_str(&narrowed_result.outbound[0]).unwrap();
        assert!(!narrowed_applied.body.ok);
        assert_eq!(
            narrowed_applied.body.error.as_deref(),
            Some("scope_not_granted")
        );

        reconnect(&mut harness, vec![Scope::SessionRead]);
        let retried = command(
            &harness,
            3,
            "reconnect-dedupe-command",
            Scope::SessionRead,
            Action::SystemSnapshot,
            json!({}),
            None,
        );
        let retried_result = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&retried).unwrap());
        let retried_applied: AppliedEnvelope =
            serde_json::from_str(&retried_result.outbound[0]).unwrap();
        assert_eq!(first_applied.body, retried_applied.body);

        let changed = command(
            &harness,
            4,
            "reconnect-dedupe-command",
            Scope::SessionRead,
            Action::SystemSnapshot,
            json!({"changed": true}),
            None,
        );
        let changed_result = harness
            .relay
            .handle_frame(&mut harness.core, &serde_json::to_string(&changed).unwrap());
        assert!(changed_result.close);
        let error: ErrorEnvelope = serde_json::from_str(&changed_result.outbound[0]).unwrap();
        assert_eq!(error.body.code, "command_id_reused");
    }

    #[test]
    fn handshake_fixture_negotiation_is_retained() {
        let harness = authenticated(vec![Scope::SessionTransport, Scope::SessionAbort]);
        assert_eq!(
            harness.negotiated.accepted_scopes,
            vec![Scope::SessionAbort, Scope::SessionTransport]
        );
    }
}
