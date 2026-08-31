use std::{
    collections::{HashMap, VecDeque},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex, TryLockError,
    },
    time::Instant,
};

use pps_contracts::JSON_MAX_SAFE_INTEGER;
use serde::Serialize;

pub(crate) const DEFAULT_TRACE_CAPACITY: usize = 512;
const STAGE_COUNT: usize = 10;
#[cfg(test)]
const DEFAULT_MAILBOX_CAPACITY: usize = 64;
#[cfg(test)]
const DEFAULT_ORDINARY_MAILBOX_LIMIT: usize = 56;

/// Native ingress classes are intentionally transport-level facts, not peer
/// identities. A route never contains a room, owner, participant, or command
/// identifier.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
pub(crate) enum LatencyRoute {
    #[serde(rename = "local-tauri")]
    LocalTauri,
    #[serde(rename = "lan-websocket")]
    LanWebSocket,
    #[serde(rename = "webview-vdo")]
    WebViewVdo,
    #[serde(rename = "unknown")]
    Unknown,
}

impl LatencyRoute {
    const ALL: [Self; 4] = [
        Self::LocalTauri,
        Self::LanWebSocket,
        Self::WebViewVdo,
        Self::Unknown,
    ];
}

/// Cumulative observation points measured from `NativeIngress` in one native
/// process monotonic clock. Missing points are omitted from that stage's
/// percentile population rather than inferred across another clock domain.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize)]
#[serde(rename_all = "kebab-case")]
pub(crate) enum LatencyStage {
    NativeIngress,
    AdapterValidationComplete,
    AuthorityAdmission,
    AuthorityDequeue,
    AuthorityAuthorizationComplete,
    ReducerValidationComplete,
    ReducerApplied,
    ReplyReady,
    AdapterHandoff,
    SendCompleted,
}

impl LatencyStage {
    const ALL: [Self; STAGE_COUNT] = [
        Self::NativeIngress,
        Self::AdapterValidationComplete,
        Self::AuthorityAdmission,
        Self::AuthorityDequeue,
        Self::AuthorityAuthorizationComplete,
        Self::ReducerValidationComplete,
        Self::ReducerApplied,
        Self::ReplyReady,
        Self::AdapterHandoff,
        Self::SendCompleted,
    ];

    pub(crate) const fn index(self) -> usize {
        match self {
            Self::NativeIngress => 0,
            Self::AdapterValidationComplete => 1,
            Self::AuthorityAdmission => 2,
            Self::AuthorityDequeue => 3,
            Self::AuthorityAuthorizationComplete => 4,
            Self::ReducerValidationComplete => 5,
            Self::ReducerApplied => 6,
            Self::ReplyReady => 7,
            Self::AdapterHandoff => 8,
            Self::SendCompleted => 9,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum TraceOutcome {
    Applied,
    Rejected,
    Failed,
    Interrupted,
}

/// A raw point in the diagnostics clock captured before frame parsing. It is
/// process-local, non-serializable, and can later seed a command trace without
/// forcing non-command BRSP traffic into the command population.
#[derive(Debug, Clone, Copy)]
pub(crate) struct NativeIngress {
    monotonic_ns: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LatencyPercentiles {
    pub sample_count: u64,
    pub p50_us: u64,
    pub p95_us: u64,
    pub p99_us: u64,
    pub worst_us: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct AuthorityMailboxDepthPercentiles {
    pub sample_count: u64,
    pub p50: u64,
    pub p95: u64,
    pub p99: u64,
    pub worst: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct AuthorityMailboxClassSummary {
    pub latest_observed_depth: u64,
    pub high_water_mark: u64,
    pub successful_admission_count: u64,
    pub queue_full_reject_count: u64,
    pub depth_after_successful_admission: AuthorityMailboxDepthPercentiles,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct AuthorityMailboxSummary {
    pub measurement: &'static str,
    pub total_capacity: u64,
    pub ordinary_admission_limit: u64,
    pub reserved_safety_slots: u64,
    pub ordinary: AuthorityMailboxClassSummary,
    pub safety: AuthorityMailboxClassSummary,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LatencyStageSummary {
    pub stage: LatencyStage,
    pub elapsed_from_native_ingress: LatencyPercentiles,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LatencyRouteSummary {
    pub route: LatencyRoute,
    pub count: u64,
    pub authority_queue_wait: LatencyPercentiles,
    pub stages: Vec<LatencyStageSummary>,
}

/// The only serializable diagnostics surface. It contains aggregate integer
/// microseconds and fixed vocabulary; individual traces never cross IPC.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct NativeLatencySummary {
    pub schema: &'static str,
    pub clock_domain: &'static str,
    pub measurement: &'static str,
    pub authority_queue_wait_measurement: &'static str,
    pub count: u64,
    pub dropped_count: u64,
    pub dropped_stage_update_count: u64,
    pub interrupted_count: u64,
    pub unfinished_count: u64,
    pub authority_mailbox: AuthorityMailboxSummary,
    pub routes: Vec<LatencyRouteSummary>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
struct TraceId(u64);

#[derive(Debug, Clone)]
struct TraceRecord {
    route: LatencyRoute,
    stages_ns: [Option<u64>; STAGE_COUNT],
    outcome: Option<TraceOutcome>,
}

impl TraceRecord {
    fn new(route: LatencyRoute, ingress_ns: u64) -> Self {
        let mut stages_ns = [None; STAGE_COUNT];
        stages_ns[LatencyStage::NativeIngress.index()] = Some(ingress_ns);
        Self {
            route,
            stages_ns,
            outcome: None,
        }
    }

    fn mark(&mut self, stage: LatencyStage, now_ns: u64) {
        let slot = &mut self.stages_ns[stage.index()];
        if slot.is_none() {
            *slot = Some(now_ns);
        }
    }

    fn elapsed_us(&self, stage: LatencyStage) -> Option<u64> {
        let ingress = self.stages_ns[LatencyStage::NativeIngress.index()]?;
        let observed = self.stages_ns[stage.index()]?;
        Some(observed.saturating_sub(ingress) / 1_000)
    }

    fn authority_queue_wait_us(&self) -> Option<u64> {
        let admitted = self.stages_ns[LatencyStage::AuthorityAdmission.index()]?;
        let dequeued = self.stages_ns[LatencyStage::AuthorityDequeue.index()]?;
        Some(dequeued.checked_sub(admitted)? / 1_000)
    }
}

struct AuthorityMailboxClassDiagnostics {
    queue_full_rejects: AtomicU64,
    depth_histogram: Box<[AtomicU64]>,
}

impl AuthorityMailboxClassDiagnostics {
    fn new(maximum_depth: usize) -> Self {
        Self {
            queue_full_rejects: AtomicU64::new(0),
            depth_histogram: (0..=maximum_depth)
                .map(|_| AtomicU64::new(0))
                .collect::<Vec<_>>()
                .into_boxed_slice(),
        }
    }

    fn record_successful_admission(&self, depth: usize) {
        let bounded_depth = depth.min(self.depth_histogram.len().saturating_sub(1));
        saturating_atomic_increment(&self.depth_histogram[bounded_depth]);
    }

    fn record_queue_full_reject(&self) {
        saturating_atomic_increment(&self.queue_full_rejects);
    }

    fn summary(&self, latest_observed_depth: usize) -> AuthorityMailboxClassSummary {
        let depth_after_successful_admission = summarize_depth_histogram(&self.depth_histogram);
        AuthorityMailboxClassSummary {
            latest_observed_depth: clamp_json_u64(latest_observed_depth),
            high_water_mark: depth_after_successful_admission.worst,
            successful_admission_count: depth_after_successful_admission.sample_count,
            queue_full_reject_count: self
                .queue_full_rejects
                .load(Ordering::Relaxed)
                .min(JSON_MAX_SAFE_INTEGER),
            depth_after_successful_admission,
        }
    }
}

struct AuthorityMailboxDiagnosticsInner {
    total_capacity: usize,
    ordinary_admission_limit: usize,
    latest_observed_depths: AtomicU64,
    ordinary: AuthorityMailboxClassDiagnostics,
    safety: AuthorityMailboxClassDiagnostics,
}

/// Bounded, atomic-only mailbox pressure evidence. The authority mailbox feeds
/// it already-derived counts while holding its own semantic lock; diagnostics
/// never acquire that lock and cannot accept or reject work.
#[derive(Clone)]
pub(crate) struct AuthorityMailboxDiagnostics(Arc<AuthorityMailboxDiagnosticsInner>);

impl AuthorityMailboxDiagnostics {
    fn new(total_capacity: usize, ordinary_admission_limit: usize) -> Self {
        let total_capacity = total_capacity.max(1);
        let ordinary_admission_limit = ordinary_admission_limit.min(total_capacity);
        Self(Arc::new(AuthorityMailboxDiagnosticsInner {
            total_capacity,
            ordinary_admission_limit,
            latest_observed_depths: AtomicU64::new(0),
            ordinary: AuthorityMailboxClassDiagnostics::new(ordinary_admission_limit),
            safety: AuthorityMailboxClassDiagnostics::new(total_capacity),
        }))
    }

    pub(crate) fn record_successful_admission(
        &self,
        safety: bool,
        ordinary_depth: usize,
        safety_depth: usize,
    ) {
        if safety {
            self.0.safety.record_successful_admission(safety_depth);
        } else {
            self.0.ordinary.record_successful_admission(ordinary_depth);
        }
        self.store_latest_observed_depths(ordinary_depth, safety_depth);
    }

    pub(crate) fn record_queue_full_reject(&self, safety: bool) {
        if safety {
            self.0.safety.record_queue_full_reject();
        } else {
            self.0.ordinary.record_queue_full_reject();
        }
    }

    pub(crate) fn record_latest_depths(&self, ordinary_depth: usize, safety_depth: usize) {
        self.store_latest_observed_depths(ordinary_depth, safety_depth);
    }

    fn store_latest_observed_depths(&self, ordinary_depth: usize, safety_depth: usize) {
        self.0
            .latest_observed_depths
            .store(pack_depths(ordinary_depth, safety_depth), Ordering::Release);
    }

    fn summary(&self) -> AuthorityMailboxSummary {
        let (ordinary_depth, safety_depth) =
            unpack_depths(self.0.latest_observed_depths.load(Ordering::Acquire));
        AuthorityMailboxSummary {
            measurement: "per-class-depth-after-successful-admission",
            total_capacity: clamp_json_u64(self.0.total_capacity),
            ordinary_admission_limit: clamp_json_u64(self.0.ordinary_admission_limit),
            reserved_safety_slots: clamp_json_u64(
                self.0
                    .total_capacity
                    .saturating_sub(self.0.ordinary_admission_limit),
            ),
            ordinary: self.0.ordinary.summary(ordinary_depth),
            safety: self.0.safety.summary(safety_depth),
        }
    }
}

struct TraceStore {
    capacity: usize,
    order: VecDeque<TraceId>,
    records: HashMap<TraceId, TraceRecord>,
    evicted: u64,
}

impl TraceStore {
    fn new(capacity: usize) -> Self {
        Self {
            capacity: capacity.max(1),
            order: VecDeque::with_capacity(capacity.max(1)),
            records: HashMap::with_capacity(capacity.max(1)),
            evicted: 0,
        }
    }

    fn insert(&mut self, id: TraceId, record: TraceRecord) {
        if self.records.len() == self.capacity {
            if let Some(oldest) = self.order.pop_front() {
                self.records.remove(&oldest);
                self.evicted = self.evicted.saturating_add(1);
            }
        }
        self.order.push_back(id);
        self.records.insert(id, record);
    }
}

struct NativeLatencyInner {
    started: Instant,
    next_trace: AtomicU64,
    dropped_traces: AtomicU64,
    dropped_stage_updates: AtomicU64,
    authority_mailbox: AuthorityMailboxDiagnostics,
    store: Mutex<TraceStore>,
}

/// Best-effort local diagnostics. Authority paths use `try_lock` exclusively:
/// contention or poisoning loses diagnostics instead of delaying or changing
/// a Runner transition.
#[derive(Clone)]
pub(crate) struct NativeLatencyDiagnostics(Arc<NativeLatencyInner>);

impl NativeLatencyDiagnostics {
    #[cfg(test)]
    pub(crate) fn new() -> Self {
        Self::with_capacity_and_mailbox_limits(
            DEFAULT_TRACE_CAPACITY,
            DEFAULT_MAILBOX_CAPACITY,
            DEFAULT_ORDINARY_MAILBOX_LIMIT,
        )
    }

    #[cfg(test)]
    fn with_capacity(capacity: usize) -> Self {
        Self::with_capacity_and_mailbox_limits(
            capacity,
            DEFAULT_MAILBOX_CAPACITY,
            DEFAULT_ORDINARY_MAILBOX_LIMIT,
        )
    }

    pub(crate) fn with_mailbox_limits(
        total_capacity: usize,
        ordinary_admission_limit: usize,
    ) -> Self {
        Self::with_capacity_and_mailbox_limits(
            DEFAULT_TRACE_CAPACITY,
            total_capacity,
            ordinary_admission_limit,
        )
    }

    fn with_capacity_and_mailbox_limits(
        capacity: usize,
        total_capacity: usize,
        ordinary_admission_limit: usize,
    ) -> Self {
        Self(Arc::new(NativeLatencyInner {
            started: Instant::now(),
            next_trace: AtomicU64::new(1),
            dropped_traces: AtomicU64::new(0),
            dropped_stage_updates: AtomicU64::new(0),
            authority_mailbox: AuthorityMailboxDiagnostics::new(
                total_capacity,
                ordinary_admission_limit,
            ),
            store: Mutex::new(TraceStore::new(capacity)),
        }))
    }

    pub(crate) fn authority_mailbox(&self) -> AuthorityMailboxDiagnostics {
        self.0.authority_mailbox.clone()
    }

    pub(crate) fn start_trace(&self, route: LatencyRoute) -> LatencyTraceGuard {
        self.start_trace_from(route, self.capture_ingress())
    }

    pub(crate) fn capture_ingress(&self) -> NativeIngress {
        NativeIngress {
            monotonic_ns: self.now_ns(),
        }
    }

    pub(crate) fn start_trace_from(
        &self,
        route: LatencyRoute,
        ingress: NativeIngress,
    ) -> LatencyTraceGuard {
        let Some(id) = self.next_trace_id() else {
            saturating_atomic_increment(&self.0.dropped_traces);
            return LatencyTraceGuard {
                trace: LatencyTrace {
                    diagnostics: self.clone(),
                    id: None,
                },
                finished: false,
            };
        };
        let active = match self.0.store.try_lock() {
            Ok(mut store) => {
                store.insert(id, TraceRecord::new(route, ingress.monotonic_ns));
                true
            }
            Err(TryLockError::WouldBlock | TryLockError::Poisoned(_)) => {
                saturating_atomic_increment(&self.0.dropped_traces);
                false
            }
        };
        LatencyTraceGuard {
            trace: LatencyTrace {
                diagnostics: self.clone(),
                id: active.then_some(id),
            },
            finished: false,
        }
    }

    pub(crate) fn summary(&self) -> NativeLatencySummary {
        let dropped_traces = self.0.dropped_traces.load(Ordering::Relaxed);
        let dropped_stage_updates = self.0.dropped_stage_updates.load(Ordering::Relaxed);
        let store = self
            .0
            .store
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let records = store.records.values().cloned().collect::<Vec<_>>();
        let dropped_count = store.evicted.saturating_add(dropped_traces);
        drop(store);
        summarize_records(
            &records,
            dropped_count,
            dropped_stage_updates,
            self.0.authority_mailbox.summary(),
        )
    }

    fn now_ns(&self) -> u64 {
        u64::try_from(self.0.started.elapsed().as_nanos()).unwrap_or(u64::MAX)
    }

    fn next_trace_id(&self) -> Option<TraceId> {
        self.0
            .next_trace
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |value| {
                value.checked_add(1)
            })
            .ok()
            .map(TraceId)
    }

    fn note_dropped_stage_update(&self) {
        saturating_atomic_increment(&self.0.dropped_stage_updates);
    }

    fn update(&self, id: TraceId, operation: impl FnOnce(&mut TraceRecord)) {
        match self.0.store.try_lock() {
            Ok(mut store) => {
                if let Some(record) = store.records.get_mut(&id) {
                    operation(record);
                }
            }
            Err(TryLockError::WouldBlock | TryLockError::Poisoned(_)) => {
                self.note_dropped_stage_update();
            }
        }
    }

    #[cfg(test)]
    fn start_at(&self, route: LatencyRoute, now_ns: u64) -> LatencyTraceGuard {
        let id = self
            .next_trace_id()
            .expect("test diagnostics trace identifiers remain available");
        let mut store = self
            .0
            .store
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        store.insert(id, TraceRecord::new(route, now_ns));
        drop(store);
        LatencyTraceGuard {
            trace: LatencyTrace {
                diagnostics: self.clone(),
                id: Some(id),
            },
            finished: false,
        }
    }

    #[cfg(test)]
    pub(crate) fn while_store_locked_for_test<R>(&self, operation: impl FnOnce() -> R) -> R {
        let _guard = self
            .0
            .store
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        operation()
    }
}

#[derive(Clone)]
pub(crate) struct LatencyTrace {
    diagnostics: NativeLatencyDiagnostics,
    id: Option<TraceId>,
}

impl LatencyTrace {
    pub(crate) fn mark(&self, stage: LatencyStage) {
        let Some(id) = self.id else {
            return;
        };
        let now_ns = self.diagnostics.now_ns();
        self.diagnostics
            .update(id, |record| record.mark(stage, now_ns));
    }

    #[cfg(test)]
    fn mark_at(&self, stage: LatencyStage, now_ns: u64) {
        let Some(id) = self.id else {
            return;
        };
        self.diagnostics
            .update(id, |record| record.mark(stage, now_ns));
    }

    fn finish(&self, outcome: TraceOutcome) {
        let Some(id) = self.id else {
            return;
        };
        self.diagnostics.update(id, |record| {
            if record.outcome.is_none() {
                record.outcome = Some(outcome);
            }
        });
    }
}

pub(crate) struct LatencyTraceGuard {
    trace: LatencyTrace,
    finished: bool,
}

impl LatencyTraceGuard {
    pub(crate) fn trace(&self) -> LatencyTrace {
        self.trace.clone()
    }

    pub(crate) fn mark(&self, stage: LatencyStage) {
        self.trace.mark(stage);
    }

    pub(crate) fn finish(&mut self, outcome: TraceOutcome) {
        if !self.finished {
            self.trace.finish(outcome);
            self.finished = true;
        }
    }

    #[cfg(test)]
    fn mark_at(&self, stage: LatencyStage, now_ns: u64) {
        self.trace.mark_at(stage, now_ns);
    }
}

impl Drop for LatencyTraceGuard {
    fn drop(&mut self) {
        if !self.finished {
            self.trace.finish(TraceOutcome::Interrupted);
            self.finished = true;
        }
    }
}

fn summarize_records(
    records: &[TraceRecord],
    dropped_count: u64,
    dropped_stage_update_count: u64,
    authority_mailbox: AuthorityMailboxSummary,
) -> NativeLatencySummary {
    let count = clamp_json_u64(
        records
            .iter()
            .filter(|record| {
                record
                    .outcome
                    .is_some_and(|outcome| outcome != TraceOutcome::Interrupted)
            })
            .count(),
    );
    let interrupted_count = clamp_json_u64(
        records
            .iter()
            .filter(|record| record.outcome == Some(TraceOutcome::Interrupted))
            .count(),
    );
    let unfinished_count = clamp_json_u64(
        records
            .iter()
            .filter(|record| record.outcome.is_none())
            .count(),
    );
    let routes = LatencyRoute::ALL
        .into_iter()
        .map(|route| {
            let route_records = records
                .iter()
                .filter(|record| {
                    record.route == route
                        && record
                            .outcome
                            .is_some_and(|outcome| outcome != TraceOutcome::Interrupted)
                })
                .collect::<Vec<_>>();
            let stages = LatencyStage::ALL
                .into_iter()
                .map(|stage| {
                    let samples = route_records
                        .iter()
                        .filter_map(|record| record.elapsed_us(stage))
                        .collect::<Vec<_>>();
                    LatencyStageSummary {
                        stage,
                        elapsed_from_native_ingress: summarize_samples(samples),
                    }
                })
                .collect();
            let authority_queue_wait = summarize_samples(
                route_records
                    .iter()
                    .filter_map(|record| record.authority_queue_wait_us())
                    .collect(),
            );
            LatencyRouteSummary {
                route,
                count: clamp_json_u64(route_records.len()),
                authority_queue_wait,
                stages,
            }
        })
        .collect();
    NativeLatencySummary {
        schema: "pps-runner-native-latency-summary.v2",
        clock_domain: "one-process-monotonic",
        measurement: "cumulative-from-native-ingress",
        authority_queue_wait_measurement: "same-trace-authority-dequeue-minus-admission",
        count,
        dropped_count: dropped_count.min(JSON_MAX_SAFE_INTEGER),
        dropped_stage_update_count: dropped_stage_update_count.min(JSON_MAX_SAFE_INTEGER),
        interrupted_count,
        unfinished_count,
        authority_mailbox,
        routes,
    }
}

fn summarize_samples(mut samples: Vec<u64>) -> LatencyPercentiles {
    samples.sort_unstable();
    let sample_count = samples.len();
    LatencyPercentiles {
        sample_count: clamp_json_u64(sample_count),
        p50_us: nearest_rank(&samples, 50).min(JSON_MAX_SAFE_INTEGER),
        p95_us: nearest_rank(&samples, 95).min(JSON_MAX_SAFE_INTEGER),
        p99_us: nearest_rank(&samples, 99).min(JSON_MAX_SAFE_INTEGER),
        worst_us: samples
            .last()
            .copied()
            .unwrap_or_default()
            .min(JSON_MAX_SAFE_INTEGER),
    }
}

fn nearest_rank(sorted: &[u64], percentile: usize) -> u64 {
    if sorted.is_empty() {
        return 0;
    }
    let rank = percentile.saturating_mul(sorted.len()).saturating_add(99) / 100;
    sorted[rank.saturating_sub(1).min(sorted.len() - 1)]
}

fn summarize_depth_histogram(histogram: &[AtomicU64]) -> AuthorityMailboxDepthPercentiles {
    let counts = histogram
        .iter()
        .map(|count| count.load(Ordering::Relaxed))
        .collect::<Vec<_>>();
    let sample_count = counts
        .iter()
        .fold(0_u64, |total, count| total.saturating_add(*count));
    AuthorityMailboxDepthPercentiles {
        sample_count: sample_count.min(JSON_MAX_SAFE_INTEGER),
        p50: histogram_nearest_rank(&counts, sample_count, 50),
        p95: histogram_nearest_rank(&counts, sample_count, 95),
        p99: histogram_nearest_rank(&counts, sample_count, 99),
        worst: counts
            .iter()
            .rposition(|count| *count != 0)
            .map(clamp_json_u64)
            .unwrap_or_default(),
    }
}

fn histogram_nearest_rank(counts: &[u64], sample_count: u64, percentile: u64) -> u64 {
    if sample_count == 0 {
        return 0;
    }
    let rank = u64::try_from((u128::from(sample_count) * u128::from(percentile)).div_ceil(100))
        .unwrap_or(u64::MAX);
    let mut cumulative = 0_u64;
    for (depth, count) in counts.iter().enumerate() {
        cumulative = cumulative.saturating_add(*count);
        if cumulative >= rank {
            return clamp_json_u64(depth);
        }
    }
    clamp_json_u64(counts.len().saturating_sub(1))
}

fn saturating_atomic_increment(counter: &AtomicU64) {
    let _ = counter.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |value| {
        Some(value.saturating_add(1))
    });
}

fn pack_depths(ordinary_depth: usize, safety_depth: usize) -> u64 {
    let ordinary = u32::try_from(ordinary_depth).unwrap_or(u32::MAX);
    let safety = u32::try_from(safety_depth).unwrap_or(u32::MAX);
    (u64::from(ordinary) << 32) | u64::from(safety)
}

fn unpack_depths(packed: u64) -> (usize, usize) {
    let ordinary = usize::try_from(packed >> 32).unwrap_or(usize::MAX);
    let safety = usize::try_from(packed & u64::from(u32::MAX)).unwrap_or(usize::MAX);
    (ordinary, safety)
}

fn clamp_json_u64(value: usize) -> u64 {
    u64::try_from(value)
        .unwrap_or(u64::MAX)
        .min(JSON_MAX_SAFE_INTEGER)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn percentile_math_uses_nearest_rank_and_reports_worst_separately() {
        let summary = summarize_samples(vec![1, 2, 3, 4, 100]);
        assert_eq!(summary.sample_count, 5);
        assert_eq!(summary.p50_us, 3);
        assert_eq!(summary.p95_us, 100);
        assert_eq!(summary.p99_us, 100);
        assert_eq!(summary.worst_us, 100);
        assert_eq!(summarize_samples(Vec::new()).worst_us, 0);
    }

    #[test]
    fn bounded_store_accounts_for_eviction_and_unfinished_traces() {
        let diagnostics = NativeLatencyDiagnostics::with_capacity(2);
        for offset in 0..3 {
            let mut trace = diagnostics.start_at(LatencyRoute::LocalTauri, offset * 1_000);
            trace.mark_at(LatencyStage::AdapterHandoff, offset * 1_000 + 500);
            trace.finish(TraceOutcome::Applied);
        }
        let _unfinished = diagnostics.start_at(LatencyRoute::Unknown, 10_000);
        let summary = diagnostics.summary();
        assert_eq!(summary.count, 1);
        assert_eq!(summary.unfinished_count, 1);
        assert_eq!(summary.dropped_count, 2);
    }

    #[test]
    fn route_populations_and_cumulative_stage_samples_remain_separate() {
        let diagnostics = NativeLatencyDiagnostics::with_capacity(8);
        let mut local = diagnostics.start_at(LatencyRoute::LocalTauri, 10_000);
        local.mark_at(LatencyStage::ReplyReady, 13_000);
        local.finish(TraceOutcome::Applied);
        let mut lan = diagnostics.start_at(LatencyRoute::LanWebSocket, 20_000);
        lan.mark_at(LatencyStage::ReplyReady, 29_000);
        lan.finish(TraceOutcome::Rejected);

        let summary = diagnostics.summary();
        let local = summary
            .routes
            .iter()
            .find(|route| route.route == LatencyRoute::LocalTauri)
            .unwrap();
        let lan = summary
            .routes
            .iter()
            .find(|route| route.route == LatencyRoute::LanWebSocket)
            .unwrap();
        assert_eq!(local.count, 1);
        assert_eq!(lan.count, 1);
        assert_eq!(
            local.stages[LatencyStage::ReplyReady.index()]
                .elapsed_from_native_ingress
                .p50_us,
            3
        );
        assert_eq!(
            lan.stages[LatencyStage::ReplyReady.index()]
                .elapsed_from_native_ingress
                .p50_us,
            9
        );
    }

    #[test]
    fn authority_queue_wait_uses_each_completed_trace_and_omits_incomplete_pairs() {
        let diagnostics = NativeLatencyDiagnostics::with_capacity(8);
        let mut first = diagnostics.start_at(LatencyRoute::LocalTauri, 0);
        first.mark_at(LatencyStage::AuthorityAdmission, 10_000);
        first.mark_at(LatencyStage::AuthorityDequeue, 12_000);
        first.finish(TraceOutcome::Applied);

        let mut second = diagnostics.start_at(LatencyRoute::LocalTauri, 0);
        second.mark_at(LatencyStage::AuthorityAdmission, 100_000);
        second.mark_at(LatencyStage::AuthorityDequeue, 101_000);
        second.finish(TraceOutcome::Rejected);

        let mut missing_dequeue = diagnostics.start_at(LatencyRoute::LocalTauri, 0);
        missing_dequeue.mark_at(LatencyStage::AuthorityAdmission, 200_000);
        missing_dequeue.finish(TraceOutcome::Failed);

        let mut inverted_pair = diagnostics.start_at(LatencyRoute::LocalTauri, 0);
        inverted_pair.mark_at(LatencyStage::AuthorityAdmission, 250_000);
        inverted_pair.mark_at(LatencyStage::AuthorityDequeue, 249_000);
        inverted_pair.finish(TraceOutcome::Failed);

        {
            let interrupted = diagnostics.start_at(LatencyRoute::LocalTauri, 0);
            interrupted.mark_at(LatencyStage::AuthorityAdmission, 300_000);
            interrupted.mark_at(LatencyStage::AuthorityDequeue, 900_000);
        }
        let unfinished = diagnostics.start_at(LatencyRoute::LocalTauri, 0);
        unfinished.mark_at(LatencyStage::AuthorityAdmission, 400_000);
        unfinished.mark_at(LatencyStage::AuthorityDequeue, 1_000_000);

        let summary = diagnostics.summary();
        let local = summary
            .routes
            .iter()
            .find(|route| route.route == LatencyRoute::LocalTauri)
            .unwrap();
        assert_eq!(local.count, 4);
        assert_eq!(local.authority_queue_wait.sample_count, 2);
        assert_eq!(local.authority_queue_wait.p50_us, 1);
        assert_eq!(local.authority_queue_wait.p95_us, 2);
        assert_eq!(local.authority_queue_wait.p99_us, 2);
        assert_eq!(local.authority_queue_wait.worst_us, 2);
        assert_eq!(summary.interrupted_count, 1);
        assert_eq!(summary.unfinished_count, 1);
        drop(unfinished);
    }

    #[test]
    fn bounded_mailbox_histograms_report_per_class_depth_percentiles() {
        let diagnostics = NativeLatencyDiagnostics::with_capacity_and_mailbox_limits(4, 4, 3);
        let mailbox = diagnostics.authority_mailbox();
        mailbox.record_successful_admission(false, 1, 0);
        mailbox.record_successful_admission(false, 2, 0);
        mailbox.record_successful_admission(false, 3, 0);
        mailbox.record_successful_admission(true, 3, 1);
        mailbox.record_successful_admission(true, 3, 2);
        mailbox.record_queue_full_reject(false);
        mailbox.record_queue_full_reject(true);
        mailbox.record_latest_depths(2, 1);

        let summary = diagnostics.summary().authority_mailbox;
        assert_eq!(summary.total_capacity, 4);
        assert_eq!(summary.ordinary_admission_limit, 3);
        assert_eq!(summary.reserved_safety_slots, 1);
        assert_eq!(summary.ordinary.latest_observed_depth, 2);
        assert_eq!(summary.ordinary.high_water_mark, 3);
        assert_eq!(summary.ordinary.successful_admission_count, 3);
        assert_eq!(summary.ordinary.queue_full_reject_count, 1);
        assert_eq!(
            summary.ordinary.depth_after_successful_admission,
            AuthorityMailboxDepthPercentiles {
                sample_count: 3,
                p50: 2,
                p95: 3,
                p99: 3,
                worst: 3,
            }
        );
        assert_eq!(summary.safety.latest_observed_depth, 1);
        assert_eq!(summary.safety.high_water_mark, 2);
        assert_eq!(summary.safety.successful_admission_count, 2);
        assert_eq!(summary.safety.queue_full_reject_count, 1);
        assert_eq!(summary.safety.depth_after_successful_admission.p50, 1);
        assert_eq!(summary.safety.depth_after_successful_admission.p95, 2);
        for class in [&summary.ordinary, &summary.safety] {
            assert_eq!(
                class.successful_admission_count,
                class.depth_after_successful_admission.sample_count
            );
            assert_eq!(
                class.high_water_mark,
                class.depth_after_successful_admission.worst
            );
        }
    }

    #[test]
    fn diagnostic_counters_saturate_instead_of_wrapping() {
        let diagnostics = NativeLatencyDiagnostics::with_capacity_and_mailbox_limits(2, 2, 1);
        let mailbox = diagnostics.authority_mailbox();
        mailbox
            .0
            .ordinary
            .queue_full_rejects
            .store(u64::MAX, Ordering::Relaxed);
        mailbox.0.ordinary.depth_histogram[1].store(u64::MAX, Ordering::Relaxed);
        mailbox.record_successful_admission(false, 1, 0);
        mailbox.record_queue_full_reject(false);
        assert_eq!(
            mailbox
                .0
                .ordinary
                .queue_full_rejects
                .load(Ordering::Relaxed),
            u64::MAX
        );
        assert_eq!(
            mailbox.0.ordinary.depth_histogram[1].load(Ordering::Relaxed),
            u64::MAX
        );
        let saturated = mailbox.summary().ordinary;
        assert_eq!(saturated.successful_admission_count, JSON_MAX_SAFE_INTEGER);
        assert_eq!(
            saturated.successful_admission_count,
            saturated.depth_after_successful_admission.sample_count
        );
        assert_eq!(saturated.high_water_mark, 1);
        assert_eq!(
            saturated.high_water_mark,
            saturated.depth_after_successful_admission.worst
        );
        assert_eq!(saturated.queue_full_reject_count, JSON_MAX_SAFE_INTEGER);

        diagnostics
            .0
            .dropped_stage_updates
            .store(u64::MAX, Ordering::Relaxed);
        diagnostics.note_dropped_stage_update();
        assert_eq!(
            diagnostics.0.dropped_stage_updates.load(Ordering::Relaxed),
            u64::MAX
        );
    }

    #[test]
    fn exhausted_trace_identifier_never_wraps_or_reuses_an_identifier() {
        let diagnostics = NativeLatencyDiagnostics::with_capacity(2);
        diagnostics.0.next_trace.store(u64::MAX, Ordering::Relaxed);
        let mut trace = diagnostics.start_trace(LatencyRoute::LocalTauri);
        trace.finish(TraceOutcome::Failed);

        assert_eq!(diagnostics.0.next_trace.load(Ordering::Relaxed), u64::MAX);
        let summary = diagnostics.summary();
        assert_eq!(summary.count, 0);
        assert_eq!(summary.dropped_count, 1);
    }

    #[test]
    fn serialized_summary_contains_aggregates_but_no_trace_or_private_payload() {
        let diagnostics = NativeLatencyDiagnostics::with_capacity(4);
        let mut trace = diagnostics.start_at(LatencyRoute::WebViewVdo, 1_000);
        trace.mark_at(LatencyStage::AdapterHandoff, 7_000);
        trace.finish(TraceOutcome::Failed);
        let encoded = serde_json::to_string(&diagnostics.summary()).unwrap();
        assert!(encoded.contains("pps-runner-native-latency-summary.v2"));
        assert!(encoded.contains("webview-vdo"));
        assert!(encoded.contains("authorityMailbox"));
        assert!(encoded.contains("authorityQueueWait"));
        assert!(encoded.contains("same-trace-authority-dequeue-minus-admission"));
        assert!(encoded.contains("latestObservedDepth"));
        for private in [
            "traceId",
            "participant",
            "commandId",
            "arguments",
            "args",
            "ownerToken",
            "fingerprint",
            "secret",
            "noteText",
            "rawError",
            "errorMessage",
            "manifestPath",
            "C:\\\\private",
        ] {
            assert!(!encoded.contains(private));
        }
    }

    #[test]
    fn contended_instrumentation_drops_immediately_instead_of_waiting() {
        let diagnostics = NativeLatencyDiagnostics::with_capacity(2);
        diagnostics.while_store_locked_for_test(|| {
            let mut trace = diagnostics.start_trace(LatencyRoute::LocalTauri);
            trace.mark(LatencyStage::AuthorityAdmission);
            trace.finish(TraceOutcome::Rejected);
        });
        let summary = diagnostics.summary();
        assert_eq!(summary.count, 0);
        assert_eq!(summary.unfinished_count, 0);
        assert_eq!(summary.dropped_count, 1);
        assert_eq!(summary.dropped_stage_update_count, 0);
    }

    #[test]
    fn contended_stage_updates_are_separate_and_interrupted_traces_do_not_pollute_samples() {
        let diagnostics = NativeLatencyDiagnostics::with_capacity(4);
        let mut trace = diagnostics.start_trace(LatencyRoute::LocalTauri);
        diagnostics.while_store_locked_for_test(|| {
            trace.mark(LatencyStage::AuthorityAdmission);
        });
        trace.finish(TraceOutcome::Applied);
        {
            let _interrupted = diagnostics.start_trace(LatencyRoute::LocalTauri);
        }
        let summary = diagnostics.summary();
        assert_eq!(summary.count, 1);
        assert_eq!(summary.interrupted_count, 1);
        assert_eq!(summary.dropped_count, 0);
        assert_eq!(summary.dropped_stage_update_count, 1);
        let local = summary
            .routes
            .iter()
            .find(|route| route.route == LatencyRoute::LocalTauri)
            .unwrap();
        assert_eq!(local.count, 1);
        assert_eq!(
            local.stages[LatencyStage::AuthorityAdmission.index()]
                .elapsed_from_native_ingress
                .sample_count,
            0
        );
    }
}
