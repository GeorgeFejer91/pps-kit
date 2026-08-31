use std::{
    fmt,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc::{self, Receiver, RecvTimeoutError, SyncSender, TryRecvError, TrySendError},
        Arc, Mutex,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

use pps_contracts::{RunnerPhase, RunnerSnapshot};
use pps_runner_audio_cpal::{
    CpalOutputService, ExactOutputSelection, OutputBufferSelection, OutputBufferSupport,
    OutputDeviceInventory, OutputFaultKind, OutputReservationReceipt, OutputServiceError,
    OutputServiceErrorCode, OutputServicePhase, MAXIMUM_WARMUP_TIMEOUT,
};
use serde::{Deserialize, Serialize};
use tokio::sync::oneshot;

const OUTPUT_COORDINATOR_THREAD: &str = "pps-native-output-coordinator";
const NORMAL_OPERATION_CAPACITY: usize = 1;
const SAFETY_WAKE_CAPACITY: usize = 1;
const COORDINATOR_POLL_INTERVAL: Duration = Duration::from_millis(2);
const RESERVATION_HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(100);
const ENUMERATION_DEADLINE: Duration = Duration::from_secs(6);
const RESERVATION_DEADLINE_GRACE: Duration = Duration::from_secs(3);
const CLIENT_REPLY_DEADLINE: Duration = Duration::from_secs(9);
const OUTPUT_SCHEMA: &str = "pps-runner-native-output-preflight.v1";
const INVENTORY_SCHEMA: &str = "pps-runner-native-output-inventory.v1";
const RESERVATION_SCHEMA: &str = "pps-runner-native-output-reservation.v1";
const SERVICE_GENERATION: u64 = 1;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub(crate) enum NativeOutputPhase {
    Idle,
    Enumerating,
    Enumerated,
    ReservingSilence,
    ReservedSilence,
    CleanupPending,
    Disabled,
    Faulted,
    Quarantined,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NativeOutputStatus {
    pub schema: &'static str,
    pub phase: NativeOutputPhase,
    pub policy_generation: String,
    pub service_generation: String,
    pub operation_generation: String,
    pub inventory_generation: Option<String>,
    pub reservation_generation: Option<String>,
    pub in_flight: bool,
    pub cleanup_pending: bool,
    pub silence_only: bool,
    pub media_connected: bool,
    pub armed: bool,
    pub executable: bool,
    pub qualified: bool,
    pub last_error_code: Option<&'static str>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NativeOutputInventory {
    pub schema: &'static str,
    pub policy_generation: String,
    pub service_generation: String,
    pub inventory_generation: String,
    pub devices: Vec<NativeOutputDevice>,
    pub devices_truncated: bool,
    pub silence_only: bool,
    pub media_connected: bool,
    pub armed: bool,
    pub executable: bool,
    pub qualified: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NativeOutputDevice {
    pub device_ordinal: u16,
    pub display_name: String,
    pub f32_configs: Vec<NativeOutputConfig>,
    pub configs_truncated: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NativeOutputConfig {
    pub config_ordinal: u16,
    pub channels: u16,
    pub minimum_sample_rate_hz: u32,
    pub maximum_sample_rate_hz: u32,
    pub sample_format: &'static str,
    pub minimum_buffer_frames: Option<u32>,
    pub maximum_buffer_frames: Option<u32>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct NativeOutputReserveRequest {
    pub policy_generation: String,
    pub service_generation: String,
    pub inventory_generation: String,
    pub device_ordinal: u16,
    pub config_ordinal: u16,
    pub channels: u16,
    pub sample_rate_hz: u32,
    pub buffer_frames: Option<u32>,
    pub warmup_timeout_ms: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct NativeOutputReleaseRequest {
    pub policy_generation: String,
    pub service_generation: String,
    pub reservation_generation: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NativeOutputReservation {
    pub schema: &'static str,
    pub policy_generation: String,
    pub service_generation: String,
    pub inventory_generation: String,
    pub reservation_generation: String,
    pub device_ordinal: u16,
    pub config_ordinal: u16,
    pub channels: u16,
    pub sample_rate_hz: u32,
    pub buffer_frames: Option<u32>,
    pub callback_count_at_warmup: u32,
    pub silence_only: bool,
    pub media_connected: bool,
    pub armed: bool,
    pub executable: bool,
    pub qualified: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NativeOutputCommandError {
    pub code: String,
    pub message: String,
}

impl NativeOutputCommandError {
    pub(crate) fn new(code: &str, message: &str) -> Self {
        Self {
            code: code.to_owned(),
            message: message.to_owned(),
        }
    }

    pub(crate) fn runtime() -> Self {
        Self::new(
            "runtime_unavailable",
            "The native Runner authority is unavailable.",
        )
    }

    fn busy() -> Self {
        Self::new(
            "native_output_busy",
            "Another native output preflight operation is already in progress.",
        )
    }

    fn changed() -> Self {
        Self::new(
            "native_output_changed",
            "The native output policy changed while the request was in progress.",
        )
    }

    pub(crate) fn timeout() -> Self {
        Self::new(
            "native_output_timeout",
            "The native output preflight did not complete before its deadline.",
        )
    }

    fn quarantined() -> Self {
        Self::new(
            "native_output_quarantined",
            "The native output service is quarantined after an uncertain cleanup outcome.",
        )
    }
}

impl fmt::Display for NativeOutputCommandError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.code)
    }
}

impl std::error::Error for NativeOutputCommandError {}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum NativeOutputOperationKind {
    Enumerate,
    ReserveSilence,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct NativeOutputTicket {
    policy_generation: u64,
    service_generation: u64,
    operation_generation: u64,
    kind: NativeOutputOperationKind,
}

impl NativeOutputTicket {
    pub(crate) const fn policy_generation(self) -> u64 {
        self.policy_generation
    }

    const fn service_generation(self) -> u64 {
        self.service_generation
    }

    pub(crate) const fn operation_generation(self) -> u64 {
        self.operation_generation
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct NativeOutputSelection {
    pub inventory_generation: u64,
    pub device_ordinal: u16,
    pub config_ordinal: u16,
    pub channels: u16,
    pub sample_rate_hz: u32,
    pub buffer_frames: Option<u32>,
    pub warmup_timeout: Duration,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct NativeOutputCleanupObservation {
    pub policy_generation: u64,
    pub quarantined: bool,
    pub faulted_reservation_generation: Option<u64>,
}

struct CoordinatorObservation {
    reconciled_policy_generation: AtomicU64,
    quarantined_policy_generation: AtomicU64,
    faulted_policy_generation: AtomicU64,
    faulted_reservation_generation: AtomicU64,
}

type AuthorityNoticeSink = dyn Fn() -> bool + Send + Sync + 'static;

struct CoordinatorNotice {
    sink: Mutex<Option<Arc<AuthorityNoticeSink>>>,
    pending: AtomicBool,
}

impl CoordinatorNotice {
    fn new() -> Self {
        Self {
            sink: Mutex::new(None),
            pending: AtomicBool::new(false),
        }
    }

    fn attach(&self, sink: Arc<AuthorityNoticeSink>) {
        *self.sink.lock().unwrap_or_else(|error| error.into_inner()) = Some(sink);
        self.flush();
    }

    fn mark_pending(&self) {
        self.pending.store(true, Ordering::Release);
    }

    fn flush(&self) {
        if !self.pending.swap(false, Ordering::AcqRel) {
            return;
        }
        let sink = self
            .sink
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .clone();
        if !sink.is_some_and(|sink| sink()) {
            self.pending.store(true, Ordering::Release);
        }
    }
}

impl CoordinatorObservation {
    fn new() -> Self {
        Self {
            reconciled_policy_generation: AtomicU64::new(SERVICE_GENERATION),
            quarantined_policy_generation: AtomicU64::new(0),
            faulted_policy_generation: AtomicU64::new(0),
            faulted_reservation_generation: AtomicU64::new(0),
        }
    }

    fn record(&self, policy_generation: u64, quarantined: bool) {
        self.quarantined_policy_generation.store(
            if quarantined { policy_generation } else { 0 },
            Ordering::Relaxed,
        );
        self.faulted_policy_generation.store(0, Ordering::Relaxed);
        self.faulted_reservation_generation
            .store(0, Ordering::Relaxed);
        self.reconciled_policy_generation
            .store(policy_generation, Ordering::Release);
    }

    fn record_reservation_fault(&self, policy_generation: u64, reservation_generation: u64) {
        self.faulted_reservation_generation
            .store(reservation_generation, Ordering::Relaxed);
        self.faulted_policy_generation
            .store(policy_generation, Ordering::Release);
    }

    fn load(&self) -> NativeOutputCleanupObservation {
        let policy_generation = self.reconciled_policy_generation.load(Ordering::Acquire);
        NativeOutputCleanupObservation {
            policy_generation,
            quarantined: self.quarantined_policy_generation.load(Ordering::Relaxed)
                == policy_generation,
            faulted_reservation_generation: (self
                .faulted_policy_generation
                .load(Ordering::Acquire)
                == policy_generation)
                .then(|| self.faulted_reservation_generation.load(Ordering::Relaxed)),
        }
    }
}

#[derive(Clone)]
pub(crate) struct NativeOutputInvalidator {
    latest_policy_generation: Arc<AtomicU64>,
    safety_wake: SyncSender<()>,
    shutdown_requested: Arc<AtomicBool>,
    observation: Arc<CoordinatorObservation>,
    disconnected_is_failure: bool,
}

impl NativeOutputInvalidator {
    pub(crate) fn invalidate(&self, policy_generation: u64) -> bool {
        self.latest_policy_generation
            .fetch_max(policy_generation, Ordering::AcqRel);
        match self.safety_wake.try_send(()) {
            Ok(()) | Err(TrySendError::Full(())) => true,
            Err(TrySendError::Disconnected(())) => !self.disconnected_is_failure,
        }
    }

    pub(crate) fn shutdown(&self, policy_generation: u64) {
        self.shutdown_requested.store(true, Ordering::Release);
        let _ = self.invalidate(policy_generation);
    }

    fn observation(&self) -> NativeOutputCleanupObservation {
        self.observation.load()
    }

    #[cfg(test)]
    pub(crate) fn inert() -> Self {
        let (safety_wake, _receive) = mpsc::sync_channel(SAFETY_WAKE_CAPACITY);
        Self {
            latest_policy_generation: Arc::new(AtomicU64::new(SERVICE_GENERATION)),
            safety_wake,
            shutdown_requested: Arc::new(AtomicBool::new(false)),
            observation: Arc::new(CoordinatorObservation::new()),
            disconnected_is_failure: false,
        }
    }
}

pub(crate) struct NativeOutputAuthority {
    invalidator: NativeOutputInvalidator,
    enabled: bool,
    policy_generation: u64,
    operation_generation: u64,
    inventory_generation: Option<u64>,
    reservation_generation: Option<u64>,
    in_flight: Option<NativeOutputTicket>,
    phase: NativeOutputPhase,
    cleanup_pending: bool,
    last_error_code: Option<&'static str>,
}

impl NativeOutputAuthority {
    pub(crate) fn new(invalidator: NativeOutputInvalidator) -> Self {
        Self {
            invalidator,
            enabled: true,
            policy_generation: SERVICE_GENERATION,
            operation_generation: 0,
            inventory_generation: None,
            reservation_generation: None,
            in_flight: None,
            phase: NativeOutputPhase::Idle,
            cleanup_pending: false,
            last_error_code: None,
        }
    }

    pub(crate) fn status(&self) -> NativeOutputStatus {
        NativeOutputStatus {
            schema: OUTPUT_SCHEMA,
            phase: self.phase,
            policy_generation: self.policy_generation.to_string(),
            service_generation: SERVICE_GENERATION.to_string(),
            operation_generation: self.operation_generation.to_string(),
            inventory_generation: self.inventory_generation.map(|value| value.to_string()),
            reservation_generation: self.reservation_generation.map(|value| value.to_string()),
            in_flight: self.in_flight.is_some(),
            cleanup_pending: self.cleanup_pending,
            silence_only: true,
            media_connected: false,
            armed: false,
            executable: false,
            qualified: false,
            last_error_code: self.last_error_code,
        }
    }

    pub(crate) fn refresh_from_invalidator(&mut self) {
        self.observe_cleanup(self.invalidator.observation());
    }

    pub(crate) fn observe_cleanup(&mut self, observation: NativeOutputCleanupObservation) {
        if observation.policy_generation > self.policy_generation {
            self.policy_generation = observation.policy_generation;
            self.inventory_generation = None;
            self.reservation_generation = None;
            self.in_flight = None;
            self.cleanup_pending = false;
            self.phase = if observation.quarantined {
                NativeOutputPhase::Quarantined
            } else if self.enabled {
                NativeOutputPhase::Idle
            } else {
                NativeOutputPhase::Disabled
            };
            self.last_error_code = observation
                .quarantined
                .then_some("native_output_quarantined");
            return;
        }
        if observation.policy_generation == self.policy_generation
            && observation.faulted_reservation_generation == self.reservation_generation
            && observation.faulted_reservation_generation.is_some()
        {
            self.inventory_generation = None;
            self.reservation_generation = None;
            self.in_flight = None;
            self.cleanup_pending = false;
            self.phase = NativeOutputPhase::Faulted;
            self.last_error_code = Some("native_output_callback_fault");
            return;
        }
        if observation.policy_generation != self.policy_generation || !self.cleanup_pending {
            return;
        }
        self.cleanup_pending = false;
        if observation.quarantined {
            self.phase = NativeOutputPhase::Quarantined;
            self.last_error_code = Some("native_output_quarantined");
        } else if self.enabled {
            self.phase = NativeOutputPhase::Idle;
            self.last_error_code = None;
        } else {
            self.phase = NativeOutputPhase::Disabled;
            self.last_error_code = None;
        }
    }

    pub(crate) fn begin_enumerate(
        &mut self,
        snapshot: &RunnerSnapshot,
    ) -> Result<NativeOutputTicket, NativeOutputCommandError> {
        self.require_quiescent(snapshot)?;
        if self.in_flight.is_some() {
            return Err(NativeOutputCommandError::busy());
        }
        if self.phase == NativeOutputPhase::Quarantined {
            return Err(NativeOutputCommandError::quarantined());
        }
        if self.reservation_generation.is_some() {
            return Err(NativeOutputCommandError::new(
                "native_output_reserved",
                "Release the silence reservation before enumerating output devices.",
            ));
        }
        self.enabled = true;
        let ticket = self.next_ticket(NativeOutputOperationKind::Enumerate)?;
        self.phase = NativeOutputPhase::Enumerating;
        self.last_error_code = None;
        Ok(ticket)
    }

    pub(crate) fn begin_reserve(
        &mut self,
        snapshot: &RunnerSnapshot,
        request: &NativeOutputReserveRequest,
    ) -> Result<(NativeOutputTicket, NativeOutputSelection), NativeOutputCommandError> {
        self.require_quiescent(snapshot)?;
        if self.in_flight.is_some() {
            return Err(NativeOutputCommandError::busy());
        }
        if self.phase == NativeOutputPhase::Quarantined {
            return Err(NativeOutputCommandError::quarantined());
        }
        let policy_generation = parse_generation(&request.policy_generation)?;
        let service_generation = parse_generation(&request.service_generation)?;
        let inventory_generation = parse_generation(&request.inventory_generation)?;
        if policy_generation != self.policy_generation
            || service_generation != SERVICE_GENERATION
            || self.inventory_generation != Some(inventory_generation)
        {
            return Err(NativeOutputCommandError::changed());
        }
        if self.reservation_generation.is_some() {
            return Err(NativeOutputCommandError::new(
                "native_output_reserved",
                "A native silence reservation already exists.",
            ));
        }
        let warmup_timeout = Duration::from_millis(u64::from(request.warmup_timeout_ms));
        if request.channels == 0
            || request.sample_rate_hz == 0
            || request.buffer_frames == Some(0)
            || warmup_timeout.is_zero()
            || warmup_timeout > MAXIMUM_WARMUP_TIMEOUT
        {
            return Err(NativeOutputCommandError::new(
                "native_output_invalid_selection",
                "The native output selection is invalid.",
            ));
        }
        let ticket = self.next_ticket(NativeOutputOperationKind::ReserveSilence)?;
        self.phase = NativeOutputPhase::ReservingSilence;
        self.last_error_code = None;
        Ok((
            ticket,
            NativeOutputSelection {
                inventory_generation,
                device_ordinal: request.device_ordinal,
                config_ordinal: request.config_ordinal,
                channels: request.channels,
                sample_rate_hz: request.sample_rate_hz,
                buffer_frames: request.buffer_frames,
                warmup_timeout,
            },
        ))
    }

    pub(crate) fn complete_enumerate(
        &mut self,
        ticket: NativeOutputTicket,
        result: Result<u64, NativeOutputCommandError>,
    ) -> Result<NativeOutputStatus, NativeOutputCommandError> {
        self.require_current_ticket(ticket, NativeOutputOperationKind::Enumerate)?;
        self.in_flight = None;
        match result {
            Ok(inventory_generation) => {
                self.inventory_generation = Some(inventory_generation);
                self.reservation_generation = None;
                self.phase = NativeOutputPhase::Enumerated;
                self.last_error_code = None;
                Ok(self.status())
            }
            Err(error) => {
                self.inventory_generation = None;
                self.phase = if error.code == "native_output_quarantined" {
                    NativeOutputPhase::Quarantined
                } else {
                    NativeOutputPhase::Idle
                };
                self.last_error_code = Some(error_code(&error));
                Err(error)
            }
        }
    }

    pub(crate) fn complete_reserve(
        &mut self,
        ticket: NativeOutputTicket,
        result: Result<u64, NativeOutputCommandError>,
    ) -> Result<NativeOutputStatus, NativeOutputCommandError> {
        self.require_current_ticket(ticket, NativeOutputOperationKind::ReserveSilence)?;
        self.in_flight = None;
        match result {
            Ok(reservation_generation) => {
                self.reservation_generation = Some(reservation_generation);
                self.phase = NativeOutputPhase::ReservedSilence;
                self.last_error_code = None;
                Ok(self.status())
            }
            Err(error) => {
                self.reservation_generation = None;
                self.phase = if error.code == "native_output_quarantined" {
                    self.inventory_generation = None;
                    NativeOutputPhase::Quarantined
                } else if self.inventory_generation.is_some() {
                    NativeOutputPhase::Enumerated
                } else {
                    NativeOutputPhase::Idle
                };
                self.last_error_code = Some(error_code(&error));
                Err(error)
            }
        }
    }

    pub(crate) fn release(
        &mut self,
        request: &NativeOutputReleaseRequest,
    ) -> Result<NativeOutputStatus, NativeOutputCommandError> {
        let policy_generation = parse_generation(&request.policy_generation)?;
        let service_generation = parse_generation(&request.service_generation)?;
        let reservation_generation = parse_generation(&request.reservation_generation)?;
        if policy_generation != self.policy_generation
            || service_generation != SERVICE_GENERATION
            || self.reservation_generation != Some(reservation_generation)
        {
            return Err(NativeOutputCommandError::changed());
        }
        self.invalidate(false)?;
        Ok(self.status())
    }

    pub(crate) fn disable(&mut self) -> Result<NativeOutputStatus, NativeOutputCommandError> {
        self.invalidate(true)?;
        Ok(self.status())
    }

    pub(crate) fn invalidate_for_runner_change(&mut self) {
        if self.invalidate(false).is_err() {
            self.quarantine("native_output_generation_exhausted");
        }
    }

    pub(crate) fn part_start_blocked(&mut self) -> bool {
        self.observe_cleanup(self.invalidator.observation());
        self.in_flight.is_some()
            || self.reservation_generation.is_some()
            || self.cleanup_pending
            || matches!(
                self.phase,
                NativeOutputPhase::Faulted | NativeOutputPhase::Quarantined
            )
    }

    pub(crate) fn shutdown(&mut self) {
        if self.invalidate(true).is_err() {
            self.phase = NativeOutputPhase::Quarantined;
            self.last_error_code = Some("native_output_generation_exhausted");
            self.invalidator.shutdown(self.policy_generation);
            return;
        }
        self.invalidator.shutdown(self.policy_generation);
    }

    fn next_ticket(
        &mut self,
        kind: NativeOutputOperationKind,
    ) -> Result<NativeOutputTicket, NativeOutputCommandError> {
        if self.policy_generation == u64::MAX {
            self.quarantine("native_output_generation_exhausted");
            return Err(NativeOutputCommandError::new(
                "native_output_generation_exhausted",
                "The native output policy generation is exhausted.",
            ));
        }
        let Some(operation_generation) = self.operation_generation.checked_add(1) else {
            self.quarantine("native_output_generation_exhausted");
            return Err(NativeOutputCommandError::new(
                "native_output_generation_exhausted",
                "The native output operation generation is exhausted.",
            ));
        };
        self.operation_generation = operation_generation;
        let ticket = NativeOutputTicket {
            policy_generation: self.policy_generation,
            service_generation: SERVICE_GENERATION,
            operation_generation,
            kind,
        };
        self.in_flight = Some(ticket);
        Ok(ticket)
    }

    fn require_current_ticket(
        &self,
        ticket: NativeOutputTicket,
        kind: NativeOutputOperationKind,
    ) -> Result<(), NativeOutputCommandError> {
        if ticket.kind != kind
            || ticket.policy_generation != self.policy_generation
            || ticket.service_generation != SERVICE_GENERATION
            || self.in_flight != Some(ticket)
        {
            return Err(NativeOutputCommandError::changed());
        }
        Ok(())
    }

    fn require_quiescent(&self, snapshot: &RunnerSnapshot) -> Result<(), NativeOutputCommandError> {
        if snapshot.safety.local_armed
            || matches!(
                snapshot.run.phase,
                RunnerPhase::Ready
                    | RunnerPhase::InstructionGate
                    | RunnerPhase::Running
                    | RunnerPhase::Paused
                    | RunnerPhase::Stopping
            )
        {
            return Err(NativeOutputCommandError::new(
                "native_output_not_quiescent",
                "Native output preflight is available only while the Runner is quiescent and disarmed.",
            ));
        }
        Ok(())
    }

    fn invalidate(&mut self, disable: bool) -> Result<(), NativeOutputCommandError> {
        let Some(next) = self.policy_generation.checked_add(1) else {
            self.quarantine("native_output_generation_exhausted");
            return Err(NativeOutputCommandError::new(
                "native_output_generation_exhausted",
                "The native output policy generation is exhausted.",
            ));
        };
        let had_private_state = self.inventory_generation.is_some()
            || self.reservation_generation.is_some()
            || self.in_flight.is_some()
            || self.cleanup_pending;
        self.policy_generation = next;
        self.enabled = !disable;
        self.inventory_generation = None;
        self.reservation_generation = None;
        self.in_flight = None;
        self.cleanup_pending = had_private_state;
        self.phase = if disable {
            NativeOutputPhase::Disabled
        } else if had_private_state {
            NativeOutputPhase::CleanupPending
        } else {
            NativeOutputPhase::Idle
        };
        self.last_error_code = None;
        if !self.invalidator.invalidate(next) {
            self.quarantine("native_output_runtime_unavailable");
            return Err(NativeOutputCommandError::runtime());
        }
        Ok(())
    }

    fn quarantine(&mut self, code: &'static str) {
        self.enabled = false;
        self.inventory_generation = None;
        self.reservation_generation = None;
        self.in_flight = None;
        self.cleanup_pending = false;
        self.phase = NativeOutputPhase::Quarantined;
        self.last_error_code = Some(code);
    }
}

fn error_code(error: &NativeOutputCommandError) -> &'static str {
    match error.code.as_str() {
        "native_output_busy" => "native_output_busy",
        "native_output_changed" => "native_output_changed",
        "native_output_timeout" => "native_output_timeout",
        "native_output_quarantined" => "native_output_quarantined",
        "native_output_invalid_selection" => "native_output_invalid_selection",
        "native_output_backend_unavailable" => "native_output_backend_unavailable",
        "native_output_enumeration_failed" => "native_output_enumeration_failed",
        "native_output_stream_build_failed" => "native_output_stream_build_failed",
        "native_output_stream_play_failed" => "native_output_stream_play_failed",
        "native_output_callback_fault" => "native_output_callback_fault",
        _ => "native_output_unavailable",
    }
}

fn parse_generation(value: &str) -> Result<u64, NativeOutputCommandError> {
    if value.is_empty()
        || (value.len() > 1 && value.starts_with('0'))
        || !value.bytes().all(|byte| byte.is_ascii_digit())
    {
        return Err(NativeOutputCommandError::new(
            "native_output_invalid_generation",
            "Native output generations must be canonical unsigned decimal strings.",
        ));
    }
    value.parse::<u64>().map_err(|_| {
        NativeOutputCommandError::new(
            "native_output_invalid_generation",
            "Native output generations must be canonical unsigned decimal strings.",
        )
    })
}

enum CoordinatorOperation {
    Enumerate,
    Reserve(NativeOutputSelection),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ReservationHealth {
    Healthy,
    ReleasedAfterCallbackFault,
    Uncertain,
}

struct CoordinatorRequest {
    ticket: NativeOutputTicket,
    deadline: Instant,
    operation: CoordinatorOperation,
    reply: oneshot::Sender<CoordinatorReply>,
}

pub(crate) enum CoordinatorReply {
    Enumerated {
        ticket: NativeOutputTicket,
        inventory_generation: u64,
        inventory: NativeOutputInventory,
    },
    Reserved {
        ticket: NativeOutputTicket,
        reservation_generation: u64,
        reservation: NativeOutputReservation,
    },
    Failed {
        ticket: NativeOutputTicket,
        error: NativeOutputCommandError,
    },
}

trait NativeOutputDriver: Send + 'static {
    type Inventory: Send + 'static;
    type Selection: Send + 'static;
    type Receipt: Send + 'static;

    fn enumerate(&mut self) -> Result<Self::Inventory, NativeOutputCommandError>;
    fn inventory_generation(inventory: &Self::Inventory) -> u64;
    fn inventory_projection(
        inventory: &Self::Inventory,
        policy_generation: u64,
    ) -> NativeOutputInventory;
    fn select(
        inventory: &Self::Inventory,
        selection: NativeOutputSelection,
    ) -> Result<Self::Selection, NativeOutputCommandError>;
    fn reserve(
        &mut self,
        selection: Self::Selection,
    ) -> Result<Self::Receipt, NativeOutputCommandError>;
    fn reservation_generation(receipt: &Self::Receipt) -> u64;
    fn reservation_projection(
        receipt: &Self::Receipt,
        policy_generation: u64,
    ) -> NativeOutputReservation;
    fn reservation_health(
        &mut self,
        receipt: &Self::Receipt,
    ) -> Result<ReservationHealth, NativeOutputCommandError>;
    fn release(&mut self, receipt: &Self::Receipt) -> Result<(), NativeOutputCommandError>;
    fn shutdown(&mut self) -> Result<(), NativeOutputCommandError>;
}

struct CpalDriver {
    service: CpalOutputService,
}

impl CpalDriver {
    fn open() -> Result<Self, NativeOutputCommandError> {
        CpalOutputService::new()
            .map(|service| Self { service })
            .map_err(map_service_error)
    }
}

impl NativeOutputDriver for CpalDriver {
    type Inventory = OutputDeviceInventory;
    type Selection = ExactOutputSelection;
    type Receipt = OutputReservationReceipt;

    fn enumerate(&mut self) -> Result<Self::Inventory, NativeOutputCommandError> {
        self.service
            .enumerate_output_devices()
            .map_err(map_service_error)
    }

    fn inventory_generation(inventory: &Self::Inventory) -> u64 {
        inventory.generation()
    }

    fn inventory_projection(
        inventory: &Self::Inventory,
        policy_generation: u64,
    ) -> NativeOutputInventory {
        NativeOutputInventory {
            schema: INVENTORY_SCHEMA,
            policy_generation: policy_generation.to_string(),
            service_generation: SERVICE_GENERATION.to_string(),
            inventory_generation: inventory.generation().to_string(),
            devices: inventory
                .devices()
                .iter()
                .map(|device| NativeOutputDevice {
                    device_ordinal: device.device_ordinal(),
                    display_name: device.display_name().to_owned(),
                    f32_configs: device
                        .f32_configs()
                        .iter()
                        .map(|config| {
                            let (minimum_buffer_frames, maximum_buffer_frames) =
                                match config.buffer_support() {
                                    OutputBufferSupport::Unknown => (None, None),
                                    OutputBufferSupport::Range {
                                        minimum_frames,
                                        maximum_frames,
                                    } => (Some(minimum_frames), Some(maximum_frames)),
                                };
                            NativeOutputConfig {
                                config_ordinal: config.config_ordinal(),
                                channels: config.channels(),
                                minimum_sample_rate_hz: config.minimum_sample_rate_hz(),
                                maximum_sample_rate_hz: config.maximum_sample_rate_hz(),
                                sample_format: "f32",
                                minimum_buffer_frames,
                                maximum_buffer_frames,
                            }
                        })
                        .collect(),
                    configs_truncated: device.configs_truncated(),
                })
                .collect(),
            devices_truncated: inventory.devices_truncated(),
            silence_only: true,
            media_connected: false,
            armed: false,
            executable: false,
            qualified: false,
        }
    }

    fn select(
        inventory: &Self::Inventory,
        selection: NativeOutputSelection,
    ) -> Result<Self::Selection, NativeOutputCommandError> {
        let buffer = selection
            .buffer_frames
            .map(OutputBufferSelection::Fixed)
            .unwrap_or(OutputBufferSelection::Default);
        inventory
            .select_exact(
                selection.device_ordinal,
                selection.config_ordinal,
                selection.channels,
                selection.sample_rate_hz,
                buffer,
                selection.warmup_timeout,
            )
            .map_err(map_service_error)
    }

    fn reserve(
        &mut self,
        selection: Self::Selection,
    ) -> Result<Self::Receipt, NativeOutputCommandError> {
        self.service
            .reserve_silence(selection)
            .map_err(map_service_error)
    }

    fn reservation_generation(receipt: &Self::Receipt) -> u64 {
        receipt.reservation_generation()
    }

    fn reservation_projection(
        receipt: &Self::Receipt,
        policy_generation: u64,
    ) -> NativeOutputReservation {
        let selection = receipt.selection();
        NativeOutputReservation {
            schema: RESERVATION_SCHEMA,
            policy_generation: policy_generation.to_string(),
            service_generation: SERVICE_GENERATION.to_string(),
            inventory_generation: selection.inventory_generation().to_string(),
            reservation_generation: receipt.reservation_generation().to_string(),
            device_ordinal: selection.device_ordinal(),
            config_ordinal: selection.config_ordinal(),
            channels: selection.channels(),
            sample_rate_hz: selection.sample_rate_hz(),
            buffer_frames: match selection.buffer() {
                OutputBufferSelection::Default => None,
                OutputBufferSelection::Fixed(frames) => Some(frames),
            },
            callback_count_at_warmup: receipt.callback_count_at_warmup(),
            silence_only: true,
            media_connected: false,
            armed: false,
            executable: false,
            qualified: false,
        }
    }

    fn reservation_health(
        &mut self,
        receipt: &Self::Receipt,
    ) -> Result<ReservationHealth, NativeOutputCommandError> {
        let status = self.service.status().map_err(map_service_error)?;
        if status.phase() == OutputServicePhase::ReservedSilence
            && status.reservation_generation() == Some(receipt.reservation_generation())
            && status.callback_fault_count() == 0
            && status.last_fault().is_none()
        {
            return Ok(ReservationHealth::Healthy);
        }
        if status.phase() == OutputServicePhase::Faulted
            && status.reservation_generation().is_none()
            && status
                .last_fault()
                .is_some_and(|fault| fault.kind() == OutputFaultKind::CallbackFault)
        {
            return Ok(ReservationHealth::ReleasedAfterCallbackFault);
        }
        Ok(ReservationHealth::Uncertain)
    }

    fn release(&mut self, receipt: &Self::Receipt) -> Result<(), NativeOutputCommandError> {
        self.service.release(receipt).map_err(map_service_error)
    }

    fn shutdown(&mut self) -> Result<(), NativeOutputCommandError> {
        self.service.shutdown().map_err(map_service_error)
    }
}

fn map_service_error(error: OutputServiceError) -> NativeOutputCommandError {
    let code = match error.code() {
        OutputServiceErrorCode::InvalidSelection
        | OutputServiceErrorCode::InventoryMissing
        | OutputServiceErrorCode::StaleInventory
        | OutputServiceErrorCode::SelectionOwnerMismatch
        | OutputServiceErrorCode::ExactConfigMismatch
        | OutputServiceErrorCode::ReceiptMismatch
        | OutputServiceErrorCode::StaleReservation => "native_output_invalid_selection",
        OutputServiceErrorCode::QueueFull | OutputServiceErrorCode::AlreadyReserved => {
            "native_output_busy"
        }
        OutputServiceErrorCode::RequestTimeout | OutputServiceErrorCode::WarmupTimeout => {
            "native_output_timeout"
        }
        OutputServiceErrorCode::BackendUnavailable
        | OutputServiceErrorCode::ServiceUnavailable
        | OutputServiceErrorCode::ThreadSpawnFailed => "native_output_backend_unavailable",
        OutputServiceErrorCode::EnumerationFailed => "native_output_enumeration_failed",
        OutputServiceErrorCode::BackendContractViolation
        | OutputServiceErrorCode::GenerationExhausted => "native_output_contract_failed",
        OutputServiceErrorCode::StreamBuildFailed => "native_output_stream_build_failed",
        OutputServiceErrorCode::StreamPlayFailed => "native_output_stream_play_failed",
        OutputServiceErrorCode::CallbackFault => "native_output_callback_fault",
        OutputServiceErrorCode::StreamReleaseFailed => "native_output_release_failed",
        OutputServiceErrorCode::ServiceShuttingDown => "native_output_service_stopping",
    };
    NativeOutputCommandError::new(code, error.public_message())
}

struct CoordinatorState<D: NativeOutputDriver> {
    driver: Option<D>,
    inventory: Option<D::Inventory>,
    receipt: Option<D::Receipt>,
    observed_policy_generation: u64,
    quarantined: bool,
}

impl<D: NativeOutputDriver> CoordinatorState<D> {
    fn new(driver: Result<D, NativeOutputCommandError>) -> Self {
        match driver {
            Ok(driver) => Self {
                driver: Some(driver),
                inventory: None,
                receipt: None,
                observed_policy_generation: SERVICE_GENERATION,
                quarantined: false,
            },
            Err(_) => Self {
                driver: None,
                inventory: None,
                receipt: None,
                observed_policy_generation: SERVICE_GENERATION,
                quarantined: true,
            },
        }
    }

    fn reconcile(
        &mut self,
        policy_generation: u64,
        observation: &CoordinatorObservation,
        notice: &CoordinatorNotice,
    ) {
        if policy_generation == self.observed_policy_generation {
            return;
        }
        self.inventory = None;
        if !self.quarantined {
            if let Some(receipt) = self.receipt.as_ref() {
                let release = self
                    .driver
                    .as_mut()
                    .ok_or_else(NativeOutputCommandError::quarantined)
                    .and_then(|driver| driver.release(receipt));
                if release.is_ok() {
                    self.receipt = None;
                } else {
                    self.quarantined = true;
                }
            }
        }
        self.observed_policy_generation = policy_generation;
        observation.record(policy_generation, self.quarantined);
        notice.mark_pending();
    }

    fn poll_reservation_health(
        &mut self,
        observation: &CoordinatorObservation,
        notice: &CoordinatorNotice,
        latest_policy_generation: &AtomicU64,
        shutdown_requested: &AtomicBool,
    ) {
        if self.quarantined {
            return;
        }
        let Some(receipt) = self.receipt.as_ref() else {
            return;
        };
        let reservation_generation = D::reservation_generation(receipt);
        let health = self
            .driver
            .as_mut()
            .ok_or_else(NativeOutputCommandError::quarantined)
            .and_then(|driver| driver.reservation_health(receipt));
        let latest = latest_policy_generation.load(Ordering::Acquire);
        if latest != self.observed_policy_generation
            || shutdown_requested.load(Ordering::Acquire)
        {
            self.reconcile(latest, observation, notice);
            return;
        }
        match health {
            Ok(ReservationHealth::Healthy) => {}
            Ok(ReservationHealth::ReleasedAfterCallbackFault) => {
                self.receipt = None;
                self.inventory = None;
                observation.record_reservation_fault(
                    self.observed_policy_generation,
                    reservation_generation,
                );
                notice.mark_pending();
            }
            Ok(ReservationHealth::Uncertain) | Err(_) => {
                self.quarantined = true;
                self.inventory = None;
                observation.record(self.observed_policy_generation, true);
                notice.mark_pending();
            }
        }
    }

    fn process(
        &mut self,
        request: CoordinatorRequest,
        latest_policy_generation: &AtomicU64,
        observation: &CoordinatorObservation,
        notice: &CoordinatorNotice,
        shutdown_requested: &AtomicBool,
    ) {
        let now = Instant::now();
        let latest = latest_policy_generation.load(Ordering::Acquire);
        if shutdown_requested.load(Ordering::Acquire)
            || request.ticket.policy_generation != latest
            || request.ticket.service_generation != SERVICE_GENERATION
        {
            let _ = request.reply.send(CoordinatorReply::Failed {
                ticket: request.ticket,
                error: NativeOutputCommandError::changed(),
            });
            return;
        }
        if !deadline_open(now, request.deadline) {
            let _ = request.reply.send(CoordinatorReply::Failed {
                ticket: request.ticket,
                error: NativeOutputCommandError::timeout(),
            });
            return;
        }
        if self.quarantined {
            let _ = request.reply.send(CoordinatorReply::Failed {
                ticket: request.ticket,
                error: NativeOutputCommandError::quarantined(),
            });
            return;
        }
        match request.operation {
            CoordinatorOperation::Enumerate => {
                let result = self
                    .driver
                    .as_mut()
                    .ok_or_else(NativeOutputCommandError::quarantined)
                    .and_then(NativeOutputDriver::enumerate);
                let latest = latest_policy_generation.load(Ordering::Acquire);
                if latest != request.ticket.policy_generation
                    || shutdown_requested.load(Ordering::Acquire)
                    || !deadline_open(Instant::now(), request.deadline)
                {
                    self.inventory = None;
                    let timed_out_with_current_policy = latest == request.ticket.policy_generation
                        && !shutdown_requested.load(Ordering::Acquire);
                    if timed_out_with_current_policy {
                        self.quarantined = true;
                        observation.record(request.ticket.policy_generation, true);
                        notice.mark_pending();
                    } else {
                        self.reconcile(latest, observation, notice);
                    }
                    let _ = request.reply.send(CoordinatorReply::Failed {
                        ticket: request.ticket,
                        error: if self.quarantined {
                            NativeOutputCommandError::quarantined()
                        } else if latest != request.ticket.policy_generation {
                            NativeOutputCommandError::changed()
                        } else {
                            NativeOutputCommandError::timeout()
                        },
                    });
                    return;
                }
                match result {
                    Ok(inventory) => {
                        let inventory_generation = D::inventory_generation(&inventory);
                        let projection =
                            D::inventory_projection(&inventory, request.ticket.policy_generation);
                        self.inventory = Some(inventory);
                        let _ = request.reply.send(CoordinatorReply::Enumerated {
                            ticket: request.ticket,
                            inventory_generation,
                            inventory: projection,
                        });
                    }
                    Err(error) => {
                        if enumeration_error_requires_quarantine(&error) {
                            self.quarantined = true;
                            self.inventory = None;
                            observation.record(request.ticket.policy_generation, true);
                            notice.mark_pending();
                            let _ = request.reply.send(CoordinatorReply::Failed {
                                ticket: request.ticket,
                                error: NativeOutputCommandError::quarantined(),
                            });
                        } else {
                            let _ = request.reply.send(CoordinatorReply::Failed {
                                ticket: request.ticket,
                                error,
                            });
                        }
                    }
                }
            }
            CoordinatorOperation::Reserve(selection) => {
                let selected = self.inventory.as_ref().ok_or_else(|| {
                    NativeOutputCommandError::new(
                        "native_output_inventory_missing",
                        "Enumerate native output devices before reserving silence.",
                    )
                });
                let selected = selected.and_then(|inventory| {
                    if D::inventory_generation(inventory) != selection.inventory_generation {
                        return Err(NativeOutputCommandError::changed());
                    }
                    D::select(inventory, selection)
                });
                let result = selected.and_then(|selection| {
                    self.driver
                        .as_mut()
                        .ok_or_else(NativeOutputCommandError::quarantined)?
                        .reserve(selection)
                });
                match result {
                    Ok(receipt) => {
                        let latest = latest_policy_generation.load(Ordering::Acquire);
                        if latest != request.ticket.policy_generation
                            || shutdown_requested.load(Ordering::Acquire)
                            || !deadline_open(Instant::now(), request.deadline)
                        {
                            self.receipt = Some(receipt);
                            self.reconcile(latest, observation, notice);
                            let error = if self.quarantined {
                                NativeOutputCommandError::quarantined()
                            } else if latest != request.ticket.policy_generation {
                                NativeOutputCommandError::changed()
                            } else {
                                NativeOutputCommandError::timeout()
                            };
                            let _ = request.reply.send(CoordinatorReply::Failed {
                                ticket: request.ticket,
                                error,
                            });
                            return;
                        }
                        let reservation_generation = D::reservation_generation(&receipt);
                        let projection =
                            D::reservation_projection(&receipt, request.ticket.policy_generation);
                        self.receipt = Some(receipt);
                        let _ = request.reply.send(CoordinatorReply::Reserved {
                            ticket: request.ticket,
                            reservation_generation,
                            reservation: projection,
                        });
                    }
                    Err(error) => {
                        if reserve_error_requires_quarantine(&error) {
                            self.quarantined = true;
                            self.inventory = None;
                            observation.record(request.ticket.policy_generation, true);
                            notice.mark_pending();
                            let _ = request.reply.send(CoordinatorReply::Failed {
                                ticket: request.ticket,
                                error: NativeOutputCommandError::quarantined(),
                            });
                        } else {
                            let _ = request.reply.send(CoordinatorReply::Failed {
                                ticket: request.ticket,
                                error,
                            });
                        }
                    }
                }
            }
        }
    }

    fn shutdown(
        &mut self,
        policy_generation: u64,
        observation: &CoordinatorObservation,
        notice: &CoordinatorNotice,
    ) {
        self.reconcile(policy_generation, observation, notice);
        if let Some(driver) = self.driver.as_mut() {
            if driver.shutdown().is_err() {
                self.quarantined = true;
                observation.record(policy_generation, true);
                notice.mark_pending();
            }
        }
    }
}

fn reserve_error_requires_quarantine(error: &NativeOutputCommandError) -> bool {
    matches!(
        error.code.as_str(),
        "native_output_timeout"
            | "native_output_stream_play_failed"
            | "native_output_callback_fault"
            | "native_output_release_failed"
            | "native_output_backend_unavailable"
            | "native_output_service_stopping"
    )
}

fn enumeration_error_requires_quarantine(error: &NativeOutputCommandError) -> bool {
    matches!(
        error.code.as_str(),
        "native_output_timeout"
            | "native_output_backend_unavailable"
            | "native_output_service_stopping"
            | "native_output_contract_failed"
    )
}

fn deadline_open(now: Instant, deadline: Instant) -> bool {
    now < deadline
}

pub(crate) struct NativeOutputCoordinator {
    normal_tx: SyncSender<CoordinatorRequest>,
    invalidator: NativeOutputInvalidator,
    observation: Arc<CoordinatorObservation>,
    notice: Arc<CoordinatorNotice>,
    _thread: Option<JoinHandle<()>>,
}

impl NativeOutputCoordinator {
    pub(crate) fn start() -> Self {
        Self::start_with_factory(CpalDriver::open)
    }

    fn start_with_factory<D: NativeOutputDriver>(
        factory: impl FnOnce() -> Result<D, NativeOutputCommandError> + Send + 'static,
    ) -> Self {
        let (normal_tx, normal_rx) = mpsc::sync_channel(NORMAL_OPERATION_CAPACITY);
        let (safety_wake, safety_rx) = mpsc::sync_channel(SAFETY_WAKE_CAPACITY);
        let latest_policy_generation = Arc::new(AtomicU64::new(SERVICE_GENERATION));
        let shutdown_requested = Arc::new(AtomicBool::new(false));
        let observation = Arc::new(CoordinatorObservation::new());
        let notice = Arc::new(CoordinatorNotice::new());
        let thread_policy = Arc::clone(&latest_policy_generation);
        let thread_shutdown = Arc::clone(&shutdown_requested);
        let thread_observation = Arc::clone(&observation);
        let thread_notice = Arc::clone(&notice);
        let handle = thread::Builder::new()
            .name(OUTPUT_COORDINATOR_THREAD.to_owned())
            .spawn(move || {
                coordinator_loop(
                    CoordinatorState::new(factory()),
                    normal_rx,
                    safety_rx,
                    thread_policy,
                    thread_shutdown,
                    thread_observation,
                    thread_notice,
                );
            })
            .ok();
        Self {
            normal_tx,
            invalidator: NativeOutputInvalidator {
                latest_policy_generation,
                safety_wake,
                shutdown_requested,
                observation: Arc::clone(&observation),
                disconnected_is_failure: true,
            },
            observation,
            notice,
            _thread: handle,
        }
    }

    pub(crate) fn invalidator(&self) -> NativeOutputInvalidator {
        self.invalidator.clone()
    }

    pub(crate) fn observation(&self) -> NativeOutputCleanupObservation {
        self.observation.load()
    }

    pub(crate) fn attach_notice_sink(&self, sink: Arc<AuthorityNoticeSink>) {
        self.notice.attach(sink);
    }

    pub(crate) fn invalidate_after_completion_failure(&self, ticket: NativeOutputTicket) {
        let emergency_generation = ticket
            .policy_generation()
            .checked_add(1)
            .expect("admitted native output tickets never use the terminal policy generation");
        let _ = self.invalidator.invalidate(emergency_generation);
    }

    pub(crate) fn enumerate(
        &self,
        ticket: NativeOutputTicket,
    ) -> Result<oneshot::Receiver<CoordinatorReply>, NativeOutputCommandError> {
        self.submit(
            ticket,
            CoordinatorOperation::Enumerate,
            ENUMERATION_DEADLINE,
        )
    }

    pub(crate) fn reserve(
        &self,
        ticket: NativeOutputTicket,
        selection: NativeOutputSelection,
    ) -> Result<oneshot::Receiver<CoordinatorReply>, NativeOutputCommandError> {
        let timeout = selection
            .warmup_timeout
            .checked_add(RESERVATION_DEADLINE_GRACE)
            .unwrap_or(CLIENT_REPLY_DEADLINE)
            .min(CLIENT_REPLY_DEADLINE);
        self.submit(ticket, CoordinatorOperation::Reserve(selection), timeout)
    }

    fn submit(
        &self,
        ticket: NativeOutputTicket,
        operation: CoordinatorOperation,
        timeout: Duration,
    ) -> Result<oneshot::Receiver<CoordinatorReply>, NativeOutputCommandError> {
        if self.invalidator.shutdown_requested.load(Ordering::Acquire) {
            return Err(NativeOutputCommandError::runtime());
        }
        let deadline = Instant::now()
            .checked_add(timeout)
            .ok_or_else(NativeOutputCommandError::timeout)?;
        let (reply, receive) = oneshot::channel();
        self.normal_tx
            .try_send(CoordinatorRequest {
                ticket,
                deadline,
                operation,
                reply,
            })
            .map_err(|error| match error {
                TrySendError::Full(_) => NativeOutputCommandError::busy(),
                TrySendError::Disconnected(_) => NativeOutputCommandError::runtime(),
            })?;
        Ok(receive)
    }

    pub(crate) const fn client_reply_deadline() -> Duration {
        CLIENT_REPLY_DEADLINE
    }
}

impl Drop for NativeOutputCoordinator {
    fn drop(&mut self) {
        self.invalidator
            .shutdown_requested
            .store(true, Ordering::Release);
        self.invalidator.invalidate(u64::MAX);
        // Dropping a JoinHandle detaches. A synchronous platform driver call is
        // not cancellable, so destructors must never wait for it.
        self._thread.take();
    }
}

fn coordinator_loop<D: NativeOutputDriver>(
    mut state: CoordinatorState<D>,
    normal_rx: Receiver<CoordinatorRequest>,
    safety_rx: Receiver<()>,
    latest_policy_generation: Arc<AtomicU64>,
    shutdown_requested: Arc<AtomicBool>,
    observation: Arc<CoordinatorObservation>,
    notice: Arc<CoordinatorNotice>,
) {
    let mut next_health_poll = Instant::now();
    if state.quarantined {
        observation.record(SERVICE_GENERATION, true);
        notice.mark_pending();
    }
    loop {
        while matches!(safety_rx.try_recv(), Ok(())) {}
        let latest = latest_policy_generation.load(Ordering::Acquire);
        state.reconcile(latest, &observation, &notice);
        notice.flush();
        if shutdown_requested.load(Ordering::Acquire) {
            state.shutdown(latest, &observation, &notice);
            notice.flush();
            return;
        }
        let now = Instant::now();
        if now >= next_health_poll {
            state.poll_reservation_health(
                &observation,
                &notice,
                &latest_policy_generation,
                &shutdown_requested,
            );
            notice.flush();
            next_health_poll = now
                .checked_add(RESERVATION_HEALTH_POLL_INTERVAL)
                .unwrap_or(now);
        }
        match normal_rx.recv_timeout(COORDINATOR_POLL_INTERVAL) {
            Ok(request) => state.process(
                request,
                &latest_policy_generation,
                &observation,
                &notice,
                &shutdown_requested,
            ),
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => {
                let latest = latest_policy_generation.load(Ordering::Acquire);
                state.shutdown(latest, &observation, &notice);
                notice.flush();
                return;
            }
        }
        match safety_rx.try_recv() {
            Ok(()) | Err(TryRecvError::Empty) => {}
            Err(TryRecvError::Disconnected) => {}
        }
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use pps_contracts::{ClockStamp, TimingTier};
    use pps_runner_core::RunnerCore;
    use std::sync::{Condvar, Mutex};

    #[derive(Clone)]
    struct FakeInventory {
        generation: u64,
    }

    #[derive(Clone, Copy)]
    struct FakeSelection(NativeOutputSelection);

    struct FakeReceipt {
        generation: u64,
        selection: NativeOutputSelection,
    }

    #[derive(Default)]
    pub(crate) struct FakeControl {
        enumerate_calls: AtomicU64,
        enumerate_finished: AtomicU64,
        reserve_calls: AtomicU64,
        reserve_finished: AtomicU64,
        release_calls: AtomicU64,
        shutdown_calls: AtomicU64,
        block_enumerate: (Mutex<bool>, Condvar),
        block_reserve: (Mutex<bool>, Condvar),
        block_release: (Mutex<bool>, Condvar),
        fail_release: AtomicBool,
        callback_fault: AtomicBool,
        health_uncertain: AtomicBool,
        driver_threads: Mutex<Vec<String>>,
    }

    impl FakeControl {
        pub(crate) fn block_enumerate(&self, blocked: bool) {
            *self.block_enumerate.0.lock().unwrap() = blocked;
            if !blocked {
                self.block_enumerate.1.notify_all();
            }
        }

        pub(crate) fn block_reserve(&self, blocked: bool) {
            *self.block_reserve.0.lock().unwrap() = blocked;
            if !blocked {
                self.block_reserve.1.notify_all();
            }
        }

        pub(crate) fn block_release(&self, blocked: bool) {
            *self.block_release.0.lock().unwrap() = blocked;
            if !blocked {
                self.block_release.1.notify_all();
            }
        }

        pub(crate) fn fail_release(&self, fail: bool) {
            self.fail_release.store(fail, Ordering::Release);
        }

        pub(crate) fn enumerate_calls(&self) -> u64 {
            self.enumerate_calls.load(Ordering::Acquire)
        }

        pub(crate) fn enumerate_finished(&self) -> u64 {
            self.enumerate_finished.load(Ordering::Acquire)
        }

        pub(crate) fn reserve_calls(&self) -> u64 {
            self.reserve_calls.load(Ordering::Acquire)
        }

        pub(crate) fn reserve_finished(&self) -> u64 {
            self.reserve_finished.load(Ordering::Acquire)
        }

        pub(crate) fn release_calls(&self) -> u64 {
            self.release_calls.load(Ordering::Acquire)
        }

        pub(crate) fn set_callback_fault(&self) {
            self.callback_fault.store(true, Ordering::Release);
        }

        pub(crate) fn driver_threads(&self) -> Vec<String> {
            self.driver_threads.lock().unwrap().clone()
        }

        fn record_driver_thread(&self) {
            self.driver_threads.lock().unwrap().push(
                thread::current()
                    .name()
                    .unwrap_or("unnamed")
                    .to_owned(),
            );
        }
    }

    struct FakeDriver {
        control: Arc<FakeControl>,
        inventory_generation: u64,
        reservation_generation: u64,
    }

    impl NativeOutputDriver for FakeDriver {
        type Inventory = FakeInventory;
        type Selection = FakeSelection;
        type Receipt = FakeReceipt;

        fn enumerate(&mut self) -> Result<Self::Inventory, NativeOutputCommandError> {
            self.control.record_driver_thread();
            self.control.enumerate_calls.fetch_add(1, Ordering::Relaxed);
            let (blocked, wake) = &self.control.block_enumerate;
            let mut blocked = blocked.lock().unwrap();
            while *blocked {
                blocked = wake.wait(blocked).unwrap();
            }
            self.inventory_generation += 1;
            let inventory = FakeInventory {
                generation: self.inventory_generation,
            };
            self.control
                .enumerate_finished
                .fetch_add(1, Ordering::Release);
            Ok(inventory)
        }

        fn inventory_generation(inventory: &Self::Inventory) -> u64 {
            inventory.generation
        }

        fn inventory_projection(
            inventory: &Self::Inventory,
            policy_generation: u64,
        ) -> NativeOutputInventory {
            NativeOutputInventory {
                schema: INVENTORY_SCHEMA,
                policy_generation: policy_generation.to_string(),
                service_generation: SERVICE_GENERATION.to_string(),
                inventory_generation: inventory.generation.to_string(),
                devices: Vec::new(),
                devices_truncated: false,
                silence_only: true,
                media_connected: false,
                armed: false,
                executable: false,
                qualified: false,
            }
        }

        fn select(
            _inventory: &Self::Inventory,
            selection: NativeOutputSelection,
        ) -> Result<Self::Selection, NativeOutputCommandError> {
            Ok(FakeSelection(selection))
        }

        fn reserve(
            &mut self,
            selection: Self::Selection,
        ) -> Result<Self::Receipt, NativeOutputCommandError> {
            self.control.record_driver_thread();
            self.control.reserve_calls.fetch_add(1, Ordering::Relaxed);
            let (blocked, wake) = &self.control.block_reserve;
            let mut blocked = blocked.lock().unwrap();
            while *blocked {
                blocked = wake.wait(blocked).unwrap();
            }
            self.reservation_generation += 1;
            let receipt = FakeReceipt {
                generation: self.reservation_generation,
                selection: selection.0,
            };
            self.control
                .reserve_finished
                .fetch_add(1, Ordering::Release);
            Ok(receipt)
        }

        fn reservation_generation(receipt: &Self::Receipt) -> u64 {
            receipt.generation
        }

        fn reservation_projection(
            receipt: &Self::Receipt,
            policy_generation: u64,
        ) -> NativeOutputReservation {
            NativeOutputReservation {
                schema: RESERVATION_SCHEMA,
                policy_generation: policy_generation.to_string(),
                service_generation: SERVICE_GENERATION.to_string(),
                inventory_generation: receipt.selection.inventory_generation.to_string(),
                reservation_generation: receipt.generation.to_string(),
                device_ordinal: receipt.selection.device_ordinal,
                config_ordinal: receipt.selection.config_ordinal,
                channels: receipt.selection.channels,
                sample_rate_hz: receipt.selection.sample_rate_hz,
                buffer_frames: receipt.selection.buffer_frames,
                callback_count_at_warmup: 1,
                silence_only: true,
                media_connected: false,
                armed: false,
                executable: false,
                qualified: false,
            }
        }

        fn reservation_health(
            &mut self,
            _receipt: &Self::Receipt,
        ) -> Result<ReservationHealth, NativeOutputCommandError> {
            self.control.record_driver_thread();
            if self.control.health_uncertain.load(Ordering::Acquire) {
                return Ok(ReservationHealth::Uncertain);
            }
            if self.control.callback_fault.load(Ordering::Acquire) {
                return Ok(ReservationHealth::ReleasedAfterCallbackFault);
            }
            Ok(ReservationHealth::Healthy)
        }

        fn release(&mut self, _receipt: &Self::Receipt) -> Result<(), NativeOutputCommandError> {
            self.control.record_driver_thread();
            self.control.release_calls.fetch_add(1, Ordering::Relaxed);
            let (blocked, wake) = &self.control.block_release;
            let mut blocked = blocked.lock().unwrap();
            while *blocked {
                blocked = wake.wait(blocked).unwrap();
            }
            if self.control.fail_release.load(Ordering::Acquire) {
                return Err(NativeOutputCommandError::new(
                    "native_output_release_failed",
                    "The fake release outcome is unknown.",
                ));
            }
            Ok(())
        }

        fn shutdown(&mut self) -> Result<(), NativeOutputCommandError> {
            self.control.record_driver_thread();
            self.control.shutdown_calls.fetch_add(1, Ordering::Relaxed);
            Ok(())
        }
    }

    pub(crate) fn fake_coordinator(control: &Arc<FakeControl>) -> NativeOutputCoordinator {
        let worker_control = Arc::clone(control);
        NativeOutputCoordinator::start_with_factory(move || {
            Ok(FakeDriver {
                control: worker_control,
                inventory_generation: 0,
                reservation_generation: 0,
            })
        })
    }

    fn ticket(kind: NativeOutputOperationKind, operation_generation: u64) -> NativeOutputTicket {
        NativeOutputTicket {
            policy_generation: SERVICE_GENERATION,
            service_generation: SERVICE_GENERATION,
            operation_generation,
            kind,
        }
    }

    fn selection(inventory_generation: u64) -> NativeOutputSelection {
        NativeOutputSelection {
            inventory_generation,
            device_ordinal: 0,
            config_ordinal: 0,
            channels: 2,
            sample_rate_hz: 48_000,
            buffer_frames: None,
            warmup_timeout: Duration::from_millis(50),
        }
    }

    fn quiescent_snapshot() -> RunnerSnapshot {
        RunnerCore::new(
            "native-output-test",
            "desktop-tauri-preview",
            7,
            TimingTier::DesktopPreview,
            ClockStamp {
                unix_ms: 1_800_000_000_000,
                monotonic_ns: 0,
            },
        )
        .snapshot()
    }

    fn authority_with_reservation() -> NativeOutputAuthority {
        let mut authority = NativeOutputAuthority::new(NativeOutputInvalidator::inert());
        let enumerate = authority.begin_enumerate(&quiescent_snapshot()).unwrap();
        authority.complete_enumerate(enumerate, Ok(11)).unwrap();
        let request = NativeOutputReserveRequest {
            policy_generation: authority.policy_generation.to_string(),
            service_generation: SERVICE_GENERATION.to_string(),
            inventory_generation: "11".to_owned(),
            device_ordinal: 0,
            config_ordinal: 0,
            channels: 2,
            sample_rate_hz: 48_000,
            buffer_frames: None,
            warmup_timeout_ms: 50,
        };
        let (reserve, _) = authority
            .begin_reserve(&quiescent_snapshot(), &request)
            .unwrap();
        authority.complete_reserve(reserve, Ok(21)).unwrap();
        authority
    }

    #[test]
    fn deadlines_are_strict_before_at_and_after() {
        let deadline = Instant::now() + Duration::from_secs(1);
        assert!(deadline_open(deadline - Duration::from_nanos(1), deadline));
        assert!(!deadline_open(deadline, deadline));
        assert!(!deadline_open(deadline + Duration::from_nanos(1), deadline));
    }

    #[tokio::test]
    async fn normal_lane_is_capacity_one_and_inventory_is_service_fenced() {
        let control = Arc::new(FakeControl::default());
        let coordinator = fake_coordinator(&control);
        let first = coordinator.enumerate(ticket(NativeOutputOperationKind::Enumerate, 1));
        let second = coordinator.enumerate(ticket(NativeOutputOperationKind::Enumerate, 2));
        assert!(first.is_ok());
        assert!(second.is_err());
        let reply = first.unwrap().await.unwrap();
        let CoordinatorReply::Enumerated { inventory, .. } = reply else {
            panic!("expected inventory");
        };
        assert_eq!(inventory.service_generation, "1");
        assert_eq!(inventory.inventory_generation, "1");
        drop(coordinator);
    }

    #[tokio::test]
    async fn invalidation_during_blocked_reserve_makes_completion_inert_and_cleans_once() {
        let control = Arc::new(FakeControl::default());
        let coordinator = fake_coordinator(&control);
        let inventory = coordinator
            .enumerate(ticket(NativeOutputOperationKind::Enumerate, 1))
            .unwrap()
            .await
            .unwrap();
        let CoordinatorReply::Enumerated { inventory, .. } = inventory else {
            panic!("expected inventory");
        };
        *control.block_reserve.0.lock().unwrap() = true;
        let reserve = coordinator
            .reserve(
                ticket(NativeOutputOperationKind::ReserveSilence, 2),
                selection(inventory.inventory_generation.parse().unwrap()),
            )
            .unwrap();
        while control.reserve_calls.load(Ordering::Acquire) == 0 {
            thread::yield_now();
        }
        assert!(coordinator.invalidator.invalidate(2));
        *control.block_reserve.0.lock().unwrap() = false;
        control.block_reserve.1.notify_all();
        let reply = reserve.await.unwrap();
        assert!(matches!(reply, CoordinatorReply::Failed { .. }));
        assert_eq!(control.release_calls.load(Ordering::Acquire), 1);
        for _ in 0..100 {
            if coordinator.observation().policy_generation == 2 {
                break;
            }
            thread::sleep(Duration::from_millis(1));
        }
        assert_eq!(coordinator.observation().policy_generation, 2);
        assert!(!coordinator.observation().quarantined);
    }

    #[tokio::test]
    async fn failed_cleanup_quarantines_the_only_service() {
        let control = Arc::new(FakeControl::default());
        let coordinator = fake_coordinator(&control);
        let inventory = coordinator
            .enumerate(ticket(NativeOutputOperationKind::Enumerate, 1))
            .unwrap()
            .await
            .unwrap();
        let CoordinatorReply::Enumerated { inventory, .. } = inventory else {
            panic!("expected inventory");
        };
        let reserved = coordinator
            .reserve(
                ticket(NativeOutputOperationKind::ReserveSilence, 2),
                selection(inventory.inventory_generation.parse().unwrap()),
            )
            .unwrap()
            .await
            .unwrap();
        assert!(matches!(reserved, CoordinatorReply::Reserved { .. }));
        control.fail_release.store(true, Ordering::Release);
        assert!(coordinator.invalidator.invalidate(2));
        for _ in 0..100 {
            if coordinator.observation().policy_generation == 2 {
                break;
            }
            thread::sleep(Duration::from_millis(1));
        }
        assert!(coordinator.observation().quarantined);
        assert_eq!(control.release_calls.load(Ordering::Acquire), 1);
        let retry = coordinator
            .enumerate(NativeOutputTicket {
                policy_generation: 2,
                service_generation: SERVICE_GENERATION,
                operation_generation: 3,
                kind: NativeOutputOperationKind::Enumerate,
            })
            .unwrap()
            .await
            .unwrap();
        assert!(matches!(
            retry,
            CoordinatorReply::Failed { error, .. }
                if error.code == "native_output_quarantined"
        ));
        assert_eq!(control.enumerate_calls.load(Ordering::Acquire), 1);
    }

    #[tokio::test]
    async fn callback_fault_is_reconciled_without_a_client_poll_or_release_command() {
        let control = Arc::new(FakeControl::default());
        let coordinator = fake_coordinator(&control);
        let inventory = coordinator
            .enumerate(ticket(NativeOutputOperationKind::Enumerate, 1))
            .unwrap()
            .await
            .unwrap();
        let CoordinatorReply::Enumerated { inventory, .. } = inventory else {
            panic!("expected inventory");
        };
        let reserved = coordinator
            .reserve(
                ticket(NativeOutputOperationKind::ReserveSilence, 2),
                selection(inventory.inventory_generation.parse().unwrap()),
            )
            .unwrap()
            .await
            .unwrap();
        let CoordinatorReply::Reserved {
            reservation_generation,
            ..
        } = reserved
        else {
            panic!("expected reservation");
        };

        control.set_callback_fault();
        let deadline = Instant::now() + Duration::from_secs(2);
        loop {
            let observation = coordinator.observation();
            if observation.faulted_reservation_generation == Some(reservation_generation) {
                assert!(!observation.quarantined);
                break;
            }
            assert!(Instant::now() < deadline, "callback fault was not reconciled");
            thread::sleep(Duration::from_millis(2));
        }
        assert_eq!(control.release_calls(), 0);
    }

    #[test]
    fn runner_invalidation_blocks_start_until_exact_cleanup_and_faults_fail_closed() {
        let mut authority = authority_with_reservation();
        authority.invalidate_for_runner_change();
        assert_eq!(authority.phase, NativeOutputPhase::CleanupPending);
        assert!(authority.part_start_blocked());
        let policy_generation = authority.policy_generation;
        authority.observe_cleanup(NativeOutputCleanupObservation {
            policy_generation,
            quarantined: false,
            faulted_reservation_generation: None,
        });
        assert_eq!(authority.phase, NativeOutputPhase::Idle);
        assert!(!authority.part_start_blocked());

        let mut faulted = authority_with_reservation();
        faulted.observe_cleanup(NativeOutputCleanupObservation {
            policy_generation: faulted.policy_generation,
            quarantined: false,
            faulted_reservation_generation: faulted.reservation_generation,
        });
        assert_eq!(faulted.phase, NativeOutputPhase::Faulted);
        assert!(faulted.part_start_blocked());

        let mut quarantined = authority_with_reservation();
        quarantined.invalidate_for_runner_change();
        quarantined.observe_cleanup(NativeOutputCleanupObservation {
            policy_generation: quarantined.policy_generation,
            quarantined: true,
            faulted_reservation_generation: None,
        });
        assert_eq!(quarantined.phase, NativeOutputPhase::Quarantined);
        assert!(quarantined.part_start_blocked());
    }

    #[test]
    fn generation_exhaustion_permanently_quarantines_instead_of_reusing_a_fence() {
        let mut policy = NativeOutputAuthority::new(NativeOutputInvalidator::inert());
        policy.policy_generation = u64::MAX;
        let error = policy.begin_enumerate(&quiescent_snapshot()).unwrap_err();
        assert_eq!(error.code, "native_output_generation_exhausted");
        assert_eq!(policy.phase, NativeOutputPhase::Quarantined);

        let mut operation = NativeOutputAuthority::new(NativeOutputInvalidator::inert());
        operation.operation_generation = u64::MAX;
        let error = operation
            .begin_enumerate(&quiescent_snapshot())
            .unwrap_err();
        assert_eq!(error.code, "native_output_generation_exhausted");
        assert_eq!(operation.phase, NativeOutputPhase::Quarantined);
    }

    #[test]
    fn drop_is_nonblocking_even_when_driver_is_stuck() {
        let control = Arc::new(FakeControl::default());
        let coordinator = fake_coordinator(&control);
        *control.block_reserve.0.lock().unwrap() = true;
        let started = Instant::now();
        drop(coordinator);
        assert!(started.elapsed() < Duration::from_millis(100));
        *control.block_reserve.0.lock().unwrap() = false;
        control.block_reserve.1.notify_all();
    }

    #[test]
    fn dto_generations_are_canonical_decimal_strings_and_private_free() {
        for invalid in ["", "01", "+1", "-1", " 1", "1.0"] {
            assert!(parse_generation(invalid).is_err());
        }
        assert_eq!(parse_generation("0").unwrap(), 0);
        assert_eq!(parse_generation(&u64::MAX.to_string()).unwrap(), u64::MAX);
        let authority = NativeOutputAuthority::new(NativeOutputInvalidator::inert());
        let encoded = serde_json::to_string(&authority.status()).unwrap();
        for private in [
            "path",
            "participant",
            "commandId",
            "ownerToken",
            "secret",
            "receipt",
            "deviceCapability",
        ] {
            assert!(!encoded.contains(private));
        }
        assert!(encoded.contains("\"executable\":false"));
        assert!(encoded.contains("\"mediaConnected\":false"));
        assert!(encoded.contains("\"armed\":false"));
        assert!(encoded.contains("\"qualified\":false"));
    }
}
