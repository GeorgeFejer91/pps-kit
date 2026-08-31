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
pub(crate) struct LatencyStageSummary {
    pub stage: LatencyStage,
    pub elapsed_from_native_ingress: LatencyPercentiles,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LatencyRouteSummary {
    pub route: LatencyRoute,
    pub count: u64,
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
    pub count: u64,
    pub dropped_count: u64,
    pub dropped_stage_update_count: u64,
    pub interrupted_count: u64,
    pub unfinished_count: u64,
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
    store: Mutex<TraceStore>,
}

/// Best-effort local diagnostics. Authority paths use `try_lock` exclusively:
/// contention or poisoning loses diagnostics instead of delaying or changing
/// a Runner transition.
#[derive(Clone)]
pub(crate) struct NativeLatencyDiagnostics(Arc<NativeLatencyInner>);

impl NativeLatencyDiagnostics {
    pub(crate) fn new() -> Self {
        Self::with_capacity(DEFAULT_TRACE_CAPACITY)
    }

    fn with_capacity(capacity: usize) -> Self {
        Self(Arc::new(NativeLatencyInner {
            started: Instant::now(),
            next_trace: AtomicU64::new(1),
            dropped_traces: AtomicU64::new(0),
            dropped_stage_updates: AtomicU64::new(0),
            store: Mutex::new(TraceStore::new(capacity)),
        }))
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
        let id = TraceId(self.0.next_trace.fetch_add(1, Ordering::Relaxed));
        let active = match self.0.store.try_lock() {
            Ok(mut store) => {
                store.insert(id, TraceRecord::new(route, ingress.monotonic_ns));
                true
            }
            Err(TryLockError::WouldBlock | TryLockError::Poisoned(_)) => {
                self.0.dropped_traces.fetch_add(1, Ordering::Relaxed);
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
        summarize_records(&records, dropped_count, dropped_stage_updates)
    }

    fn now_ns(&self) -> u64 {
        u64::try_from(self.0.started.elapsed().as_nanos()).unwrap_or(u64::MAX)
    }

    fn note_dropped_stage_update(&self) {
        self.0.dropped_stage_updates.fetch_add(1, Ordering::Relaxed);
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
        let id = TraceId(self.0.next_trace.fetch_add(1, Ordering::Relaxed));
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
            LatencyRouteSummary {
                route,
                count: clamp_json_u64(route_records.len()),
                stages,
            }
        })
        .collect();
    NativeLatencySummary {
        schema: "pps-runner-native-latency-summary.v1",
        clock_domain: "one-process-monotonic",
        measurement: "cumulative-from-native-ingress",
        count,
        dropped_count: dropped_count.min(JSON_MAX_SAFE_INTEGER),
        dropped_stage_update_count: dropped_stage_update_count.min(JSON_MAX_SAFE_INTEGER),
        interrupted_count,
        unfinished_count,
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
    fn serialized_summary_contains_aggregates_but_no_trace_or_private_payload() {
        let diagnostics = NativeLatencyDiagnostics::with_capacity(4);
        let mut trace = diagnostics.start_at(LatencyRoute::WebViewVdo, 1_000);
        trace.mark_at(LatencyStage::AdapterHandoff, 7_000);
        trace.finish(TraceOutcome::Failed);
        let encoded = serde_json::to_string(&diagnostics.summary()).unwrap();
        assert!(encoded.contains("pps-runner-native-latency-summary.v1"));
        assert!(encoded.contains("webview-vdo"));
        for private in [
            "traceId",
            "participant",
            "commandId",
            "ownerToken",
            "fingerprint",
            "secret",
            "noteText",
            "rawError",
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
