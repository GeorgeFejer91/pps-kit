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
    PlaybackFault, PlaybackPort, PlaybackRecordKind, PlaybackStatus, PLAYBACK_EVENT_CAPACITY,
};
pub use service::CpalOutputService;

/// Device-free access to the production callback, available only to explicit
/// test builds. These observations never establish physical timing.
#[cfg(feature = "test-support")]
pub mod test_support {
    use crate::{
        playback::{PlaybackCallback, PlaybackOwner},
        PlaybackPort,
    };
    use pps_runner_audio::PreparedPlaybackPlan;
    use std::{sync::Arc, time::Instant};

    pub struct SoftwarePlayback {
        _owner: PlaybackOwner,
        callback: PlaybackCallback,
    }
    impl SoftwarePlayback {
        pub fn new(plan: Arc<PreparedPlaybackPlan>) -> (Self, PlaybackPort) {
            let (mut owner, callback) = PlaybackOwner::new(plan);
            let fence = owner.fence().clone();
            let port = owner
                .take_port(&fence)
                .expect("new software callback has one port");
            (
                Self {
                    _owner: owner,
                    callback,
                },
                port,
            )
        }
        pub fn render(&mut self, output: &mut [f32], observed: Instant) -> bool {
            self.callback.render(output, observed, None)
        }
        pub fn status(&self) -> crate::PlaybackStatus {
            self._owner.status()
        }
    }
}
