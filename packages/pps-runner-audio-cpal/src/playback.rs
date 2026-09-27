//! Bounded native control/evidence handoff around the existing PPS renderer.
//! No path, Tauri, transport, JSON, or experiment policy is owned here.

use std::sync::{
    atomic::{AtomicBool, AtomicU64, AtomicU8, Ordering},
    Arc,
};
use std::time::Instant;

use pps_runner_audio::{
    ControlResult, OutputFence, PreparedPlaybackPlan, RenderControl, RenderEngine, RenderOutcome,
    RenderState, RtEvent, RtEventFence, RtEventSink, MAXIMUM_RT_EVENTS_PER_CALLBACK,
};
use rtrb::{Consumer, Producer, RingBuffer};

pub const PLAYBACK_EVENT_CAPACITY: usize = 4_096;
const RECORDS_PER_CALLBACK: usize = MAXIMUM_RT_EVENTS_PER_CALLBACK + 3;
const STOP: u64 = 1;
const ABORT: u64 = 2;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlaybackFault {
    EvidenceQueueFull,
    RendererIntegrity,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PlaybackControlError {
    StaleFence,
    Busy,
    SequenceExhausted,
    CallbackUnavailable,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PlaybackControlReceipt {
    pub sequence: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct PlaybackStatus {
    pub state: RenderState,
    pub submitted_frames: u64,
    pub callbacks: u64,
    pub last_control_sequence: u64,
    pub fault: Option<PlaybackFault>,
    pub callback_retired: bool,
}

#[derive(Debug, Clone, Copy)]
pub enum PlaybackRecordKind {
    Boundary(RtEvent),
    Control {
        sequence: u64,
        requested: RenderControl,
        result: ControlResult,
        state: RenderState,
    },
    Render(RenderOutcome),
}

/// CPAL timestamps are retained in their own clock domain. Playback time is
/// a driver's prediction, not a measured physical audio/tactile onset.
#[derive(Debug, Clone, Copy)]
pub struct NativePlaybackRecord {
    pub fence: RtEventFence,
    pub host_received: Instant,
    pub device_timestamp: Option<cpal::OutputStreamTimestamp>,
    pub kind: PlaybackRecordKind,
}

struct Signals {
    abort: AtomicBool,
    safety_control: AtomicU64,
    state: AtomicU8,
    frames: AtomicU64,
    callbacks: AtomicU64,
    applied_control: AtomicU64,
    fault: AtomicU8,
    retired: AtomicBool,
}

impl Signals {
    fn new() -> Self {
        Self {
            abort: AtomicBool::new(false),
            safety_control: AtomicU64::new(0),
            state: AtomicU8::new(0),
            frames: AtomicU64::new(0),
            callbacks: AtomicU64::new(0),
            applied_control: AtomicU64::new(0),
            fault: AtomicU8::new(0),
            retired: AtomicBool::new(false),
        }
    }
}

/// Irreversible cancellation for a single immutable playback fence. A new
/// playback needs a new callback, so an old invalidator cannot affect it.
#[derive(Clone)]
pub struct PlaybackCancellation(Arc<Signals>);

impl PlaybackCancellation {
    pub fn abort(&self) {
        self.0.abort.store(true, Ordering::Release);
    }
}

#[derive(Clone, Copy)]
struct Control {
    sequence: u64,
    action: RenderControl,
}

/// Owned exclusively by the non-real-time CPAL owner. It must outlive the
/// callback: plan and ring storage are retired here after stream quiescence.
pub(crate) struct PlaybackOwner {
    plan: Arc<PreparedPlaybackPlan>,
    controls: Producer<Control>,
    events: Consumer<NativePlaybackRecord>,
    signals: Arc<Signals>,
    next_sequence: u64,
}

impl PlaybackOwner {
    pub(crate) fn new(plan: Arc<PreparedPlaybackPlan>) -> (Self, PlaybackCallback) {
        Self::with_capacity(plan, PLAYBACK_EVENT_CAPACITY)
    }

    fn with_capacity(plan: Arc<PreparedPlaybackPlan>, capacity: usize) -> (Self, PlaybackCallback) {
        let (commands, control_rx) = RingBuffer::new(1);
        let (events, event_rx) = RingBuffer::new(capacity);
        let signals = Arc::new(Signals::new());
        let callback = PlaybackCallback {
            engine: RenderEngine::from_shared_plan(Arc::clone(&plan)),
            plan: Arc::clone(&plan),
            controls: control_rx,
            events,
            slots: [None; MAXIMUM_RT_EVENTS_PER_CALLBACK],
            signals: Arc::clone(&signals),
            _lifetime: CallbackLifetime(Arc::clone(&signals)),
        };
        (
            Self {
                plan,
                controls: commands,
                events: event_rx,
                signals,
                next_sequence: 1,
            },
            callback,
        )
    }

    pub(crate) fn fence(&self) -> &OutputFence {
        self.plan.fence()
    }

    pub(crate) fn cancellation(&self) -> PlaybackCancellation {
        PlaybackCancellation(Arc::clone(&self.signals))
    }

    pub(crate) fn control(
        &mut self,
        fence: &OutputFence,
        action: RenderControl,
    ) -> Result<PlaybackControlReceipt, PlaybackControlError> {
        if fence != self.fence() {
            return Err(PlaybackControlError::StaleFence);
        }
        if self.signals.retired.load(Ordering::Acquire) {
            return Err(PlaybackControlError::CallbackUnavailable);
        }
        if self.next_sequence > u64::MAX >> 3 {
            return Err(PlaybackControlError::SequenceExhausted);
        }
        let sequence = self.next_sequence;
        match action {
            RenderControl::Stop | RenderControl::Abort => {
                if action == RenderControl::Abort {
                    self.signals.abort.store(true, Ordering::Release);
                }
                let kind = if action == RenderControl::Abort {
                    ABORT
                } else {
                    STOP
                };
                self.signals
                    .safety_control
                    .store((sequence << 3) | kind, Ordering::Release);
            }
            _ => self
                .controls
                .push(Control { sequence, action })
                .map_err(|_| PlaybackControlError::Busy)?,
        }
        self.next_sequence += 1;
        Ok(PlaybackControlReceipt { sequence })
    }

    pub(crate) fn status(&self) -> PlaybackStatus {
        PlaybackStatus {
            state: decode_state(self.signals.state.load(Ordering::Acquire)),
            submitted_frames: self.signals.frames.load(Ordering::Acquire),
            callbacks: self.signals.callbacks.load(Ordering::Acquire),
            last_control_sequence: self.signals.applied_control.load(Ordering::Acquire),
            fault: match self.signals.fault.load(Ordering::Acquire) {
                0 => None,
                1 => Some(PlaybackFault::EvidenceQueueFull),
                _ => Some(PlaybackFault::RendererIntegrity),
            },
            callback_retired: self.signals.retired.load(Ordering::Acquire),
        }
    }

    pub(crate) fn drain(&mut self, maximum: usize) -> Vec<NativePlaybackRecord> {
        let mut records = Vec::with_capacity(maximum.min(PLAYBACK_EVENT_CAPACITY));
        for _ in 0..maximum.min(PLAYBACK_EVENT_CAPACITY) {
            match self.events.pop() {
                Ok(record) => records.push(record),
                Err(_) => break,
            }
        }
        records
    }
}

// Declared last in PlaybackCallback, so its release fence follows destruction
// of the engine and both callback queue endpoints.
struct CallbackLifetime(Arc<Signals>);
impl Drop for CallbackLifetime {
    fn drop(&mut self) {
        self.0.retired.store(true, Ordering::Release);
    }
}

pub(crate) struct PlaybackCallback {
    engine: RenderEngine,
    plan: Arc<PreparedPlaybackPlan>,
    controls: Consumer<Control>,
    events: Producer<NativePlaybackRecord>,
    slots: [Option<RtEvent>; MAXIMUM_RT_EVENTS_PER_CALLBACK],
    signals: Arc<Signals>,
    _lifetime: CallbackLifetime,
}

impl PlaybackCallback {
    /// No allocation, lock, formatting, filesystem, or frontend call occurs
    /// here. Worst-case record capacity is admitted before any source sample.
    pub(crate) fn render(
        &mut self,
        output: &mut [f32],
        host_received: Instant,
        device_timestamp: Option<cpal::OutputStreamTimestamp>,
    ) -> bool {
        output.fill(0.0);
        if self.signals.fault.load(Ordering::Acquire) != 0 {
            return true;
        }
        if self.events.slots() < RECORDS_PER_CALLBACK {
            self.signals.fault.store(1, Ordering::Release);
            self.engine
                .apply_control(self.plan.fence(), RenderControl::Abort);
            self.signals
                .state
                .store(encode_state(self.engine.state()), Ordering::Release);
            return true;
        }
        let previous_state = self.engine.state();
        if let Ok(command) = self.controls.pop() {
            self.apply_control(command, host_received, device_timestamp);
        }
        let safety = self.signals.safety_control.swap(0, Ordering::AcqRel);
        if safety != 0 {
            self.apply_control(
                Control {
                    sequence: safety >> 3,
                    action: if safety & 7 == ABORT {
                        RenderControl::Abort
                    } else {
                        RenderControl::Stop
                    },
                },
                host_received,
                device_timestamp,
            );
        }
        if self.signals.abort.load(Ordering::Acquire) {
            self.engine
                .apply_control(self.plan.fence(), RenderControl::Abort);
        }
        let mut sink = RtEventSink::new(&mut self.slots);
        let outcome = self.engine.render(output, &mut sink);
        let fence = self.plan.fence().rt_projection();
        for event in sink.events().iter().flatten() {
            // One producer, admitted maximum, and a consumer can only free
            // slots: this push cannot fail after the capacity check above.
            let _ = self.events.push(NativePlaybackRecord {
                fence,
                host_received,
                device_timestamp,
                kind: PlaybackRecordKind::Boundary(*event),
            });
        }
        // Idle silence does not consume evidence slots while an operator is
        // choosing or pausing a run. Active submission and state changes do.
        if previous_state == RenderState::Playing
            || outcome.state != previous_state
            || outcome.fault.is_some()
        {
            let _ = self.events.push(NativePlaybackRecord {
                fence,
                host_received,
                device_timestamp,
                kind: PlaybackRecordKind::Render(outcome),
            });
        }
        self.signals
            .frames
            .store(outcome.cursor_frames, Ordering::Release);
        self.signals.callbacks.store(
            outcome.callback_sequence.saturating_add(1),
            Ordering::Release,
        );
        self.signals
            .state
            .store(encode_state(outcome.state), Ordering::Release);
        if outcome.fault.is_some() {
            self.signals.fault.store(2, Ordering::Release);
        }
        outcome.fault.is_some()
    }

    fn apply_control(
        &mut self,
        command: Control,
        host_received: Instant,
        device_timestamp: Option<cpal::OutputStreamTimestamp>,
    ) {
        let result = self.engine.apply_control(self.plan.fence(), command.action);
        self.signals
            .applied_control
            .store(command.sequence, Ordering::Release);
        let _ = self.events.push(NativePlaybackRecord {
            fence: self.plan.fence().rt_projection(),
            host_received,
            device_timestamp,
            kind: PlaybackRecordKind::Control {
                sequence: command.sequence,
                requested: command.action,
                result,
                state: self.engine.state(),
            },
        });
    }
}

const fn encode_state(state: RenderState) -> u8 {
    match state {
        RenderState::Prepared => 0,
        RenderState::Playing => 1,
        RenderState::Paused => 2,
        RenderState::SourceExhausted => 3,
        RenderState::Stopped => 4,
        RenderState::Aborted => 5,
        RenderState::Faulted => 6,
    }
}

const fn decode_state(state: u8) -> RenderState {
    match state {
        0 => RenderState::Prepared,
        1 => RenderState::Playing,
        2 => RenderState::Paused,
        3 => RenderState::SourceExhausted,
        4 => RenderState::Stopped,
        5 => RenderState::Aborted,
        _ => RenderState::Faulted,
    }
}

#[cfg(test)]
pub(crate) mod tests;
