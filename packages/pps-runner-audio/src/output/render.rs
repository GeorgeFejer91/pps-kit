use super::{
    OutputFence, PreparedPlaybackPlan, ResolvedOutputRouteKind, RtEventFence, RtScheduledEvent,
    MAXIMUM_METADATA_EVENTS_PER_CALLBACK, MAXIMUM_OUTPUT_CALLBACK_FRAMES,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RenderControl {
    Start,
    Pause,
    Resume,
    Stop,
    Abort,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ControlResult {
    Applied,
    NoChange,
    Stale,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RenderState {
    Prepared,
    Playing,
    Paused,
    /// Every source frame has been copied into callback buffers.
    ///
    /// This does not mean that a platform device drained or physically
    /// presented those frames.
    SourceExhausted,
    Stopped,
    Aborted,
    Faulted,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RenderIntegrityFault {
    OutputBufferShape,
    CallbackFrameLimitExceeded { observed: usize, maximum: usize },
    PreparedMediaInvariant,
    PreparedEventDensityInvariant,
    CallbackSequenceExhausted,
    EventSinkOverflow { required: usize, available: usize },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RtEventKind {
    /// The authoritative callback-placement boundary for canonical audio-zero
    /// evidence. A prepared schedule's metadata `audio_sample_zero` anchor is
    /// validated but must not also be projected as a `Scheduled` event.
    SampleZero,
    Scheduled {
        event_index: u32,
    },
    /// The final source frame was copied into this callback buffer.
    ///
    /// This is a software submission boundary, not device drain, DAC onset,
    /// physical audio arrival, or tactile onset.
    FinalFrameSubmitted,
}

/// Fixed callback record. String/JSON metadata is resolved by a non-real-time
/// owner using `event_index` after this record leaves the render path.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RtEvent {
    fence: RtEventFence,
    kind: RtEventKind,
    callback_sequence: u64,
    sample_index: u64,
    sample_offset_in_callback: u64,
}

impl RtEvent {
    pub const fn fence(self) -> RtEventFence {
        self.fence
    }

    pub const fn kind(self) -> RtEventKind {
        self.kind
    }

    pub const fn callback_sequence(self) -> u64 {
        self.callback_sequence
    }

    pub const fn sample_index(self) -> u64 {
        self.sample_index
    }

    pub const fn sample_offset_in_callback(self) -> u64 {
        self.sample_offset_in_callback
    }
}

/// Caller-owned, fixed-capacity callback event storage.
///
/// Construction resets the logical length without clearing unused slots. Only
/// the prefix returned by [`Self::events`] belongs to the current callback.
pub struct RtEventSink<'a> {
    slots: &'a mut [Option<RtEvent>],
    len: usize,
}

impl<'a> RtEventSink<'a> {
    pub fn new(slots: &'a mut [Option<RtEvent>]) -> Self {
        Self { slots, len: 0 }
    }

    pub const fn len(&self) -> usize {
        self.len
    }

    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    pub fn capacity(&self) -> usize {
        self.slots.len()
    }

    pub fn remaining(&self) -> usize {
        self.capacity() - self.len
    }

    pub fn events(&self) -> &[Option<RtEvent>] {
        &self.slots[..self.len]
    }

    fn push(&mut self, event: RtEvent) -> bool {
        let Some(slot) = self.slots.get_mut(self.len) else {
            return false;
        };
        *slot = Some(event);
        self.len += 1;
        true
    }

    fn clear_current_callback(&mut self) {
        for slot in &mut self.slots[..self.len] {
            *slot = None;
        }
        self.len = 0;
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RenderOutcome {
    pub state: RenderState,
    pub callback_sequence: u64,
    pub cursor_frames: u64,
    pub requested_frames: usize,
    pub rendered_source_frames: usize,
    pub events_written: usize,
    pub fault: Option<RenderIntegrityFault>,
}

/// Persistent device-independent callback state.
///
/// `render` performs no allocation, deallocation, locking, I/O, logging, JSON
/// work, or formatting. The caller owns both output and event storage.
///
/// The engine owns an immutable plan containing heap-backed PCM and event
/// storage. A future platform output owner must quiesce the callback, move the
/// engine away from that callback, and drop it on the non-real-time owner
/// thread so reference-count or allocation teardown never runs in the callback.
pub struct RenderEngine {
    plan: PreparedPlaybackPlan,
    state: RenderState,
    fault: Option<RenderIntegrityFault>,
    cursor_frames: u64,
    event_cursor: usize,
    callback_sequence: u64,
    sample_zero_emitted: bool,
    final_frame_submitted: bool,
}

impl RenderEngine {
    pub fn new(plan: PreparedPlaybackPlan) -> Self {
        Self {
            plan,
            state: RenderState::Prepared,
            fault: None,
            cursor_frames: 0,
            event_cursor: 0,
            callback_sequence: 0,
            sample_zero_emitted: false,
            final_frame_submitted: false,
        }
    }

    pub fn fence(&self) -> &OutputFence {
        self.plan.fence()
    }

    pub const fn state(&self) -> RenderState {
        self.state
    }

    pub const fn fault(&self) -> Option<RenderIntegrityFault> {
        self.fault
    }

    pub const fn cursor_frames(&self) -> u64 {
        self.cursor_frames
    }

    #[cfg(test)]
    fn set_callback_sequence_for_test(&mut self, callback_sequence: u64) {
        self.callback_sequence = callback_sequence;
    }

    pub fn apply_control(&mut self, fence: &OutputFence, control: RenderControl) -> ControlResult {
        if fence != self.plan.fence() {
            return ControlResult::Stale;
        }
        let next = match (self.state, control) {
            (RenderState::Prepared, RenderControl::Start) => Some(RenderState::Playing),
            (RenderState::Playing, RenderControl::Pause) => Some(RenderState::Paused),
            (RenderState::Paused, RenderControl::Resume) => Some(RenderState::Playing),
            (
                RenderState::Prepared | RenderState::Playing | RenderState::Paused,
                RenderControl::Stop,
            ) => Some(RenderState::Stopped),
            (
                RenderState::Prepared | RenderState::Playing | RenderState::Paused,
                RenderControl::Abort,
            ) => Some(RenderState::Aborted),
            _ => None,
        };
        if let Some(next) = next {
            self.state = next;
            ControlResult::Applied
        } else {
            ControlResult::NoChange
        }
    }

    pub fn render(&mut self, output: &mut [f32], events: &mut RtEventSink<'_>) -> RenderOutcome {
        output.fill(0.0);
        let callback_sequence = self.callback_sequence;
        let Some(next_sequence) = self.callback_sequence.checked_add(1) else {
            return self.fail(
                output,
                events,
                callback_sequence,
                0,
                RenderIntegrityFault::CallbackSequenceExhausted,
            );
        };
        self.callback_sequence = next_sequence;

        let output_channels = usize::from(self.plan.route.output_channels());
        if output_channels == 0 || !output.len().is_multiple_of(output_channels) {
            return self.fail(
                output,
                events,
                callback_sequence,
                0,
                RenderIntegrityFault::OutputBufferShape,
            );
        }
        let requested_frames = output.len() / output_channels;
        if requested_frames > MAXIMUM_OUTPUT_CALLBACK_FRAMES {
            return self.fail(
                output,
                events,
                callback_sequence,
                requested_frames,
                RenderIntegrityFault::CallbackFrameLimitExceeded {
                    observed: requested_frames,
                    maximum: MAXIMUM_OUTPUT_CALLBACK_FRAMES,
                },
            );
        }
        if self.state != RenderState::Playing || requested_frames == 0 {
            return self.outcome(callback_sequence, requested_frames, 0, events.len());
        }

        let remaining = self.plan.media.frames().saturating_sub(self.cursor_frames);
        let rendered_frames_u64 = remaining.min(requested_frames as u64);
        let Ok(rendered_frames) = usize::try_from(rendered_frames_u64) else {
            return self.fail(
                output,
                events,
                callback_sequence,
                requested_frames,
                RenderIntegrityFault::PreparedMediaInvariant,
            );
        };
        if rendered_frames == 0 {
            self.state = RenderState::SourceExhausted;
            return self.outcome(callback_sequence, requested_frames, 0, events.len());
        }

        let buffer_start = self.cursor_frames;
        let Some(buffer_end) = buffer_start.checked_add(rendered_frames_u64) else {
            return self.fail(
                output,
                events,
                callback_sequence,
                requested_frames,
                RenderIntegrityFault::PreparedMediaInvariant,
            );
        };
        let terminal = buffer_end == self.plan.media.frames();
        let Ok(due_end) = due_event_end(
            &self.plan.scheduled_events,
            self.event_cursor,
            buffer_end,
            terminal,
            self.plan.media.frames(),
        ) else {
            return self.fail(
                output,
                events,
                callback_sequence,
                requested_frames,
                RenderIntegrityFault::PreparedEventDensityInvariant,
            );
        };
        let sample_zero_count = usize::from(!self.sample_zero_emitted);
        let final_frame_count = usize::from(terminal && !self.final_frame_submitted);
        let required_events =
            sample_zero_count + due_end.saturating_sub(self.event_cursor) + final_frame_count;
        if required_events > events.remaining() {
            return self.fail(
                output,
                events,
                callback_sequence,
                requested_frames,
                RenderIntegrityFault::EventSinkOverflow {
                    required: required_events,
                    available: events.remaining(),
                },
            );
        }

        if !self.render_samples(output, rendered_frames, output_channels) {
            return self.fail(
                output,
                events,
                callback_sequence,
                requested_frames,
                RenderIntegrityFault::PreparedMediaInvariant,
            );
        }

        let event_fence = self.plan.fence.rt_projection();
        if !self.sample_zero_emitted {
            let pushed = events.push(RtEvent {
                fence: event_fence,
                kind: RtEventKind::SampleZero,
                callback_sequence,
                sample_index: 0,
                sample_offset_in_callback: 0,
            });
            if !pushed {
                return self.fail(
                    output,
                    events,
                    callback_sequence,
                    requested_frames,
                    RenderIntegrityFault::EventSinkOverflow {
                        required: required_events,
                        available: events.remaining(),
                    },
                );
            }
            self.sample_zero_emitted = true;
        }
        for event in &self.plan.scheduled_events[self.event_cursor..due_end] {
            let pushed = events.push(scheduled_record(
                event_fence,
                callback_sequence,
                buffer_start,
                *event,
            ));
            if !pushed {
                return self.fail(
                    output,
                    events,
                    callback_sequence,
                    requested_frames,
                    RenderIntegrityFault::EventSinkOverflow {
                        required: required_events,
                        available: events.remaining(),
                    },
                );
            }
        }
        if terminal && !self.final_frame_submitted {
            let pushed = events.push(RtEvent {
                fence: event_fence,
                kind: RtEventKind::FinalFrameSubmitted,
                callback_sequence,
                sample_index: self.plan.media.frames(),
                sample_offset_in_callback: rendered_frames_u64,
            });
            if !pushed {
                return self.fail(
                    output,
                    events,
                    callback_sequence,
                    requested_frames,
                    RenderIntegrityFault::EventSinkOverflow {
                        required: required_events,
                        available: events.remaining(),
                    },
                );
            }
            self.final_frame_submitted = true;
        }
        self.event_cursor = due_end;
        self.cursor_frames = buffer_end;
        if terminal {
            self.state = RenderState::SourceExhausted;
        }
        self.outcome(
            callback_sequence,
            requested_frames,
            rendered_frames,
            events.len(),
        )
    }

    fn render_samples(
        &self,
        output: &mut [f32],
        rendered_frames: usize,
        output_channels: usize,
    ) -> bool {
        let source_channels = usize::from(self.plan.media.channels());
        let Some(source_frame_start) = usize::try_from(self.cursor_frames).ok() else {
            return false;
        };
        let Some(source_start) = source_frame_start.checked_mul(source_channels) else {
            return false;
        };
        let Some(source_samples) = rendered_frames.checked_mul(source_channels) else {
            return false;
        };
        let Some(source_end) = source_start.checked_add(source_samples) else {
            return false;
        };
        let Some(source) = self
            .plan
            .media
            .interleaved_f32()
            .get(source_start..source_end)
        else {
            return false;
        };

        let audio_gain = self.plan.gains.audio();
        let tactile_gain = self.plan.gains.tactile();
        match self.plan.route.kind() {
            ResolvedOutputRouteKind::LegacyStereo => {
                if source_channels != 2 || output_channels != 2 {
                    return false;
                }
                for frame in 0..rendered_frames {
                    let source_offset = frame * 2;
                    let output_offset = frame * 2;
                    output[output_offset] = clamp(source[source_offset + 1] * audio_gain);
                    output[output_offset + 1] = clamp(source[source_offset] * tactile_gain);
                }
            }
            ResolvedOutputRouteKind::CanonicalThree => {
                if source_channels != 3 || output_channels != 3 {
                    return false;
                }
                for frame in 0..rendered_frames {
                    let source_offset = frame * 3;
                    let output_offset = frame * 3;
                    output[output_offset] = clamp(source[source_offset] * audio_gain);
                    output[output_offset + 1] = clamp(source[source_offset + 1] * audio_gain);
                    output[output_offset + 2] = clamp(source[source_offset + 2] * tactile_gain);
                }
            }
            ResolvedOutputRouteKind::CanonicalFourWithTactileMirror => {
                if source_channels != 3 || output_channels != 4 {
                    return false;
                }
                for frame in 0..rendered_frames {
                    let source_offset = frame * 3;
                    let output_offset = frame * 4;
                    output[output_offset] = clamp(source[source_offset] * audio_gain);
                    output[output_offset + 1] = clamp(source[source_offset + 1] * audio_gain);
                    let tactile = clamp(source[source_offset + 2] * tactile_gain);
                    output[output_offset + 2] = tactile;
                    output[output_offset + 3] = tactile;
                }
            }
        }
        true
    }

    fn fail(
        &mut self,
        output: &mut [f32],
        events: &mut RtEventSink<'_>,
        callback_sequence: u64,
        requested_frames: usize,
        fault: RenderIntegrityFault,
    ) -> RenderOutcome {
        output.fill(0.0);
        events.clear_current_callback();
        self.state = RenderState::Faulted;
        self.fault = Some(fault);
        self.outcome(callback_sequence, requested_frames, 0, events.len())
    }

    fn outcome(
        &self,
        callback_sequence: u64,
        requested_frames: usize,
        rendered_source_frames: usize,
        events_written: usize,
    ) -> RenderOutcome {
        RenderOutcome {
            state: self.state,
            callback_sequence,
            cursor_frames: self.cursor_frames,
            requested_frames,
            rendered_source_frames,
            events_written,
            fault: self.fault,
        }
    }
}

fn due_event_end(
    events: &[RtScheduledEvent],
    start: usize,
    buffer_end: u64,
    terminal: bool,
    total_frames: u64,
) -> Result<usize, ()> {
    let mut end = start;
    let maximum_end = start
        .saturating_add(MAXIMUM_METADATA_EVENTS_PER_CALLBACK)
        .min(events.len());
    while end < maximum_end {
        let event = &events[end];
        let due =
            event.sample_index() < buffer_end || (terminal && event.sample_index() == total_frames);
        if !due {
            break;
        }
        end += 1;
    }
    if let Some(event) = events.get(end) {
        let still_due =
            event.sample_index() < buffer_end || (terminal && event.sample_index() == total_frames);
        if still_due {
            return Err(());
        }
    }
    Ok(end)
}

fn scheduled_record(
    fence: RtEventFence,
    callback_sequence: u64,
    buffer_start: u64,
    event: RtScheduledEvent,
) -> RtEvent {
    RtEvent {
        fence,
        kind: RtEventKind::Scheduled {
            event_index: event.event_index(),
        },
        callback_sequence,
        sample_index: event.sample_index(),
        sample_offset_in_callback: event.sample_index().saturating_sub(buffer_start),
    }
}

fn clamp(sample: f32) -> f32 {
    sample.clamp(-1.0, 1.0)
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use crate::{
        AudioFence, OutputGains, OutputRouteRequest, PpsChannelLayout, PreparedMediaIdentity,
        PreparedPcmBlock, PreparedPlaybackPlan,
    };

    use super::*;

    fn one_frame_plan() -> PreparedPlaybackPlan {
        let media = PreparedPcmBlock {
            fence: AudioFence::new(1, "a".repeat(64), 7),
            identity: PreparedMediaIdentity {
                sha256: Arc::from("b".repeat(64)),
                encoded_byte_count: 48,
            },
            layout: PpsChannelLayout::LegacyStudy5TactileAudio,
            sample_rate_hz: 48_000,
            channels: 2,
            frames: 1,
            interleaved_f32: Arc::new(vec![0.25, 0.5]),
        };
        PreparedPlaybackPlan::new(
            media,
            2,
            OutputRouteRequest::legacy_stereo(),
            OutputGains::unity(),
            Box::new([]),
        )
        .expect("the unit-test fixture must be a valid plan")
    }

    #[test]
    fn callback_sequence_exhaustion_latches_silence_without_rendering() {
        let mut engine = RenderEngine::new(one_frame_plan());
        let fence = engine.fence().clone();
        assert_eq!(
            engine.apply_control(&fence, RenderControl::Start),
            ControlResult::Applied
        );
        engine.set_callback_sequence_for_test(u64::MAX);

        let mut output = [7.0; 2];
        let mut slots = [None; 2];
        let mut sink = RtEventSink::new(&mut slots);
        let outcome = engine.render(&mut output, &mut sink);

        assert_eq!(outcome.state, RenderState::Faulted);
        assert_eq!(
            outcome.fault,
            Some(RenderIntegrityFault::CallbackSequenceExhausted)
        );
        assert_eq!(outcome.callback_sequence, u64::MAX);
        assert_eq!(outcome.cursor_frames, 0);
        assert_eq!(outcome.events_written, 0);
        assert_eq!(output, [0.0; 2]);
    }
}
