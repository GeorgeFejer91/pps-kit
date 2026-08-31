use super::{
    ControlResult, OutputFence, PreparedPlaybackPlan, RenderControl, RenderEngine, RenderOutcome,
    RenderState, RtEvent, RtEventSink,
};

/// Deterministic, device-free callback harness.
///
/// Buffer length selects the callback frame count, so tests can exercise
/// arbitrary backend buffer sequences without a device, clock, thread, or
/// asynchronous runtime.
pub struct MockOutput {
    engine: RenderEngine,
}

impl MockOutput {
    pub fn new(plan: PreparedPlaybackPlan) -> Self {
        Self {
            engine: RenderEngine::new(plan),
        }
    }

    pub fn fence(&self) -> &OutputFence {
        self.engine.fence()
    }

    pub const fn state(&self) -> RenderState {
        self.engine.state()
    }

    pub const fn cursor_frames(&self) -> u64 {
        self.engine.cursor_frames()
    }

    pub fn apply_control(&mut self, fence: &OutputFence, control: RenderControl) -> ControlResult {
        self.engine.apply_control(fence, control)
    }

    pub fn callback(
        &mut self,
        output: &mut [f32],
        event_slots: &mut [Option<RtEvent>],
    ) -> RenderOutcome {
        let mut sink = RtEventSink::new(event_slots);
        self.engine.render(output, &mut sink)
    }
}
