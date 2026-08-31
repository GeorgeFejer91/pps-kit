//! Device-independent PPS output planning and rendering.
//!
//! This module is intentionally smaller than a complete output runtime. It
//! proves immutable playback planning, closed channel routing, deterministic
//! callback rendering, generation-fenced control, and fail-closed event
//! backpressure without owning a device or an execution authority.
//!
//! Later slices must provide the persistent platform callback owner, the
//! prepare/reserve/commit handshake, response-marker mixing, timestamp
//! mapping, digital-evidence persistence, and physical route qualification.
//! Successful rendering here is therefore neither executable readiness nor
//! scientific timing evidence.

mod contract;
mod mock;
mod render;

pub use contract::{
    resolve_output_route, OutputFence, OutputGains, OutputPlanError, OutputRouteError,
    OutputRouteRequest, PreparedPlaybackPlan, ResolvedOutputRoute, ResolvedOutputRouteKind,
    RtEventFence, RtScheduledEvent, MAXIMUM_METADATA_EVENTS_PER_CALLBACK,
    MAXIMUM_OUTPUT_CALLBACK_FRAMES, MAXIMUM_RT_EVENTS_PER_CALLBACK,
};
pub use mock::MockOutput;
pub use render::{
    ControlResult, RenderControl, RenderEngine, RenderIntegrityFault, RenderOutcome, RenderState,
    RtEvent, RtEventKind, RtEventSink,
};
