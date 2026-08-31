//! Platform output reservation for the native PPS Runner.
//!
//! This crate owns CPAL objects on one named thread and can only open a
//! persistent, F32, silence-producing output stream. It deliberately has no
//! experiment-media, arming, Runner-state, Tauri, transport, filesystem, or
//! serialization surface.

mod contract;
mod cpal_backend;
mod service;

pub use contract::{
    ExactOutputSelection, OutputBufferSelection, OutputBufferSupport, OutputConfigDescriptor,
    OutputDeviceDescriptor, OutputDeviceInventory, OutputFault, OutputFaultKind,
    OutputReservationReceipt, OutputSampleFormat, OutputServiceError, OutputServiceErrorCode,
    OutputServicePhase, OutputServiceStatus, MAXIMUM_CALLBACK_FRAMES, MAXIMUM_DEVICE_NAME_BYTES,
    MAXIMUM_F32_CONFIGS_PER_DEVICE, MAXIMUM_OUTPUT_CHANNELS, MAXIMUM_OUTPUT_DEVICES,
    MAXIMUM_WARMUP_TIMEOUT,
};
pub use service::CpalOutputService;
