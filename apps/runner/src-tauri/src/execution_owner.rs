use std::{
    collections::{BTreeSet, VecDeque},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Condvar, Mutex,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use pps_brsp::{is_newer_sequence, PairingSecret};
use pps_contracts::{
    Action, Applied, ClockStamp, CommandRequest, RunnerPhase, RunnerSnapshot, Scope, TimingTier,
    JSON_MAX_SAFE_INTEGER,
};
use pps_runner_audio::AudioFence;
use pps_runner_core::{DispatchMilestone, DispatchOrigin, RunnerCore, VerifiedPackageSummary};
use pps_runner_execution::{EventLedger, LedgerEventInput, LedgerReserve, DEFAULT_LEDGER_CAPACITY};
use pps_session_package::VerifiedPreparedSession;
use serde_json::Value;
use tokio::sync::{broadcast, oneshot};

#[cfg(test)]
use std::path::PathBuf;

use crate::{
    latency_diagnostics::{AuthorityMailboxDiagnostics, LatencyStage, LatencyTrace},
    native_output::{
        NativeOutputAuthority, NativeOutputCleanupObservation, NativeOutputCommandError,
        NativeOutputReleaseRequest, NativeOutputReserveRequest, NativeOutputSelection,
        NativeOutputStatus, NativeOutputTicket,
    },
    prepared_audio::{
        PreparedAudioCandidate, PreparedAudioLookup, PreparedAudioSource,
        PreparedAudioSourceReceipt, PreparedAudioSummary, MAXIMUM_CACHED_DECODED_BYTES,
    },
    prepared_execution::{
        CompiledPreparedExecution, PreparedExecutionSource, PreparedExecutionSummary,
    },
    runtime::{
        ActiveController, RemoteApplied, RemoteConfig, RemoteRunnerSnapshot, RemoteSessionError,
        RemoteSessionLeaseReceipt, RemoteSessionRevocationReceipt,
    },
};

pub(crate) const MAILBOX_CAPACITY: usize = 64;
pub(crate) const NORMAL_MAILBOX_CAPACITY: usize = 56;
#[cfg(test)]
pub(crate) const LOCAL_SAFETY_RESERVE: usize = MAILBOX_CAPACITY - NORMAL_MAILBOX_CAPACITY;

const DEFAULT_REMOTE_LEASE: Duration = Duration::from_secs(5);
const LEDGER_SAFETY_RECORD_RESERVE: usize = 8;
const LEDGER_SAFETY_BYTE_RESERVE: usize = 64 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AdmissionClass {
    Normal,
    LocalSafety,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CommitPolicy {
    Ordinary,
    SafetyFallback,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum OwnerSubmitError {
    Full,
    Closed,
}

impl OwnerSubmitError {
    pub(crate) const fn as_runtime_message(self) -> &'static str {
        match self {
            Self::Full => "runner authority queue is full",
            Self::Closed => "runner authority is unavailable",
        }
    }
}

type AuthorityTask = Box<dyn FnOnce(&mut OwnerState) + Send + 'static>;

struct MailboxEntry {
    class: AdmissionClass,
    trace: Option<LatencyTrace>,
    task: AuthorityTask,
}

#[derive(Default)]
struct MailboxState {
    queue: VecDeque<MailboxEntry>,
    normal_count: usize,
    accepting: bool,
    shutdown_requested: bool,
}

struct Mailbox {
    state: Mutex<MailboxState>,
    wake: Condvar,
    diagnostics: AuthorityMailboxDiagnostics,
}

impl Mailbox {
    fn new(diagnostics: AuthorityMailboxDiagnostics) -> Self {
        Self {
            state: Mutex::new(MailboxState {
                accepting: true,
                ..MailboxState::default()
            }),
            wake: Condvar::new(),
            diagnostics,
        }
    }

    fn push(&self, entry: MailboxEntry) -> Result<(), OwnerSubmitError> {
        let mut state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        let safety = entry.class == AdmissionClass::LocalSafety;
        if !state.accepting {
            return Err(OwnerSubmitError::Closed);
        }
        if state.queue.len() == MAILBOX_CAPACITY
            || (entry.class == AdmissionClass::Normal
                && state.normal_count == NORMAL_MAILBOX_CAPACITY)
        {
            self.diagnostics.record_queue_full_reject(safety);
            return Err(OwnerSubmitError::Full);
        }
        if entry.class == AdmissionClass::Normal {
            state.normal_count += 1;
        }
        state.queue.push_back(entry);
        if let Some(trace) = state.queue.back().and_then(|entry| entry.trace.as_ref()) {
            // The entry is now in the queue, while the mailbox lock prevents
            // dequeue. Diagnostics use a non-blocking internal lock.
            trace.mark(LatencyStage::AuthorityAdmission);
        }
        let ordinary_depth = state.normal_count;
        let safety_depth = state.queue.len().saturating_sub(state.normal_count);
        self.diagnostics
            .record_successful_admission(safety, ordinary_depth, safety_depth);
        drop(state);
        self.wake.notify_one();
        Ok(())
    }

    fn pop(&self) -> Option<MailboxEntry> {
        let mut state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        if state.shutdown_requested {
            return None;
        }
        let entry = state.queue.pop_front()?;
        if entry.class == AdmissionClass::Normal {
            state.normal_count = state.normal_count.saturating_sub(1);
        }
        self.diagnostics.record_latest_depths(
            state.normal_count,
            state.queue.len().saturating_sub(state.normal_count),
        );
        Some(entry)
    }

    fn should_stop(&self) -> bool {
        let state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        state.shutdown_requested
    }

    fn wait(&self, timeout: Option<Duration>) {
        let state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        if !state.queue.is_empty() || state.shutdown_requested {
            return;
        }
        match timeout {
            Some(timeout) => {
                let _ = self
                    .wake
                    .wait_timeout(state, timeout)
                    .unwrap_or_else(|error| error.into_inner());
            }
            None => {
                drop(
                    self.wake
                        .wait(state)
                        .unwrap_or_else(|error| error.into_inner()),
                );
            }
        }
    }

    fn request_shutdown(&self) {
        let queued = {
            let mut state = self.state.lock().unwrap_or_else(|error| error.into_inner());
            state.accepting = false;
            state.shutdown_requested = true;
            state.normal_count = 0;
            let queued = std::mem::take(&mut state.queue);
            self.diagnostics.record_latest_depths(0, 0);
            queued
        };
        // Dropping queued task closures closes their oneshot reply channels.
        // Do this outside the mailbox lock in case a captured value has a
        // non-trivial destructor.
        drop(queued);
        self.wake.notify_all();
    }

    #[cfg(test)]
    fn queued_counts(&self) -> (usize, usize) {
        let state = self.state.lock().unwrap_or_else(|error| error.into_inner());
        (state.queue.len(), state.normal_count)
    }

    #[cfg(test)]
    fn shutdown_requested(&self) -> bool {
        self.state
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .shutdown_requested
    }
}

#[derive(Debug)]
struct ProcessClock {
    started: Instant,
}

impl ProcessClock {
    fn new() -> Self {
        Self {
            started: Instant::now(),
        }
    }

    fn monotonic_ns(&self) -> u64 {
        u64::try_from(self.started.elapsed().as_nanos()).unwrap_or(u64::MAX)
    }

    fn stamp(&self) -> ClockStamp {
        let unix_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_millis() as u64)
            .unwrap_or_default()
            .min(JSON_MAX_SAFE_INTEGER);
        ClockStamp {
            unix_ms,
            // ClockStamp is a browser-visible DTO. Preserve the raw u64 clock
            // internally and clamp only at this serialization boundary.
            monotonic_ns: self.monotonic_ns().min(JSON_MAX_SAFE_INTEGER),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RemoteTransport {
    WebView,
    Lan,
}

#[derive(Debug, Clone)]
struct RemoteOwner {
    generation: u64,
    transport: RemoteTransport,
    controller_id: String,
    session_id: String,
    owner_token: String,
    granted_scopes: BTreeSet<Scope>,
    last_control_sequence: Option<u32>,
    lease_deadline: Instant,
}

impl RemoteOwner {
    fn active_controller(&self) -> ActiveController {
        ActiveController {
            id: self.controller_id.clone(),
            granted_scopes: self.granted_scopes.iter().copied().collect(),
        }
    }

    fn matches(&self, identity: &RemoteOwnerIdentity) -> bool {
        self.generation == identity.generation
            && self.session_id == identity.session_id
            && self.controller_id == identity.controller_id
            && self.owner_token == identity.owner_token
    }
}

#[derive(Debug)]
struct RetainedPreparedSession {
    generation: u64,
    receipt: Arc<VerifiedPreparedSession>,
}

/// One-block native PCM and renderer-neutral output-plan cache.
///
/// The candidate is native-only and retains both the exact actor-issued source
/// receipt and its non-serializable playback plan. A later platform adapter
/// must reserve it through the authority rather than reaching into this state.
struct CachedPreparedAudio {
    candidate: PreparedAudioCandidate,
    summary: PreparedAudioSummary,
}

struct OwnerState {
    core: RunnerCore,
    remote: RemoteConfig,
    remote_owner: Option<RemoteOwner>,
    retained_session: Option<RetainedPreparedSession>,
    compiled_execution: Option<CompiledPreparedExecution>,
    prepared_audio: Option<CachedPreparedAudio>,
    prepared_audio_reservation: Option<Arc<PreparedAudioSourceReceipt>>,
    prepared_audio_preparation_generation: u64,
    package_generation: u64,
    run_generation: u64,
    native_output: NativeOutputAuthority,
    owner_generation: u64,
    ledger: EventLedger,
    evidence_unavailable: bool,
    clock: ProcessClock,
    lease_duration: Duration,
    state_tx: broadcast::Sender<RunnerSnapshot>,
}

#[derive(Debug, Clone)]
pub(crate) struct AuthorityView {
    pub snapshot: RunnerSnapshot,
    pub remote: RemoteConfig,
    pub active_controller: Option<ActiveController>,
}

#[derive(Debug, Clone)]
pub(crate) struct RemoteOwnerIdentity {
    pub controller_id: String,
    pub session_id: String,
    pub owner_token: String,
    pub generation: u64,
}

#[derive(Debug, Clone)]
pub(crate) struct LanOwnerReceipt {
    pub identity: RemoteOwnerIdentity,
    pub snapshot: RemoteRunnerSnapshot,
}

#[cfg(test)]
pub(crate) struct OwnerTestView {
    pub active_controller: Option<ActiveController>,
    pub manifest_path: Option<PathBuf>,
    pub package_generation: u64,
    pub compiled_schedule_count: Option<usize>,
    pub prepared_audio_block_ordinal: Option<u32>,
    pub prepared_audio_decoded_bytes: Option<u64>,
    pub prepared_output_plan_event_count: Option<usize>,
    pub prepared_output_plan_run_generation: Option<u64>,
    pub compiled_schedule_strong_count: Option<usize>,
    pub retained_session_strong_count: Option<usize>,
    pub native_output_status: NativeOutputStatus,
}

impl OwnerState {
    fn invalidate_prepared_audio(&mut self) {
        self.prepared_audio = None;
        self.prepared_audio_reservation = None;
    }

    fn view(&self) -> AuthorityView {
        AuthorityView {
            snapshot: self.core.snapshot(),
            remote: self.remote.clone(),
            active_controller: self
                .remote_owner
                .as_ref()
                .map(RemoteOwner::active_controller),
        }
    }

    fn next_owner_generation(&mut self) -> Result<u64, RemoteSessionError> {
        match self.owner_generation.checked_add(1) {
            Some(next) => Ok(next),
            None => {
                self.fail_stop_unavailable(
                    "authority.generation.exhausted",
                    "authority_unavailable",
                );
                Err(RemoteSessionError::unavailable())
            }
        }
    }

    fn ledger_input(
        event_type: &'static str,
        source: &'static str,
        stamp: &ClockStamp,
    ) -> LedgerEventInput {
        let mut event = LedgerEventInput::new(event_type, source, stamp.monotonic_ns);
        event.unix_ms = Some(stamp.unix_ms);
        event
    }

    fn commit_candidate(
        &mut self,
        candidate: RunnerCore,
        event: LedgerEventInput,
        policy: CommitPolicy,
        publish: bool,
    ) -> Result<RunnerSnapshot, &'static str> {
        if self.evidence_unavailable && policy == CommitPolicy::Ordinary {
            return Err("runtime_unavailable");
        }
        let reserve = match policy {
            CommitPolicy::Ordinary => {
                LedgerReserve::new(LEDGER_SAFETY_RECORD_RESERVE, LEDGER_SAFETY_BYTE_RESERVE)
            }
            CommitPolicy::SafetyFallback => LedgerReserve::NONE,
        };
        let evidence_result = self
            .ledger
            .prepare_batch([event], reserve)
            .and_then(|prepared| self.ledger.commit_prepared(prepared));
        if evidence_result.is_err() {
            if policy == CommitPolicy::Ordinary {
                self.fail_stop_unavailable(
                    "authority.evidence.unavailable",
                    "evidence_unavailable",
                );
                return Err("runtime_unavailable");
            }
            self.evidence_unavailable = true;
        }
        let snapshot = candidate.snapshot();
        self.core = candidate;
        if publish {
            let _ = self.state_tx.send(snapshot.clone());
        }
        Ok(snapshot)
    }

    fn next_run_generation_for_dispatch(
        &mut self,
        action: Action,
        changed: bool,
    ) -> Result<Option<u64>, &'static str> {
        if !changed {
            return Ok(None);
        }
        if matches!(
            action,
            Action::PartStart | Action::RunStop | Action::RunAbort | Action::RunCompleteDemo
        ) {
            let Some(next) = self.run_generation.checked_add(1) else {
                self.fail_stop_unavailable(
                    "authority.generation.exhausted",
                    "authority_unavailable",
                );
                return Err("runtime_unavailable");
            };
            return Ok(Some(next));
        }
        Ok(None)
    }

    fn safe_neutral_candidate(
        &self,
        connection_state: &'static str,
        stamp: &ClockStamp,
    ) -> RunnerCore {
        let mut candidate = self.core.clone();
        let snapshot = candidate.snapshot();
        let active = matches!(
            snapshot.run.phase,
            RunnerPhase::Running | RunnerPhase::Paused | RunnerPhase::InstructionGate
        );
        if snapshot.run.phase == RunnerPhase::Running {
            candidate.dispatch_local(Action::RunPause, serde_json::json!({}), stamp.clone());
        }
        if active || snapshot.safety.local_armed {
            // The pure reducer deliberately forbids disarming an active run.
            // A fail-stop therefore aborts after pausing, which is the native
            // safe-neutral transition that also clears local arm/output state.
            candidate.dispatch_local(Action::RunAbort, serde_json::json!({}), stamp.clone());
        }
        candidate.set_controller_lease(None, None, stamp.clone());
        candidate.set_connection_state(connection_state, stamp.clone());
        candidate
    }

    fn advance_owner_generation_or_latch(&mut self) {
        match self.owner_generation.checked_add(1) {
            Some(next) => self.owner_generation = next,
            // Every caller clears/revokes the owner and establishes safe state
            // before advancing this fence. At the numeric ceiling, keep the
            // non-reusable generation and permanently fail closed; recursing
            // through the fail-stop path would add no safety and could loop.
            None => self.evidence_unavailable = true,
        }
    }

    fn advance_run_generation_or_latch(&mut self) {
        match self.run_generation.checked_add(1) {
            Some(next) => self.run_generation = next,
            // Safe-neutral state is already installed before this helper is
            // called. Retaining the maximum generation prevents reuse while
            // the unavailable latch rejects subsequent ordinary work.
            None => self.evidence_unavailable = true,
        }
    }

    fn fail_stop_unavailable(
        &mut self,
        event_type: &'static str,
        connection_state: &'static str,
    ) -> RunnerSnapshot {
        let stamp = self.clock.stamp();
        let mut event = Self::ledger_input(event_type, "local-safety", &stamp);
        event.authority_id = self
            .remote_owner
            .as_ref()
            .map(|owner| owner.controller_id.clone());
        // Ordinary writers preserve this capacity. The fail-stop consumes at
        // most one bounded record; safety itself never depends on that append.
        let _ = self
            .ledger
            .prepare_batch([event], LedgerReserve::NONE)
            .and_then(|prepared| self.ledger.commit_prepared(prepared));

        let candidate = self.safe_neutral_candidate(connection_state, &stamp);
        let snapshot = candidate.snapshot();
        self.core = candidate;
        if self.remote_owner.take().is_some() {
            self.advance_owner_generation_or_latch();
        }
        // Fail-stop invalidates every callback/effect captured for the former
        // run, even when no remote owner was present.
        self.advance_run_generation_or_latch();
        self.invalidate_prepared_audio();
        self.native_output.invalidate_for_runner_change();
        self.evidence_unavailable = true;
        let _ = self.state_tx.send(snapshot.clone());
        snapshot
    }

    #[cfg(test)]
    fn dispatch_local(
        &mut self,
        action: Action,
        args: Value,
        class: AdmissionClass,
    ) -> Result<Applied, String> {
        self.dispatch_local_traced(action, args, class, None)
    }

    fn dispatch_local_traced(
        &mut self,
        action: Action,
        args: Value,
        class: AdmissionClass,
        trace: Option<&LatencyTrace>,
    ) -> Result<Applied, String> {
        let result = (|| {
            if action == Action::PartStart && self.native_output.part_start_blocked() {
                return Err("native_output_cleanup_pending".to_owned());
            }
            let stamp = self.clock.stamp();
            let previous_revision = self.core.revision();
            let mut candidate = self.core.clone();
            let applied = candidate.dispatch_local_observed(action, args, stamp.clone(), |point| {
                observe_reducer_milestone(trace, point);
            });
            let changed = candidate.revision() != previous_revision;
            if changed {
                let next_run_generation = self
                    .next_run_generation_for_dispatch(applied.action, changed)
                    .map_err(str::to_owned)?;
                let mut event = Self::ledger_input("runner.dispatch", "local", &stamp);
                event.command_id = Some(applied.id.clone());
                self.commit_candidate(
                    candidate,
                    event,
                    if class == AdmissionClass::LocalSafety {
                        CommitPolicy::SafetyFallback
                    } else {
                        CommitPolicy::Ordinary
                    },
                    true,
                )
                .map_err(str::to_owned)?;
                if let Some(next) = next_run_generation {
                    self.run_generation = next;
                    self.invalidate_prepared_audio();
                    self.native_output.invalidate_for_runner_change();
                } else if applied.action == Action::TargetArm {
                    self.native_output.invalidate_for_runner_change();
                }
            } else {
                // Rejections and accepted no-ops still retain reducer
                // dedupe/stamp semantics, but cannot consume the scientific
                // evidence ledger.
                self.core = candidate;
            }
            Ok(applied)
        })();
        if let Some(trace) = trace {
            trace.mark(LatencyStage::ReplyReady);
        }
        result
    }

    #[cfg(test)]
    fn dispatch_remote(
        &mut self,
        owner: &RemoteOwner,
        command: CommandRequest,
    ) -> Result<Applied, RemoteSessionError> {
        self.dispatch_remote_traced(owner, command, None)
    }

    fn dispatch_remote_traced(
        &mut self,
        owner: &RemoteOwner,
        command: CommandRequest,
        trace: Option<&LatencyTrace>,
    ) -> Result<Applied, RemoteSessionError> {
        (|| {
            if command.action == Action::PartStart && self.native_output.part_start_blocked() {
                return Err(RemoteSessionError::unavailable());
            }
            let stamp = self.clock.stamp();
            let previous_revision = self.core.revision();
            let mut candidate = self.core.clone();
            let applied = candidate.dispatch_observed(
                DispatchOrigin::Remote {
                    controller_id: owner.controller_id.clone(),
                    granted_scopes: owner.granted_scopes.clone(),
                    lease_valid: true,
                },
                command,
                stamp.clone(),
                |point| observe_reducer_milestone(trace, point),
            );
            let changed = candidate.revision() != previous_revision;
            if changed {
                let next_run_generation = self
                    .next_run_generation_for_dispatch(applied.action, changed)
                    .map_err(|_| RemoteSessionError::unavailable())?;
                let mut event = Self::ledger_input("runner.dispatch", "remote", &stamp);
                event.authority_id = Some(owner.controller_id.clone());
                event.command_id = Some(applied.id.clone());
                self.commit_candidate(candidate, event, CommitPolicy::Ordinary, true)
                    .map_err(|_| RemoteSessionError::unavailable())?;
                if let Some(next) = next_run_generation {
                    self.run_generation = next;
                    self.invalidate_prepared_audio();
                    self.native_output.invalidate_for_runner_change();
                } else if applied.action == Action::TargetArm {
                    self.native_output.invalidate_for_runner_change();
                }
            } else {
                self.core = candidate;
            }
            Ok(applied)
        })()
    }

    fn inspection_source(&self) -> Result<PreparedExecutionSource, &'static str> {
        let retained = self
            .retained_session
            .as_ref()
            .ok_or("prepared_session_missing")?;
        Ok(PreparedExecutionSource {
            generation: retained.generation,
            fingerprint: retained.receipt.manifest_sha256().to_owned(),
            receipt: Arc::clone(&retained.receipt),
        })
    }

    fn cache_compiled(
        &mut self,
        compiled: CompiledPreparedExecution,
    ) -> Result<PreparedExecutionSummary, &'static str> {
        let retained = self
            .retained_session
            .as_ref()
            .ok_or("prepared_package_replaced")?;
        if retained.generation != compiled.generation
            || retained.receipt.manifest_sha256() != compiled.fingerprint
        {
            return Err("prepared_package_replaced");
        }
        if usize::try_from(compiled.summary().block_count).ok() != Some(compiled.schedules().len())
        {
            return Err("runtime_unavailable");
        }
        let summary = compiled.summary().clone();
        self.compiled_execution = Some(compiled);
        self.invalidate_prepared_audio();
        Ok(summary)
    }

    fn prepared_audio_source(
        &mut self,
        block_ordinal: u32,
    ) -> Result<PreparedAudioLookup, &'static str> {
        if matches!(
            self.core.snapshot().run.phase,
            RunnerPhase::InstructionGate
                | RunnerPhase::Running
                | RunnerPhase::Paused
                | RunnerPhase::Stopping
        ) {
            return Err("prepared_audio_active_run");
        }
        let (
            package_generation,
            package_fingerprint,
            verified_session,
            schedule,
            expected_sample_rate_hz,
        ) = {
            let retained = self
                .retained_session
                .as_ref()
                .ok_or("prepared_session_missing")?;
            let compiled = self
                .compiled_execution
                .as_ref()
                .ok_or("prepared_execution_missing")?;
            if retained.generation != compiled.generation
                || retained.receipt.manifest_sha256() != compiled.fingerprint
            {
                return Err("prepared_package_replaced");
            }
            let ordinal =
                usize::try_from(block_ordinal).map_err(|_| "prepared_audio_block_missing")?;
            retained
                .receipt
                .blocks()
                .get(ordinal)
                .ok_or("prepared_audio_block_missing")?;
            let schedule = compiled
                .schedules()
                .get(ordinal)
                .ok_or("prepared_audio_block_missing")?;
            let expected_sample_rate_hz = u32::try_from(schedule.summary().sample_rate_hz)
                .ok()
                .filter(|rate| *rate > 0)
                .ok_or("prepared_audio_sample_rate_invalid")?;
            (
                retained.generation,
                retained.receipt.manifest_sha256().to_owned(),
                Arc::clone(&retained.receipt),
                Arc::clone(schedule),
                expected_sample_rate_hz,
            )
        };
        let ordinal = usize::try_from(block_ordinal).map_err(|_| "prepared_audio_block_missing")?;
        let current_wav = verified_session
            .blocks()
            .get(ordinal)
            .map(|block| block.block_wav())
            .ok_or("prepared_audio_block_missing")?;

        if let Some(cached) = self.prepared_audio.as_ref() {
            let candidate = &cached.candidate;
            let fence = candidate.media().fence();
            let cache_is_current = fence.block_ordinal() == block_ordinal
                && fence.package_generation() == package_generation
                && fence.package_fingerprint() == package_fingerprint
                && candidate.run_generation() == self.run_generation
                && Arc::ptr_eq(candidate.verified_session(), &verified_session)
                && candidate.wav_receipt() == Some(current_wav)
                && Arc::ptr_eq(candidate.schedule(), &schedule)
                && candidate.media().identity().sha256() == current_wav.sha256()
                && candidate.media().identity().encoded_byte_count()
                    == current_wav.encoded_byte_count()
                && candidate.media().sample_rate_hz() == expected_sample_rate_hz;
            if cache_is_current {
                return Ok(PreparedAudioLookup::Cached(cached.summary.clone()));
            }
        }
        // A different or stale cached block is dropped before the worker may
        // allocate another decoded buffer. Together with adapter single-flight
        // this keeps the process to one Tauri-preload byte budget, not one old
        // cache plus one equally large candidate.
        let next_preparation_generation = self
            .prepared_audio_preparation_generation
            .checked_add(1)
            .ok_or("runtime_unavailable")?;
        self.prepared_audio_preparation_generation = next_preparation_generation;
        self.invalidate_prepared_audio();
        let receipt = Arc::new(PreparedAudioSourceReceipt::new(
            next_preparation_generation,
            AudioFence::new(package_generation, package_fingerprint, block_ordinal),
            self.run_generation,
            verified_session,
            schedule,
        ));
        self.prepared_audio_reservation = Some(Arc::clone(&receipt));

        Ok(PreparedAudioLookup::Decode(PreparedAudioSource::new(
            receipt,
        )))
    }

    fn cache_prepared_audio(
        &mut self,
        candidate: PreparedAudioCandidate,
    ) -> Result<PreparedAudioSummary, &'static str> {
        let retained = self
            .retained_session
            .as_ref()
            .ok_or("prepared_package_replaced")?;
        let source_receipt = candidate.source_receipt();
        let fence = source_receipt.fence();
        if retained.generation != fence.package_generation()
            || retained.receipt.manifest_sha256() != fence.package_fingerprint()
            || !Arc::ptr_eq(candidate.verified_session(), &retained.receipt)
        {
            return Err("prepared_package_replaced");
        }
        if candidate.run_generation() != self.run_generation {
            return Err("prepared_audio_run_replaced");
        }
        let compiled = self
            .compiled_execution
            .as_ref()
            .ok_or("prepared_execution_replaced")?;
        if compiled.generation != retained.generation
            || compiled.fingerprint != retained.receipt.manifest_sha256()
        {
            return Err("prepared_execution_replaced");
        }
        let ordinal =
            usize::try_from(fence.block_ordinal()).map_err(|_| "prepared_audio_block_replaced")?;
        let current_wav = retained
            .receipt
            .blocks()
            .get(ordinal)
            .map(|block| block.block_wav())
            .ok_or("prepared_audio_block_replaced")?;
        let schedule = compiled
            .schedules()
            .get(ordinal)
            .ok_or("prepared_audio_block_replaced")?;
        let expected_sample_rate_hz = u32::try_from(schedule.summary().sample_rate_hz)
            .ok()
            .filter(|rate| *rate > 0)
            .ok_or("prepared_audio_sample_rate_invalid")?;
        if !Arc::ptr_eq(schedule, candidate.schedule()) {
            return Err("prepared_execution_replaced");
        }
        let plan_fence = candidate.playback_plan().fence();
        if plan_fence.audio() != fence
            || plan_fence.run_generation() != candidate.run_generation()
            || plan_fence.audio().block_ordinal() != fence.block_ordinal()
        {
            return Err("prepared_audio_block_replaced");
        }
        if candidate.wav_receipt() != Some(current_wav)
            || current_wav.sha256() != candidate.media().identity().sha256()
            || current_wav.encoded_byte_count() != candidate.media().identity().encoded_byte_count()
            || candidate.media().sample_rate_hz() != expected_sample_rate_hz
        {
            return Err("prepared_audio_block_replaced");
        }
        let reservation_is_current =
            self.prepared_audio_reservation
                .as_ref()
                .is_some_and(|reservation| {
                    Arc::ptr_eq(reservation, source_receipt)
                        && reservation.preparation_generation()
                            == source_receipt.preparation_generation()
                });
        if !reservation_is_current {
            return Err("prepared_audio_preparation_replaced");
        }
        let decoded_bytes = candidate
            .decoded_bytes()
            .map_err(|_| "prepared_audio_resource_limit")?;
        if decoded_bytes > MAXIMUM_CACHED_DECODED_BYTES {
            return Err("prepared_audio_resource_limit");
        }
        let summary = candidate
            .summary()
            .map_err(|_| "prepared_audio_resource_limit")?;
        // Exactly one immutable block is retained. Replacing this Option drops
        // the prior Arc-backed PCM before the authority processes more work.
        self.prepared_audio_reservation = None;
        self.prepared_audio = Some(CachedPreparedAudio {
            candidate,
            summary: summary.clone(),
        });
        Ok(summary)
    }

    fn adopt_verified_session(
        &mut self,
        verified: VerifiedPreparedSession,
        package: VerifiedPackageSummary,
        next_secret: PairingSecret,
        next_session_id: String,
        next_epoch: u64,
    ) -> Result<RunnerSnapshot, &'static str> {
        let Some(next_generation) = self.package_generation.checked_add(1) else {
            self.fail_stop_unavailable("authority.generation.exhausted", "authority_unavailable");
            return Err("runtime_unavailable");
        };
        let Some(next_owner_generation) = self.owner_generation.checked_add(1) else {
            self.fail_stop_unavailable("authority.generation.exhausted", "authority_unavailable");
            return Err("runtime_unavailable");
        };
        let Some(next_run_generation) = self.run_generation.checked_add(1) else {
            self.fail_stop_unavailable("authority.generation.exhausted", "authority_unavailable");
            return Err("runtime_unavailable");
        };
        let stamp = self.clock.stamp();
        let mut candidate = self.core.clone();
        candidate.adopt_verified_package(package, stamp.clone())?;
        candidate.rotate_epoch(next_epoch, stamp.clone());
        candidate.set_controller_lease(None, None, stamp.clone());
        candidate.set_connection_state(
            if self.remote.enabled {
                "package_changed"
            } else {
                "local_only"
            },
            stamp.clone(),
        );
        let event = Self::ledger_input("package.adopted", "local", &stamp);
        let snapshot = self.commit_candidate(candidate, event, CommitPolicy::Ordinary, true)?;
        self.remote.secret = next_secret;
        self.remote.session_id = next_session_id;
        self.remote_owner = None;
        self.owner_generation = next_owner_generation;
        self.package_generation = next_generation;
        self.run_generation = next_run_generation;
        self.retained_session = Some(RetainedPreparedSession {
            generation: next_generation,
            receipt: Arc::new(verified),
        });
        self.compiled_execution = None;
        self.invalidate_prepared_audio();
        self.native_output.invalidate_for_runner_change();
        Ok(snapshot)
    }

    fn available_scopes(&self) -> Vec<Scope> {
        let mut scopes = Scope::DEFAULT_REMOTE.to_vec();
        if self.remote.allow_abort {
            scopes.push(Scope::SessionAbort);
        }
        scopes
    }

    fn validate_remote_claim(
        &self,
        session_id: &str,
        accepted_scopes: &BTreeSet<Scope>,
    ) -> Result<(), RemoteSessionError> {
        if !self.remote.enabled {
            return Err(RemoteSessionError::new(
                "remote_disabled",
                "Remote control is not enabled by the local operator.",
            ));
        }
        if self.remote.session_id != session_id {
            return Err(RemoteSessionError::new(
                "session_mismatch",
                "The remote activation changed; use a fresh invitation.",
            ));
        }
        if self.remote_owner.is_some() {
            return Err(RemoteSessionError::new(
                "controller_busy",
                "The Runner already has an active remote controller.",
            ));
        }
        let available = self.available_scopes().into_iter().collect::<BTreeSet<_>>();
        if !accepted_scopes.is_subset(&available) {
            return Err(RemoteSessionError::new(
                "scope_not_available",
                "The WebView requested a scope that the local operator did not enable.",
            ));
        }
        Ok(())
    }

    fn install_remote_owner(
        &mut self,
        transport: RemoteTransport,
        session_id: String,
        controller_id: String,
        owner_token: String,
        accepted_scopes: BTreeSet<Scope>,
        last_control_sequence: Option<u32>,
    ) -> Result<(RemoteOwner, RunnerSnapshot, u64), RemoteSessionError> {
        self.validate_remote_claim(&session_id, &accepted_scopes)?;
        let generation = self.next_owner_generation()?;
        let owner = RemoteOwner {
            generation,
            transport,
            controller_id,
            session_id,
            owner_token,
            granted_scopes: accepted_scopes,
            last_control_sequence,
            lease_deadline: Instant::now() + self.lease_duration,
        };
        let stamp = self.clock.stamp();
        let expires_at = lease_expiry_unix_ms(&stamp, self.lease_duration);
        let mut candidate = self.core.clone();
        candidate.set_connection_state("remote_connected", stamp.clone());
        candidate.set_controller_lease(Some(&owner.controller_id), Some(expires_at), stamp.clone());
        let mut event = Self::ledger_input("remote.owner.claimed", "remote", &stamp);
        event.authority_id = Some(owner.controller_id.clone());
        let snapshot = self
            .commit_candidate(candidate, event, CommitPolicy::Ordinary, true)
            .map_err(|_| RemoteSessionError::unavailable())?;
        self.owner_generation = generation;
        self.remote_owner = Some(owner.clone());
        Ok((owner, snapshot, expires_at))
    }

    fn claim_webview(
        &mut self,
        session_id: String,
        controller_id: String,
        owner_token: String,
        accepted_scopes: BTreeSet<Scope>,
        ready_sequence: u32,
    ) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
        let (owner, snapshot, expires_at) = self.install_remote_owner(
            RemoteTransport::WebView,
            session_id,
            controller_id,
            owner_token,
            accepted_scopes,
            Some(ready_sequence),
        )?;
        Ok(RemoteSessionLeaseReceipt {
            session_id: owner.session_id,
            controller_id: owner.controller_id,
            owner_token: owner.owner_token,
            accepted_scopes: owner.granted_scopes.into_iter().collect(),
            lease_expires_at_unix_ms: expires_at,
            snapshot: snapshot.into(),
        })
    }

    fn claim_lan(
        &mut self,
        session_id: String,
        controller_id: String,
        owner_token: String,
        accepted_scopes: BTreeSet<Scope>,
    ) -> Result<LanOwnerReceipt, RemoteSessionError> {
        let (owner, snapshot, _) = self.install_remote_owner(
            RemoteTransport::Lan,
            session_id,
            controller_id,
            owner_token,
            accepted_scopes,
            None,
        )?;
        Ok(LanOwnerReceipt {
            identity: RemoteOwnerIdentity {
                controller_id: owner.controller_id,
                session_id: owner.session_id,
                owner_token: owner.owner_token,
                generation: owner.generation,
            },
            snapshot: snapshot.into(),
        })
    }

    fn owner_by_identity(
        &self,
        identity: &RemoteOwnerIdentity,
        transport: RemoteTransport,
    ) -> Option<&RemoteOwner> {
        self.remote_owner
            .as_ref()
            .filter(|owner| owner.transport == transport && owner.matches(identity))
    }

    /// Return the public remote projection only while this exact LAN owner is
    /// current and still holds read scope. This intentionally takes `&self`:
    /// publication checks can never renew the controller lease.
    fn lan_publication_snapshot(
        &self,
        identity: &RemoteOwnerIdentity,
    ) -> Option<RemoteRunnerSnapshot> {
        let owner = self.owner_by_identity(identity, RemoteTransport::Lan)?;
        if !self.remote_is_current(owner) || !owner.granted_scopes.contains(&Scope::SessionRead) {
            return None;
        }
        Some(self.core.snapshot().into())
    }

    fn webview_owner(
        &self,
        session_id: &str,
        owner_token: &str,
    ) -> Result<&RemoteOwner, RemoteSessionError> {
        self.remote_owner
            .as_ref()
            .filter(|owner| {
                owner.transport == RemoteTransport::WebView
                    && owner.session_id == session_id
                    && owner.owner_token == owner_token
            })
            .ok_or_else(stale_owner_error)
    }

    fn remote_is_current(&self, owner: &RemoteOwner) -> bool {
        self.remote.enabled
            && self.remote.session_id == owner.session_id
            && Instant::now() < owner.lease_deadline
    }

    fn refresh_owner(&mut self, owner: RemoteOwner) -> Result<RunnerSnapshot, RemoteSessionError> {
        let stamp = self.clock.stamp();
        let expires_at = lease_expiry_unix_ms(&stamp, self.lease_duration);
        let mut candidate = self.core.clone();
        let snapshot =
            candidate.set_controller_lease(Some(&owner.controller_id), Some(expires_at), stamp);
        self.core = candidate;
        let _ = self.state_tx.send(snapshot.clone());
        self.remote_owner = Some(owner);
        Ok(snapshot)
    }

    fn renew_webview(
        &mut self,
        session_id: String,
        owner_token: String,
        control_sequence: u32,
    ) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
        let mut owner = self.webview_owner(&session_id, &owner_token)?.clone();
        if !self.remote_is_current(&owner) {
            self.expire_deadman_if_due();
            return Err(RemoteSessionError::new(
                "controller_lease_expired",
                "The native remote-controller lease expired.",
            ));
        }
        let previous = owner
            .last_control_sequence
            .expect("WebView owners always retain a sequence");
        if !is_newer_sequence(control_sequence, previous) {
            return Err(RemoteSessionError::new(
                "replayed_sequence",
                "The BRSP control sequence is duplicate, old, or ambiguous.",
            ));
        }
        owner.last_control_sequence = Some(control_sequence);
        owner.lease_deadline = Instant::now() + self.lease_duration;
        let snapshot = self.refresh_owner(owner.clone())?;
        Ok(RemoteSessionLeaseReceipt {
            session_id: owner.session_id,
            controller_id: owner.controller_id,
            owner_token: owner.owner_token,
            accepted_scopes: owner.granted_scopes.into_iter().collect(),
            lease_expires_at_unix_ms: snapshot.safety.lease_expires_at_unix_ms.unwrap_or_default(),
            snapshot: snapshot.into(),
        })
    }

    #[cfg(test)]
    fn dispatch_webview(
        &mut self,
        session_id: String,
        owner_token: String,
        control_sequence: u32,
        command: pps_contracts::CommandBody,
    ) -> Result<RemoteApplied, RemoteSessionError> {
        self.dispatch_webview_traced(session_id, owner_token, control_sequence, command, None)
    }

    fn dispatch_webview_traced(
        &mut self,
        session_id: String,
        owner_token: String,
        control_sequence: u32,
        command: pps_contracts::CommandBody,
        trace: Option<&LatencyTrace>,
    ) -> Result<RemoteApplied, RemoteSessionError> {
        let result = (|| {
            let mut owner = match self.webview_owner(&session_id, &owner_token) {
                Ok(owner) => owner.clone(),
                Err(error) => {
                    if let Some(trace) = trace {
                        trace.mark(LatencyStage::AuthorityAuthorizationComplete);
                    }
                    return Err(error);
                }
            };
            if !self.remote_is_current(&owner) {
                self.expire_deadman_if_due();
                if let Some(trace) = trace {
                    trace.mark(LatencyStage::AuthorityAuthorizationComplete);
                }
                return Err(RemoteSessionError::new(
                    "controller_lease_expired",
                    "The native remote-controller lease expired.",
                ));
            }
            let previous = owner
                .last_control_sequence
                .expect("WebView owners always retain a sequence");
            if !is_newer_sequence(control_sequence, previous) {
                if let Some(trace) = trace {
                    trace.mark(LatencyStage::AuthorityAuthorizationComplete);
                }
                return Err(RemoteSessionError::new(
                    "replayed_sequence",
                    "The BRSP control sequence is duplicate, old, or ambiguous.",
                ));
            }
            if !owner.granted_scopes.contains(&command.scope) {
                if let Some(trace) = trace {
                    trace.mark(LatencyStage::AuthorityAuthorizationComplete);
                }
                return Err(RemoteSessionError::new(
                    "scope_not_granted",
                    "The command scope was not negotiated for this controller.",
                ));
            }
            if let Some(trace) = trace {
                trace.mark(LatencyStage::AuthorityAuthorizationComplete);
            }
            owner.last_control_sequence = Some(control_sequence);
            owner.lease_deadline = Instant::now() + self.lease_duration;
            let epoch = self.core.epoch();
            self.refresh_owner(owner.clone())?;
            let applied = self.dispatch_remote_traced(
                &owner,
                command.into_request(epoch, control_sequence),
                trace,
            )?;
            Ok(RemoteApplied::from_native(applied, self.core.snapshot()))
        })();
        if let Some(trace) = trace {
            trace.mark(LatencyStage::ReplyReady);
        }
        result
    }

    fn renew_lan(&mut self, identity: RemoteOwnerIdentity) -> Result<bool, String> {
        let Some(mut owner) = self
            .owner_by_identity(&identity, RemoteTransport::Lan)
            .cloned()
        else {
            return Ok(false);
        };
        if !self.remote_is_current(&owner) {
            self.expire_deadman_if_due();
            return Ok(false);
        }
        owner.lease_deadline = Instant::now() + self.lease_duration;
        self.refresh_owner(owner)
            .map(|_| true)
            .map_err(|error| error.code)
    }

    fn dispatch_lan_traced(
        &mut self,
        identity: RemoteOwnerIdentity,
        control_sequence: u32,
        command: pps_contracts::CommandBody,
        trace: Option<&LatencyTrace>,
    ) -> Result<RemoteApplied, String> {
        let result = (|| {
            let mut owner = match self
                .owner_by_identity(&identity, RemoteTransport::Lan)
                .cloned()
            {
                Some(owner) => owner,
                None => {
                    if let Some(trace) = trace {
                        trace.mark(LatencyStage::AuthorityAuthorizationComplete);
                    }
                    return Err("controller authority changed".to_owned());
                }
            };
            if !self.remote_is_current(&owner) {
                self.expire_deadman_if_due();
                if let Some(trace) = trace {
                    trace.mark(LatencyStage::AuthorityAuthorizationComplete);
                }
                return Err("controller lease expired".to_owned());
            }
            // Scope validation remains authoritative in RunnerCore so a
            // rejected command still receives the same BRSP `applied`
            // semantics. This read completes the actor-local owner/scope
            // observation without changing that decision path.
            let _scope_is_granted = owner.granted_scopes.contains(&command.scope);
            if let Some(trace) = trace {
                trace.mark(LatencyStage::AuthorityAuthorizationComplete);
            }
            owner.lease_deadline = Instant::now() + self.lease_duration;
            self.refresh_owner(owner.clone())
                .map_err(|error| error.code)?;
            let request = command.into_request(self.core.epoch(), control_sequence);
            let applied = self
                .dispatch_remote_traced(&owner, request, trace)
                .map_err(|error| error.code)?;
            Ok(RemoteApplied::from_native(applied, self.core.snapshot()))
        })();
        if let Some(trace) = trace {
            trace.mark(LatencyStage::ReplyReady);
        }
        result
    }

    fn revoke_owner_if_matches(
        &mut self,
        predicate: impl FnOnce(&RemoteOwner) -> bool,
        connection_state: &'static str,
    ) -> Result<Option<RunnerSnapshot>, &'static str> {
        let Some(owner) = self.remote_owner.as_ref() else {
            return Ok(None);
        };
        if !predicate(owner) {
            return Ok(None);
        }
        let stamp = self.clock.stamp();
        let mut candidate = self.core.clone();
        candidate.set_controller_lease(None, None, stamp.clone());
        candidate.set_connection_state(connection_state, stamp.clone());
        if candidate.snapshot().run.phase == RunnerPhase::Running {
            candidate.dispatch_local(Action::RunPause, serde_json::json!({}), stamp.clone());
        }
        let mut event = Self::ledger_input("remote.owner.revoked", "local-safety", &stamp);
        event.authority_id = Some(owner.controller_id.clone());
        let snapshot =
            self.commit_candidate(candidate, event, CommitPolicy::SafetyFallback, true)?;
        self.remote_owner = None;
        self.advance_owner_generation_or_latch();
        Ok(Some(snapshot))
    }

    fn revoke_webview(
        &mut self,
        session_id: String,
        owner_token: String,
    ) -> Result<RemoteSessionRevocationReceipt, RemoteSessionError> {
        self.webview_owner(&session_id, &owner_token)?;
        let snapshot = self
            .revoke_owner_if_matches(
                |owner| {
                    owner.transport == RemoteTransport::WebView
                        && owner.session_id == session_id
                        && owner.owner_token == owner_token
                },
                "remote_waiting",
            )
            .map_err(|_| RemoteSessionError::unavailable())?
            .ok_or_else(stale_owner_error)?;
        Ok(RemoteSessionRevocationReceipt {
            revoked: true,
            snapshot: snapshot.into(),
        })
    }

    fn revoke_lan(
        &mut self,
        identity: RemoteOwnerIdentity,
        connection_state: &'static str,
    ) -> Result<bool, String> {
        self.revoke_owner_if_matches(
            |owner| owner.transport == RemoteTransport::Lan && owner.matches(&identity),
            connection_state,
        )
        .map(|snapshot| snapshot.is_some())
        .map_err(str::to_owned)
    }

    fn invalidate_remote_owner(
        &mut self,
        connection_state: &'static str,
        next_epoch: u64,
    ) -> Result<RunnerSnapshot, &'static str> {
        let displaced = self.remote_owner.is_some();
        let stamp = self.clock.stamp();
        let mut candidate = self.core.clone();
        candidate.rotate_epoch(next_epoch, stamp.clone());
        candidate.set_controller_lease(None, None, stamp.clone());
        candidate.set_connection_state(connection_state, stamp.clone());
        if displaced && candidate.snapshot().run.phase == RunnerPhase::Running {
            candidate.dispatch_local(Action::RunPause, serde_json::json!({}), stamp.clone());
        }
        let event = Self::ledger_input("remote.configuration.changed", "local-safety", &stamp);
        let snapshot =
            self.commit_candidate(candidate, event, CommitPolicy::SafetyFallback, true)?;
        self.remote_owner = None;
        self.advance_owner_generation_or_latch();
        Ok(snapshot)
    }

    fn configure_remote(
        &mut self,
        enabled: bool,
        allow_abort: bool,
        next_secret: PairingSecret,
        next_session_id: String,
        next_epoch: u64,
    ) -> Result<(), &'static str> {
        let changed = self.remote.enabled != enabled || self.remote.allow_abort != allow_abort;
        if !changed {
            return Ok(());
        }
        let next_remote = RemoteConfig {
            enabled,
            allow_abort,
            secret: next_secret,
            session_id: next_session_id,
        };
        self.invalidate_remote_owner(
            if enabled {
                "remote_enabled"
            } else {
                "local_only"
            },
            next_epoch,
        )?;
        self.remote = next_remote;
        Ok(())
    }

    fn rotate_pairing(
        &mut self,
        next_secret: PairingSecret,
        next_session_id: String,
        next_epoch: u64,
    ) -> Result<(), &'static str> {
        let next_remote = RemoteConfig {
            enabled: self.remote.enabled,
            allow_abort: self.remote.allow_abort,
            secret: next_secret,
            session_id: next_session_id,
        };
        self.invalidate_remote_owner("pairing_rotated", next_epoch)?;
        self.remote = next_remote;
        Ok(())
    }

    fn expire_deadman_if_due(&mut self) -> bool {
        let Some(owner) = self.remote_owner.as_ref() else {
            return false;
        };
        if Instant::now() < owner.lease_deadline {
            return false;
        }
        self.revoke_owner_if_matches(|_| true, "remote_lease_expired")
            .ok()
            .flatten()
            .is_some()
    }

    fn next_deadman_delay(&self) -> Option<Duration> {
        self.remote_owner.as_ref().map(|owner| {
            owner
                .lease_deadline
                .saturating_duration_since(Instant::now())
        })
    }

    fn shutdown(&mut self) {
        let stamp = self.clock.stamp();
        let candidate = self.safe_neutral_candidate("local_only", &stamp);
        let event = Self::ledger_input("authority.shutdown", "local-safety", &stamp);
        // Shutdown is intrinsically fail-safe: evidence exhaustion cannot
        // prevent neutralization, authority revocation, or final publication.
        let _ = self.commit_candidate(candidate, event, CommitPolicy::SafetyFallback, true);
        if self.remote_owner.take().is_some() {
            self.advance_owner_generation_or_latch();
        }
        self.advance_run_generation_or_latch();
        self.invalidate_prepared_audio();
        self.native_output.shutdown();
    }

    fn native_output_status(
        &mut self,
        observation: NativeOutputCleanupObservation,
    ) -> NativeOutputStatus {
        self.native_output.observe_cleanup(observation);
        self.native_output.status()
    }

    fn begin_native_output_enumerate(
        &mut self,
        observation: NativeOutputCleanupObservation,
    ) -> Result<NativeOutputTicket, NativeOutputCommandError> {
        self.native_output.observe_cleanup(observation);
        self.native_output.begin_enumerate(&self.core.snapshot())
    }

    fn begin_native_output_reserve(
        &mut self,
        observation: NativeOutputCleanupObservation,
        request: NativeOutputReserveRequest,
    ) -> Result<(NativeOutputTicket, NativeOutputSelection), NativeOutputCommandError> {
        self.native_output.observe_cleanup(observation);
        self.native_output
            .begin_reserve(&self.core.snapshot(), &request)
    }

    fn complete_native_output_enumerate(
        &mut self,
        ticket: NativeOutputTicket,
        result: Result<u64, NativeOutputCommandError>,
    ) -> Result<NativeOutputStatus, NativeOutputCommandError> {
        self.native_output.complete_enumerate(ticket, result)
    }

    fn complete_native_output_reserve(
        &mut self,
        ticket: NativeOutputTicket,
        result: Result<u64, NativeOutputCommandError>,
    ) -> Result<NativeOutputStatus, NativeOutputCommandError> {
        self.native_output.complete_reserve(ticket, result)
    }

    fn release_native_output(
        &mut self,
        observation: NativeOutputCleanupObservation,
        request: NativeOutputReleaseRequest,
    ) -> Result<NativeOutputStatus, NativeOutputCommandError> {
        self.native_output.observe_cleanup(observation);
        self.native_output.release(&request)
    }

    fn disable_native_output(
        &mut self,
        observation: NativeOutputCleanupObservation,
    ) -> Result<NativeOutputStatus, NativeOutputCommandError> {
        self.native_output.observe_cleanup(observation);
        self.native_output.disable()
    }
}

fn stale_owner_error() -> RemoteSessionError {
    RemoteSessionError::new(
        "stale_owner",
        "The WebView no longer owns the native remote session.",
    )
}

fn observe_reducer_milestone(trace: Option<&LatencyTrace>, milestone: DispatchMilestone) {
    let Some(trace) = trace else {
        return;
    };
    match milestone {
        DispatchMilestone::ValidationCompleted { .. } => {
            trace.mark(LatencyStage::ReducerValidationComplete);
        }
        DispatchMilestone::TransitionEvaluated { accepted: true, .. } => {
            trace.mark(LatencyStage::ReducerApplied);
        }
        DispatchMilestone::DedupeResolved { .. }
        | DispatchMilestone::TransitionEvaluated {
            accepted: false, ..
        } => {}
    }
}

fn lease_expiry_unix_ms(stamp: &ClockStamp, lease: Duration) -> u64 {
    stamp
        .unix_ms
        .saturating_add(lease.as_millis() as u64)
        .min(JSON_MAX_SAFE_INTEGER)
}

pub(crate) struct ExecutionOwner {
    mailbox: Arc<Mailbox>,
    thread: Mutex<Option<JoinHandle<()>>>,
    _alive: Arc<AtomicBool>,
}

#[derive(Clone)]
pub(crate) struct NativeOutputNoticeIngress {
    mailbox: Arc<Mailbox>,
}

impl NativeOutputNoticeIngress {
    /// Queues only a compact observation refresh. The coordinator retains all
    /// driver state and retries this bounded safety admission if it is full.
    pub(crate) fn notify(&self) -> bool {
        self.mailbox
            .push(MailboxEntry {
                class: AdmissionClass::LocalSafety,
                trace: None,
                task: Box::new(|state| state.native_output.refresh_from_invalidator()),
            })
            .is_ok()
    }
}

struct OwnerStartConfiguration {
    lease_duration: Duration,
    mailbox_diagnostics: AuthorityMailboxDiagnostics,
    native_output: NativeOutputAuthority,
}

impl ExecutionOwner {
    pub(crate) fn start(
        target_id: String,
        target_kind: &'static str,
        epoch: u64,
        timing_tier: TimingTier,
        remote: RemoteConfig,
        state_tx: broadcast::Sender<RunnerSnapshot>,
        mailbox_diagnostics: AuthorityMailboxDiagnostics,
        native_output: NativeOutputAuthority,
    ) -> Result<Self, String> {
        Self::start_with_lease(
            target_id,
            target_kind,
            epoch,
            timing_tier,
            remote,
            state_tx,
            OwnerStartConfiguration {
                lease_duration: DEFAULT_REMOTE_LEASE,
                mailbox_diagnostics,
                native_output,
            },
        )
    }

    fn start_with_lease(
        target_id: String,
        target_kind: &'static str,
        epoch: u64,
        timing_tier: TimingTier,
        remote: RemoteConfig,
        state_tx: broadcast::Sender<RunnerSnapshot>,
        configuration: OwnerStartConfiguration,
    ) -> Result<Self, String> {
        let mailbox = Arc::new(Mailbox::new(configuration.mailbox_diagnostics));
        let lease_duration = configuration.lease_duration;
        let native_output = configuration.native_output;
        let alive = Arc::new(AtomicBool::new(false));
        let thread_mailbox = Arc::clone(&mailbox);
        let thread_alive = Arc::clone(&alive);
        let (ready_tx, ready_rx) = mpsc::sync_channel(1);
        let handle = thread::Builder::new()
            .name("pps-runner-authority".to_owned())
            .spawn(move || {
                let clock = ProcessClock::new();
                let core =
                    RunnerCore::new(target_id, target_kind, epoch, timing_tier, clock.stamp());
                let ledger = EventLedger::new(DEFAULT_LEDGER_CAPACITY)
                    .expect("the fixed authority ledger capacity is valid");
                let mut state = OwnerState {
                    core,
                    remote,
                    remote_owner: None,
                    retained_session: None,
                    compiled_execution: None,
                    prepared_audio: None,
                    prepared_audio_reservation: None,
                    prepared_audio_preparation_generation: 0,
                    package_generation: 0,
                    run_generation: 0,
                    native_output,
                    owner_generation: 0,
                    ledger,
                    evidence_unavailable: false,
                    clock,
                    lease_duration,
                    state_tx,
                };
                thread_alive.store(true, Ordering::Release);
                let _ = ready_tx.send(());
                authority_loop(&thread_mailbox, &mut state);
                state.shutdown();
                thread_alive.store(false, Ordering::Release);
            })
            .map_err(|error| format!("could not start Runner authority thread: {error}"))?;
        ready_rx
            .recv()
            .map_err(|_| "Runner authority thread stopped during startup".to_owned())?;
        Ok(Self {
            mailbox,
            thread: Mutex::new(Some(handle)),
            _alive: alive,
        })
    }

    fn submit<T, F>(
        &self,
        class: AdmissionClass,
        label: &'static str,
        operation: F,
    ) -> Result<oneshot::Receiver<T>, OwnerSubmitError>
    where
        T: Send + 'static,
        F: FnOnce(&mut OwnerState) -> T + Send + 'static,
    {
        self.submit_traced(class, label, None, operation)
    }

    pub(crate) fn native_output_notice_ingress(&self) -> NativeOutputNoticeIngress {
        NativeOutputNoticeIngress {
            mailbox: Arc::clone(&self.mailbox),
        }
    }

    fn submit_traced<T, F>(
        &self,
        class: AdmissionClass,
        _label: &'static str,
        trace: Option<LatencyTrace>,
        operation: F,
    ) -> Result<oneshot::Receiver<T>, OwnerSubmitError>
    where
        T: Send + 'static,
        F: FnOnce(&mut OwnerState) -> T + Send + 'static,
    {
        let (reply, receiver) = oneshot::channel();
        self.mailbox.push(MailboxEntry {
            class,
            trace,
            task: Box::new(move |state| {
                let _ = reply.send(operation(state));
            }),
        })?;
        Ok(receiver)
    }

    #[cfg(test)]
    fn blocking<T, F>(
        &self,
        class: AdmissionClass,
        label: &'static str,
        operation: F,
    ) -> Result<T, OwnerSubmitError>
    where
        T: Send + 'static,
        F: FnOnce(&mut OwnerState) -> T + Send + 'static,
    {
        self.submit(class, label, operation)?
            .blocking_recv()
            .map_err(|_| OwnerSubmitError::Closed)
    }

    #[cfg(test)]
    fn blocking_traced<T, F>(
        &self,
        class: AdmissionClass,
        label: &'static str,
        trace: LatencyTrace,
        operation: F,
    ) -> Result<T, OwnerSubmitError>
    where
        T: Send + 'static,
        F: FnOnce(&mut OwnerState) -> T + Send + 'static,
    {
        self.submit_traced(class, label, Some(trace), operation)?
            .blocking_recv()
            .map_err(|_| OwnerSubmitError::Closed)
    }

    async fn asynchronous<T, F>(
        &self,
        class: AdmissionClass,
        label: &'static str,
        operation: F,
    ) -> Result<T, OwnerSubmitError>
    where
        T: Send + 'static,
        F: FnOnce(&mut OwnerState) -> T + Send + 'static,
    {
        self.submit(class, label, operation)?
            .await
            .map_err(|_| OwnerSubmitError::Closed)
    }

    async fn asynchronous_traced<T, F>(
        &self,
        class: AdmissionClass,
        label: &'static str,
        trace: LatencyTrace,
        operation: F,
    ) -> Result<T, OwnerSubmitError>
    where
        T: Send + 'static,
        F: FnOnce(&mut OwnerState) -> T + Send + 'static,
    {
        self.submit_traced(class, label, Some(trace), operation)?
            .await
            .map_err(|_| OwnerSubmitError::Closed)
    }

    #[cfg(test)]
    pub(crate) fn view_blocking(&self) -> Result<AuthorityView, OwnerSubmitError> {
        self.blocking(AdmissionClass::Normal, "view", |state| state.view())
    }

    #[cfg(test)]
    pub(crate) fn hold_for_test(
        &self,
    ) -> Result<(Arc<std::sync::Barrier>, oneshot::Receiver<()>), OwnerSubmitError> {
        let barrier = Arc::new(std::sync::Barrier::new(2));
        let actor_barrier = Arc::clone(&barrier);
        let receiver = self.submit(AdmissionClass::Normal, "test_hold", move |_| {
            actor_barrier.wait();
        })?;
        while self.mailbox.queued_counts().0 != 0 {
            thread::yield_now();
        }
        Ok((barrier, receiver))
    }

    #[cfg(test)]
    pub(crate) fn fill_safety_lane_for_test(&self) -> usize {
        let mut admitted = 0;
        loop {
            match self.mailbox.push(MailboxEntry {
                class: AdmissionClass::LocalSafety,
                trace: None,
                task: Box::new(|_| {}),
            }) {
                Ok(()) => admitted += 1,
                Err(OwnerSubmitError::Full | OwnerSubmitError::Closed) => return admitted,
            }
        }
    }

    pub(crate) async fn view(&self) -> Result<AuthorityView, OwnerSubmitError> {
        self.asynchronous(AdmissionClass::Normal, "view", |state| state.view())
            .await
    }

    pub(crate) async fn native_output_status(
        &self,
        observation: NativeOutputCleanupObservation,
    ) -> Result<NativeOutputStatus, OwnerSubmitError> {
        self.asynchronous(
            AdmissionClass::Normal,
            "native_output_status",
            move |state| state.native_output_status(observation),
        )
        .await
    }

    pub(crate) async fn begin_native_output_enumerate(
        &self,
        observation: NativeOutputCleanupObservation,
    ) -> Result<Result<NativeOutputTicket, NativeOutputCommandError>, OwnerSubmitError> {
        self.asynchronous(
            AdmissionClass::Normal,
            "native_output_begin_enumerate",
            move |state| state.begin_native_output_enumerate(observation),
        )
        .await
    }

    pub(crate) async fn begin_native_output_reserve(
        &self,
        observation: NativeOutputCleanupObservation,
        request: NativeOutputReserveRequest,
    ) -> Result<
        Result<(NativeOutputTicket, NativeOutputSelection), NativeOutputCommandError>,
        OwnerSubmitError,
    > {
        self.asynchronous(
            AdmissionClass::Normal,
            "native_output_begin_reserve",
            move |state| state.begin_native_output_reserve(observation, request),
        )
        .await
    }

    pub(crate) async fn complete_native_output_enumerate(
        &self,
        ticket: NativeOutputTicket,
        result: Result<u64, NativeOutputCommandError>,
    ) -> Result<Result<NativeOutputStatus, NativeOutputCommandError>, OwnerSubmitError> {
        self.asynchronous(
            AdmissionClass::LocalSafety,
            "native_output_complete_enumerate",
            move |state| state.complete_native_output_enumerate(ticket, result),
        )
        .await
    }

    pub(crate) async fn complete_native_output_reserve(
        &self,
        ticket: NativeOutputTicket,
        result: Result<u64, NativeOutputCommandError>,
    ) -> Result<Result<NativeOutputStatus, NativeOutputCommandError>, OwnerSubmitError> {
        self.asynchronous(
            AdmissionClass::LocalSafety,
            "native_output_complete_reserve",
            move |state| state.complete_native_output_reserve(ticket, result),
        )
        .await
    }

    pub(crate) async fn release_native_output(
        &self,
        observation: NativeOutputCleanupObservation,
        request: NativeOutputReleaseRequest,
    ) -> Result<Result<NativeOutputStatus, NativeOutputCommandError>, OwnerSubmitError> {
        self.asynchronous(
            AdmissionClass::LocalSafety,
            "native_output_release",
            move |state| state.release_native_output(observation, request),
        )
        .await
    }

    pub(crate) async fn disable_native_output(
        &self,
        observation: NativeOutputCleanupObservation,
    ) -> Result<Result<NativeOutputStatus, NativeOutputCommandError>, OwnerSubmitError> {
        self.asynchronous(
            AdmissionClass::LocalSafety,
            "native_output_disable",
            move |state| state.disable_native_output(observation),
        )
        .await
    }

    #[cfg(test)]
    pub(crate) fn dispatch_local_blocking(
        &self,
        action: Action,
        args: Value,
    ) -> Result<Result<Applied, String>, OwnerSubmitError> {
        let class = local_action_class(action);
        self.blocking(class, "dispatch_local", move |state| {
            state.dispatch_local(action, args, class)
        })
    }

    #[cfg(test)]
    pub(crate) async fn dispatch_local(
        &self,
        action: Action,
        args: Value,
    ) -> Result<Result<Applied, String>, OwnerSubmitError> {
        let class = local_action_class(action);
        self.asynchronous(class, "dispatch_local", move |state| {
            state.dispatch_local(action, args, class)
        })
        .await
    }

    pub(crate) async fn dispatch_local_traced(
        &self,
        action: Action,
        args: Value,
        trace: LatencyTrace,
    ) -> Result<Result<Applied, String>, OwnerSubmitError> {
        let class = local_action_class(action);
        let operation_trace = trace.clone();
        self.asynchronous_traced(class, "dispatch_local", trace, move |state| {
            state.dispatch_local_traced(action, args, class, Some(&operation_trace))
        })
        .await
    }

    #[cfg(test)]
    fn dispatch_local_traced_blocking(
        &self,
        action: Action,
        args: Value,
        trace: LatencyTrace,
    ) -> Result<Result<Applied, String>, OwnerSubmitError> {
        let class = local_action_class(action);
        let operation_trace = trace.clone();
        self.blocking_traced(class, "dispatch_local", trace, move |state| {
            state.dispatch_local_traced(action, args, class, Some(&operation_trace))
        })
    }

    #[cfg(test)]
    pub(crate) fn inspection_source_blocking(
        &self,
    ) -> Result<Result<PreparedExecutionSource, &'static str>, OwnerSubmitError> {
        self.blocking(AdmissionClass::Normal, "inspection_source", |state| {
            state.inspection_source()
        })
    }

    pub(crate) async fn inspection_source(
        &self,
    ) -> Result<Result<PreparedExecutionSource, &'static str>, OwnerSubmitError> {
        self.asynchronous(AdmissionClass::Normal, "inspection_source", |state| {
            state.inspection_source()
        })
        .await
    }

    #[cfg(test)]
    pub(crate) fn cache_compiled_blocking(
        &self,
        compiled: CompiledPreparedExecution,
    ) -> Result<Result<PreparedExecutionSummary, &'static str>, OwnerSubmitError> {
        self.blocking(AdmissionClass::Normal, "cache_compiled", move |state| {
            state.cache_compiled(compiled)
        })
    }

    pub(crate) async fn cache_compiled(
        &self,
        compiled: CompiledPreparedExecution,
    ) -> Result<Result<PreparedExecutionSummary, &'static str>, OwnerSubmitError> {
        self.asynchronous(AdmissionClass::Normal, "cache_compiled", move |state| {
            state.cache_compiled(compiled)
        })
        .await
    }

    #[cfg(test)]
    pub(crate) fn prepared_audio_source_blocking(
        &self,
        block_ordinal: u32,
    ) -> Result<Result<PreparedAudioLookup, &'static str>, OwnerSubmitError> {
        self.blocking(
            AdmissionClass::Normal,
            "prepared_audio_source",
            move |state| state.prepared_audio_source(block_ordinal),
        )
    }

    pub(crate) async fn prepared_audio_source(
        &self,
        block_ordinal: u32,
    ) -> Result<Result<PreparedAudioLookup, &'static str>, OwnerSubmitError> {
        self.asynchronous(
            AdmissionClass::Normal,
            "prepared_audio_source",
            move |state| state.prepared_audio_source(block_ordinal),
        )
        .await
    }

    #[cfg(test)]
    pub(crate) fn cache_prepared_audio_blocking(
        &self,
        candidate: PreparedAudioCandidate,
    ) -> Result<Result<PreparedAudioSummary, &'static str>, OwnerSubmitError> {
        self.blocking(
            AdmissionClass::Normal,
            "cache_prepared_audio",
            move |state| state.cache_prepared_audio(candidate),
        )
    }

    pub(crate) async fn cache_prepared_audio(
        &self,
        candidate: PreparedAudioCandidate,
    ) -> Result<Result<PreparedAudioSummary, &'static str>, OwnerSubmitError> {
        self.asynchronous(
            AdmissionClass::Normal,
            "cache_prepared_audio",
            move |state| state.cache_prepared_audio(candidate),
        )
        .await
    }

    #[cfg(test)]
    pub(crate) fn adopt_verified_session_blocking(
        &self,
        verified: VerifiedPreparedSession,
        package: VerifiedPackageSummary,
        next_secret: PairingSecret,
        next_session_id: String,
        next_epoch: u64,
    ) -> Result<Result<RunnerSnapshot, &'static str>, OwnerSubmitError> {
        self.blocking(
            AdmissionClass::Normal,
            "adopt_verified_session",
            move |state| {
                state.adopt_verified_session(
                    verified,
                    package,
                    next_secret,
                    next_session_id,
                    next_epoch,
                )
            },
        )
    }

    pub(crate) async fn adopt_verified_session(
        &self,
        verified: VerifiedPreparedSession,
        package: VerifiedPackageSummary,
        next_secret: PairingSecret,
        next_session_id: String,
        next_epoch: u64,
    ) -> Result<Result<RunnerSnapshot, &'static str>, OwnerSubmitError> {
        self.asynchronous(
            AdmissionClass::Normal,
            "adopt_verified_session",
            move |state| {
                state.adopt_verified_session(
                    verified,
                    package,
                    next_secret,
                    next_session_id,
                    next_epoch,
                )
            },
        )
        .await
    }

    #[cfg(test)]
    pub(crate) fn claim_webview_blocking(
        &self,
        session_id: String,
        controller_id: String,
        owner_token: String,
        accepted_scopes: BTreeSet<Scope>,
        ready_sequence: u32,
    ) -> Result<Result<RemoteSessionLeaseReceipt, RemoteSessionError>, OwnerSubmitError> {
        self.blocking(AdmissionClass::Normal, "claim_webview", move |state| {
            state.claim_webview(
                session_id,
                controller_id,
                owner_token,
                accepted_scopes,
                ready_sequence,
            )
        })
    }

    pub(crate) async fn claim_webview(
        &self,
        session_id: String,
        controller_id: String,
        owner_token: String,
        accepted_scopes: BTreeSet<Scope>,
        ready_sequence: u32,
    ) -> Result<Result<RemoteSessionLeaseReceipt, RemoteSessionError>, OwnerSubmitError> {
        self.asynchronous(AdmissionClass::Normal, "claim_webview", move |state| {
            state.claim_webview(
                session_id,
                controller_id,
                owner_token,
                accepted_scopes,
                ready_sequence,
            )
        })
        .await
    }

    #[cfg(test)]
    pub(crate) fn renew_webview_blocking(
        &self,
        session_id: String,
        owner_token: String,
        control_sequence: u32,
    ) -> Result<Result<RemoteSessionLeaseReceipt, RemoteSessionError>, OwnerSubmitError> {
        self.blocking(AdmissionClass::Normal, "renew_webview", move |state| {
            state.renew_webview(session_id, owner_token, control_sequence)
        })
    }

    pub(crate) async fn renew_webview(
        &self,
        session_id: String,
        owner_token: String,
        control_sequence: u32,
    ) -> Result<Result<RemoteSessionLeaseReceipt, RemoteSessionError>, OwnerSubmitError> {
        self.asynchronous(AdmissionClass::Normal, "renew_webview", move |state| {
            state.renew_webview(session_id, owner_token, control_sequence)
        })
        .await
    }

    #[cfg(test)]
    pub(crate) fn dispatch_webview_blocking(
        &self,
        session_id: String,
        owner_token: String,
        control_sequence: u32,
        command: pps_contracts::CommandBody,
    ) -> Result<Result<RemoteApplied, RemoteSessionError>, OwnerSubmitError> {
        self.blocking(AdmissionClass::Normal, "dispatch_webview", move |state| {
            state.dispatch_webview(session_id, owner_token, control_sequence, command)
        })
    }

    pub(crate) async fn dispatch_webview_traced(
        &self,
        session_id: String,
        owner_token: String,
        control_sequence: u32,
        command: pps_contracts::CommandBody,
        trace: LatencyTrace,
    ) -> Result<Result<RemoteApplied, RemoteSessionError>, OwnerSubmitError> {
        let operation_trace = trace.clone();
        self.asynchronous_traced(
            AdmissionClass::Normal,
            "dispatch_webview",
            trace,
            move |state| {
                state.dispatch_webview_traced(
                    session_id,
                    owner_token,
                    control_sequence,
                    command,
                    Some(&operation_trace),
                )
            },
        )
        .await
    }

    #[cfg(test)]
    pub(crate) fn revoke_webview_blocking(
        &self,
        session_id: String,
        owner_token: String,
    ) -> Result<Result<RemoteSessionRevocationReceipt, RemoteSessionError>, OwnerSubmitError> {
        self.blocking(AdmissionClass::Normal, "revoke_webview", move |state| {
            state.revoke_webview(session_id, owner_token)
        })
    }

    pub(crate) async fn revoke_webview(
        &self,
        session_id: String,
        owner_token: String,
    ) -> Result<Result<RemoteSessionRevocationReceipt, RemoteSessionError>, OwnerSubmitError> {
        self.asynchronous(AdmissionClass::Normal, "revoke_webview", move |state| {
            state.revoke_webview(session_id, owner_token)
        })
        .await
    }

    pub(crate) async fn claim_lan(
        &self,
        session_id: String,
        controller_id: String,
        owner_token: String,
        accepted_scopes: BTreeSet<Scope>,
    ) -> Result<Result<LanOwnerReceipt, RemoteSessionError>, OwnerSubmitError> {
        self.asynchronous(AdmissionClass::Normal, "claim_lan", move |state| {
            state.claim_lan(session_id, controller_id, owner_token, accepted_scopes)
        })
        .await
    }

    pub(crate) async fn renew_lan(
        &self,
        identity: RemoteOwnerIdentity,
    ) -> Result<Result<bool, String>, OwnerSubmitError> {
        self.asynchronous(AdmissionClass::Normal, "renew_lan", move |state| {
            state.renew_lan(identity)
        })
        .await
    }

    pub(crate) async fn lan_publication_snapshot(
        &self,
        identity: RemoteOwnerIdentity,
    ) -> Result<Option<RemoteRunnerSnapshot>, OwnerSubmitError> {
        self.asynchronous(
            AdmissionClass::Normal,
            "lan_publication_snapshot",
            move |state| state.lan_publication_snapshot(&identity),
        )
        .await
    }

    pub(crate) async fn dispatch_lan_traced(
        &self,
        identity: RemoteOwnerIdentity,
        control_sequence: u32,
        command: pps_contracts::CommandBody,
        trace: LatencyTrace,
    ) -> Result<Result<RemoteApplied, String>, OwnerSubmitError> {
        let operation_trace = trace.clone();
        self.asynchronous_traced(
            AdmissionClass::Normal,
            "dispatch_lan",
            trace,
            move |state| {
                state.dispatch_lan_traced(
                    identity,
                    control_sequence,
                    command,
                    Some(&operation_trace),
                )
            },
        )
        .await
    }

    pub(crate) async fn revoke_lan(
        &self,
        identity: RemoteOwnerIdentity,
        connection_state: &'static str,
    ) -> Result<Result<bool, String>, OwnerSubmitError> {
        self.submit_lan_revoke(identity, connection_state, "revoke_lan")?
            .await
            .map_err(|_| OwnerSubmitError::Closed)
    }

    pub(crate) fn revoke_lan_detached(
        &self,
        identity: RemoteOwnerIdentity,
        connection_state: &'static str,
    ) {
        let _ = self.submit_lan_revoke(identity, connection_state, "revoke_lan_detached");
    }

    fn submit_lan_revoke(
        &self,
        identity: RemoteOwnerIdentity,
        connection_state: &'static str,
        label: &'static str,
    ) -> Result<oneshot::Receiver<Result<bool, String>>, OwnerSubmitError> {
        self.submit(AdmissionClass::LocalSafety, label, move |state| {
            state.revoke_lan(identity, connection_state)
        })
    }

    #[cfg(test)]
    pub(crate) fn configure_remote_blocking(
        &self,
        enabled: bool,
        allow_abort: bool,
        next_secret: PairingSecret,
        next_session_id: String,
        next_epoch: u64,
    ) -> Result<Result<(), &'static str>, OwnerSubmitError> {
        self.blocking(AdmissionClass::Normal, "configure_remote", move |state| {
            state.configure_remote(
                enabled,
                allow_abort,
                next_secret,
                next_session_id,
                next_epoch,
            )
        })
    }

    pub(crate) async fn configure_remote(
        &self,
        enabled: bool,
        allow_abort: bool,
        next_secret: PairingSecret,
        next_session_id: String,
        next_epoch: u64,
    ) -> Result<Result<(), &'static str>, OwnerSubmitError> {
        self.asynchronous(AdmissionClass::Normal, "configure_remote", move |state| {
            state.configure_remote(
                enabled,
                allow_abort,
                next_secret,
                next_session_id,
                next_epoch,
            )
        })
        .await
    }

    #[cfg(test)]
    pub(crate) fn rotate_pairing_blocking(
        &self,
        next_secret: PairingSecret,
        next_session_id: String,
        next_epoch: u64,
    ) -> Result<Result<(), &'static str>, OwnerSubmitError> {
        self.blocking(AdmissionClass::Normal, "rotate_pairing", move |state| {
            state.rotate_pairing(next_secret, next_session_id, next_epoch)
        })
    }

    pub(crate) async fn rotate_pairing(
        &self,
        next_secret: PairingSecret,
        next_session_id: String,
        next_epoch: u64,
    ) -> Result<Result<(), &'static str>, OwnerSubmitError> {
        self.asynchronous(AdmissionClass::Normal, "rotate_pairing", move |state| {
            state.rotate_pairing(next_secret, next_session_id, next_epoch)
        })
        .await
    }

    #[cfg(test)]
    pub(crate) fn force_owner_expiry(&self) {
        let _ = self.blocking(AdmissionClass::LocalSafety, "force_owner_expiry", |state| {
            if let Some(owner) = state.remote_owner.as_mut() {
                owner.lease_deadline = Instant::now() - Duration::from_millis(1);
            }
        });
    }

    #[cfg(test)]
    pub(crate) fn advance_run_generation_for_test(&self) {
        self.blocking(AdmissionClass::Normal, "advance_run_generation", |state| {
            state.run_generation = state.run_generation.checked_add(1).unwrap();
            state.invalidate_prepared_audio();
        })
        .expect("test authority remains available");
    }

    #[cfg(test)]
    pub(crate) fn test_view(&self) -> OwnerTestView {
        self.blocking(AdmissionClass::Normal, "test_view", |state| OwnerTestView {
            active_controller: state
                .remote_owner
                .as_ref()
                .map(RemoteOwner::active_controller),
            manifest_path: state
                .retained_session
                .as_ref()
                .map(|retained| retained.receipt.manifest_path().to_path_buf()),
            package_generation: state.package_generation,
            compiled_schedule_count: state
                .compiled_execution
                .as_ref()
                .map(|compiled| compiled.schedules().len()),
            prepared_audio_block_ordinal: state
                .prepared_audio
                .as_ref()
                .map(|cached| cached.candidate.media().fence().block_ordinal()),
            prepared_audio_decoded_bytes: state
                .prepared_audio
                .as_ref()
                .and_then(|cached| cached.candidate.decoded_bytes().ok()),
            prepared_output_plan_event_count: state
                .prepared_audio
                .as_ref()
                .map(|cached| cached.candidate.playback_plan().scheduled_events().len()),
            prepared_output_plan_run_generation: state
                .prepared_audio
                .as_ref()
                .map(|cached| cached.candidate.playback_plan().fence().run_generation()),
            compiled_schedule_strong_count: state
                .compiled_execution
                .as_ref()
                .and_then(|compiled| compiled.schedules().first())
                .map(Arc::strong_count),
            retained_session_strong_count: state
                .retained_session
                .as_ref()
                .map(|retained| Arc::strong_count(&retained.receipt)),
            native_output_status: state.native_output.status(),
        })
        .expect("test authority remains available")
    }
}

impl Drop for ExecutionOwner {
    fn drop(&mut self) {
        self.mailbox.request_shutdown();
        if let Some(handle) = self
            .thread
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .take()
        {
            let _ = handle.join();
        }
    }
}

fn authority_loop(mailbox: &Mailbox, state: &mut OwnerState) {
    loop {
        if mailbox.should_stop() {
            break;
        }
        // Deadman processing is deliberately ahead of every dequeue, including
        // when ordinary traffic keeps the mailbox continuously non-empty.
        state.expire_deadman_if_due();
        if mailbox.should_stop() {
            break;
        }
        if let Some(entry) = mailbox.pop() {
            if let Some(trace) = entry.trace.as_ref() {
                trace.mark(LatencyStage::AuthorityDequeue);
            }
            (entry.task)(state);
            continue;
        }
        mailbox.wait(state.next_deadman_delay());
    }
}

fn local_action_class(action: Action) -> AdmissionClass {
    if matches!(
        action,
        Action::RunPause | Action::RunStop | Action::RunAbort | Action::TargetDisarm
    ) {
        AdmissionClass::LocalSafety
    } else {
        AdmissionClass::Normal
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::latency_diagnostics::{LatencyRoute, NativeLatencyDiagnostics, TraceOutcome};
    use pps_contracts::AppliedStatus;
    use std::sync::Barrier;

    fn owner(lease: Duration) -> ExecutionOwner {
        let (state_tx, _) = broadcast::channel(64);
        let diagnostics = NativeLatencyDiagnostics::with_mailbox_limits(
            MAILBOX_CAPACITY,
            NORMAL_MAILBOX_CAPACITY,
        );
        ExecutionOwner::start_with_lease(
            "owner-test-target".to_owned(),
            "desktop-tauri-preview",
            7,
            TimingTier::DesktopPreview,
            RemoteConfig {
                enabled: true,
                allow_abort: false,
                secret: PairingSecret::generate(),
                session_id: "session_owner_test".to_owned(),
            },
            state_tx,
            OwnerStartConfiguration {
                lease_duration: lease,
                mailbox_diagnostics: diagnostics.authority_mailbox(),
                native_output: NativeOutputAuthority::new(
                    crate::native_output::NativeOutputInvalidator::inert(),
                ),
            },
        )
        .unwrap()
    }

    fn owner_with_state_rx(
        lease: Duration,
    ) -> (ExecutionOwner, broadcast::Receiver<RunnerSnapshot>) {
        let (state_tx, state_rx) = broadcast::channel(64);
        let diagnostics = NativeLatencyDiagnostics::with_mailbox_limits(
            MAILBOX_CAPACITY,
            NORMAL_MAILBOX_CAPACITY,
        );
        let owner = ExecutionOwner::start_with_lease(
            "owner-test-target".to_owned(),
            "desktop-tauri-preview",
            7,
            TimingTier::DesktopPreview,
            RemoteConfig {
                enabled: true,
                allow_abort: false,
                secret: PairingSecret::generate(),
                session_id: "session_owner_test".to_owned(),
            },
            state_tx,
            OwnerStartConfiguration {
                lease_duration: lease,
                mailbox_diagnostics: diagnostics.authority_mailbox(),
                native_output: NativeOutputAuthority::new(
                    crate::native_output::NativeOutputInvalidator::inert(),
                ),
            },
        )
        .unwrap();
        (owner, state_rx)
    }

    fn wait_for_actor_stop(owner: &ExecutionOwner) {
        let deadline = Instant::now() + Duration::from_secs(2);
        while owner._alive.load(Ordering::Acquire) {
            assert!(
                Instant::now() < deadline,
                "authority actor did not stop after shutdown"
            );
            thread::yield_now();
        }
    }

    fn newest_snapshot(receiver: &mut broadcast::Receiver<RunnerSnapshot>) -> RunnerSnapshot {
        let mut newest = receiver
            .try_recv()
            .expect("at least one authority snapshot was published");
        while let Ok(snapshot) = receiver.try_recv() {
            newest = snapshot;
        }
        newest
    }

    fn block_authority(owner: &ExecutionOwner) -> (Arc<Barrier>, oneshot::Receiver<()>) {
        let barrier = Arc::new(Barrier::new(2));
        let actor_barrier = Arc::clone(&barrier);
        let receiver = owner
            .submit(AdmissionClass::Normal, "test_block", move |_| {
                actor_barrier.wait();
            })
            .unwrap();
        while owner.mailbox.queued_counts().0 != 0 {
            thread::yield_now();
        }
        (barrier, receiver)
    }

    fn prepare_ready_demo(state: &mut OwnerState) {
        assert_eq!(
            state
                .dispatch_local(
                    Action::PackagePrepareDemo,
                    serde_json::json!({}),
                    AdmissionClass::Normal,
                )
                .unwrap()
                .status,
            AppliedStatus::Accepted
        );
        assert_eq!(
            state
                .dispatch_local(
                    Action::SetupSubmit,
                    serde_json::json!({
                        "participant_code": "P001",
                        "age": 30,
                        "handedness": "right",
                        "gender": "other",
                        "name_sharing_opt_in": false,
                        "part_labels": {"1": "A", "2": "B"}
                    }),
                    AdmissionClass::Normal,
                )
                .unwrap()
                .status,
            AppliedStatus::Accepted
        );
        state
            .dispatch_local(
                Action::TargetArm,
                serde_json::json!({}),
                AdmissionClass::Normal,
            )
            .unwrap();
        assert_eq!(state.core.snapshot().run.phase, RunnerPhase::Ready);
    }

    fn prepare_running_demo(state: &mut OwnerState) {
        prepare_ready_demo(state);
        let started = state
            .dispatch_local(
                Action::PartStart,
                serde_json::json!({"part_number": 1}),
                AdmissionClass::Normal,
            )
            .unwrap();
        assert_eq!(started.status, AppliedStatus::Accepted);
        assert_eq!(started.snapshot.run.phase, RunnerPhase::Running);
    }

    fn empty_mailbox_entry(class: AdmissionClass) -> MailboxEntry {
        MailboxEntry {
            class,
            trace: None,
            task: Box::new(|_| {}),
        }
    }

    #[test]
    fn mailbox_pressure_tracks_class_interleaving_and_each_dequeue_once() {
        let diagnostics = NativeLatencyDiagnostics::with_mailbox_limits(
            MAILBOX_CAPACITY,
            NORMAL_MAILBOX_CAPACITY,
        );
        let mailbox = Mailbox::new(diagnostics.authority_mailbox());
        mailbox
            .push(empty_mailbox_entry(AdmissionClass::Normal))
            .unwrap();
        mailbox
            .push(empty_mailbox_entry(AdmissionClass::LocalSafety))
            .unwrap();
        mailbox
            .push(empty_mailbox_entry(AdmissionClass::Normal))
            .unwrap();

        let admitted = diagnostics.summary().authority_mailbox;
        assert_eq!(admitted.ordinary.latest_observed_depth, 2);
        assert_eq!(admitted.safety.latest_observed_depth, 1);
        assert_eq!(admitted.ordinary.high_water_mark, 2);
        assert_eq!(admitted.safety.high_water_mark, 1);

        assert_eq!(mailbox.pop().unwrap().class, AdmissionClass::Normal);
        let after_first = diagnostics.summary().authority_mailbox;
        assert_eq!(after_first.ordinary.latest_observed_depth, 1);
        assert_eq!(after_first.safety.latest_observed_depth, 1);

        assert_eq!(mailbox.pop().unwrap().class, AdmissionClass::LocalSafety);
        let after_second = diagnostics.summary().authority_mailbox;
        assert_eq!(after_second.ordinary.latest_observed_depth, 1);
        assert_eq!(after_second.safety.latest_observed_depth, 0);

        assert_eq!(mailbox.pop().unwrap().class, AdmissionClass::Normal);
        assert!(mailbox.pop().is_none());
        let empty = diagnostics.summary().authority_mailbox;
        assert_eq!(empty.ordinary.latest_observed_depth, 0);
        assert_eq!(empty.safety.latest_observed_depth, 0);
        assert_eq!(empty.ordinary.successful_admission_count, 2);
        assert_eq!(empty.safety.successful_admission_count, 1);
    }

    #[test]
    fn mailbox_pressure_saturation_and_shutdown_are_bounded_and_exact() {
        let diagnostics = NativeLatencyDiagnostics::with_mailbox_limits(
            MAILBOX_CAPACITY,
            NORMAL_MAILBOX_CAPACITY,
        );
        let mailbox = Mailbox::new(diagnostics.authority_mailbox());
        for _ in 0..NORMAL_MAILBOX_CAPACITY {
            mailbox
                .push(empty_mailbox_entry(AdmissionClass::Normal))
                .unwrap();
        }
        assert!(matches!(
            mailbox.push(empty_mailbox_entry(AdmissionClass::Normal)),
            Err(OwnerSubmitError::Full)
        ));
        for _ in 0..LOCAL_SAFETY_RESERVE {
            mailbox
                .push(empty_mailbox_entry(AdmissionClass::LocalSafety))
                .unwrap();
        }
        assert!(matches!(
            mailbox.push(empty_mailbox_entry(AdmissionClass::LocalSafety)),
            Err(OwnerSubmitError::Full)
        ));

        let full = diagnostics.summary().authority_mailbox;
        assert_eq!(
            full.ordinary.latest_observed_depth,
            NORMAL_MAILBOX_CAPACITY as u64
        );
        assert_eq!(
            full.safety.latest_observed_depth,
            LOCAL_SAFETY_RESERVE as u64
        );
        assert_eq!(
            full.ordinary.high_water_mark,
            NORMAL_MAILBOX_CAPACITY as u64
        );
        assert_eq!(full.safety.high_water_mark, LOCAL_SAFETY_RESERVE as u64);
        assert_eq!(full.ordinary.queue_full_reject_count, 1);
        assert_eq!(full.safety.queue_full_reject_count, 1);
        assert_eq!(full.ordinary.depth_after_successful_admission.p50, 28);
        assert_eq!(full.ordinary.depth_after_successful_admission.p95, 54);
        assert_eq!(
            full.ordinary.depth_after_successful_admission.worst,
            NORMAL_MAILBOX_CAPACITY as u64
        );
        assert_eq!(full.safety.depth_after_successful_admission.p50, 4);
        assert_eq!(
            full.safety.depth_after_successful_admission.worst,
            LOCAL_SAFETY_RESERVE as u64
        );

        mailbox.request_shutdown();
        mailbox.request_shutdown();
        assert!(matches!(
            mailbox.push(empty_mailbox_entry(AdmissionClass::LocalSafety)),
            Err(OwnerSubmitError::Closed)
        ));
        let shutdown = diagnostics.summary().authority_mailbox;
        assert_eq!(shutdown.ordinary.latest_observed_depth, 0);
        assert_eq!(shutdown.safety.latest_observed_depth, 0);
        assert_eq!(
            shutdown.ordinary.successful_admission_count,
            NORMAL_MAILBOX_CAPACITY as u64
        );
        assert_eq!(
            shutdown.safety.successful_admission_count,
            LOCAL_SAFETY_RESERVE as u64
        );
        assert_eq!(shutdown.ordinary.queue_full_reject_count, 1);
        assert_eq!(shutdown.safety.queue_full_reject_count, 1);
    }

    #[test]
    fn normal_saturation_preserves_the_local_safety_reserve() {
        let owner = owner(Duration::from_secs(5));
        let (barrier, blocked) = block_authority(&owner);
        let mut normal_replies = Vec::new();
        for _ in 0..NORMAL_MAILBOX_CAPACITY {
            normal_replies.push(
                owner
                    .submit(AdmissionClass::Normal, "normal", |_| ())
                    .unwrap(),
            );
        }
        assert!(matches!(
            owner.submit(AdmissionClass::Normal, "overflow", |_| ()),
            Err(OwnerSubmitError::Full)
        ));
        let mut safety_replies = Vec::new();
        for _ in 0..LOCAL_SAFETY_RESERVE {
            safety_replies.push(
                owner
                    .submit(AdmissionClass::LocalSafety, "safety", |_| ())
                    .unwrap(),
            );
        }
        assert_eq!(owner.mailbox.queued_counts(), (MAILBOX_CAPACITY, 56));
        assert!(matches!(
            owner.submit(AdmissionClass::LocalSafety, "overflow", |_| ()),
            Err(OwnerSubmitError::Full)
        ));
        barrier.wait();
        blocked.blocking_recv().unwrap();
        for reply in normal_replies.into_iter().chain(safety_replies) {
            reply.blocking_recv().unwrap();
        }
    }

    #[test]
    fn normal_saturation_cannot_block_exact_lan_owner_cleanup_admission() {
        let owner = owner(Duration::from_secs(5));
        let claim = owner
            .blocking(AdmissionClass::Normal, "claim_lan", |state| {
                state.claim_lan(
                    "session_owner_test".to_owned(),
                    "controller_cleanup".to_owned(),
                    "owner_cleanup_token".to_owned(),
                    Scope::DEFAULT_REMOTE.into_iter().collect(),
                )
            })
            .unwrap()
            .unwrap();
        owner
            .blocking(AdmissionClass::Normal, "prepare_running", |state| {
                prepare_running_demo(state);
            })
            .unwrap();

        let (barrier, blocked) = block_authority(&owner);
        let mut normal_replies = Vec::new();
        for _ in 0..NORMAL_MAILBOX_CAPACITY {
            normal_replies.push(
                owner
                    .submit(AdmissionClass::Normal, "normal", |_| ())
                    .unwrap(),
            );
        }
        assert!(matches!(
            owner.submit(AdmissionClass::Normal, "overflow", |_| ()),
            Err(OwnerSubmitError::Full)
        ));

        let cleanup = owner
            .submit_lan_revoke(
                claim.identity,
                "remote_transport_unresponsive",
                "test_lan_cleanup",
            )
            .expect("exact-owner cleanup uses the reserved local-safety admission class");
        assert_eq!(
            owner.mailbox.queued_counts(),
            (NORMAL_MAILBOX_CAPACITY + 1, NORMAL_MAILBOX_CAPACITY)
        );

        barrier.wait();
        blocked.blocking_recv().unwrap();
        assert!(cleanup.blocking_recv().unwrap().unwrap());
        for reply in normal_replies {
            reply.blocking_recv().unwrap();
        }

        let view = owner.view_blocking().unwrap();
        assert!(view.active_controller.is_none());
        assert_eq!(view.snapshot.run.phase, RunnerPhase::Paused);
        assert_eq!(
            view.snapshot.connection_state,
            "remote_transport_unresponsive"
        );
    }

    #[test]
    fn administrative_saturation_cannot_block_emergency_admission_or_deadman() {
        let owner = owner(Duration::from_secs(5));
        owner
            .claim_webview_blocking(
                "session_owner_test".to_owned(),
                "controller_saturated".to_owned(),
                "owner_saturated_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
                2,
            )
            .unwrap()
            .unwrap();
        owner
            .blocking(AdmissionClass::Normal, "prepare_running", |state| {
                prepare_running_demo(state);
            })
            .unwrap();

        let barrier = Arc::new(Barrier::new(2));
        let actor_barrier = Arc::clone(&barrier);
        let blocked = owner
            .submit(AdmissionClass::Normal, "expire_then_block", move |state| {
                state.remote_owner.as_mut().unwrap().lease_deadline =
                    Instant::now() - Duration::from_millis(1);
                actor_barrier.wait();
            })
            .unwrap();
        while owner.mailbox.queued_counts().0 != 0 {
            thread::yield_now();
        }

        let first_admin = owner
            .submit(AdmissionClass::Normal, "admin_first", |state| {
                (
                    state.remote_owner.is_none(),
                    state.core.snapshot().run.phase,
                )
            })
            .unwrap();
        let mut remaining_admin = Vec::new();
        for _ in 1..NORMAL_MAILBOX_CAPACITY {
            remaining_admin.push(
                owner
                    .submit(AdmissionClass::Normal, "admin", |_| ())
                    .unwrap(),
            );
        }
        assert!(matches!(
            owner.submit(AdmissionClass::Normal, "admin_overflow", |_| ()),
            Err(OwnerSubmitError::Full)
        ));

        let emergency = owner
            .submit(AdmissionClass::LocalSafety, "emergency_abort", |state| {
                state.dispatch_local(
                    Action::RunAbort,
                    serde_json::json!({}),
                    AdmissionClass::LocalSafety,
                )
            })
            .expect("the eight-slot emergency reserve remains available");

        barrier.wait();
        blocked.blocking_recv().unwrap();
        let (revoked_before_admin, phase_before_admin) = first_admin.blocking_recv().unwrap();
        assert!(revoked_before_admin);
        assert_eq!(phase_before_admin, RunnerPhase::Paused);
        for reply in remaining_admin {
            reply.blocking_recv().unwrap();
        }
        let emergency = emergency.blocking_recv().unwrap().unwrap();
        assert_eq!(emergency.snapshot.run.phase, RunnerPhase::Interrupted);
        assert!(!emergency.snapshot.safety.local_armed);
    }

    #[test]
    fn fifo_requests_linearize_mutation_before_later_reads() {
        let owner = owner(Duration::from_secs(5));
        let dispatch = owner
            .submit(AdmissionClass::Normal, "prepare", |state| {
                state.dispatch_local(
                    Action::PackagePrepareDemo,
                    serde_json::json!({}),
                    AdmissionClass::Normal,
                )
            })
            .unwrap();
        let snapshot = owner
            .submit(AdmissionClass::Normal, "snapshot", |state| {
                state.core.snapshot()
            })
            .unwrap();
        dispatch.blocking_recv().unwrap().unwrap();
        assert!(snapshot.blocking_recv().unwrap().package_verified);
    }

    #[test]
    fn dropped_reply_does_not_undo_and_same_command_id_is_idempotent() {
        let owner = owner(Duration::from_secs(5));
        owner
            .claim_webview_blocking(
                "session_owner_test".to_owned(),
                "controller_retry".to_owned(),
                "owner_retry_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
                2,
            )
            .unwrap()
            .unwrap();
        owner
            .blocking(AdmissionClass::Normal, "prepare_running", |state| {
                prepare_running_demo(state);
            })
            .unwrap();

        let request = owner
            .blocking(AdmissionClass::Normal, "retry_request", |state| {
                CommandRequest {
                    id: "dropped-reply-command".to_owned(),
                    epoch: state.core.epoch(),
                    sequence: 3,
                    expected_revision: Some(state.core.revision()),
                    scope: Scope::SessionTransport,
                    action: Action::RunPause,
                    args: serde_json::json!({}),
                }
            })
            .unwrap();
        let first_request = request.clone();
        let dropped = owner
            .submit(AdmissionClass::Normal, "dropped_reply", move |state| {
                let remote = state.remote_owner.clone().unwrap();
                state.dispatch_remote(&remote, first_request)
            })
            .unwrap();
        drop(dropped);

        let after_first = owner
            .blocking(AdmissionClass::Normal, "after_dropped_reply", |state| {
                (
                    state.core.snapshot(),
                    state.ledger.records().len(),
                    state.remote_owner.clone().unwrap(),
                )
            })
            .unwrap();
        assert_eq!(after_first.0.run.phase, RunnerPhase::Paused);
        let first_snapshot = after_first.0;
        let first_ledger_count = after_first.1;
        let retry_owner = after_first.2;

        let retry = owner
            .blocking(AdmissionClass::Normal, "idempotent_retry", move |state| {
                let applied = state.dispatch_remote(&retry_owner, request).unwrap();
                (applied, state.ledger.records().len(), state.core.snapshot())
            })
            .unwrap();
        assert_eq!(retry.0.resulting_revision, first_snapshot.revision);
        assert_eq!(retry.0.status, AppliedStatus::Accepted);
        assert_eq!(retry.1, first_ledger_count);
        assert_eq!(retry.2.revision, first_snapshot.revision);
        assert_eq!(retry.2.run.phase, first_snapshot.run.phase);
        assert_eq!(
            retry.2.safety.controller_lease_id,
            first_snapshot.safety.controller_lease_id
        );
    }

    #[test]
    fn ack_lost_revoke_reclaim_retry_keeps_current_projection_and_no_duplicate_evidence() {
        let owner = owner(Duration::from_secs(5));
        let (
            first,
            retry,
            current,
            ledger_before_retry,
            ledger_after_retry,
            run_generation_before_retry,
            run_generation_after_retry,
        ) = owner
            .blocking(AdmissionClass::Normal, "ack_lost_retry", |state| {
                state
                    .claim_webview(
                        "session_owner_test".to_owned(),
                        "controller_ack_lost".to_owned(),
                        "owner_ack_lost_first".to_owned(),
                        Scope::DEFAULT_REMOTE.into_iter().collect(),
                        2,
                    )
                    .unwrap();
                prepare_ready_demo(state);
                let command = pps_contracts::CommandBody {
                    command_id: "ack-lost-part-start".to_owned(),
                    scope: Scope::SessionTransport,
                    action: Action::PartStart,
                    args: serde_json::json!({"part_number": 1}),
                    expected_revision: Some(state.core.revision()),
                };
                let first = state
                    .dispatch_webview(
                        "session_owner_test".to_owned(),
                        "owner_ack_lost_first".to_owned(),
                        3,
                        command.clone(),
                    )
                    .unwrap();
                assert_eq!(state.core.snapshot().run.phase, RunnerPhase::Running);

                // The first Applied is intentionally not acknowledged. The
                // transport cleanup pauses/revokes, and the same controller
                // identity then reclaims with a fresh owner token.
                state
                    .revoke_webview(
                        "session_owner_test".to_owned(),
                        "owner_ack_lost_first".to_owned(),
                    )
                    .unwrap();
                state
                    .claim_webview(
                        "session_owner_test".to_owned(),
                        "controller_ack_lost".to_owned(),
                        "owner_ack_lost_second".to_owned(),
                        Scope::DEFAULT_REMOTE.into_iter().collect(),
                        10,
                    )
                    .unwrap();
                let ledger_before_retry = state.ledger.records().len();
                let run_generation_before_retry = state.run_generation;
                let retry = state
                    .dispatch_webview(
                        "session_owner_test".to_owned(),
                        "owner_ack_lost_second".to_owned(),
                        11,
                        command,
                    )
                    .unwrap();
                (
                    first,
                    retry,
                    state.core.snapshot(),
                    ledger_before_retry,
                    state.ledger.records().len(),
                    run_generation_before_retry,
                    state.run_generation,
                )
            })
            .unwrap();

        assert_eq!(retry.status, AppliedStatus::Accepted);
        assert_eq!(retry.resulting_revision, first.resulting_revision);
        assert_eq!(current.run.phase, RunnerPhase::Paused);
        assert_eq!(retry.snapshot.run.phase, RunnerPhase::Paused);
        assert_eq!(retry.snapshot.revision, current.revision);
        assert!(retry.snapshot.revision > retry.resulting_revision);
        assert_eq!(ledger_after_retry, ledger_before_retry);
        assert_eq!(run_generation_after_retry, run_generation_before_retry);
    }

    #[test]
    fn rejected_and_noop_dispatches_cannot_exhaust_scientific_evidence() {
        let owner = owner(Duration::from_secs(5));
        let receipt = owner
            .claim_webview_blocking(
                "session_owner_test".to_owned(),
                "controller_rejections".to_owned(),
                "owner_rejections_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
                2,
            )
            .unwrap()
            .unwrap();
        let (before, after_remote, after_noops) = owner
            .blocking(AdmissionClass::Normal, "rejection_storm", move |state| {
                let before = state.ledger.records().len();
                let remote = state.remote_owner.clone().unwrap();
                for sequence in 0..(DEFAULT_LEDGER_CAPACITY + 32) {
                    let applied = state
                        .dispatch_remote(
                            &remote,
                            CommandRequest {
                                id: format!("remote-rejected-{sequence}"),
                                epoch: state.core.epoch(),
                                sequence: sequence as u64 + 1,
                                expected_revision: Some(state.core.revision()),
                                scope: Scope::SessionTransport,
                                action: Action::TargetArm,
                                args: serde_json::json!({}),
                            },
                        )
                        .unwrap();
                    assert_eq!(applied.status, AppliedStatus::Rejected);
                }
                let after_remote = state.ledger.records().len();
                state
                    .dispatch_local(
                        Action::PackagePrepareDemo,
                        serde_json::json!({}),
                        AdmissionClass::Normal,
                    )
                    .unwrap();
                let after_prepare = state.ledger.records().len();
                for _ in 0..256 {
                    let applied = state
                        .dispatch_local(
                            Action::PackagePrepareDemo,
                            serde_json::json!({}),
                            AdmissionClass::Normal,
                        )
                        .unwrap();
                    assert_eq!(applied.status, AppliedStatus::Accepted);
                    assert_eq!(applied.reason, "already_in_requested_state");
                }
                assert_eq!(state.ledger.records().len(), after_prepare);
                (before, after_remote, state.ledger.records().len())
            })
            .unwrap();
        assert_eq!(before, after_remote);
        assert_eq!(after_noops, before + 1);
        assert_eq!(receipt.controller_id, "controller_rejections");
    }

    #[test]
    fn ordinary_ledger_failure_latches_and_forces_local_running_state_safe() {
        let owner = owner(Duration::from_secs(5));
        let (error, snapshot, event_types, unavailable, before_generation, after_generation) =
            owner
                .blocking(
                    AdmissionClass::Normal,
                    "ordinary_evidence_failure",
                    |state| {
                        prepare_running_demo(state);
                        let before_generation = state.run_generation;
                        state.ledger = EventLedger::new(LEDGER_SAFETY_RECORD_RESERVE + 1).unwrap();
                        let stamp = state.clock.stamp();
                        state
                            .ledger
                            .append(OwnerState::ledger_input("test.preexisting", "test", &stamp))
                            .unwrap();

                        let error = state
                            .dispatch_local(
                                Action::SessionNote,
                                serde_json::json!({"text": "must-not-commit"}),
                                AdmissionClass::Normal,
                            )
                            .unwrap_err();
                        let snapshot = state.core.snapshot();
                        let event_types = state
                            .ledger
                            .records()
                            .iter()
                            .map(|record| record.event_type.clone())
                            .collect::<Vec<_>>();
                        (
                            error,
                            snapshot,
                            event_types,
                            state.evidence_unavailable,
                            before_generation,
                            state.run_generation,
                        )
                    },
                )
                .unwrap();

        assert_eq!(error, "runtime_unavailable");
        assert!(unavailable);
        assert_eq!(snapshot.run.phase, RunnerPhase::Interrupted);
        assert!(!snapshot.safety.local_armed);
        assert!(snapshot.last_note.is_empty());
        assert_eq!(after_generation, before_generation + 1);
        assert_eq!(
            event_types,
            vec![
                "test.preexisting".to_owned(),
                "authority.evidence.unavailable".to_owned()
            ]
        );
    }

    #[test]
    fn ordinary_remote_ledger_failure_revokes_owner_and_redacts_trigger_result() {
        let owner = owner(Duration::from_secs(5));
        owner
            .claim_webview_blocking(
                "session_owner_test".to_owned(),
                "controller_evidence".to_owned(),
                "owner_evidence_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
                2,
            )
            .unwrap()
            .unwrap();

        let (error, view, event_types) = owner
            .blocking(AdmissionClass::Normal, "remote_evidence_failure", |state| {
                prepare_running_demo(state);
                state.ledger = EventLedger::new(LEDGER_SAFETY_RECORD_RESERVE + 1).unwrap();
                let stamp = state.clock.stamp();
                state
                    .ledger
                    .append(OwnerState::ledger_input("test.preexisting", "test", &stamp))
                    .unwrap();
                let remote = state.remote_owner.clone().unwrap();
                let error = state
                    .dispatch_remote(
                        &remote,
                        CommandRequest {
                            id: "remote-evidence-failure".to_owned(),
                            epoch: state.core.epoch(),
                            sequence: 3,
                            expected_revision: Some(state.core.revision()),
                            scope: Scope::SessionTransport,
                            action: Action::RunPause,
                            args: serde_json::json!({}),
                        },
                    )
                    .unwrap_err();
                let event_types = state
                    .ledger
                    .records()
                    .iter()
                    .map(|record| record.event_type.clone())
                    .collect::<Vec<_>>();
                (error, state.view(), event_types)
            })
            .unwrap();

        assert_eq!(error.code, "runtime_unavailable");
        assert!(view.active_controller.is_none());
        assert_eq!(view.snapshot.run.phase, RunnerPhase::Interrupted);
        assert!(!view.snapshot.safety.local_armed);
        assert_eq!(view.snapshot.connection_state, "evidence_unavailable");
        assert_eq!(
            event_types.last().unwrap(),
            "authority.evidence.unavailable"
        );
    }

    #[test]
    fn claim_ledger_failure_cannot_leave_a_local_run_active() {
        let owner = owner(Duration::from_secs(5));
        let (error, view) = owner
            .blocking(AdmissionClass::Normal, "claim_evidence_failure", |state| {
                prepare_running_demo(state);
                state.ledger = EventLedger::new(LEDGER_SAFETY_RECORD_RESERVE + 1).unwrap();
                let stamp = state.clock.stamp();
                state
                    .ledger
                    .append(OwnerState::ledger_input("test.preexisting", "test", &stamp))
                    .unwrap();
                let error = state
                    .claim_webview(
                        "session_owner_test".to_owned(),
                        "controller_claim_failure".to_owned(),
                        "owner_claim_failure_token".to_owned(),
                        Scope::DEFAULT_REMOTE.into_iter().collect(),
                        2,
                    )
                    .unwrap_err();
                (error, state.view())
            })
            .unwrap();

        assert_eq!(error.code, "runtime_unavailable");
        assert!(view.active_controller.is_none());
        assert_eq!(view.snapshot.run.phase, RunnerPhase::Interrupted);
        assert!(!view.snapshot.safety.local_armed);
    }

    #[test]
    fn run_generation_fences_start_completion_stop_and_shutdown_not_pause_resume() {
        let first_owner = owner(Duration::from_secs(5));
        let generations = first_owner
            .blocking(AdmissionClass::Normal, "run_generation", |state| {
                prepare_running_demo(state);
                let started = state.run_generation;
                state
                    .dispatch_local(
                        Action::RunPause,
                        serde_json::json!({}),
                        AdmissionClass::LocalSafety,
                    )
                    .unwrap();
                let paused = state.run_generation;
                state
                    .dispatch_local(
                        Action::RunResume,
                        serde_json::json!({}),
                        AdmissionClass::Normal,
                    )
                    .unwrap();
                let resumed = state.run_generation;
                state
                    .dispatch_local(
                        Action::RunCompleteDemo,
                        serde_json::json!({}),
                        AdmissionClass::Normal,
                    )
                    .unwrap();
                let completed = state.run_generation;
                state.shutdown();
                (started, paused, resumed, completed, state.run_generation)
            })
            .unwrap();
        assert_eq!(generations.0, 1);
        assert_eq!(generations.1, generations.0);
        assert_eq!(generations.2, generations.0);
        assert_eq!(generations.3, generations.0 + 1);
        assert_eq!(generations.4, generations.3 + 1);

        let stop_owner = owner(Duration::from_secs(5));
        let (started, stopped) = stop_owner
            .blocking(AdmissionClass::Normal, "stop_generation", |state| {
                prepare_running_demo(state);
                let started = state.run_generation;
                state
                    .dispatch_local(
                        Action::RunStop,
                        serde_json::json!({}),
                        AdmissionClass::LocalSafety,
                    )
                    .unwrap();
                (started, state.run_generation)
            })
            .unwrap();
        assert_eq!(stopped, started + 1);
    }

    #[test]
    fn generation_exhaustion_fails_safe_instead_of_wrapping() {
        let owner = owner(Duration::from_secs(5));
        let (start_error, start_view, run_generation) = owner
            .blocking(
                AdmissionClass::Normal,
                "run_generation_exhaustion",
                |state| {
                    prepare_ready_demo(state);
                    state.run_generation = u64::MAX;
                    let error = state
                        .dispatch_local(
                            Action::PartStart,
                            serde_json::json!({"part_number": 1}),
                            AdmissionClass::Normal,
                        )
                        .unwrap_err();
                    (error, state.view(), state.run_generation)
                },
            )
            .unwrap();
        assert_eq!(start_error, "runtime_unavailable");
        assert_eq!(run_generation, u64::MAX);
        assert_eq!(start_view.snapshot.run.phase, RunnerPhase::Interrupted);
        assert!(!start_view.snapshot.safety.local_armed);

        let claim_error = owner
            .blocking(
                AdmissionClass::Normal,
                "owner_generation_exhaustion",
                |state| {
                    state.owner_generation = u64::MAX;
                    state
                        .claim_webview(
                            "session_owner_test".to_owned(),
                            "controller_generation".to_owned(),
                            "owner_generation_token".to_owned(),
                            Scope::DEFAULT_REMOTE.into_iter().collect(),
                            2,
                        )
                        .unwrap_err()
                },
            )
            .unwrap();
        assert_eq!(claim_error.code, "runtime_unavailable");
        assert!(owner.view_blocking().unwrap().active_controller.is_none());
    }

    #[test]
    fn revoking_at_owner_generation_ceiling_latches_without_recursion() {
        let owner = owner(Duration::from_secs(5));
        owner
            .claim_webview_blocking(
                "session_owner_test".to_owned(),
                "controller_generation_ceiling".to_owned(),
                "owner_generation_ceiling_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
                2,
            )
            .unwrap()
            .unwrap();
        let (view, owner_generation, evidence_unavailable) = owner
            .blocking(AdmissionClass::LocalSafety, "revoke_at_ceiling", |state| {
                prepare_running_demo(state);
                state.owner_generation = u64::MAX;
                state.remote_owner.as_mut().unwrap().generation = u64::MAX;
                assert!(state
                    .revoke_owner_if_matches(|_| true, "remote_waiting")
                    .unwrap()
                    .is_some());
                (
                    state.view(),
                    state.owner_generation,
                    state.evidence_unavailable,
                )
            })
            .unwrap();
        assert!(view.active_controller.is_none());
        assert_eq!(view.snapshot.run.phase, RunnerPhase::Paused);
        assert_eq!(owner_generation, u64::MAX);
        assert!(evidence_unavailable);
    }

    #[test]
    fn exhausted_evidence_cannot_split_remote_policy_from_safety_state() {
        let owner = owner(Duration::from_secs(5));
        let receipt = owner
            .claim_webview_blocking(
                "session_owner_test".to_owned(),
                "controller_config".to_owned(),
                "owner_config_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
                2,
            )
            .unwrap()
            .unwrap();
        let old_epoch = receipt.snapshot.epoch;
        let view = owner
            .blocking(
                AdmissionClass::LocalSafety,
                "exhausted_config",
                move |state| {
                    prepare_running_demo(state);
                    state.ledger = EventLedger::new(1).unwrap();
                    let stamp = state.clock.stamp();
                    state
                        .ledger
                        .append(OwnerState::ledger_input("test.full", "test", &stamp))
                        .unwrap();
                    state
                        .configure_remote(
                            false,
                            true,
                            PairingSecret::generate(),
                            "session_after_exhaustion".to_owned(),
                            old_epoch + 1,
                        )
                        .unwrap();
                    assert!(state.evidence_unavailable);
                    state.view()
                },
            )
            .unwrap();
        assert!(!view.remote.enabled);
        assert!(view.remote.allow_abort);
        assert_eq!(view.remote.session_id, "session_after_exhaustion");
        assert_eq!(view.snapshot.epoch, old_epoch + 1);
        assert_eq!(view.snapshot.run.phase, RunnerPhase::Paused);
        assert!(view.active_controller.is_none());
    }

    #[test]
    fn deadman_revokes_and_pauses_even_when_safety_evidence_is_exhausted() {
        let owner = owner(Duration::from_secs(5));
        owner
            .claim_webview_blocking(
                "session_owner_test".to_owned(),
                "controller_fail_stop".to_owned(),
                "owner_fail_stop_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
                2,
            )
            .unwrap()
            .unwrap();
        let view = owner
            .blocking(AdmissionClass::LocalSafety, "deadman_fail_stop", |state| {
                prepare_running_demo(state);
                state.ledger = EventLedger::new(1).unwrap();
                let stamp = state.clock.stamp();
                state
                    .ledger
                    .append(OwnerState::ledger_input("test.full", "test", &stamp))
                    .unwrap();
                state.remote_owner.as_mut().unwrap().lease_deadline =
                    Instant::now() - Duration::from_millis(1);
                assert!(state.expire_deadman_if_due());
                assert!(state.evidence_unavailable);
                state.view()
            })
            .unwrap();
        assert_eq!(view.snapshot.run.phase, RunnerPhase::Paused);
        assert_eq!(view.snapshot.connection_state, "remote_lease_expired");
        assert!(view.active_controller.is_none());
    }

    #[test]
    fn actor_deadman_runs_without_a_transport_watchdog_thread() {
        let owner = owner(Duration::from_millis(20));
        let receipt = owner
            .claim_webview_blocking(
                "session_owner_test".to_owned(),
                "controller_deadman".to_owned(),
                "owner_deadman_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
                2,
            )
            .unwrap()
            .unwrap();
        assert!(receipt.snapshot.safety.lease_expires_at_unix_ms.is_some());
        thread::sleep(Duration::from_millis(35));
        let expired = owner.view_blocking().unwrap();
        assert!(expired.active_controller.is_none());
        assert_eq!(expired.snapshot.connection_state, "remote_lease_expired");
        assert!(expired.snapshot.safety.controller_lease_id.is_empty());
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn stale_owner_generation_is_inert_after_replacement() {
        let owner = owner(Duration::from_secs(5));
        let first = owner
            .claim_lan(
                "session_owner_test".to_owned(),
                "controller_old".to_owned(),
                "owner_old_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
            )
            .await
            .unwrap()
            .unwrap();
        owner
            .revoke_lan(first.identity.clone(), "remote_waiting")
            .await
            .unwrap()
            .unwrap();
        let second = owner
            .claim_lan(
                "session_owner_test".to_owned(),
                "controller_new".to_owned(),
                "owner_new_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
            )
            .await
            .unwrap()
            .unwrap();
        assert!(owner
            .lan_publication_snapshot(second.identity.clone())
            .await
            .unwrap()
            .is_some());
        assert!(owner
            .lan_publication_snapshot(first.identity.clone())
            .await
            .unwrap()
            .is_none());
        assert!(!owner.renew_lan(first.identity).await.unwrap().unwrap());
        assert_eq!(
            owner.view().await.unwrap().active_controller.unwrap().id,
            second.identity.controller_id
        );
    }

    #[test]
    fn shutdown_joins_the_named_owner_thread() {
        let owner = owner(Duration::from_secs(5));
        let alive = Arc::clone(&owner._alive);
        assert!(alive.load(Ordering::Acquire));
        drop(owner);
        assert!(!alive.load(Ordering::Acquire));
    }

    #[test]
    fn shutdown_drops_queued_start_and_publishes_safe_neutral_state() {
        let (owner, mut state_rx) = owner_with_state_rx(Duration::from_secs(5));
        owner
            .blocking(AdmissionClass::Normal, "prepare_ready", |state| {
                prepare_ready_demo(state);
            })
            .unwrap();
        let (barrier, blocked) = block_authority(&owner);
        let queued_start = owner
            .submit(AdmissionClass::Normal, "queued_start", |state| {
                state.dispatch_local(
                    Action::PartStart,
                    serde_json::json!({"part_number": 1}),
                    AdmissionClass::Normal,
                )
            })
            .unwrap();

        owner.mailbox.request_shutdown();
        assert!(owner.mailbox.shutdown_requested());
        assert_eq!(owner.mailbox.queued_counts(), (0, 0));
        assert!(matches!(
            owner.submit(AdmissionClass::LocalSafety, "late_emergency", |_| ()),
            Err(OwnerSubmitError::Closed)
        ));
        barrier.wait();
        blocked.blocking_recv().unwrap();
        assert!(queued_start.blocking_recv().is_err());
        wait_for_actor_stop(&owner);

        let final_snapshot = newest_snapshot(&mut state_rx);
        assert_eq!(final_snapshot.run.phase, RunnerPhase::Interrupted);
        assert!(!final_snapshot.safety.local_armed);
        assert!(final_snapshot.safety.controller_lease_id.is_empty());
        assert_eq!(final_snapshot.connection_state, "local_only");
    }

    #[test]
    fn shutdown_neutralizes_a_local_running_session_before_thread_exit() {
        let (owner, mut state_rx) = owner_with_state_rx(Duration::from_secs(5));
        owner
            .blocking(AdmissionClass::Normal, "prepare_running", |state| {
                prepare_running_demo(state);
            })
            .unwrap();
        assert_eq!(
            owner.view_blocking().unwrap().snapshot.run.phase,
            RunnerPhase::Running
        );

        owner.mailbox.request_shutdown();
        wait_for_actor_stop(&owner);
        let final_snapshot = newest_snapshot(&mut state_rx);
        assert_eq!(final_snapshot.run.phase, RunnerPhase::Interrupted);
        assert!(!final_snapshot.safety.local_armed);
        assert!(!final_snapshot.safety.capture_started);
        assert_eq!(final_snapshot.connection_state, "local_only");
    }

    #[test]
    fn test_deadline_override_remains_actor_owned() {
        let owner = owner(Duration::from_secs(5));
        owner
            .claim_webview_blocking(
                "session_owner_test".to_owned(),
                "controller_override".to_owned(),
                "owner_override_token".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
                2,
            )
            .unwrap()
            .unwrap();
        owner.force_owner_expiry();
        assert!(owner.view_blocking().unwrap().active_controller.is_none());
    }

    #[test]
    fn diagnostics_contention_cannot_block_or_change_an_authority_transition() {
        let owner = owner(Duration::from_secs(5));
        let diagnostics = NativeLatencyDiagnostics::new();
        diagnostics.while_store_locked_for_test(|| {
            let mut trace = diagnostics.start_trace(LatencyRoute::LocalTauri);
            let applied = owner
                .dispatch_local_traced_blocking(
                    Action::PackagePrepareDemo,
                    serde_json::json!({}),
                    trace.trace(),
                )
                .unwrap()
                .unwrap();
            assert_eq!(applied.status, AppliedStatus::Accepted);
            trace.finish(TraceOutcome::Applied);
        });
        let snapshot = owner.view_blocking().unwrap().snapshot;
        assert!(snapshot.package_verified);
        assert_eq!(diagnostics.summary().count, 0);
        assert_eq!(diagnostics.summary().dropped_count, 1);
    }
}
