use std::{error::Error, fmt, sync::Arc, time::Duration};

pub const MAXIMUM_OUTPUT_DEVICES: usize = 32;
pub const MAXIMUM_F32_CONFIGS_PER_DEVICE: usize = 64;
pub const MAXIMUM_DEVICE_NAME_BYTES: usize = 256;
pub const MAXIMUM_OUTPUT_CHANNELS: u16 = 4;
pub const MAXIMUM_CALLBACK_FRAMES: usize = 4_096;
pub const MAXIMUM_WARMUP_TIMEOUT: Duration = Duration::from_secs(5);
pub(crate) const MINIMUM_WARMUP_TIMEOUT: Duration = Duration::from_millis(1);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputSampleFormat {
    F32,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputBufferSupport {
    Unknown,
    Range {
        minimum_frames: u32,
        maximum_frames: u32,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputBufferSelection {
    Default,
    Fixed(u32),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutputConfigDescriptor {
    config_ordinal: u16,
    channels: u16,
    minimum_sample_rate_hz: u32,
    maximum_sample_rate_hz: u32,
    sample_format: OutputSampleFormat,
    buffer_support: OutputBufferSupport,
}

impl OutputConfigDescriptor {
    pub(crate) const fn new(
        config_ordinal: u16,
        channels: u16,
        minimum_sample_rate_hz: u32,
        maximum_sample_rate_hz: u32,
        buffer_support: OutputBufferSupport,
    ) -> Self {
        Self {
            config_ordinal,
            channels,
            minimum_sample_rate_hz,
            maximum_sample_rate_hz,
            sample_format: OutputSampleFormat::F32,
            buffer_support,
        }
    }

    pub const fn config_ordinal(&self) -> u16 {
        self.config_ordinal
    }

    pub const fn channels(&self) -> u16 {
        self.channels
    }

    pub const fn minimum_sample_rate_hz(&self) -> u32 {
        self.minimum_sample_rate_hz
    }

    pub const fn maximum_sample_rate_hz(&self) -> u32 {
        self.maximum_sample_rate_hz
    }

    pub const fn sample_format(&self) -> OutputSampleFormat {
        self.sample_format
    }

    pub const fn buffer_support(&self) -> OutputBufferSupport {
        self.buffer_support
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutputDeviceDescriptor {
    device_ordinal: u16,
    display_name: String,
    f32_configs: Box<[OutputConfigDescriptor]>,
    configs_truncated: bool,
}

impl OutputDeviceDescriptor {
    pub(crate) fn new(
        device_ordinal: u16,
        display_name: String,
        f32_configs: Box<[OutputConfigDescriptor]>,
        configs_truncated: bool,
    ) -> Self {
        Self {
            device_ordinal,
            display_name,
            f32_configs,
            configs_truncated,
        }
    }

    pub const fn device_ordinal(&self) -> u16 {
        self.device_ordinal
    }

    pub fn display_name(&self) -> &str {
        &self.display_name
    }

    pub fn f32_configs(&self) -> &[OutputConfigDescriptor] {
        &self.f32_configs
    }

    pub const fn configs_truncated(&self) -> bool {
        self.configs_truncated
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutputDeviceInventory {
    service_identity: Arc<ServiceIdentity>,
    generation: u64,
    devices: Box<[OutputDeviceDescriptor]>,
    devices_truncated: bool,
}

impl OutputDeviceInventory {
    pub(crate) fn new(
        service_identity: Arc<ServiceIdentity>,
        generation: u64,
        devices: Box<[OutputDeviceDescriptor]>,
        devices_truncated: bool,
    ) -> Self {
        Self {
            service_identity,
            generation,
            devices,
            devices_truncated,
        }
    }

    pub const fn generation(&self) -> u64 {
        self.generation
    }

    pub fn devices(&self) -> &[OutputDeviceDescriptor] {
        &self.devices
    }

    pub const fn devices_truncated(&self) -> bool {
        self.devices_truncated
    }

    /// Creates an exact, native-only selection capability tied to this
    /// inventory's output-service owner.
    pub fn select_exact(
        &self,
        device_ordinal: u16,
        config_ordinal: u16,
        channels: u16,
        sample_rate_hz: u32,
        buffer: OutputBufferSelection,
        warmup_timeout: Duration,
    ) -> Result<ExactOutputSelection, OutputServiceError> {
        if self.generation == 0
            || channels == 0
            || channels > MAXIMUM_OUTPUT_CHANNELS
            || sample_rate_hz == 0
            || matches!(buffer, OutputBufferSelection::Fixed(0))
            || matches!(
                buffer,
                OutputBufferSelection::Fixed(frames)
                    if u64::from(frames) > MAXIMUM_CALLBACK_FRAMES as u64
            )
            || !(MINIMUM_WARMUP_TIMEOUT..=MAXIMUM_WARMUP_TIMEOUT).contains(&warmup_timeout)
        {
            return Err(OutputServiceError::invalid_selection());
        }
        Ok(ExactOutputSelection {
            service_identity: Arc::clone(&self.service_identity),
            inventory_generation: self.generation,
            device_ordinal,
            config_ordinal,
            channels,
            sample_rate_hz,
            buffer,
            warmup_timeout,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExactOutputSelection {
    service_identity: Arc<ServiceIdentity>,
    inventory_generation: u64,
    device_ordinal: u16,
    config_ordinal: u16,
    channels: u16,
    sample_rate_hz: u32,
    buffer: OutputBufferSelection,
    warmup_timeout: Duration,
}

impl ExactOutputSelection {
    pub const fn inventory_generation(&self) -> u64 {
        self.inventory_generation
    }

    pub const fn device_ordinal(&self) -> u16 {
        self.device_ordinal
    }

    pub const fn config_ordinal(&self) -> u16 {
        self.config_ordinal
    }

    pub const fn channels(&self) -> u16 {
        self.channels
    }

    pub const fn sample_rate_hz(&self) -> u32 {
        self.sample_rate_hz
    }

    pub const fn buffer(&self) -> OutputBufferSelection {
        self.buffer
    }

    pub const fn warmup_timeout(&self) -> Duration {
        self.warmup_timeout
    }

    pub(crate) fn belongs_to(&self, identity: &Arc<ServiceIdentity>) -> bool {
        Arc::ptr_eq(&self.service_identity, identity) && self.service_identity.id == identity.id
    }

    #[cfg(test)]
    pub(crate) fn with_inventory_generation_for_test(mut self, generation: u64) -> Self {
        self.inventory_generation = generation;
        self
    }
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) struct ServiceIdentity {
    pub id: u64,
}

/// Native-only proof that one exact silence stream warmed successfully.
///
/// The private service identity deliberately makes this receipt unsuitable for
/// serialization or reconstruction by a caller.
pub struct OutputReservationReceipt {
    pub(crate) service_identity: Arc<ServiceIdentity>,
    reservation_generation: u64,
    selection: ExactOutputSelection,
    callback_count_at_warmup: u32,
}

impl OutputReservationReceipt {
    pub(crate) fn new(
        service_identity: Arc<ServiceIdentity>,
        reservation_generation: u64,
        selection: ExactOutputSelection,
        callback_count_at_warmup: u32,
    ) -> Self {
        Self {
            service_identity,
            reservation_generation,
            selection,
            callback_count_at_warmup,
        }
    }

    pub const fn reservation_generation(&self) -> u64 {
        self.reservation_generation
    }

    pub const fn selection(&self) -> &ExactOutputSelection {
        &self.selection
    }

    pub const fn callback_count_at_warmup(&self) -> u32 {
        self.callback_count_at_warmup
    }
}

impl fmt::Debug for OutputReservationReceipt {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("OutputReservationReceipt")
            .field("reservation_generation", &self.reservation_generation)
            .field("selection", &self.selection)
            .field("callback_count_at_warmup", &self.callback_count_at_warmup)
            .finish_non_exhaustive()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputServicePhase {
    Idle,
    Enumerated,
    ReservedSilence,
    Faulted,
    ShuttingDown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputFaultKind {
    BackendUnavailable,
    EnumerationFailed,
    BackendContractViolation,
    GenerationExhausted,
    StreamBuildFailed,
    StreamPlayFailed,
    WarmupTimeout,
    CallbackFault,
    StreamReleaseFailed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct OutputFault {
    kind: OutputFaultKind,
    occurrence: u64,
}

impl OutputFault {
    pub(crate) const fn new(kind: OutputFaultKind, occurrence: u64) -> Self {
        Self { kind, occurrence }
    }

    pub const fn kind(self) -> OutputFaultKind {
        self.kind
    }

    pub const fn occurrence(self) -> u64 {
        self.occurrence
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutputServiceStatus {
    phase: OutputServicePhase,
    inventory_generation: Option<u64>,
    reservation_generation: Option<u64>,
    callback_count: u32,
    callback_fault_count: u32,
    last_fault: Option<OutputFault>,
}

impl OutputServiceStatus {
    pub(crate) const fn new(
        phase: OutputServicePhase,
        inventory_generation: Option<u64>,
        reservation_generation: Option<u64>,
        callback_count: u32,
        callback_fault_count: u32,
        last_fault: Option<OutputFault>,
    ) -> Self {
        Self {
            phase,
            inventory_generation,
            reservation_generation,
            callback_count,
            callback_fault_count,
            last_fault,
        }
    }

    pub const fn phase(&self) -> OutputServicePhase {
        self.phase
    }

    pub const fn inventory_generation(&self) -> Option<u64> {
        self.inventory_generation
    }

    pub const fn reservation_generation(&self) -> Option<u64> {
        self.reservation_generation
    }

    pub const fn callback_count(&self) -> u32 {
        self.callback_count
    }

    pub const fn callback_fault_count(&self) -> u32 {
        self.callback_fault_count
    }

    pub const fn last_fault(&self) -> Option<OutputFault> {
        self.last_fault
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputServiceErrorCode {
    InvalidSelection,
    QueueFull,
    ServiceUnavailable,
    RequestTimeout,
    AlreadyReserved,
    InventoryMissing,
    StaleInventory,
    SelectionOwnerMismatch,
    ExactConfigMismatch,
    ReceiptMismatch,
    StaleReservation,
    BackendUnavailable,
    EnumerationFailed,
    BackendContractViolation,
    GenerationExhausted,
    StreamBuildFailed,
    StreamPlayFailed,
    WarmupTimeout,
    CallbackFault,
    StreamReleaseFailed,
    ServiceShuttingDown,
    ThreadSpawnFailed,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutputServiceError {
    code: OutputServiceErrorCode,
    public_message: &'static str,
}

impl OutputServiceError {
    pub(crate) const fn new(code: OutputServiceErrorCode, public_message: &'static str) -> Self {
        Self {
            code,
            public_message,
        }
    }

    pub(crate) const fn invalid_selection() -> Self {
        Self::new(
            OutputServiceErrorCode::InvalidSelection,
            "The requested output selection is invalid.",
        )
    }

    pub const fn code(&self) -> OutputServiceErrorCode {
        self.code
    }

    pub const fn public_message(&self) -> &'static str {
        self.public_message
    }
}

impl fmt::Display for OutputServiceError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.public_message)
    }
}

impl Error for OutputServiceError {}
