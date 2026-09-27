//! Platform output reservation for the native PPS Runner.
//!
//! This crate owns CPAL objects on one named thread. Output is reserved in
//! silence; native callers can then bind a validated immutable PPS playback
//! plan. Preparing media never starts it. The experiment authority still owns
//! arming, state, response/results, paths, and qualification; none is inferred
//! from an open device or a submitted software frame.

mod contract;
mod cpal_backend;
mod playback;
mod service;

pub use contract::{
    ExactOutputSelection, OutputBufferSelection, OutputBufferSupport, OutputConfigDescriptor,
    OutputDeviceDescriptor, OutputDeviceInventory, OutputFault, OutputFaultKind,
    OutputReservationReceipt, OutputSampleFormat, OutputServiceError, OutputServiceErrorCode,
    OutputServicePhase, OutputServiceStatus, MAXIMUM_CALLBACK_FRAMES, MAXIMUM_DEVICE_NAME_BYTES,
    MAXIMUM_F32_CONFIGS_PER_DEVICE, MAXIMUM_OUTPUT_CHANNELS, MAXIMUM_OUTPUT_DEVICES,
    MAXIMUM_WARMUP_TIMEOUT,
};
pub use playback::{
    NativePlaybackRecord, PlaybackCancellation, PlaybackControlError, PlaybackControlReceipt,
    PlaybackFault, PlaybackRecordKind, PlaybackStatus, PLAYBACK_EVENT_CAPACITY,
};
pub use service::CpalOutputService;
