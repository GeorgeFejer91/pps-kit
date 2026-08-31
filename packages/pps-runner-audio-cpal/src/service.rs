use std::{
    fmt,
    sync::{
        atomic::{AtomicBool, AtomicU32, AtomicU64, AtomicU8, Ordering},
        mpsc::{self, Receiver, RecvTimeoutError, SyncSender, TryRecvError, TrySendError},
        Arc, Mutex,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

use crate::{
    contract::{
        ExactOutputSelection, OutputBufferSelection, OutputBufferSupport, OutputConfigDescriptor,
        OutputDeviceDescriptor, OutputDeviceInventory, OutputFault, OutputFaultKind,
        OutputReservationReceipt, OutputServiceError, OutputServiceErrorCode, OutputServicePhase,
        OutputServiceStatus, ServiceIdentity, MAXIMUM_CALLBACK_FRAMES, MAXIMUM_DEVICE_NAME_BYTES,
        MAXIMUM_F32_CONFIGS_PER_DEVICE, MAXIMUM_OUTPUT_CHANNELS, MAXIMUM_OUTPUT_DEVICES,
    },
    cpal_backend::CpalBackend,
};

const NORMAL_COMMAND_CAPACITY: usize = 8;
const SAFETY_COMMAND_CAPACITY: usize = 4;
const OWNER_POLL_INTERVAL: Duration = Duration::from_millis(2);
const ORDINARY_REPLY_TIMEOUT: Duration = Duration::from_secs(5);
#[cfg(not(test))]
const RESERVATION_REPLY_GRACE: Duration = Duration::from_secs(2);
#[cfg(test)]
const RESERVATION_REPLY_GRACE: Duration = Duration::from_millis(20);
const BACKEND_BUILD_TIMEOUT: Duration = Duration::from_secs(2);
const OUTPUT_THREAD_NAME: &str = "pps-audio-output";
const MAXIMUM_CONSECUTIVE_RELEASES: u8 = 2;

const TRANSFER_WAITING: u8 = 0;
const TRANSFER_ACCEPTED: u8 = 1;
const TRANSFER_COMMITTED: u8 = 2;
const TRANSFER_CANCELLED: u8 = 3;

static NEXT_SERVICE_ID: AtomicU64 = AtomicU64::new(1);

pub(crate) trait SelectionKey: Copy + 'static {}

pub(crate) struct BackendConfig<K> {
    pub key: K,
    pub channels: u16,
    pub minimum_sample_rate_hz: u32,
    pub maximum_sample_rate_hz: u32,
    pub buffer_support: OutputBufferSupport,
}

pub(crate) struct BackendDevice<K> {
    pub display_name: String,
    pub configs: Vec<BackendConfig<K>>,
    pub configs_truncated: bool,
}

pub(crate) struct BackendEnumeration<K> {
    pub devices: Vec<BackendDevice<K>>,
    pub devices_truncated: bool,
}

pub(crate) struct BackendFailure {
    fault_kind: OutputFaultKind,
    error: OutputServiceError,
}

impl BackendFailure {
    pub(crate) const fn new(
        fault_kind: OutputFaultKind,
        code: OutputServiceErrorCode,
        message: &'static str,
    ) -> Self {
        Self {
            fault_kind,
            error: OutputServiceError::new(code, message),
        }
    }

    pub(crate) const fn contract() -> Self {
        Self::new(
            OutputFaultKind::BackendContractViolation,
            OutputServiceErrorCode::BackendContractViolation,
            "The native output backend returned an invalid bounded contract.",
        )
    }
}

pub(crate) trait OutputBackend: 'static {
    type Key: SelectionKey;

    fn enumerate(&mut self) -> Result<BackendEnumeration<Self::Key>, BackendFailure>;

    fn create_silence(
        &mut self,
        key: &Self::Key,
        selection: &ExactOutputSelection,
        signals: Arc<CallbackSignals>,
        backend_timeout: Duration,
    ) -> Result<(), BackendFailure>;

    fn play_silence(&mut self) -> Result<(), BackendFailure>;

    fn release(&mut self) -> Result<(), BackendFailure>;
}

pub(crate) struct CallbackSignals {
    callback_count: AtomicU32,
    callback_fault_count: AtomicU32,
}

impl CallbackSignals {
    fn new() -> Self {
        Self {
            callback_count: AtomicU32::new(0),
            callback_fault_count: AtomicU32::new(0),
        }
    }

    /// Test-only typed facade for the same zero-fill/count behavior.
    #[cfg(test)]
    pub(crate) fn write_silence(&self, samples: &mut [f32]) {
        samples.fill(0.0);
        saturating_increment(&self.callback_count);
    }

    /// Raw CPAL callback boundary. Only a positively bounded, whole-frame F32
    /// buffer is touched; every mismatch leaves CPAL's prefilled silence intact.
    pub(crate) fn write_raw_silence(
        &self,
        exact_f32: bool,
        channels: u16,
        sample_count: usize,
        bytes: &mut [u8],
    ) {
        let expected_bytes = sample_count.checked_mul(std::mem::size_of::<f32>());
        if !raw_callback_shape_is_bounded(exact_f32, channels, sample_count)
            || expected_bytes != Some(bytes.len())
        {
            saturating_increment(&self.callback_fault_count);
            return;
        }
        bytes.fill(0);
        saturating_increment(&self.callback_count);
    }

    /// CPAL error callback boundary: record only a bounded atomic fault count.
    pub(crate) fn record_callback_fault(&self) {
        saturating_increment(&self.callback_fault_count);
    }

    fn callback_count(&self) -> u32 {
        self.callback_count.load(Ordering::Acquire)
    }

    fn callback_fault_count(&self) -> u32 {
        self.callback_fault_count.load(Ordering::Acquire)
    }
}

pub(crate) fn raw_callback_shape_is_bounded(
    exact_f32: bool,
    channels: u16,
    sample_count: usize,
) -> bool {
    let channels = usize::from(channels);
    let maximum_samples = MAXIMUM_CALLBACK_FRAMES.checked_mul(channels);
    exact_f32
        && channels > 0
        && channels <= usize::from(MAXIMUM_OUTPUT_CHANNELS)
        && sample_count > 0
        && sample_count.is_multiple_of(channels)
        && maximum_samples.is_some_and(|maximum| sample_count <= maximum)
}

fn saturating_increment(counter: &AtomicU32) {
    let _ = counter.fetch_update(Ordering::Release, Ordering::Relaxed, |value| {
        Some(value.saturating_add(1))
    });
}

struct InternalConfig<K> {
    descriptor: OutputConfigDescriptor,
    key: K,
}

struct InternalDevice<K> {
    descriptor: OutputDeviceDescriptor,
    configs: Vec<InternalConfig<K>>,
}

struct InternalInventory<K> {
    public: OutputDeviceInventory,
    devices: Vec<InternalDevice<K>>,
}

struct ActiveReservation {
    generation: u64,
    signals: Arc<CallbackSignals>,
    published: bool,
}

struct ReservationTransfer {
    state: AtomicU8,
    deadline: Instant,
}

impl ReservationTransfer {
    fn new(deadline: Instant) -> Self {
        Self {
            state: AtomicU8::new(TRANSFER_WAITING),
            deadline,
        }
    }

    fn is_cancelled_or_expired(&self, now: Instant) -> bool {
        if now >= self.deadline {
            let _ = self.state.compare_exchange(
                TRANSFER_WAITING,
                TRANSFER_CANCELLED,
                Ordering::AcqRel,
                Ordering::Acquire,
            );
            let _ = self.state.compare_exchange(
                TRANSFER_ACCEPTED,
                TRANSFER_CANCELLED,
                Ordering::AcqRel,
                Ordering::Acquire,
            );
        }
        self.state.load(Ordering::Acquire) == TRANSFER_CANCELLED
    }

    fn caller_accept(&self, now: Instant) -> bool {
        if now >= self.deadline {
            self.cancel();
            return false;
        }
        self.state
            .compare_exchange(
                TRANSFER_WAITING,
                TRANSFER_ACCEPTED,
                Ordering::AcqRel,
                Ordering::Acquire,
            )
            .is_ok()
    }

    fn owner_commit(&self, now: Instant) -> bool {
        if now >= self.deadline {
            let _ = self.state.compare_exchange(
                TRANSFER_ACCEPTED,
                TRANSFER_CANCELLED,
                Ordering::AcqRel,
                Ordering::Acquire,
            );
            return false;
        }
        self.state
            .compare_exchange(
                TRANSFER_ACCEPTED,
                TRANSFER_COMMITTED,
                Ordering::AcqRel,
                Ordering::Acquire,
            )
            .is_ok()
    }

    fn cancel(&self) -> bool {
        loop {
            match self.state.load(Ordering::Acquire) {
                TRANSFER_WAITING => {
                    if self
                        .state
                        .compare_exchange(
                            TRANSFER_WAITING,
                            TRANSFER_CANCELLED,
                            Ordering::AcqRel,
                            Ordering::Acquire,
                        )
                        .is_ok()
                    {
                        return true;
                    }
                }
                TRANSFER_ACCEPTED => {
                    if self
                        .state
                        .compare_exchange(
                            TRANSFER_ACCEPTED,
                            TRANSFER_CANCELLED,
                            Ordering::AcqRel,
                            Ordering::Acquire,
                        )
                        .is_ok()
                    {
                        return true;
                    }
                }
                TRANSFER_COMMITTED => return false,
                TRANSFER_CANCELLED => return true,
                _ => return true,
            }
        }
    }

    fn state(&self) -> u8 {
        self.state.load(Ordering::Acquire)
    }
}

struct ReservationProposal {
    receipt: OutputReservationReceipt,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum WarmupObservation {
    Pending,
    Ready(u32),
    Faulted,
    TimedOut,
}

fn classify_warmup_observation(
    callback_fault_count: u32,
    callback_count: u32,
    observed_at: Instant,
    deadline: Instant,
) -> WarmupObservation {
    if callback_fault_count > 0 {
        WarmupObservation::Faulted
    } else if observed_at >= deadline {
        WarmupObservation::TimedOut
    } else if callback_count > 0 {
        WarmupObservation::Ready(callback_count)
    } else {
        WarmupObservation::Pending
    }
}

struct WorkerState<B: OutputBackend> {
    factory: Option<Box<dyn FnOnce() -> Result<B, BackendFailure> + Send>>,
    backend: Option<B>,
    inventory_generation: u64,
    reservation_generation: u64,
    inventory: Option<InternalInventory<B::Key>>,
    reservation: Option<ActiveReservation>,
    last_callback_count: u32,
    last_callback_fault_count: u32,
    last_fault: Option<OutputFault>,
    fault_occurrence: u64,
}

impl<B: OutputBackend> WorkerState<B> {
    fn new(factory: impl FnOnce() -> Result<B, BackendFailure> + Send + 'static) -> Self {
        Self {
            factory: Some(Box::new(factory)),
            backend: None,
            inventory_generation: 0,
            reservation_generation: 0,
            inventory: None,
            reservation: None,
            last_callback_count: 0,
            last_callback_fault_count: 0,
            last_fault: None,
            fault_occurrence: 0,
        }
    }

    fn backend(&mut self) -> Result<&mut B, OutputServiceError> {
        if self.backend.is_none() {
            let factory = self.factory.take().ok_or_else(backend_unavailable)?;
            match factory() {
                Ok(backend) => self.backend = Some(backend),
                Err(failure) => {
                    self.record_fault(failure.fault_kind);
                    return Err(failure.error);
                }
            }
        }
        self.backend.as_mut().ok_or_else(backend_unavailable)
    }

    fn enumerate(
        &mut self,
        identity: &Arc<ServiceIdentity>,
    ) -> Result<OutputDeviceInventory, OutputServiceError> {
        if self.reservation.is_some() {
            return Err(error(
                OutputServiceErrorCode::AlreadyReserved,
                "Release the current silence reservation before enumerating devices.",
            ));
        }
        let next_generation = self.inventory_generation.checked_add(1).ok_or_else(|| {
            self.record_fault(OutputFaultKind::GenerationExhausted);
            error(
                OutputServiceErrorCode::GenerationExhausted,
                "The native output inventory generation is exhausted.",
            )
        })?;
        // Backend enumeration is allowed to rebuild its private selection-key
        // registry. Invalidate the matching public projection first so a failed
        // refresh can never leave old ordinals addressing new backend entries.
        self.inventory = None;
        let raw = match self.backend()?.enumerate() {
            Ok(raw) => raw,
            Err(failure) => {
                self.record_fault(failure.fault_kind);
                return Err(failure.error);
            }
        };
        let inventory = match bound_inventory(Arc::clone(identity), next_generation, raw) {
            Ok(inventory) => inventory,
            Err(failure) => {
                self.record_fault(failure.fault_kind);
                return Err(failure.error);
            }
        };
        let public = inventory.public.clone();
        self.inventory_generation = next_generation;
        self.inventory = Some(inventory);
        self.last_fault = None;
        Ok(public)
    }

    fn reserve(
        &mut self,
        selection: ExactOutputSelection,
        identity: &Arc<ServiceIdentity>,
        transfer: &ReservationTransfer,
        shutdown_requested: &AtomicBool,
    ) -> Result<(OutputReservationReceipt, ActiveReservation), OutputServiceError> {
        if self.reservation.is_some() {
            return Err(error(
                OutputServiceErrorCode::AlreadyReserved,
                "A native silence stream is already reserved.",
            ));
        }
        if transfer.is_cancelled_or_expired(Instant::now()) {
            return Err(request_timeout());
        }
        if !selection.belongs_to(identity) {
            return Err(error(
                OutputServiceErrorCode::SelectionOwnerMismatch,
                "The output selection belongs to a different native output service.",
            ));
        }
        let key = *self.resolve_selection(&selection)?;
        let next_generation = self.reservation_generation.checked_add(1).ok_or_else(|| {
            self.record_fault(OutputFaultKind::GenerationExhausted);
            error(
                OutputServiceErrorCode::GenerationExhausted,
                "The native output reservation generation is exhausted.",
            )
        })?;
        let signals = Arc::new(CallbackSignals::new());
        if transfer.is_cancelled_or_expired(Instant::now()) {
            return Err(request_timeout());
        }
        if let Err(failure) = self.backend()?.create_silence(
            &key,
            &selection,
            Arc::clone(&signals),
            BACKEND_BUILD_TIMEOUT,
        ) {
            self.record_fault(failure.fault_kind);
            return Err(failure.error);
        }
        let candidate = ActiveReservation {
            generation: next_generation,
            signals: Arc::clone(&signals),
            published: false,
        };
        if transfer.is_cancelled_or_expired(Instant::now()) {
            let _ = self.discard_candidate(candidate);
            return Err(request_timeout());
        }
        if let Err(failure) = self.backend()?.play_silence() {
            if self.discard_candidate(candidate) {
                self.record_fault(failure.fault_kind);
            }
            return Err(failure.error);
        }
        if transfer.is_cancelled_or_expired(Instant::now()) {
            let _ = self.discard_candidate(candidate);
            return Err(request_timeout());
        }

        let deadline = Instant::now() + selection.warmup_timeout();
        loop {
            if shutdown_requested.load(Ordering::Acquire) {
                let _ = self.discard_candidate(candidate);
                return Err(error(
                    OutputServiceErrorCode::ServiceShuttingDown,
                    "The native output service is shutting down.",
                ));
            }
            if transfer.is_cancelled_or_expired(Instant::now()) {
                let _ = self.discard_candidate(candidate);
                return Err(request_timeout());
            }
            let callback_count = signals.callback_count();
            let callback_fault_count = signals.callback_fault_count();
            let observed_at = Instant::now();
            match classify_warmup_observation(
                callback_fault_count,
                callback_count,
                observed_at,
                deadline,
            ) {
                WarmupObservation::Ready(callback_count) => {
                    let receipt = OutputReservationReceipt::new(
                        Arc::clone(identity),
                        next_generation,
                        selection,
                        callback_count,
                    );
                    return Ok((receipt, candidate));
                }
                WarmupObservation::Faulted => {
                    if self.discard_candidate(candidate) {
                        self.record_fault(OutputFaultKind::CallbackFault);
                    }
                    return Err(error(
                        OutputServiceErrorCode::CallbackFault,
                        "The native silence callback reported a fault.",
                    ));
                }
                WarmupObservation::TimedOut => {
                    if self.discard_candidate(candidate) {
                        self.record_fault(OutputFaultKind::WarmupTimeout);
                    }
                    return Err(error(
                        OutputServiceErrorCode::WarmupTimeout,
                        "The native silence stream did not warm up before its deadline.",
                    ));
                }
                WarmupObservation::Pending => thread::sleep(OWNER_POLL_INTERVAL),
            }
        }
    }

    fn resolve_selection(
        &self,
        selection: &ExactOutputSelection,
    ) -> Result<&B::Key, OutputServiceError> {
        let inventory = self.inventory.as_ref().ok_or_else(|| {
            error(
                OutputServiceErrorCode::InventoryMissing,
                "Enumerate native output devices before selecting one.",
            )
        })?;
        if inventory.public.generation() != selection.inventory_generation() {
            return Err(error(
                OutputServiceErrorCode::StaleInventory,
                "The native output inventory changed; enumerate it again.",
            ));
        }
        let device = inventory
            .devices
            .get(usize::from(selection.device_ordinal()))
            .ok_or_else(exact_config_mismatch)?;
        let config = device
            .configs
            .get(usize::from(selection.config_ordinal()))
            .ok_or_else(exact_config_mismatch)?;
        let descriptor = &config.descriptor;
        let buffer_matches = match (descriptor.buffer_support(), selection.buffer()) {
            (_, OutputBufferSelection::Default) => true,
            (
                OutputBufferSupport::Range {
                    minimum_frames,
                    maximum_frames,
                },
                OutputBufferSelection::Fixed(frames),
            ) => (minimum_frames..=maximum_frames).contains(&frames),
            (OutputBufferSupport::Unknown, OutputBufferSelection::Fixed(_)) => false,
        };
        if descriptor.channels() != selection.channels()
            || !(descriptor.minimum_sample_rate_hz()..=descriptor.maximum_sample_rate_hz())
                .contains(&selection.sample_rate_hz())
            || !buffer_matches
        {
            return Err(exact_config_mismatch());
        }
        Ok(&config.key)
    }

    fn accept_reservation(
        &mut self,
        proposal: ReservationProposal,
        mut active: ActiveReservation,
        transfer: &ReservationTransfer,
        reply: SyncSender<Result<ReservationProposal, OutputServiceError>>,
    ) {
        if reply.try_send(Ok(proposal)).is_err() {
            transfer.cancel();
            let _ = self.discard_candidate(active);
            return;
        }
        loop {
            match transfer.state() {
                TRANSFER_ACCEPTED if transfer.owner_commit(Instant::now()) => {
                    self.reservation_generation = active.generation;
                    self.last_fault = None;
                    active.published = true;
                    self.reservation = Some(active);
                    return;
                }
                TRANSFER_COMMITTED => return,
                TRANSFER_CANCELLED => {
                    let _ = self.discard_candidate(active);
                    return;
                }
                TRANSFER_WAITING | TRANSFER_ACCEPTED => {
                    if transfer.is_cancelled_or_expired(Instant::now()) {
                        let _ = self.discard_candidate(active);
                        return;
                    }
                    thread::yield_now();
                }
                _ => {
                    transfer.cancel();
                    let _ = self.discard_candidate(active);
                    return;
                }
            }
        }
    }

    /// Returns true only when the backend confirms that the candidate is gone.
    fn discard_candidate(&mut self, active: ActiveReservation) -> bool {
        self.last_callback_count = active.signals.callback_count();
        self.last_callback_fault_count = active.signals.callback_fault_count();
        if let Err(failure) = self.release_backend() {
            // Keep ownership internal when a backend refuses release. No receipt
            // is published; explicit service shutdown remains the cleanup path.
            self.reservation = Some(active);
            self.record_fault(failure.fault_kind);
            return false;
        }
        true
    }

    fn release(&mut self, generation: u64) -> Result<(), OutputServiceError> {
        let active = self.reservation.as_ref().ok_or_else(stale_reservation)?;
        if active.generation != generation {
            return Err(stale_reservation());
        }
        let callback_count = active.signals.callback_count();
        let callback_fault_count = active.signals.callback_fault_count();
        if let Err(failure) = self.release_backend() {
            self.record_fault(failure.fault_kind);
            return Err(failure.error);
        }
        self.last_callback_count = callback_count;
        self.last_callback_fault_count = callback_fault_count;
        self.reservation = None;
        self.last_fault = None;
        Ok(())
    }

    fn refresh_callback_fault(&mut self) {
        let Some(active) = self.reservation.as_ref() else {
            return;
        };
        if !active.published {
            return;
        }
        if self
            .last_fault
            .is_some_and(|fault| fault.kind() == OutputFaultKind::StreamReleaseFailed)
        {
            // A failed cleanup is retried only by explicit release/shutdown;
            // automatic retries must not starve the bounded command lanes.
            return;
        }
        if active.signals.callback_fault_count() == 0 {
            return;
        }
        let callback_count = active.signals.callback_count();
        let callback_fault_count = active.signals.callback_fault_count();
        match self.release_backend() {
            Ok(()) => {
                self.reservation = None;
                self.last_callback_count = callback_count;
                self.last_callback_fault_count = callback_fault_count;
                self.record_fault(OutputFaultKind::CallbackFault);
            }
            Err(failure) => self.record_fault(failure.fault_kind),
        }
    }

    fn release_backend(&mut self) -> Result<(), BackendFailure> {
        match self.backend.as_mut() {
            Some(backend) => backend.release(),
            None => Ok(()),
        }
    }

    fn shutdown(&mut self) -> Result<(), OutputServiceError> {
        if let Some(active) = self.reservation.as_ref() {
            self.last_callback_count = active.signals.callback_count();
            self.last_callback_fault_count = active.signals.callback_fault_count();
        }
        if let Err(failure) = self.release_backend() {
            self.record_fault(failure.fault_kind);
            return Err(failure.error);
        }
        self.reservation = None;
        self.backend = None;
        Ok(())
    }

    fn status(&self, shutting_down: bool) -> OutputServiceStatus {
        let (callback_count, callback_fault_count) = self
            .reservation
            .as_ref()
            .map(|active| {
                (
                    active.signals.callback_count(),
                    active.signals.callback_fault_count(),
                )
            })
            .unwrap_or((self.last_callback_count, self.last_callback_fault_count));
        let phase = if shutting_down {
            OutputServicePhase::ShuttingDown
        } else if self.last_fault.is_some() {
            OutputServicePhase::Faulted
        } else if self.reservation.is_some() {
            OutputServicePhase::ReservedSilence
        } else if self.inventory.is_some() {
            OutputServicePhase::Enumerated
        } else {
            OutputServicePhase::Idle
        };
        OutputServiceStatus::new(
            phase,
            self.inventory
                .as_ref()
                .map(|value| value.public.generation()),
            self.reservation.as_ref().map(|value| value.generation),
            callback_count,
            callback_fault_count,
            self.last_fault,
        )
    }

    fn record_fault(&mut self, kind: OutputFaultKind) {
        self.fault_occurrence = self.fault_occurrence.saturating_add(1);
        self.last_fault = Some(OutputFault::new(kind, self.fault_occurrence));
    }
}

enum Command {
    Enumerate(SyncSender<Result<OutputDeviceInventory, OutputServiceError>>),
    Reserve {
        selection: ExactOutputSelection,
        transfer: Arc<ReservationTransfer>,
        reply: SyncSender<Result<ReservationProposal, OutputServiceError>>,
    },
    Status(SyncSender<Result<OutputServiceStatus, OutputServiceError>>),
    Fault(SyncSender<Result<Option<OutputFault>, OutputServiceError>>),
}

enum SafetyCommand {
    Release {
        reservation_generation: u64,
        reply: SyncSender<Result<(), OutputServiceError>>,
    },
    Shutdown {
        reply: Option<SyncSender<Result<(), OutputServiceError>>>,
    },
}

struct ServiceClient {
    identity: Arc<ServiceIdentity>,
    normal_tx: SyncSender<Command>,
    safety_tx: SyncSender<SafetyCommand>,
    shutdown_requested: Arc<AtomicBool>,
    join: Mutex<Option<JoinHandle<()>>>,
}

impl ServiceClient {
    fn spawn<B: OutputBackend>(
        factory: impl FnOnce() -> Result<B, BackendFailure> + Send + 'static,
    ) -> Result<Arc<Self>, OutputServiceError> {
        let id = NEXT_SERVICE_ID
            .fetch_update(Ordering::AcqRel, Ordering::Acquire, |value| {
                value.checked_add(1)
            })
            .map_err(|_| {
                error(
                    OutputServiceErrorCode::GenerationExhausted,
                    "The native output service identity space is exhausted.",
                )
            })?;
        let identity = Arc::new(ServiceIdentity { id });
        let (normal_tx, normal_rx) = mpsc::sync_channel(NORMAL_COMMAND_CAPACITY);
        let (safety_tx, safety_rx) = mpsc::sync_channel(SAFETY_COMMAND_CAPACITY);
        let shutdown_requested = Arc::new(AtomicBool::new(false));
        let thread_identity = Arc::clone(&identity);
        let thread_shutdown = Arc::clone(&shutdown_requested);
        let join = thread::Builder::new()
            .name(OUTPUT_THREAD_NAME.to_owned())
            .spawn(move || {
                worker_loop(
                    WorkerState::new(factory),
                    thread_identity,
                    normal_rx,
                    safety_rx,
                    thread_shutdown,
                );
            })
            .map_err(|_| {
                error(
                    OutputServiceErrorCode::ThreadSpawnFailed,
                    "The native output-owner thread could not be started.",
                )
            })?;
        Ok(Arc::new(Self {
            identity,
            normal_tx,
            safety_tx,
            shutdown_requested,
            join: Mutex::new(Some(join)),
        }))
    }

    fn enumerate(&self) -> Result<OutputDeviceInventory, OutputServiceError> {
        let (reply, receive) = mpsc::sync_channel(1);
        self.send_normal(Command::Enumerate(reply))?;
        receive_reply(receive, ORDINARY_REPLY_TIMEOUT)
    }

    fn reserve(
        &self,
        selection: ExactOutputSelection,
    ) -> Result<OutputReservationReceipt, OutputServiceError> {
        let timeout = selection
            .warmup_timeout()
            .checked_add(RESERVATION_REPLY_GRACE)
            .unwrap_or(ORDINARY_REPLY_TIMEOUT);
        let deadline = Instant::now()
            .checked_add(timeout)
            .ok_or_else(request_timeout)?;
        let transfer = Arc::new(ReservationTransfer::new(deadline));
        let (reply, receive) = mpsc::sync_channel(1);
        if let Err(error) = self.send_normal(Command::Reserve {
            selection,
            transfer: Arc::clone(&transfer),
            reply,
        }) {
            transfer.cancel();
            return Err(error);
        }
        let proposal =
            match receive.recv_timeout(deadline.saturating_duration_since(Instant::now())) {
                Ok(Ok(proposal)) => proposal,
                Ok(Err(error)) => {
                    transfer.cancel();
                    return Err(error);
                }
                Err(RecvTimeoutError::Timeout) => {
                    transfer.cancel();
                    return Err(request_timeout());
                }
                Err(RecvTimeoutError::Disconnected) => {
                    transfer.cancel();
                    return Err(service_unavailable());
                }
            };
        if !transfer.caller_accept(Instant::now()) {
            return Err(request_timeout());
        }
        loop {
            match transfer.state() {
                TRANSFER_COMMITTED => return Ok(proposal.receipt),
                TRANSFER_CANCELLED => return Err(request_timeout()),
                TRANSFER_ACCEPTED | TRANSFER_WAITING => {
                    if Instant::now() >= deadline && transfer.cancel() {
                        return Err(request_timeout());
                    }
                    thread::yield_now();
                }
                _ => {
                    transfer.cancel();
                    return Err(service_unavailable());
                }
            }
        }
    }

    fn status(&self) -> Result<OutputServiceStatus, OutputServiceError> {
        let (reply, receive) = mpsc::sync_channel(1);
        self.send_normal(Command::Status(reply))?;
        receive_reply(receive, ORDINARY_REPLY_TIMEOUT)
    }

    fn fault(&self) -> Result<Option<OutputFault>, OutputServiceError> {
        let (reply, receive) = mpsc::sync_channel(1);
        self.send_normal(Command::Fault(reply))?;
        receive_reply(receive, ORDINARY_REPLY_TIMEOUT)
    }

    fn release(&self, receipt: &OutputReservationReceipt) -> Result<(), OutputServiceError> {
        if !Arc::ptr_eq(&self.identity, &receipt.service_identity)
            || self.identity.id != receipt.service_identity.id
        {
            return Err(error(
                OutputServiceErrorCode::ReceiptMismatch,
                "The silence reservation belongs to a different output service.",
            ));
        }
        let (reply, receive) = mpsc::sync_channel(1);
        self.send_safety(SafetyCommand::Release {
            reservation_generation: receipt.reservation_generation(),
            reply,
        })?;
        receive_reply(receive, ORDINARY_REPLY_TIMEOUT)
    }

    fn shutdown(&self) -> Result<(), OutputServiceError> {
        if self.shutdown_requested.swap(true, Ordering::AcqRel) {
            return Err(service_shutting_down());
        }
        let (reply, receive) = mpsc::sync_channel(1);
        self.send_safety_allow_shutdown(SafetyCommand::Shutdown { reply: Some(reply) })?;
        let result = receive_reply(receive, ORDINARY_REPLY_TIMEOUT);
        if result.is_ok() {
            let join = self.join.lock().ok().and_then(|mut value| value.take());
            if let Some(join) = join {
                if join.join().is_err() {
                    return Err(service_unavailable());
                }
            }
        }
        result
    }

    fn request_shutdown_detached(&self) {
        if self.shutdown_requested.swap(true, Ordering::AcqRel) {
            return;
        }
        let _ = self
            .safety_tx
            .try_send(SafetyCommand::Shutdown { reply: None });
    }

    fn send_normal(&self, command: Command) -> Result<(), OutputServiceError> {
        if self.shutdown_requested.load(Ordering::Acquire) {
            return Err(service_shutting_down());
        }
        map_send(self.normal_tx.try_send(command))
    }

    fn send_safety(&self, command: SafetyCommand) -> Result<(), OutputServiceError> {
        if self.shutdown_requested.load(Ordering::Acquire) {
            return Err(service_shutting_down());
        }
        map_send(self.safety_tx.try_send(command))
    }

    fn send_safety_allow_shutdown(&self, command: SafetyCommand) -> Result<(), OutputServiceError> {
        map_send(self.safety_tx.try_send(command))
    }
}

/// Local, non-Tauri owner for a persistent CPAL silence stream.
pub struct CpalOutputService {
    client: Arc<ServiceClient>,
}

impl CpalOutputService {
    /// Starts only the inert named owner thread. CPAL host/device access remains
    /// lazy until [`enumerate_output_devices`](Self::enumerate_output_devices).
    pub fn new() -> Result<Self, OutputServiceError> {
        Ok(Self {
            client: ServiceClient::spawn(CpalBackend::open)?,
        })
    }

    pub fn enumerate_output_devices(&self) -> Result<OutputDeviceInventory, OutputServiceError> {
        self.client.enumerate()
    }

    pub fn reserve_silence(
        &self,
        selection: ExactOutputSelection,
    ) -> Result<OutputReservationReceipt, OutputServiceError> {
        self.client.reserve(selection)
    }

    pub fn status(&self) -> Result<OutputServiceStatus, OutputServiceError> {
        self.client.status()
    }

    pub fn fault(&self) -> Result<Option<OutputFault>, OutputServiceError> {
        self.client.fault()
    }

    pub fn release(&self, receipt: &OutputReservationReceipt) -> Result<(), OutputServiceError> {
        self.client.release(receipt)
    }

    /// Requests bounded safety-lane shutdown and joins after the owner confirms
    /// CPAL resource release. A pathological synchronous driver call itself is
    /// not cancellable and can outlive this caller-side deadline.
    pub fn shutdown(&self) -> Result<(), OutputServiceError> {
        self.client.shutdown()
    }
}

impl fmt::Debug for CpalOutputService {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("CpalOutputService")
            .field("service_id", &self.client.identity.id)
            .finish_non_exhaustive()
    }
}

impl Drop for CpalOutputService {
    fn drop(&mut self) {
        // Drop is deliberately non-blocking. Explicit `shutdown` is the only
        // joined cleanup receipt; this fallback requests safety cleanup and
        // detaches rather than risking an unbounded driver stall in a destructor.
        self.client.request_shutdown_detached();
    }
}

fn worker_loop<B: OutputBackend>(
    mut state: WorkerState<B>,
    identity: Arc<ServiceIdentity>,
    normal_rx: Receiver<Command>,
    safety_rx: Receiver<SafetyCommand>,
    shutdown_requested: Arc<AtomicBool>,
) {
    let mut consecutive_releases = 0_u8;
    loop {
        state.refresh_callback_fault();
        if shutdown_requested.load(Ordering::Acquire) {
            // The atomic request dominates queue contents. Drain no more than
            // the capacity that could have preceded a successfully enqueued
            // Shutdown, then exit even if stale Release producers refill.
            for _ in 0..SAFETY_COMMAND_CAPACITY {
                match safety_rx.recv_timeout(OWNER_POLL_INTERVAL) {
                    Ok(command) => {
                        if handle_safety(command, &mut state) {
                            return;
                        }
                    }
                    Err(RecvTimeoutError::Timeout | RecvTimeoutError::Disconnected) => break,
                }
            }
            let _ = state.shutdown();
            return;
        }
        if consecutive_releases < MAXIMUM_CONSECUTIVE_RELEASES {
            match safety_rx.try_recv() {
                Ok(command) => {
                    if handle_safety(command, &mut state) {
                        return;
                    }
                    consecutive_releases = consecutive_releases.saturating_add(1);
                    continue;
                }
                Err(TryRecvError::Disconnected | TryRecvError::Empty) => {}
            }
        }
        match normal_rx.try_recv() {
            Ok(command) => {
                handle_command(command, &mut state, &identity, shutdown_requested.as_ref());
                consecutive_releases = 0;
                continue;
            }
            Err(TryRecvError::Disconnected) => {
                let _ = state.shutdown();
                return;
            }
            Err(TryRecvError::Empty) => {}
        }
        // No normal command was ready at the fairness point, so a new bounded
        // release burst may proceed without delaying existing normal work.
        consecutive_releases = 0;
        match safety_rx.try_recv() {
            Ok(command) => {
                if handle_safety(command, &mut state) {
                    return;
                }
                consecutive_releases = 1;
                continue;
            }
            Err(TryRecvError::Disconnected | TryRecvError::Empty) => {}
        }
        match normal_rx.recv_timeout(OWNER_POLL_INTERVAL) {
            Ok(command) => {
                handle_command(command, &mut state, &identity, shutdown_requested.as_ref());
                consecutive_releases = 0;
            }
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => {
                let _ = state.shutdown();
                return;
            }
        }
    }
}

fn handle_command<B: OutputBackend>(
    command: Command,
    state: &mut WorkerState<B>,
    identity: &Arc<ServiceIdentity>,
    shutdown_requested: &AtomicBool,
) {
    match command {
        Command::Enumerate(reply) => {
            let _ = reply.try_send(state.enumerate(identity));
        }
        Command::Reserve {
            selection,
            transfer,
            reply,
        } => match state.reserve(selection, identity, &transfer, shutdown_requested) {
            Ok((receipt, active)) => {
                state.accept_reservation(ReservationProposal { receipt }, active, &transfer, reply)
            }
            Err(failure) => {
                transfer.cancel();
                let _ = reply.try_send(Err(failure));
            }
        },
        Command::Status(reply) => {
            let _ = reply.try_send(Ok(state.status(shutdown_requested.load(Ordering::Acquire))));
        }
        Command::Fault(reply) => {
            let _ = reply.try_send(Ok(state.last_fault));
        }
    }
}

fn handle_safety<B: OutputBackend>(command: SafetyCommand, state: &mut WorkerState<B>) -> bool {
    match command {
        SafetyCommand::Release {
            reservation_generation,
            reply,
        } => {
            let _ = reply.try_send(state.release(reservation_generation));
            false
        }
        SafetyCommand::Shutdown { reply } => {
            let result = state.shutdown();
            if let Some(reply) = reply {
                let _ = reply.try_send(result);
            }
            true
        }
    }
}

fn bound_inventory<K: SelectionKey>(
    identity: Arc<ServiceIdentity>,
    generation: u64,
    raw: BackendEnumeration<K>,
) -> Result<InternalInventory<K>, BackendFailure> {
    let devices_truncated = raw.devices_truncated || raw.devices.len() > MAXIMUM_OUTPUT_DEVICES;
    let mut internal_devices = Vec::with_capacity(raw.devices.len().min(MAXIMUM_OUTPUT_DEVICES));
    for (device_index, raw_device) in raw
        .devices
        .into_iter()
        .take(MAXIMUM_OUTPUT_DEVICES)
        .enumerate()
    {
        let device_ordinal = u16::try_from(device_index).map_err(|_| BackendFailure::contract())?;
        let configs_truncated = raw_device.configs_truncated
            || raw_device.configs.len() > MAXIMUM_F32_CONFIGS_PER_DEVICE;
        let mut internal_configs =
            Vec::with_capacity(raw_device.configs.len().min(MAXIMUM_F32_CONFIGS_PER_DEVICE));
        for (config_index, raw_config) in raw_device
            .configs
            .into_iter()
            .take(MAXIMUM_F32_CONFIGS_PER_DEVICE)
            .enumerate()
        {
            if raw_config.channels == 0
                || raw_config.channels > MAXIMUM_OUTPUT_CHANNELS
                || raw_config.minimum_sample_rate_hz == 0
                || raw_config.minimum_sample_rate_hz > raw_config.maximum_sample_rate_hz
                || matches!(
                    raw_config.buffer_support,
                    OutputBufferSupport::Range {
                        minimum_frames: 0,
                        ..
                    }
                )
                || matches!(
                    raw_config.buffer_support,
                    OutputBufferSupport::Range {
                        minimum_frames,
                        maximum_frames,
                    } if minimum_frames > maximum_frames
                )
            {
                return Err(BackendFailure::contract());
            }
            let config_ordinal =
                u16::try_from(config_index).map_err(|_| BackendFailure::contract())?;
            internal_configs.push(InternalConfig {
                descriptor: OutputConfigDescriptor::new(
                    config_ordinal,
                    raw_config.channels,
                    raw_config.minimum_sample_rate_hz,
                    raw_config.maximum_sample_rate_hz,
                    raw_config.buffer_support,
                ),
                key: raw_config.key,
            });
        }
        let display_name = bounded_display_name(raw_device.display_name);
        let public_configs = internal_configs
            .iter()
            .map(|config| config.descriptor.clone())
            .collect::<Vec<_>>()
            .into_boxed_slice();
        let descriptor = OutputDeviceDescriptor::new(
            device_ordinal,
            display_name,
            public_configs,
            configs_truncated,
        );
        internal_devices.push(InternalDevice {
            descriptor,
            configs: internal_configs,
        });
    }
    let public_devices = internal_devices
        .iter()
        .map(|device| device.descriptor.clone())
        .collect::<Vec<_>>()
        .into_boxed_slice();
    Ok(InternalInventory {
        public: OutputDeviceInventory::new(identity, generation, public_devices, devices_truncated),
        devices: internal_devices,
    })
}

fn bounded_display_name(mut value: String) -> String {
    if value.is_empty() {
        return "Unnamed output device".to_owned();
    }
    if value.len() <= MAXIMUM_DEVICE_NAME_BYTES {
        return value;
    }
    let mut boundary = MAXIMUM_DEVICE_NAME_BYTES;
    while !value.is_char_boundary(boundary) {
        boundary -= 1;
    }
    value.truncate(boundary);
    value
}

fn receive_reply<T>(
    receive: Receiver<Result<T, OutputServiceError>>,
    timeout: Duration,
) -> Result<T, OutputServiceError> {
    match receive.recv_timeout(timeout) {
        Ok(result) => result,
        Err(RecvTimeoutError::Timeout) => Err(error(
            OutputServiceErrorCode::RequestTimeout,
            "The native output owner did not reply before the bounded deadline.",
        )),
        Err(RecvTimeoutError::Disconnected) => Err(service_unavailable()),
    }
}

fn map_send<T>(result: Result<(), TrySendError<T>>) -> Result<(), OutputServiceError> {
    match result {
        Ok(()) => Ok(()),
        Err(TrySendError::Full(_)) => Err(error(
            OutputServiceErrorCode::QueueFull,
            "The bounded native output command queue is full.",
        )),
        Err(TrySendError::Disconnected(_)) => Err(service_unavailable()),
    }
}

const fn error(code: OutputServiceErrorCode, message: &'static str) -> OutputServiceError {
    OutputServiceError::new(code, message)
}

const fn exact_config_mismatch() -> OutputServiceError {
    error(
        OutputServiceErrorCode::ExactConfigMismatch,
        "The selected F32 output configuration does not exactly match the current inventory.",
    )
}

const fn stale_reservation() -> OutputServiceError {
    error(
        OutputServiceErrorCode::StaleReservation,
        "The native silence reservation is no longer current.",
    )
}

const fn backend_unavailable() -> OutputServiceError {
    error(
        OutputServiceErrorCode::BackendUnavailable,
        "The native output backend is unavailable.",
    )
}

const fn service_unavailable() -> OutputServiceError {
    error(
        OutputServiceErrorCode::ServiceUnavailable,
        "The native output-owner thread is unavailable.",
    )
}

const fn service_shutting_down() -> OutputServiceError {
    error(
        OutputServiceErrorCode::ServiceShuttingDown,
        "The native output service is shutting down.",
    )
}

const fn request_timeout() -> OutputServiceError {
    error(
        OutputServiceErrorCode::RequestTimeout,
        "The native output owner did not complete the request before its bounded deadline.",
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::MAXIMUM_WARMUP_TIMEOUT;
    use std::sync::{
        atomic::{AtomicBool, AtomicU8, AtomicUsize},
        Condvar,
    };

    const WARMUP_CALLBACK: u8 = 1;
    const WARMUP_NONE: u8 = 2;
    const WARMUP_FAULT: u8 = 3;

    #[derive(Default)]
    struct BlockingGate {
        state: Mutex<GateState>,
        changed: Condvar,
    }

    #[derive(Default)]
    struct GateState {
        blocked: bool,
        entered: bool,
    }

    impl BlockingGate {
        fn block(&self) {
            let mut state = self.state.lock().unwrap();
            state.blocked = true;
            state.entered = false;
        }

        fn enter_and_wait(&self) {
            let mut state = self.state.lock().unwrap();
            state.entered = true;
            self.changed.notify_all();
            while state.blocked {
                state = self.changed.wait(state).unwrap();
            }
        }

        fn wait_until_entered(&self) {
            let deadline = Instant::now() + Duration::from_secs(2);
            let mut state = self.state.lock().unwrap();
            while !state.entered {
                let remaining = deadline.saturating_duration_since(Instant::now());
                assert!(!remaining.is_zero(), "fake backend gate was never entered");
                let (next, timeout) = self.changed.wait_timeout(state, remaining).unwrap();
                state = next;
                assert!(!timeout.timed_out() || state.entered);
            }
        }

        fn unblock(&self) {
            let mut state = self.state.lock().unwrap();
            state.blocked = false;
            self.changed.notify_all();
        }
    }

    struct FakeControl {
        factory_calls: AtomicUsize,
        create_calls: AtomicUsize,
        play_calls: AtomicUsize,
        release_calls: AtomicUsize,
        drop_calls: AtomicUsize,
        device_count: AtomicUsize,
        config_count: AtomicUsize,
        long_names: AtomicBool,
        warmup: AtomicU8,
        release_fails_once: AtomicBool,
        malformed_enumeration_once: AtomicBool,
        enumerate_gate: BlockingGate,
        create_gate: BlockingGate,
        signals: Mutex<Option<Arc<CallbackSignals>>>,
        owner_thread_names: Mutex<Vec<String>>,
    }

    impl Default for FakeControl {
        fn default() -> Self {
            Self {
                factory_calls: AtomicUsize::new(0),
                create_calls: AtomicUsize::new(0),
                play_calls: AtomicUsize::new(0),
                release_calls: AtomicUsize::new(0),
                drop_calls: AtomicUsize::new(0),
                device_count: AtomicUsize::new(1),
                config_count: AtomicUsize::new(1),
                long_names: AtomicBool::new(false),
                warmup: AtomicU8::new(WARMUP_CALLBACK),
                release_fails_once: AtomicBool::new(false),
                malformed_enumeration_once: AtomicBool::new(false),
                enumerate_gate: BlockingGate::default(),
                create_gate: BlockingGate::default(),
                signals: Mutex::new(None),
                owner_thread_names: Mutex::new(Vec::new()),
            }
        }
    }

    impl FakeControl {
        fn record_owner_thread(&self) {
            self.owner_thread_names
                .lock()
                .unwrap()
                .push(thread::current().name().unwrap_or("unnamed").to_owned());
        }

        fn trigger_callback_fault(&self) {
            self.signals
                .lock()
                .unwrap()
                .as_ref()
                .unwrap()
                .record_callback_fault();
        }
    }

    #[derive(Clone, Copy)]
    struct FakeKey {
        device: usize,
        config: usize,
    }

    impl SelectionKey for FakeKey {}

    struct FakeBackend {
        control: Arc<FakeControl>,
    }

    impl OutputBackend for FakeBackend {
        type Key = FakeKey;

        fn enumerate(&mut self) -> Result<BackendEnumeration<Self::Key>, BackendFailure> {
            self.control.record_owner_thread();
            self.control.enumerate_gate.enter_and_wait();
            let device_count = self.control.device_count.load(Ordering::Acquire);
            let config_count = self.control.config_count.load(Ordering::Acquire);
            let malformed = self
                .control
                .malformed_enumeration_once
                .swap(false, Ordering::AcqRel);
            let long_names = self.control.long_names.load(Ordering::Acquire);
            let mut devices = Vec::with_capacity(device_count);
            for device in 0..device_count {
                let display_name = if long_names {
                    "é".repeat(MAXIMUM_DEVICE_NAME_BYTES)
                } else {
                    format!("Fake output {device}")
                };
                let configs = (0..config_count)
                    .map(|config| BackendConfig {
                        key: FakeKey { device, config },
                        channels: if malformed { 0 } else { 2 },
                        minimum_sample_rate_hz: 44_100,
                        maximum_sample_rate_hz: 48_000,
                        buffer_support: OutputBufferSupport::Range {
                            minimum_frames: 64,
                            maximum_frames: 1_024,
                        },
                    })
                    .collect();
                devices.push(BackendDevice {
                    display_name,
                    configs,
                    configs_truncated: false,
                });
            }
            Ok(BackendEnumeration {
                devices,
                devices_truncated: false,
            })
        }

        fn create_silence(
            &mut self,
            key: &Self::Key,
            _selection: &ExactOutputSelection,
            signals: Arc<CallbackSignals>,
            _backend_timeout: Duration,
        ) -> Result<(), BackendFailure> {
            self.control.record_owner_thread();
            self.control.create_calls.fetch_add(1, Ordering::AcqRel);
            assert_eq!((key.device, key.config), (0, 0));
            self.control.create_gate.enter_and_wait();
            *self.control.signals.lock().unwrap() = Some(Arc::clone(&signals));
            Ok(())
        }

        fn play_silence(&mut self) -> Result<(), BackendFailure> {
            self.control.record_owner_thread();
            self.control.play_calls.fetch_add(1, Ordering::AcqRel);
            let signals = self
                .control
                .signals
                .lock()
                .unwrap()
                .as_ref()
                .cloned()
                .ok_or_else(BackendFailure::contract)?;
            match self.control.warmup.load(Ordering::Acquire) {
                WARMUP_CALLBACK => {
                    let mut samples = [1.0_f32; 8];
                    signals.write_silence(&mut samples);
                    assert_eq!(samples, [0.0; 8]);
                }
                WARMUP_NONE => {}
                WARMUP_FAULT => signals.record_callback_fault(),
                other => panic!("unexpected fake warmup mode {other}"),
            }
            Ok(())
        }

        fn release(&mut self) -> Result<(), BackendFailure> {
            self.control.record_owner_thread();
            self.control.release_calls.fetch_add(1, Ordering::AcqRel);
            if self
                .control
                .release_fails_once
                .swap(false, Ordering::AcqRel)
            {
                return Err(BackendFailure::new(
                    OutputFaultKind::StreamReleaseFailed,
                    OutputServiceErrorCode::StreamReleaseFailed,
                    "The native silence stream could not be released.",
                ));
            }
            *self.control.signals.lock().unwrap() = None;
            Ok(())
        }
    }

    impl Drop for FakeBackend {
        fn drop(&mut self) {
            self.control.record_owner_thread();
            self.control.drop_calls.fetch_add(1, Ordering::AcqRel);
        }
    }

    fn fake_service(control: &Arc<FakeControl>) -> Arc<ServiceClient> {
        let factory_control = Arc::clone(control);
        ServiceClient::spawn(move || {
            factory_control.factory_calls.fetch_add(1, Ordering::AcqRel);
            factory_control.record_owner_thread();
            Ok(FakeBackend {
                control: factory_control,
            })
        })
        .unwrap()
    }

    fn selection(
        inventory: &OutputDeviceInventory,
        channels: u16,
        sample_rate_hz: u32,
        buffer: OutputBufferSelection,
        warmup_timeout: Duration,
    ) -> ExactOutputSelection {
        inventory
            .select_exact(0, 0, channels, sample_rate_hz, buffer, warmup_timeout)
            .unwrap()
    }

    #[test]
    fn construction_is_inert_and_the_named_owner_starts_without_opening_cpal() {
        let control = Arc::new(FakeControl::default());
        let service = fake_service(&control);
        assert_eq!(control.factory_calls.load(Ordering::Acquire), 0);
        assert_eq!(service.status().unwrap().phase(), OutputServicePhase::Idle);
        assert_eq!(control.factory_calls.load(Ordering::Acquire), 0);
        assert_eq!(
            service
                .join
                .lock()
                .unwrap()
                .as_ref()
                .unwrap()
                .thread()
                .name(),
            Some(OUTPUT_THREAD_NAME)
        );
        service.shutdown().unwrap();
        assert_eq!(control.factory_calls.load(Ordering::Acquire), 0);
    }

    #[test]
    fn inventory_caps_devices_configs_and_utf8_names_before_publication() {
        let control = Arc::new(FakeControl::default());
        control
            .device_count
            .store(MAXIMUM_OUTPUT_DEVICES + 2, Ordering::Release);
        control
            .config_count
            .store(MAXIMUM_F32_CONFIGS_PER_DEVICE + 2, Ordering::Release);
        control.long_names.store(true, Ordering::Release);
        let service = fake_service(&control);
        let inventory = service.enumerate().unwrap();
        assert_eq!(inventory.generation(), 1);
        assert_eq!(inventory.devices().len(), MAXIMUM_OUTPUT_DEVICES);
        assert!(inventory.devices_truncated());
        for (device_index, device) in inventory.devices().iter().enumerate() {
            assert_eq!(usize::from(device.device_ordinal()), device_index);
            assert!(device.display_name().len() <= MAXIMUM_DEVICE_NAME_BYTES);
            assert!(device
                .display_name()
                .is_char_boundary(device.display_name().len()));
            assert_eq!(device.f32_configs().len(), MAXIMUM_F32_CONFIGS_PER_DEVICE);
            assert!(device.configs_truncated());
        }
        service.shutdown().unwrap();
    }

    #[test]
    fn exact_selection_rejects_stale_or_mismatched_requests_without_opening_a_stream() {
        let control = Arc::new(FakeControl::default());
        let service = fake_service(&control);
        let inventory = service.enumerate().unwrap();
        let stale = selection(
            &inventory,
            2,
            48_000,
            OutputBufferSelection::Fixed(256),
            Duration::from_millis(50),
        )
        .with_inventory_generation_for_test(inventory.generation() + 1);
        assert_eq!(
            service.reserve(stale).unwrap_err().code(),
            OutputServiceErrorCode::StaleInventory
        );
        for invalid in [
            selection(
                &inventory,
                3,
                48_000,
                OutputBufferSelection::Fixed(256),
                Duration::from_millis(50),
            ),
            selection(
                &inventory,
                2,
                96_000,
                OutputBufferSelection::Fixed(256),
                Duration::from_millis(50),
            ),
            selection(
                &inventory,
                2,
                48_000,
                OutputBufferSelection::Fixed(2_048),
                Duration::from_millis(50),
            ),
        ] {
            assert_eq!(
                service.reserve(invalid).unwrap_err().code(),
                OutputServiceErrorCode::ExactConfigMismatch
            );
        }
        assert!(control.signals.lock().unwrap().is_none());

        let current = selection(
            &inventory,
            2,
            48_000,
            OutputBufferSelection::Fixed(256),
            Duration::from_millis(50),
        );
        let receipt = service.reserve(current.clone()).unwrap();
        assert_eq!(receipt.selection(), &current);
        service.release(&receipt).unwrap();
        let replacement = service.enumerate().unwrap();
        assert_eq!(replacement.generation(), inventory.generation() + 1);
        assert_eq!(
            service.reserve(current).unwrap_err().code(),
            OutputServiceErrorCode::StaleInventory
        );
        service.shutdown().unwrap();
    }

    #[test]
    fn exact_selection_is_fenced_to_the_inventory_owner_not_just_its_generation() {
        let first_control = Arc::new(FakeControl::default());
        let second_control = Arc::new(FakeControl::default());
        let first = fake_service(&first_control);
        let second = fake_service(&second_control);
        let first_inventory = first.enumerate().unwrap();
        let second_inventory = second.enumerate().unwrap();
        assert_eq!(first_inventory.generation(), second_inventory.generation());
        let first_selection = selection(
            &first_inventory,
            2,
            48_000,
            OutputBufferSelection::Default,
            Duration::from_millis(50),
        );
        assert_eq!(
            second.reserve(first_selection).unwrap_err().code(),
            OutputServiceErrorCode::SelectionOwnerMismatch
        );
        assert_eq!(second_control.create_calls.load(Ordering::Acquire), 0);
        first.shutdown().unwrap();
        second.shutdown().unwrap();
    }

    #[test]
    fn failed_inventory_refresh_invalidates_old_public_ordinals_before_backend_mutation() {
        let control = Arc::new(FakeControl::default());
        let service = fake_service(&control);
        let inventory = service.enumerate().unwrap();
        let old_selection = selection(
            &inventory,
            2,
            48_000,
            OutputBufferSelection::Default,
            Duration::from_millis(50),
        );
        control
            .malformed_enumeration_once
            .store(true, Ordering::Release);
        assert_eq!(
            service.enumerate().unwrap_err().code(),
            OutputServiceErrorCode::BackendContractViolation
        );
        assert_eq!(
            service.reserve(old_selection).unwrap_err().code(),
            OutputServiceErrorCode::InventoryMissing
        );
        assert_eq!(control.create_calls.load(Ordering::Acquire), 0);
        service.shutdown().unwrap();
    }

    #[test]
    fn warmup_timeout_and_immediate_callback_fault_release_without_a_receipt() {
        for (mode, expected_code, expected_fault) in [
            (
                WARMUP_NONE,
                OutputServiceErrorCode::WarmupTimeout,
                OutputFaultKind::WarmupTimeout,
            ),
            (
                WARMUP_FAULT,
                OutputServiceErrorCode::CallbackFault,
                OutputFaultKind::CallbackFault,
            ),
        ] {
            let control = Arc::new(FakeControl::default());
            control.warmup.store(mode, Ordering::Release);
            let service = fake_service(&control);
            let inventory = service.enumerate().unwrap();
            let error = service
                .reserve(selection(
                    &inventory,
                    2,
                    48_000,
                    OutputBufferSelection::Default,
                    Duration::from_millis(8),
                ))
                .unwrap_err();
            assert_eq!(error.code(), expected_code);
            assert_eq!(control.release_calls.load(Ordering::Acquire), 1);
            let status = service.status().unwrap();
            assert_eq!(status.phase(), OutputServicePhase::Faulted);
            assert_eq!(status.last_fault().unwrap().kind(), expected_fault);
            assert!(status.reservation_generation().is_none());
            service.shutdown().unwrap();
        }
    }

    #[test]
    fn callback_fault_is_latched_and_releases_the_silence_stream() {
        let control = Arc::new(FakeControl::default());
        let service = fake_service(&control);
        let inventory = service.enumerate().unwrap();
        let receipt = service
            .reserve(selection(
                &inventory,
                2,
                48_000,
                OutputBufferSelection::Default,
                Duration::from_millis(50),
            ))
            .unwrap();
        control.trigger_callback_fault();
        let deadline = Instant::now() + Duration::from_secs(1);
        let status = loop {
            let status = service.status().unwrap();
            if status.phase() == OutputServicePhase::Faulted {
                break status;
            }
            assert!(Instant::now() < deadline);
            thread::yield_now();
        };
        assert_eq!(
            status.last_fault().unwrap().kind(),
            OutputFaultKind::CallbackFault
        );
        assert_eq!(status.callback_fault_count(), 1);
        assert_eq!(control.release_calls.load(Ordering::Acquire), 1);
        assert_eq!(
            service.release(&receipt).unwrap_err().code(),
            OutputServiceErrorCode::StaleReservation
        );
        service.shutdown().unwrap();
    }

    #[test]
    fn release_is_service_and_generation_fenced_and_retryable_after_a_fault() {
        let first_control = Arc::new(FakeControl::default());
        let second_control = Arc::new(FakeControl::default());
        let first = fake_service(&first_control);
        let second = fake_service(&second_control);
        let inventory = first.enumerate().unwrap();
        let receipt = first
            .reserve(selection(
                &inventory,
                2,
                48_000,
                OutputBufferSelection::Default,
                Duration::from_millis(50),
            ))
            .unwrap();
        assert_eq!(
            second.release(&receipt).unwrap_err().code(),
            OutputServiceErrorCode::ReceiptMismatch
        );
        first_control
            .release_fails_once
            .store(true, Ordering::Release);
        assert_eq!(
            first.release(&receipt).unwrap_err().code(),
            OutputServiceErrorCode::StreamReleaseFailed
        );
        let faulted = first.status().unwrap();
        assert_eq!(faulted.phase(), OutputServicePhase::Faulted);
        assert_eq!(
            faulted.last_fault().unwrap().kind(),
            OutputFaultKind::StreamReleaseFailed
        );
        first.release(&receipt).unwrap();
        assert_eq!(
            first.release(&receipt).unwrap_err().code(),
            OutputServiceErrorCode::StaleReservation
        );
        first.shutdown().unwrap();
        second.shutdown().unwrap();
    }

    #[test]
    fn late_success_after_caller_timeout_is_released_and_never_published() {
        let control = Arc::new(FakeControl::default());
        control.create_gate.block();
        let service = fake_service(&control);
        let inventory = service.enumerate().unwrap();
        let error = service
            .reserve(selection(
                &inventory,
                2,
                48_000,
                OutputBufferSelection::Default,
                Duration::from_millis(8),
            ))
            .unwrap_err();
        assert_eq!(error.code(), OutputServiceErrorCode::RequestTimeout);
        control.create_gate.wait_until_entered();
        control.create_gate.unblock();

        let deadline = Instant::now() + Duration::from_secs(1);
        loop {
            let status = service.status().unwrap();
            if control.release_calls.load(Ordering::Acquire) == 1 {
                assert_ne!(status.phase(), OutputServicePhase::ReservedSilence);
                assert!(status.reservation_generation().is_none());
                break;
            }
            assert!(Instant::now() < deadline);
            thread::yield_now();
        }
        service.shutdown().unwrap();
    }

    #[test]
    fn reserve_abandoned_while_queued_never_enters_a_driver_side_effect() {
        let control = Arc::new(FakeControl::default());
        let service = fake_service(&control);
        let first_inventory = service.enumerate().unwrap();
        let queued_selection = selection(
            &first_inventory,
            2,
            48_000,
            OutputBufferSelection::Default,
            Duration::from_millis(8),
        );
        control.enumerate_gate.block();
        let refresh_service = Arc::clone(&service);
        let refresh = thread::spawn(move || refresh_service.enumerate());
        control.enumerate_gate.wait_until_entered();
        let reserve_service = Arc::clone(&service);
        let reserve = thread::spawn(move || reserve_service.reserve(queued_selection));
        assert_eq!(
            reserve.join().unwrap().unwrap_err().code(),
            OutputServiceErrorCode::RequestTimeout
        );
        control.enumerate_gate.unblock();
        assert!(refresh.join().unwrap().is_ok());
        assert!(service.status().is_ok());
        assert_eq!(control.create_calls.load(Ordering::Acquire), 0);
        service.shutdown().unwrap();
    }

    #[test]
    fn unaccepted_abort_release_failure_stays_fenced_until_shutdown() {
        for mode in [WARMUP_NONE, WARMUP_FAULT] {
            let control = Arc::new(FakeControl::default());
            control.warmup.store(mode, Ordering::Release);
            control.release_fails_once.store(true, Ordering::Release);
            let service = fake_service(&control);
            let inventory = service.enumerate().unwrap();
            let _ = service.reserve(selection(
                &inventory,
                2,
                48_000,
                OutputBufferSelection::Default,
                Duration::from_millis(8),
            ));
            let status = service.status().unwrap();
            assert_eq!(status.phase(), OutputServicePhase::Faulted);
            assert_eq!(
                status.last_fault().unwrap().kind(),
                OutputFaultKind::StreamReleaseFailed
            );
            assert!(status.reservation_generation().is_some());
            assert_eq!(
                service.enumerate().unwrap_err().code(),
                OutputServiceErrorCode::AlreadyReserved
            );
            assert_eq!(control.release_calls.load(Ordering::Acquire), 1);
            service.shutdown().unwrap();
            assert_eq!(control.release_calls.load(Ordering::Acquire), 2);
        }
    }

    #[test]
    fn transfer_rollback_release_failure_remains_owned_until_shutdown() {
        let control = Arc::new(FakeControl::default());
        control.create_gate.block();
        let service = fake_service(&control);
        let inventory = service.enumerate().unwrap();
        let reserve_service = Arc::clone(&service);
        let reserve = thread::spawn(move || {
            reserve_service.reserve(selection(
                &inventory,
                2,
                48_000,
                OutputBufferSelection::Default,
                Duration::from_millis(8),
            ))
        });
        control.create_gate.wait_until_entered();
        assert_eq!(
            reserve.join().unwrap().unwrap_err().code(),
            OutputServiceErrorCode::RequestTimeout
        );
        control.release_fails_once.store(true, Ordering::Release);
        control.create_gate.unblock();
        let status = service.status().unwrap();
        assert_eq!(status.phase(), OutputServicePhase::Faulted);
        assert_eq!(
            status.last_fault().unwrap().kind(),
            OutputFaultKind::StreamReleaseFailed
        );
        assert!(status.reservation_generation().is_some());
        service.shutdown().unwrap();
        assert_eq!(control.release_calls.load(Ordering::Acquire), 2);
    }

    #[test]
    fn shutdown_abort_retries_a_failed_candidate_release_before_owner_exit() {
        let control = Arc::new(FakeControl::default());
        control.warmup.store(WARMUP_NONE, Ordering::Release);
        let service = fake_service(&control);
        let inventory = service.enumerate().unwrap();
        let reserve_service = Arc::clone(&service);
        let reserve = thread::spawn(move || {
            reserve_service.reserve(selection(
                &inventory,
                2,
                48_000,
                OutputBufferSelection::Default,
                Duration::from_secs(1),
            ))
        });
        control.create_gate.wait_until_entered();
        control.release_fails_once.store(true, Ordering::Release);
        service.shutdown().unwrap();
        assert_eq!(
            reserve.join().unwrap().unwrap_err().code(),
            OutputServiceErrorCode::ServiceShuttingDown
        );
        assert_eq!(control.release_calls.load(Ordering::Acquire), 2);
        assert!(control.signals.lock().unwrap().is_none());
    }

    #[test]
    fn normal_queue_saturation_cannot_starve_safety_shutdown() {
        let control = Arc::new(FakeControl::default());
        control.enumerate_gate.block();
        let service = fake_service(&control);
        let enumerate_service = Arc::clone(&service);
        let enumerate = thread::spawn(move || enumerate_service.enumerate());
        control.enumerate_gate.wait_until_entered();

        let mut held_receivers = Vec::new();
        for _ in 0..NORMAL_COMMAND_CAPACITY {
            let (reply, receive) = mpsc::sync_channel(1);
            service.send_normal(Command::Status(reply)).unwrap();
            held_receivers.push(receive);
        }
        assert_eq!(
            service.status().unwrap_err().code(),
            OutputServiceErrorCode::QueueFull
        );
        let shutdown_service = Arc::clone(&service);
        let shutdown = thread::spawn(move || shutdown_service.shutdown());
        control.enumerate_gate.unblock();
        assert!(enumerate.join().unwrap().is_ok());
        shutdown.join().unwrap().unwrap();
        drop(held_receivers);
    }

    #[test]
    fn atomic_shutdown_exits_after_a_bounded_drain_even_when_safety_was_full() {
        let control = Arc::new(FakeControl::default());
        control.enumerate_gate.block();
        let service = fake_service(&control);
        let enumerate_service = Arc::clone(&service);
        let enumerate = thread::spawn(move || enumerate_service.enumerate());
        control.enumerate_gate.wait_until_entered();

        let mut held_receivers = Vec::new();
        for _ in 0..SAFETY_COMMAND_CAPACITY {
            let (reply, receive) = mpsc::sync_channel(1);
            service
                .send_safety(SafetyCommand::Release {
                    reservation_generation: u64::MAX,
                    reply,
                })
                .unwrap();
            held_receivers.push(receive);
        }
        assert_eq!(
            service.shutdown().unwrap_err().code(),
            OutputServiceErrorCode::QueueFull
        );

        let keep_refilling = Arc::new(AtomicBool::new(true));
        let refilling = Arc::clone(&keep_refilling);
        let refiller_service = Arc::clone(&service);
        let refiller = thread::spawn(move || {
            while refilling.load(Ordering::Acquire) {
                let (reply, _receive) = mpsc::sync_channel(1);
                let _ = refiller_service.safety_tx.try_send(SafetyCommand::Release {
                    reservation_generation: u64::MAX,
                    reply,
                });
                thread::yield_now();
            }
        });
        let owner_join = service.join.lock().unwrap().take().unwrap();
        let (exited_tx, exited_rx) = mpsc::sync_channel(1);
        let join_waiter = thread::spawn(move || {
            let result = owner_join.join();
            let _ = exited_tx.try_send(result);
        });
        control.enumerate_gate.unblock();
        assert!(enumerate.join().unwrap().is_ok());
        let exited = exited_rx.recv_timeout(Duration::from_secs(1));
        keep_refilling.store(false, Ordering::Release);
        refiller.join().unwrap();
        assert!(matches!(exited, Ok(Ok(()))));
        join_waiter.join().unwrap();
        drop(held_receivers);
    }

    #[test]
    fn continuously_refilled_release_lane_cannot_starve_ready_normal_work() {
        let control = Arc::new(FakeControl::default());
        control.enumerate_gate.block();
        let service = fake_service(&control);
        let enumerate_service = Arc::clone(&service);
        let enumerate = thread::spawn(move || enumerate_service.enumerate());
        control.enumerate_gate.wait_until_entered();

        let keep_refilling = Arc::new(AtomicBool::new(true));
        let refilling = Arc::clone(&keep_refilling);
        let refiller_service = Arc::clone(&service);
        let refiller = thread::spawn(move || {
            while refilling.load(Ordering::Acquire) {
                let (reply, _receive) = mpsc::sync_channel(1);
                let _ = refiller_service.safety_tx.try_send(SafetyCommand::Release {
                    reservation_generation: u64::MAX,
                    reply,
                });
                thread::yield_now();
            }
        });
        let (status_reply, status_receive) = mpsc::sync_channel(1);
        service.send_normal(Command::Status(status_reply)).unwrap();
        control.enumerate_gate.unblock();
        assert!(enumerate.join().unwrap().is_ok());
        assert!(matches!(
            status_receive.recv_timeout(Duration::from_secs(1)),
            Ok(Ok(_))
        ));
        keep_refilling.store(false, Ordering::Release);
        refiller.join().unwrap();
        thread::sleep(Duration::from_millis(25));
        service.shutdown().unwrap();
    }

    #[test]
    fn callback_is_silence_only_and_every_backend_operation_stays_on_the_owner() {
        let signals = CallbackSignals::new();
        let mut samples = [f32::MAX, -1.0, f32::NAN, 4.0];
        signals.write_silence(&mut samples);
        assert_eq!(samples, [0.0; 4]);
        assert_eq!(signals.callback_count(), 1);
        let mut malformed = [0xff_u8; 17];
        signals.write_raw_silence(false, 2, 4, &mut malformed);
        assert_eq!(malformed, [0xff; 17]);
        assert_eq!(signals.callback_count(), 1);
        assert_eq!(signals.callback_fault_count(), 1);
        signals.write_raw_silence(true, 2, 4, &mut malformed);
        assert_eq!(malformed, [0xff; 17]);
        assert_eq!(signals.callback_fault_count(), 2);
        let mut exact_f32 = [0xff_u8; 16];
        signals.write_raw_silence(true, 2, 4, &mut exact_f32);
        assert_eq!(exact_f32, [0; 16]);
        assert_eq!(signals.callback_count(), 2);
        assert!(raw_callback_shape_is_bounded(
            true,
            MAXIMUM_OUTPUT_CHANNELS,
            MAXIMUM_CALLBACK_FRAMES * usize::from(MAXIMUM_OUTPUT_CHANNELS)
        ));
        assert!(!raw_callback_shape_is_bounded(
            true,
            1,
            MAXIMUM_CALLBACK_FRAMES + 1
        ));
        let mut oversized = [0xff_u8; 8];
        signals.write_raw_silence(true, 1, MAXIMUM_CALLBACK_FRAMES + 1, &mut oversized);
        assert_eq!(oversized, [0xff; 8]);
        assert_eq!(signals.callback_fault_count(), 3);

        let control = Arc::new(FakeControl::default());
        let service = fake_service(&control);
        let inventory = service.enumerate().unwrap();
        let receipt = service
            .reserve(selection(
                &inventory,
                2,
                48_000,
                OutputBufferSelection::Default,
                Duration::from_millis(50),
            ))
            .unwrap();
        service.release(&receipt).unwrap();
        service.shutdown().unwrap();
        assert_eq!(control.drop_calls.load(Ordering::Acquire), 1);
        let names = control.owner_thread_names.lock().unwrap();
        assert!(names.len() >= 5);
        assert!(names.iter().all(|name| name == OUTPUT_THREAD_NAME));
    }

    #[test]
    fn invalid_selection_bounds_fail_before_service_admission() {
        let identity = Arc::new(ServiceIdentity { id: 99 });
        let valid_inventory = OutputDeviceInventory::new(
            Arc::clone(&identity),
            1,
            Vec::new().into_boxed_slice(),
            false,
        );
        let zero_generation_inventory =
            OutputDeviceInventory::new(identity, 0, Vec::new().into_boxed_slice(), false);
        for invalid in [
            zero_generation_inventory.select_exact(
                0,
                0,
                2,
                48_000,
                OutputBufferSelection::Default,
                Duration::from_millis(50),
            ),
            valid_inventory.select_exact(
                0,
                0,
                0,
                48_000,
                OutputBufferSelection::Default,
                Duration::from_millis(50),
            ),
            valid_inventory.select_exact(
                0,
                0,
                MAXIMUM_OUTPUT_CHANNELS + 1,
                48_000,
                OutputBufferSelection::Default,
                Duration::from_millis(50),
            ),
            valid_inventory.select_exact(
                0,
                0,
                2,
                48_000,
                OutputBufferSelection::Fixed(0),
                Duration::from_millis(50),
            ),
            valid_inventory.select_exact(
                0,
                0,
                2,
                48_000,
                OutputBufferSelection::Fixed(u32::try_from(MAXIMUM_CALLBACK_FRAMES).unwrap() + 1),
                Duration::from_millis(50),
            ),
            valid_inventory.select_exact(
                0,
                0,
                2,
                48_000,
                OutputBufferSelection::Default,
                MAXIMUM_WARMUP_TIMEOUT + Duration::from_millis(1),
            ),
        ] {
            assert_eq!(
                invalid.unwrap_err().code(),
                OutputServiceErrorCode::InvalidSelection
            );
        }
    }

    #[test]
    fn reservation_transfer_has_deterministic_before_at_and_after_deadline_outcomes() {
        let deadline = Instant::now() + Duration::from_secs(1);
        let before = ReservationTransfer::new(deadline);
        assert!(before.caller_accept(deadline - Duration::from_nanos(1)));
        assert!(before.owner_commit(deadline - Duration::from_nanos(1)));
        assert_eq!(before.state(), TRANSFER_COMMITTED);
        assert!(!before.cancel());

        let at = ReservationTransfer::new(deadline);
        assert!(!at.caller_accept(deadline));
        assert_eq!(at.state(), TRANSFER_CANCELLED);
        assert!(!at.owner_commit(deadline));

        let after = ReservationTransfer::new(deadline);
        assert!(after.is_cancelled_or_expired(deadline + Duration::from_nanos(1)));
        assert_eq!(after.state(), TRANSFER_CANCELLED);

        let accepted_then_cancelled = ReservationTransfer::new(deadline);
        assert!(accepted_then_cancelled.caller_accept(deadline - Duration::from_nanos(1)));
        assert!(accepted_then_cancelled.cancel());
        assert!(!accepted_then_cancelled.owner_commit(deadline - Duration::from_nanos(1)));

        let accepted_then_late_commit = ReservationTransfer::new(deadline);
        assert!(accepted_then_late_commit.caller_accept(deadline - Duration::from_nanos(1)));
        assert!(!accepted_then_late_commit.owner_commit(deadline));
        assert_eq!(accepted_then_late_commit.state(), TRANSFER_CANCELLED);
    }

    #[test]
    fn warmup_observation_is_strictly_before_deadline_and_fault_first() {
        let deadline = Instant::now() + Duration::from_secs(1);
        assert_eq!(
            classify_warmup_observation(0, 1, deadline - Duration::from_nanos(1), deadline),
            WarmupObservation::Ready(1)
        );
        assert_eq!(
            classify_warmup_observation(0, 1, deadline, deadline),
            WarmupObservation::TimedOut
        );
        assert_eq!(
            classify_warmup_observation(0, 1, deadline + Duration::from_nanos(1), deadline),
            WarmupObservation::TimedOut
        );
        assert_eq!(
            classify_warmup_observation(1, 1, deadline, deadline),
            WarmupObservation::Faulted
        );
    }
}
