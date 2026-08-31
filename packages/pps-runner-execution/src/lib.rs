//! Deterministic, platform-neutral execution primitives for PPS runners.
//!
//! This crate compiles V1 block CSV manifests into sample-indexed events and
//! provides a bounded append-only in-memory ledger. It owns no Tauri, network,
//! audio, wall-clock, or persistence adapter. Native targets inject observed
//! timestamps and retain responsibility for media I/O and durable file writes.

mod encoded;
mod error;
mod ledger;
mod schedule;

pub use error::{ExecutionError, ExecutionErrorCode};
pub use ledger::{
    EventLedger, EventLedgerSummary, ExecutionEventRecord, LedgerEventInput,
    DEFAULT_LEDGER_CAPACITY, MAX_LEDGER_CAPACITY, MAX_LEDGER_ENCODED_BYTES, MAX_LEDGER_JSON_DEPTH,
    MAX_LEDGER_JSON_NODES, MAX_LEDGER_PAYLOAD_BYTES,
};
pub use schedule::{
    compile_block_schedule, compile_verified_block_schedule, BlockEventSchedule,
    BlockScheduleOptions, BlockScheduleSummary, ScheduledBlockEvent, MAX_BLOCK_MANIFEST_BYTES,
    MAX_BLOCK_METADATA_BYTES, MAX_BLOCK_METADATA_FIELDS, MAX_BLOCK_ROWS,
    MAX_NATIVE_PATH_PAYLOAD_BYTES, MAX_SCHEDULE_ENCODED_BYTES, MAX_SCHEDULE_EVENTS,
};

/// Largest integer that can cross a JSON/JavaScript boundary without losing
/// precision. Schedule samples and serialized clock values stay within it.
pub const JSON_MAX_SAFE_INTEGER: i64 = 9_007_199_254_740_991;
