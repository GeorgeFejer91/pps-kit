use std::{error::Error, fmt};

use crate::{AudioFence, PpsChannelLayout, PreparedPcmBlock};

/// Largest callback accepted by the device-independent renderer.
///
/// 4,096 frames is approximately 92.9 ms at 44.1 kHz and 85.3 ms at 48 kHz,
/// leaving substantial headroom above the validated 256-frame Windows route
/// while keeping callback schedule work statically bounded.
pub const MAXIMUM_OUTPUT_CALLBACK_FRAMES: usize = 4_096;

/// Maximum metadata-derived events in any accepted callback window.
///
/// Two additional slots are reserved for engine-owned `SampleZero` and
/// `FinalFrameSubmitted`, making [`MAXIMUM_RT_EVENTS_PER_CALLBACK`] the exact
/// total callback-event ceiling.
pub const MAXIMUM_METADATA_EVENTS_PER_CALLBACK: usize = 62;

/// Exact maximum number of events one render call may emit.
pub const MAXIMUM_RT_EVENTS_PER_CALLBACK: usize = 64;

/// Complete native identity required to control one prepared playback plan.
///
/// Equality includes the private package fingerprint retained by
/// [`AudioFence`]. The compact callback event projection uses
/// [`RtEventFence`] instead, avoiding reference-count changes on the render
/// path.
#[derive(Clone, PartialEq, Eq)]
pub struct OutputFence {
    audio: AudioFence,
    run_generation: u64,
}

impl fmt::Debug for OutputFence {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("OutputFence")
            .field("audio", &self.audio)
            .field("run_generation", &self.run_generation)
            .finish()
    }
}

impl OutputFence {
    pub fn new(audio: &AudioFence, run_generation: u64) -> Self {
        Self {
            audio: audio.clone(),
            run_generation,
        }
    }

    pub fn audio(&self) -> &AudioFence {
        &self.audio
    }

    pub const fn run_generation(&self) -> u64 {
        self.run_generation
    }

    pub const fn rt_projection(&self) -> RtEventFence {
        RtEventFence {
            package_generation: self.audio.package_generation(),
            run_generation: self.run_generation,
            block_ordinal: self.audio.block_ordinal(),
        }
    }
}

/// Copy-only generation projection attached to callback events.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RtEventFence {
    package_generation: u64,
    run_generation: u64,
    block_ordinal: u32,
}

impl RtEventFence {
    pub const fn package_generation(self) -> u64 {
        self.package_generation
    }

    pub const fn run_generation(self) -> u64 {
        self.run_generation
    }

    pub const fn block_ordinal(self) -> u32 {
        self.block_ordinal
    }
}

/// Compact reference to metadata retained outside a future device callback.
///
/// Events must be supplied in nondecreasing sample order. Equal-sample events
/// retain their input order. `sample_index == media.frames()` is the one valid
/// terminal boundary; indices beyond it are rejected during plan creation.
#[repr(C)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RtScheduledEvent {
    sample_index: u64,
    event_index: u32,
}

impl RtScheduledEvent {
    pub const fn new(event_index: u32, sample_index: u64) -> Self {
        Self {
            sample_index,
            event_index,
        }
    }

    pub const fn event_index(self) -> u32 {
        self.event_index
    }

    pub const fn sample_index(self) -> u64 {
        self.sample_index
    }
}

/// Explicit physical route proposal. Output indices are zero-based.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputRouteRequest {
    LegacyStereo {
        output_channels: u16,
        audio_output: u16,
        tactile_output: u16,
    },
    BinauralTactile {
        output_channels: u16,
        left_output: u16,
        right_output: u16,
        tactile_output: u16,
        tactile_mirror_output: Option<u16>,
    },
}

impl OutputRouteRequest {
    /// Legacy Study 5: source `[tactile, audio]` becomes physical
    /// `[audio, tactile]` on an exact two-channel stream.
    pub const fn legacy_stereo() -> Self {
        Self::LegacyStereo {
            output_channels: 2,
            audio_output: 0,
            tactile_output: 1,
        }
    }

    /// Canonical source `[left, right, tactile]` to outputs 1/2/3.
    pub const fn canonical_three() -> Self {
        Self::BinauralTactile {
            output_channels: 3,
            left_output: 0,
            right_output: 1,
            tactile_output: 2,
            tactile_mirror_output: None,
        }
    }

    /// Canonical source `[left, right, tactile]` to outputs 1/2/3, with the
    /// final scaled tactile sample mirrored to output 4.
    pub const fn canonical_four_with_tactile_mirror() -> Self {
        Self::BinauralTactile {
            output_channels: 4,
            left_output: 0,
            right_output: 1,
            tactile_output: 2,
            tactile_mirror_output: Some(3),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ResolvedOutputRouteKind {
    LegacyStereo,
    CanonicalThree,
    CanonicalFourWithTactileMirror,
}

/// A closed route whose invariants have been checked before rendering.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ResolvedOutputRoute {
    kind: ResolvedOutputRouteKind,
    output_channels: u16,
}

impl ResolvedOutputRoute {
    pub const fn kind(self) -> ResolvedOutputRouteKind {
        self.kind
    }

    pub const fn output_channels(self) -> u16 {
        self.output_channels
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputRouteError {
    SourceLayoutMismatch,
    OutputOutOfRange,
    DuplicateOutput,
    UnsupportedMapping,
}

impl fmt::Display for OutputRouteError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::SourceLayoutMismatch => "the route does not match the prepared source layout",
            Self::OutputOutOfRange => "the route refers to an output outside the stream",
            Self::DuplicateOutput => "the route assigns multiple roles to one physical output",
            Self::UnsupportedMapping => "the output mapping is not supported by this native slice",
        })
    }
}

impl Error for OutputRouteError {}

/// Resolve only the three PPS routes implemented by the pure renderer.
pub fn resolve_output_route(
    layout: PpsChannelLayout,
    request: OutputRouteRequest,
) -> Result<ResolvedOutputRoute, OutputRouteError> {
    match request {
        OutputRouteRequest::LegacyStereo {
            output_channels,
            audio_output,
            tactile_output,
        } => {
            if layout != PpsChannelLayout::LegacyStudy5TactileAudio {
                return Err(OutputRouteError::SourceLayoutMismatch);
            }
            if audio_output >= output_channels || tactile_output >= output_channels {
                return Err(OutputRouteError::OutputOutOfRange);
            }
            if audio_output == tactile_output {
                return Err(OutputRouteError::DuplicateOutput);
            }
            if (output_channels, audio_output, tactile_output) != (2, 0, 1) {
                return Err(OutputRouteError::UnsupportedMapping);
            }
            Ok(ResolvedOutputRoute {
                kind: ResolvedOutputRouteKind::LegacyStereo,
                output_channels,
            })
        }
        OutputRouteRequest::BinauralTactile {
            output_channels,
            left_output,
            right_output,
            tactile_output,
            tactile_mirror_output,
        } => {
            if layout != PpsChannelLayout::BinauralLeftRightTactile {
                return Err(OutputRouteError::SourceLayoutMismatch);
            }
            let mut outputs = [left_output, right_output, tactile_output, u16::MAX];
            let count = if let Some(mirror) = tactile_mirror_output {
                outputs[3] = mirror;
                4
            } else {
                3
            };
            if outputs[..count]
                .iter()
                .any(|output| *output >= output_channels)
            {
                return Err(OutputRouteError::OutputOutOfRange);
            }
            for left in 0..count {
                if outputs[left + 1..count].contains(&outputs[left]) {
                    return Err(OutputRouteError::DuplicateOutput);
                }
            }
            let kind = match (
                output_channels,
                left_output,
                right_output,
                tactile_output,
                tactile_mirror_output,
            ) {
                (3, 0, 1, 2, None) => ResolvedOutputRouteKind::CanonicalThree,
                (4, 0, 1, 2, Some(3)) => ResolvedOutputRouteKind::CanonicalFourWithTactileMirror,
                _ => return Err(OutputRouteError::UnsupportedMapping),
            };
            Ok(ResolvedOutputRoute {
                kind,
                output_channels,
            })
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct OutputGains {
    audio: f32,
    tactile: f32,
}

impl OutputGains {
    pub fn new(audio: f32, tactile: f32) -> Result<Self, OutputPlanError> {
        if !valid_gain(audio) || !valid_gain(tactile) {
            return Err(OutputPlanError::InvalidGain);
        }
        Ok(Self { audio, tactile })
    }

    pub const fn unity() -> Self {
        Self {
            audio: 1.0,
            tactile: 1.0,
        }
    }

    pub const fn audio(self) -> f32 {
        self.audio
    }

    pub const fn tactile(self) -> f32 {
        self.tactile
    }
}

fn valid_gain(value: f32) -> bool {
    value.is_finite() && (0.0..=1.0).contains(&value)
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OutputPlanError {
    Route(OutputRouteError),
    InvalidGain,
    EmptyMedia,
    PreparedMediaShape,
    EventOrder,
    EventBeyondEnd {
        event_index: u32,
        sample_index: u64,
        total_frames: u64,
    },
    EventBurstLimitExceeded {
        sample_index: u64,
        event_count: usize,
        maximum: usize,
    },
    EventDensityLimitExceeded {
        window_start_sample: u64,
        window_end_sample: u64,
        event_count: usize,
        maximum: usize,
    },
}

impl fmt::Display for OutputPlanError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Route(error) => write!(formatter, "invalid output route: {error}"),
            Self::InvalidGain => formatter.write_str("output gains must be finite values from 0 to 1"),
            Self::EmptyMedia => formatter.write_str("prepared playback media must contain at least one frame"),
            Self::PreparedMediaShape => formatter.write_str("prepared playback media has an inconsistent decoded shape"),
            Self::EventOrder => formatter.write_str("real-time events must use nondecreasing sample order"),
            Self::EventBeyondEnd {
                event_index,
                sample_index,
                total_frames,
            } => write!(
                formatter,
                "event {event_index} at sample {sample_index} exceeds the terminal sample {total_frames}"
            ),
            Self::EventBurstLimitExceeded {
                sample_index,
                event_count,
                maximum,
            } => write!(
                formatter,
                "sample {sample_index} has {event_count} metadata events; the callback burst limit is {maximum}"
            ),
            Self::EventDensityLimitExceeded {
                window_start_sample,
                window_end_sample,
                event_count,
                maximum,
            } => write!(
                formatter,
                "samples {window_start_sample} through {window_end_sample} contain {event_count} metadata events; the callback density limit is {maximum}"
            ),
        }
    }
}

impl Error for OutputPlanError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Route(error) => Some(error),
            _ => None,
        }
    }
}

impl From<OutputRouteError> for OutputPlanError {
    fn from(error: OutputRouteError) -> Self {
        Self::Route(error)
    }
}

/// Immutable, native-only playback input for a future persistent callback.
///
/// Construction is the fallible preparation boundary: route, gains, decoded
/// shape, and compact event order are all validated here. Rendering never
/// mutates this plan or allocates derived storage.
///
/// This type deliberately does not implement `Serialize`.
///
/// ```compile_fail
/// fn require_serialize<T: serde::Serialize>() {}
/// require_serialize::<pps_runner_audio::PreparedPlaybackPlan>();
/// ```
pub struct PreparedPlaybackPlan {
    pub(super) fence: OutputFence,
    pub(super) media: PreparedPcmBlock,
    pub(super) route: ResolvedOutputRoute,
    pub(super) gains: OutputGains,
    pub(super) scheduled_events: Box<[RtScheduledEvent]>,
}

impl fmt::Debug for PreparedPlaybackPlan {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("PreparedPlaybackPlan")
            .field("fence", &self.fence)
            .field("layout", &self.media.layout())
            .field("sample_rate_hz", &self.media.sample_rate_hz())
            .field("source_channels", &self.media.channels())
            .field("frames", &self.media.frames())
            .field("route", &self.route)
            .field("gains", &self.gains)
            .field("scheduled_event_count", &self.scheduled_events.len())
            .finish()
    }
}

impl PreparedPlaybackPlan {
    pub fn new(
        media: PreparedPcmBlock,
        run_generation: u64,
        route_request: OutputRouteRequest,
        gains: OutputGains,
        scheduled_events: Box<[RtScheduledEvent]>,
    ) -> Result<Self, OutputPlanError> {
        if media.frames() == 0 {
            return Err(OutputPlanError::EmptyMedia);
        }
        let expected_samples = media
            .frames()
            .checked_mul(u64::from(media.channels()))
            .and_then(|samples| usize::try_from(samples).ok())
            .ok_or(OutputPlanError::PreparedMediaShape)?;
        if expected_samples != media.interleaved_f32().len() {
            return Err(OutputPlanError::PreparedMediaShape);
        }
        let route = resolve_output_route(media.layout(), route_request)?;
        let mut prior_sample = None;
        for event in &scheduled_events {
            if prior_sample.is_some_and(|prior| event.sample_index() < prior) {
                return Err(OutputPlanError::EventOrder);
            }
            if event.sample_index() > media.frames() {
                return Err(OutputPlanError::EventBeyondEnd {
                    event_index: event.event_index(),
                    sample_index: event.sample_index(),
                    total_frames: media.frames(),
                });
            }
            prior_sample = Some(event.sample_index());
        }
        validate_event_bursts(&scheduled_events)?;
        validate_event_density(&scheduled_events)?;
        let fence = OutputFence::new(media.fence(), run_generation);
        Ok(Self {
            fence,
            media,
            route,
            gains,
            scheduled_events,
        })
    }

    pub fn fence(&self) -> &OutputFence {
        &self.fence
    }

    pub fn media(&self) -> &PreparedPcmBlock {
        &self.media
    }

    pub const fn route(&self) -> ResolvedOutputRoute {
        self.route
    }

    pub const fn gains(&self) -> OutputGains {
        self.gains
    }

    pub fn scheduled_events(&self) -> &[RtScheduledEvent] {
        &self.scheduled_events
    }
}

fn validate_event_bursts(events: &[RtScheduledEvent]) -> Result<(), OutputPlanError> {
    let mut start = 0;
    while start < events.len() {
        let sample_index = events[start].sample_index();
        let mut end = start + 1;
        while end < events.len() && events[end].sample_index() == sample_index {
            end += 1;
        }
        let event_count = end - start;
        if event_count > MAXIMUM_METADATA_EVENTS_PER_CALLBACK {
            return Err(OutputPlanError::EventBurstLimitExceeded {
                sample_index,
                event_count,
                maximum: MAXIMUM_METADATA_EVENTS_PER_CALLBACK,
            });
        }
        start = end;
    }
    Ok(())
}

fn validate_event_density(events: &[RtScheduledEvent]) -> Result<(), OutputPlanError> {
    let maximum_span = MAXIMUM_OUTPUT_CALLBACK_FRAMES as u64;
    let mut start = 0;
    for end in 0..events.len() {
        while events[end]
            .sample_index()
            .saturating_sub(events[start].sample_index())
            > maximum_span
        {
            start += 1;
        }
        let event_count = end - start + 1;
        if event_count > MAXIMUM_METADATA_EVENTS_PER_CALLBACK {
            return Err(OutputPlanError::EventDensityLimitExceeded {
                window_start_sample: events[start].sample_index(),
                window_end_sample: events[end].sample_index(),
                event_count,
                maximum: MAXIMUM_METADATA_EVENTS_PER_CALLBACK,
            });
        }
    }
    Ok(())
}
