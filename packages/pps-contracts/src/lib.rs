//! Versioned, transport-neutral contracts shared by PPS targets and controllers.

use std::{collections::BTreeMap, fmt, str::FromStr};

use serde::{de::Error as _, Deserialize, Deserializer, Serialize};
use serde_json::Value;
use thiserror::Error;

pub const BRSP_PROTOCOL: &str = "brsp";
pub const BRSP_VERSION: u8 = 1;
pub const SNAPSHOT_SCHEMA: &str = "pps-runner-authority-snapshot.v1";
pub const MAX_CONTROL_BYTES: usize = 16 * 1024;
pub const MAX_STATE_BYTES: usize = 8 * 1024;
/// Largest integer that round-trips exactly through browser JSON numbers.
pub const JSON_MAX_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

pub const CAPABILITY_COMMAND_ACK: &str = "command-ack";
pub const CAPABILITY_LATEST_STATE: &str = "latest-state";
pub const CAPABILITY_STATE_SNAPSHOT: &str = "state-snapshot";
pub const CAPABILITY_PPS_RUNNER_V1: &str = "pps-runner-v1";
pub const PPS_REMOTE_CAPABILITIES: [&str; 4] = [
    CAPABILITY_COMMAND_ACK,
    CAPABILITY_LATEST_STATE,
    CAPABILITY_PPS_RUNNER_V1,
    CAPABILITY_STATE_SNAPSHOT,
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Scope {
    #[serde(rename = "session.read")]
    SessionRead,
    #[serde(rename = "session.prepare")]
    SessionPrepare,
    #[serde(rename = "session.transport")]
    SessionTransport,
    #[serde(rename = "session.annotate")]
    SessionAnnotate,
    #[serde(rename = "session.abort")]
    SessionAbort,
}

impl Scope {
    pub const DEFAULT_REMOTE: [Self; 3] = [
        Self::SessionRead,
        Self::SessionPrepare,
        Self::SessionTransport,
    ];

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::SessionRead => "session.read",
            Self::SessionPrepare => "session.prepare",
            Self::SessionTransport => "session.transport",
            Self::SessionAnnotate => "session.annotate",
            Self::SessionAbort => "session.abort",
        }
    }
}

impl fmt::Display for Scope {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

impl Ord for Scope {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.as_str().cmp(other.as_str())
    }
}

impl PartialOrd for Scope {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl FromStr for Scope {
    type Err = ContractError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "session.read" => Ok(Self::SessionRead),
            "session.prepare" => Ok(Self::SessionPrepare),
            "session.transport" => Ok(Self::SessionTransport),
            "session.annotate" => Ok(Self::SessionAnnotate),
            "session.abort" => Ok(Self::SessionAbort),
            _ => Err(ContractError::UnknownScope(value.to_owned())),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Action {
    #[serde(rename = "system.snapshot")]
    SystemSnapshot,
    #[serde(rename = "package.prepare_demo")]
    PackagePrepareDemo,
    #[serde(rename = "setup.submit")]
    SetupSubmit,
    #[serde(rename = "target.arm")]
    TargetArm,
    #[serde(rename = "target.disarm")]
    TargetDisarm,
    #[serde(rename = "part.start")]
    PartStart,
    #[serde(rename = "instruction.continue")]
    InstructionContinue,
    #[serde(rename = "run.pause")]
    RunPause,
    #[serde(rename = "run.resume")]
    RunResume,
    #[serde(rename = "run.stop")]
    RunStop,
    #[serde(rename = "run.abort")]
    RunAbort,
    #[serde(rename = "run.complete_demo")]
    RunCompleteDemo,
    #[serde(rename = "session.note")]
    SessionNote,
}

impl Action {
    pub const ALL: [Self; 13] = [
        Self::SystemSnapshot,
        Self::PackagePrepareDemo,
        Self::SetupSubmit,
        Self::TargetArm,
        Self::TargetDisarm,
        Self::PartStart,
        Self::InstructionContinue,
        Self::RunPause,
        Self::RunResume,
        Self::RunStop,
        Self::RunAbort,
        Self::RunCompleteDemo,
        Self::SessionNote,
    ];

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::SystemSnapshot => "system.snapshot",
            Self::PackagePrepareDemo => "package.prepare_demo",
            Self::SetupSubmit => "setup.submit",
            Self::TargetArm => "target.arm",
            Self::TargetDisarm => "target.disarm",
            Self::PartStart => "part.start",
            Self::InstructionContinue => "instruction.continue",
            Self::RunPause => "run.pause",
            Self::RunResume => "run.resume",
            Self::RunStop => "run.stop",
            Self::RunAbort => "run.abort",
            Self::RunCompleteDemo => "run.complete_demo",
            Self::SessionNote => "session.note",
        }
    }

    pub const fn required_scope(self) -> Option<Scope> {
        match self {
            Self::SystemSnapshot => Some(Scope::SessionRead),
            Self::PackagePrepareDemo | Self::SetupSubmit => Some(Scope::SessionPrepare),
            Self::PartStart | Self::InstructionContinue | Self::RunPause | Self::RunResume => {
                Some(Scope::SessionTransport)
            }
            Self::RunStop | Self::RunAbort => Some(Scope::SessionAbort),
            Self::SessionNote => Some(Scope::SessionAnnotate),
            Self::TargetArm | Self::TargetDisarm | Self::RunCompleteDemo => None,
        }
    }

    pub const fn remotely_eligible(self) -> bool {
        self.required_scope().is_some()
    }

    pub const fn mutates_state(self) -> bool {
        !matches!(self, Self::SystemSnapshot)
    }
}

impl fmt::Display for Action {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

impl FromStr for Action {
    type Err = ContractError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        Self::ALL
            .into_iter()
            .find(|action| action.as_str() == value)
            .ok_or_else(|| ContractError::UnknownAction(value.to_owned()))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RunnerPhase {
    Idle,
    Prepared,
    Ready,
    InstructionGate,
    Running,
    Paused,
    Stopping,
    Completed,
    Interrupted,
    Error,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TimingTier {
    DesktopPreview,
    BrowserExploratory,
    NativeQuestUnqualified,
    NativeQualified,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ClockStamp {
    pub unix_ms: u64,
    pub monotonic_ns: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CommandRequest {
    pub id: String,
    pub epoch: u64,
    pub sequence: u64,
    pub expected_revision: Option<u64>,
    pub scope: Scope,
    pub action: Action,
    #[serde(default)]
    pub args: Value,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AppliedStatus {
    Accepted,
    Rejected,
    Duplicate,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Applied {
    pub id: String,
    pub action: Action,
    pub status: AppliedStatus,
    pub reason: String,
    pub accepted_revision: u64,
    pub resulting_revision: u64,
    pub snapshot: RunnerSnapshot,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IdentitySnapshot {
    pub participant_id: String,
    pub selected_participant_id: String,
    pub session_id: String,
    pub session_group_id: String,
    pub part_session_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SetupSnapshot {
    pub submitted: bool,
    pub ready: bool,
    pub required_missing: Vec<String>,
    pub participant_code: String,
    pub participant_name_present: bool,
    pub name_sharing_opt_in: bool,
    pub age: Option<u8>,
    pub handedness: String,
    pub gender: String,
    pub part_labels: BTreeMap<String, String>,
    pub part_label_options: Vec<String>,
    pub part_label_controls_visible: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PartSnapshot {
    pub available_parts: Vec<u8>,
    pub selected_part: Option<u8>,
    pub current_package_part: Option<u8>,
    pub pending_start_part: Option<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunSnapshot {
    pub phase: RunnerPhase,
    pub state_label: String,
    pub progress_label: String,
    pub event_label: String,
    pub thread_alive: bool,
    pub complete: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InstructionGateSnapshot {
    pub waiting: bool,
    pub gate_id: String,
    pub part2_start_gate: bool,
    pub instruction_label: String,
    pub button_label: String,
    pub next_action: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ActiveBlockSnapshot {
    pub active: bool,
    pub part_number: Option<u8>,
    pub phase_label: String,
    pub block_index: Option<u32>,
    pub block_label: String,
    pub display_block_index: Option<u32>,
    pub duration_s: Option<f64>,
    pub elapsed_s: Option<f64>,
    pub last_anchor_server_monotonic_ns: Option<u64>,
    pub running: bool,
    pub paused: bool,
    pub instruction_waiting: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SafetySnapshot {
    pub controller_lease_id: String,
    pub lease_expires_at_unix_ms: Option<u64>,
    pub local_override: bool,
    pub local_armed: bool,
    pub audio_route_ready: bool,
    pub publication_ready: bool,
    pub lsl_ready: bool,
    pub capture_started: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunnerSnapshot {
    pub schema: String,
    pub protocol: String,
    pub target_id: String,
    pub target_kind: String,
    pub epoch: u64,
    pub revision: u64,
    pub server_unix_ms: u64,
    pub server_monotonic_ns: u64,
    pub connection_state: String,
    pub timing_tier: TimingTier,
    pub package_verified: bool,
    pub package_label: String,
    pub allowed_actions: Vec<Action>,
    pub identity: IdentitySnapshot,
    pub setup: SetupSnapshot,
    pub part: PartSnapshot,
    pub run: RunSnapshot,
    pub instruction_gate: InstructionGateSnapshot,
    pub active_block: ActiveBlockSnapshot,
    pub safety: SafetySnapshot,
    pub audit_event_count: u64,
    pub last_note: String,
}

/// The normative BRSP/1 common envelope. Every wire message has exactly these
/// fields; application-specific data lives only in `body`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Envelope<T> {
    pub protocol: String,
    pub version: u8,
    #[serde(rename = "type")]
    pub message_type: String,
    pub session_id: String,
    pub sender_id: String,
    pub sender_epoch: u32,
    pub sequence: u32,
    pub body: T,
}

impl<T> Envelope<T> {
    pub fn new(
        message_type: impl Into<String>,
        session_id: impl Into<String>,
        sender_id: impl Into<String>,
        sender_epoch: u32,
        sequence: u32,
        body: T,
    ) -> Self {
        Self {
            protocol: BRSP_PROTOCOL.to_owned(),
            version: BRSP_VERSION,
            message_type: message_type.into(),
            session_id: session_id.into(),
            sender_id: sender_id.into(),
            sender_epoch,
            sequence,
            body,
        }
    }
}

pub type WireEnvelope = Envelope<Value>;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum BrspRole {
    Controller,
    Target,
}

impl BrspRole {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Controller => "controller",
            Self::Target => "target",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct HelloBody {
    pub role: BrspRole,
    pub nonce: String,
    pub capabilities: Vec<String>,
    pub requested_scopes: Vec<Scope>,
    pub granted_scopes: Vec<Scope>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProofBody {
    pub algorithm: String,
    pub role: BrspRole,
    pub value: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ReadyBody {
    pub capabilities: Vec<String>,
    pub accepted_scopes: Vec<Scope>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CommandBody {
    #[serde(deserialize_with = "deserialize_command_id")]
    pub command_id: String,
    pub scope: Scope,
    pub action: Action,
    pub args: Value,
    #[serde(deserialize_with = "deserialize_required_nullable")]
    pub expected_revision: Option<u64>,
}

fn deserialize_command_id<'de, D>(deserializer: D) -> Result<String, D::Error>
where
    D: Deserializer<'de>,
{
    let value = String::deserialize(deserializer)?;
    let mut characters = value.chars();
    let valid = (8..=96).contains(&value.len())
        && characters
            .next()
            .is_some_and(|character| character.is_ascii_alphanumeric())
        && characters.all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | ':' | '.')
        });
    if !valid {
        return Err(D::Error::custom(
            "commandId must be an 8-96 character BRSP token",
        ));
    }
    Ok(value)
}

// `Option<T>` fields normally deserialize a missing field as `None`. BRSP/1
// requires `expectedRevision` to be present, while permitting an explicit
// JSON null, so a custom deserializer makes absence a structural error.
fn deserialize_required_nullable<'de, D, T>(deserializer: D) -> Result<Option<T>, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de>,
{
    Option::<T>::deserialize(deserializer)
}

impl CommandBody {
    /// Adapt an authenticated BRSP command to the target-owned PPS reducer.
    /// The reducer epoch is the target authority epoch, while BRSP sender epoch
    /// and lane sequence remain transport/session replay boundaries.
    pub fn into_request(self, authority_epoch: u64, control_sequence: u32) -> CommandRequest {
        CommandRequest {
            id: self.command_id,
            epoch: authority_epoch,
            sequence: u64::from(control_sequence),
            expected_revision: self.expected_revision,
            scope: self.scope,
            action: self.action,
            args: self.args,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct PpsAppliedResult {
    pub action: Action,
    pub status: AppliedStatus,
    pub reason: String,
    pub accepted_revision: u64,
    pub resulting_revision: u64,
}

impl From<&Applied> for PpsAppliedResult {
    fn from(applied: &Applied) -> Self {
        Self {
            action: applied.action,
            status: applied.status,
            reason: applied.reason.clone(),
            accepted_revision: applied.accepted_revision,
            resulting_revision: applied.resulting_revision,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct AppliedBody {
    pub command_id: String,
    pub ok: bool,
    pub revision: u64,
    pub result: Option<Value>,
    pub error: Option<String>,
}

impl From<&Applied> for AppliedBody {
    fn from(applied: &Applied) -> Self {
        let ok = !matches!(applied.status, AppliedStatus::Rejected);
        Self {
            command_id: applied.id.clone(),
            ok,
            revision: applied.resulting_revision,
            result: serde_json::to_value(PpsAppliedResult::from(applied)).ok(),
            error: (!ok).then(|| applied.reason.clone()),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SnapshotBody {
    pub revision: u64,
    pub state: RunnerSnapshot,
}

pub type StateBody = SnapshotBody;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(deny_unknown_fields)]
pub struct EmptyBody {}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ErrorBody {
    pub code: String,
    pub message: String,
}

pub type HelloEnvelope = Envelope<HelloBody>;
pub type ProofEnvelope = Envelope<ProofBody>;
pub type ReadyEnvelope = Envelope<ReadyBody>;
pub type CommandEnvelope = Envelope<CommandBody>;
pub type AppliedEnvelope = Envelope<AppliedBody>;
pub type SnapshotEnvelope = Envelope<SnapshotBody>;
pub type StateEnvelope = Envelope<StateBody>;
pub type EmptyEnvelope = Envelope<EmptyBody>;
pub type ErrorEnvelope = Envelope<ErrorBody>;

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum ContractError {
    #[error("unknown PPS action: {0}")]
    UnknownAction(String),
    #[error("unknown PPS scope: {0}")]
    UnknownScope(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn action_scope_registry_is_closed() {
        assert_eq!(
            Action::RunPause.required_scope(),
            Some(Scope::SessionTransport)
        );
        assert_eq!(Action::RunStop.required_scope(), Some(Scope::SessionAbort));
        assert!(!Action::TargetArm.remotely_eligible());
        for action in Action::ALL {
            assert_eq!(Action::from_str(action.as_str()).unwrap(), action);
        }
    }

    #[test]
    fn unknown_command_fields_are_rejected() {
        let value = serde_json::json!({
            "id": "cmd-1",
            "epoch": 1,
            "sequence": 1,
            "expected_revision": 0,
            "scope": "session.transport",
            "action": "run.pause",
            "args": {},
            "surprise": true
        });
        assert!(serde_json::from_value::<CommandRequest>(value).is_err());
    }

    #[test]
    fn canonical_command_envelope_round_trips_and_rejects_unknown_fields() {
        let value = serde_json::json!({
            "protocol": "brsp",
            "version": 1,
            "type": "command",
            "sessionId": "session-1234",
            "senderId": "controller-1234",
            "senderEpoch": 7,
            "sequence": 2,
            "body": {
                "commandId": "cmd-1234",
                "scope": "session.transport",
                "action": "run.pause",
                "args": {},
                "expectedRevision": 3
            }
        });
        let message: CommandEnvelope = serde_json::from_value(value.clone()).unwrap();
        assert_eq!(message.message_type, "command");
        assert_eq!(message.body.action, Action::RunPause);
        assert_eq!(serde_json::to_value(message).unwrap(), value);

        let mut unknown = value;
        unknown["unexpected"] = serde_json::json!(true);
        assert!(serde_json::from_value::<CommandEnvelope>(unknown).is_err());
    }

    #[test]
    fn canonical_command_requires_all_fields_and_a_bounded_token_id() {
        let value = serde_json::json!({
            "protocol": "brsp",
            "version": 1,
            "type": "command",
            "sessionId": "session-1234",
            "senderId": "controller-1234",
            "senderEpoch": 7,
            "sequence": 2,
            "body": {
                "commandId": "command-1234",
                "scope": "session.transport",
                "action": "run.pause",
                "args": {},
                "expectedRevision": null
            }
        });
        assert!(serde_json::from_value::<CommandEnvelope>(value.clone()).is_ok());

        for field in ["args", "expectedRevision"] {
            let mut missing = value.clone();
            missing["body"].as_object_mut().unwrap().remove(field);
            assert!(serde_json::from_value::<CommandEnvelope>(missing).is_err());
        }

        for command_id in ["short", "-command-1234", "command/1234"] {
            let mut invalid = value.clone();
            invalid["body"]["commandId"] = serde_json::json!(command_id);
            assert!(serde_json::from_value::<CommandEnvelope>(invalid).is_err());
        }
    }
}
