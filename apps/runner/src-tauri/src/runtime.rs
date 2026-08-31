use std::{
    collections::BTreeSet,
    net::{IpAddr, Ipv4Addr, SocketAddr, TcpListener as StdTcpListener},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
};

use pps_brsp::{random_epoch, random_nonce, valid_peer_id, PairingSecret};
use pps_contracts::{
    Action, ActiveBlockSnapshot, Applied, AppliedStatus, CommandBody, InstructionGateSnapshot,
    PartSnapshot, RunSnapshot, RunnerSnapshot, Scope, TimingTier,
};
use pps_runner_core::VerifiedPackageSummary;
use pps_session_package::VerifiedPreparedSession;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::sync::broadcast;

use crate::execution_owner::{
    AuthorityView, ExecutionOwner, LanOwnerReceipt, OwnerSubmitError, RemoteOwnerIdentity,
    MAILBOX_CAPACITY, NORMAL_MAILBOX_CAPACITY,
};
use crate::latency_diagnostics::{
    LatencyRoute, LatencyStage, LatencyTrace, LatencyTraceGuard, NativeIngress,
    NativeLatencyDiagnostics, NativeLatencySummary,
};
use crate::prepared_audio::{
    PreparedAudioCandidate, PreparedAudioLookup, PreparedAudioSource, PreparedAudioSummary,
};
use crate::prepared_execution::{
    CompiledPreparedExecution, PreparedExecutionSource, PreparedExecutionSummary,
};

const MAX_ACCEPTED_SCOPES: usize = 16;

#[derive(Debug, Clone)]
pub struct RemoteConfig {
    pub enabled: bool,
    pub allow_abort: bool,
    pub secret: PairingSecret,
    pub session_id: String,
}

#[derive(Debug, Clone)]
pub struct ActiveController {
    pub id: String,
    pub granted_scopes: Vec<Scope>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RemoteSessionError {
    pub code: String,
    pub message: String,
}

impl RemoteSessionError {
    pub(crate) fn new(code: &str, message: &str) -> Self {
        Self {
            code: code.to_owned(),
            message: message.to_owned(),
        }
    }

    pub(crate) fn unavailable() -> Self {
        Self::new(
            "runtime_unavailable",
            "The native Runner authority is unavailable.",
        )
    }
}

impl std::fmt::Display for RemoteSessionError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.code)
    }
}

impl std::error::Error for RemoteSessionError {}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RemoteSessionClaimRequest {
    pub session_id: String,
    pub controller_id: String,
    pub accepted_scopes: Vec<Scope>,
    pub ready_sequence: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RemoteSessionOwnerRequest {
    pub session_id: String,
    pub owner_token: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RemoteSessionRenewRequest {
    pub session_id: String,
    pub owner_token: String,
    pub control_sequence: u32,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RemoteSessionDispatchRequest {
    pub session_id: String,
    pub owner_token: String,
    pub control_sequence: u32,
    pub command: CommandBody,
}

/// Deliberately smaller state projection for every remote/native seam.
///
/// The local operator UI keeps the complete [`RunnerSnapshot`]. Remote peers
/// receive only operational state needed to render and control the target;
/// participant/session identity, demographics, package labels, notes, and
/// evidence/private native state are absent by construction.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct RemoteRunnerSnapshot {
    pub schema: String,
    pub protocol: String,
    pub target_id: String,
    pub target_kind: String,
    pub epoch: u64,
    pub revision: u64,
    pub server_unix_ms: u64,
    pub server_monotonic_ns: u64,
    pub connection_state: String,
    pub timing_tier: TimingTier,
    pub package_verified: bool,
    pub allowed_actions: Vec<Action>,
    pub setup: RemoteSetupSnapshot,
    pub part: PartSnapshot,
    pub run: RunSnapshot,
    pub instruction_gate: InstructionGateSnapshot,
    pub active_block: ActiveBlockSnapshot,
    pub safety: RemoteSafetySnapshot,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct RemoteSetupSnapshot {
    pub submitted: bool,
    pub ready: bool,
    pub required_missing: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct RemoteSafetySnapshot {
    pub lease_expires_at_unix_ms: Option<u64>,
    pub local_override: bool,
    pub local_armed: bool,
    pub audio_route_ready: bool,
    pub publication_ready: bool,
    pub lsl_ready: bool,
    pub capture_started: bool,
}

impl From<RunnerSnapshot> for RemoteRunnerSnapshot {
    fn from(snapshot: RunnerSnapshot) -> Self {
        Self {
            schema: "pps-runner-public-snapshot.v1".to_owned(),
            protocol: snapshot.protocol,
            target_id: snapshot.target_id,
            target_kind: snapshot.target_kind,
            epoch: snapshot.epoch,
            revision: snapshot.revision,
            server_unix_ms: snapshot.server_unix_ms,
            server_monotonic_ns: snapshot.server_monotonic_ns,
            connection_state: snapshot.connection_state,
            timing_tier: snapshot.timing_tier,
            package_verified: snapshot.package_verified,
            allowed_actions: snapshot.allowed_actions,
            setup: RemoteSetupSnapshot {
                submitted: snapshot.setup.submitted,
                ready: snapshot.setup.ready,
                required_missing: snapshot.setup.required_missing,
            },
            part: snapshot.part,
            run: snapshot.run,
            instruction_gate: snapshot.instruction_gate,
            active_block: snapshot.active_block,
            safety: RemoteSafetySnapshot {
                lease_expires_at_unix_ms: snapshot.safety.lease_expires_at_unix_ms,
                local_override: snapshot.safety.local_override,
                local_armed: snapshot.safety.local_armed,
                audio_route_ready: snapshot.safety.audio_route_ready,
                publication_ready: snapshot.safety.publication_ready,
                lsl_ready: snapshot.safety.lsl_ready,
                capture_started: snapshot.safety.capture_started,
            },
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct RemoteApplied {
    pub id: String,
    pub action: Action,
    pub status: AppliedStatus,
    pub reason: String,
    pub accepted_revision: u64,
    pub resulting_revision: u64,
    pub snapshot: RemoteRunnerSnapshot,
}

impl RemoteApplied {
    pub(crate) fn from_native(applied: Applied, current_snapshot: RunnerSnapshot) -> Self {
        let reason = if matches!(applied.status, AppliedStatus::Rejected) {
            "request_rejected"
        } else {
            "request_accepted"
        };
        Self {
            id: applied.id,
            action: applied.action,
            status: applied.status,
            reason: reason.to_owned(),
            accepted_revision: applied.accepted_revision,
            resulting_revision: applied.resulting_revision,
            // The cached Applied outcome keeps its original accepted/resulting
            // revisions, but publication must always project current actor
            // state after owner revocation/reclaim and idempotent retry.
            snapshot: current_snapshot.into(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RemoteSessionLeaseReceipt {
    pub session_id: String,
    pub controller_id: String,
    pub owner_token: String,
    pub accepted_scopes: Vec<Scope>,
    pub lease_expires_at_unix_ms: u64,
    pub snapshot: RemoteRunnerSnapshot,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RemoteSessionRevocationReceipt {
    pub revoked: bool,
    pub snapshot: RemoteRunnerSnapshot,
}

#[derive(Debug, Default)]
pub struct RemoteServerState {
    pub bind_addr: Option<SocketAddr>,
    pub last_error: Option<String>,
}

pub struct RuntimeShared {
    pub authority: ExecutionOwner,
    latency_diagnostics: NativeLatencyDiagnostics,
    prepared_session_selection_in_flight: AtomicBool,
    prepared_execution_inspection_in_flight: AtomicBool,
    prepared_audio_preparation_in_flight: AtomicBool,
    pub state_tx: broadcast::Sender<RunnerSnapshot>,
    pub remote_server: Mutex<RemoteServerState>,
    pub advertised_ip: IpAddr,
}

#[derive(Clone)]
pub struct AppRuntime(pub Arc<RuntimeShared>);

pub struct PreparedSessionSelectionGuard {
    shared: Arc<RuntimeShared>,
}

pub struct PreparedExecutionInspectionGuard {
    shared: Arc<RuntimeShared>,
}

pub struct PreparedAudioPreparationGuard {
    shared: Arc<RuntimeShared>,
}

pub(crate) enum PreparedAudioPreparation {
    Cached(PreparedAudioSummary),
    Decode {
        _guard: PreparedAudioPreparationGuard,
        source: PreparedAudioSource,
    },
}

impl Drop for PreparedSessionSelectionGuard {
    fn drop(&mut self) {
        self.shared
            .prepared_session_selection_in_flight
            .store(false, Ordering::Release);
    }
}

impl Drop for PreparedExecutionInspectionGuard {
    fn drop(&mut self) {
        self.shared
            .prepared_execution_inspection_in_flight
            .store(false, Ordering::Release);
    }
}

impl Drop for PreparedAudioPreparationGuard {
    fn drop(&mut self) {
        self.shared
            .prepared_audio_preparation_in_flight
            .store(false, Ordering::Release);
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RemoteStatus {
    pub enabled: bool,
    pub allow_abort: bool,
    pub bind_address: String,
    pub base_url: String,
    pub controller_url: String,
    pub target_id: String,
    pub session_id: String,
    pub epoch: u64,
    pub controller_connected: bool,
    pub controller_id: Option<String>,
    pub granted_scopes: Vec<Scope>,
    pub server_available: bool,
    pub server_error: Option<String>,
    pub transport: String,
    pub production_transport_qualified: bool,
}

impl AppRuntime {
    pub fn new() -> Self {
        let advertised_ip = local_ip_address::local_ip()
            .ok()
            .filter(|ip| !ip.is_loopback())
            .unwrap_or(IpAddr::V4(Ipv4Addr::LOCALHOST));
        let epoch = u64::from(random_epoch());
        let target_id = format!("pps-desktop-{}", &random_nonce()[..12]);
        let (state_tx, _) = broadcast::channel(64);
        let remote = RemoteConfig {
            enabled: false,
            allow_abort: false,
            secret: PairingSecret::generate(),
            session_id: format!("session_{}", &random_nonce()[..18]),
        };
        let latency_diagnostics = NativeLatencyDiagnostics::with_mailbox_limits(
            MAILBOX_CAPACITY,
            NORMAL_MAILBOX_CAPACITY,
        );
        let authority = ExecutionOwner::start(
            target_id,
            "desktop-tauri-preview",
            epoch,
            TimingTier::DesktopPreview,
            remote,
            state_tx.clone(),
            latency_diagnostics.authority_mailbox(),
        )
        .expect("the Runner authority thread must start");
        let shared = RuntimeShared {
            authority,
            latency_diagnostics,
            prepared_session_selection_in_flight: AtomicBool::new(false),
            prepared_execution_inspection_in_flight: AtomicBool::new(false),
            prepared_audio_preparation_in_flight: AtomicBool::new(false),
            state_tx,
            remote_server: Mutex::new(RemoteServerState::default()),
            advertised_ip,
        };
        Self(Arc::new(shared))
    }

    #[cfg(test)]
    pub fn snapshot(&self) -> Result<RunnerSnapshot, String> {
        self.0
            .authority
            .view_blocking()
            .map(|view| view.snapshot)
            .map_err(owner_runtime_error)
    }

    pub async fn snapshot_async(&self) -> Result<RunnerSnapshot, String> {
        self.0
            .authority
            .view()
            .await
            .map(|view| view.snapshot)
            .map_err(owner_runtime_error)
    }

    pub(crate) fn start_latency_trace(&self, route: LatencyRoute) -> LatencyTraceGuard {
        self.0.latency_diagnostics.start_trace(route)
    }

    pub(crate) fn capture_latency_ingress(&self) -> NativeIngress {
        self.0.latency_diagnostics.capture_ingress()
    }

    pub(crate) fn start_latency_trace_from(
        &self,
        route: LatencyRoute,
        ingress: NativeIngress,
    ) -> LatencyTraceGuard {
        self.0.latency_diagnostics.start_trace_from(route, ingress)
    }

    pub(crate) fn latency_summary(&self) -> NativeLatencySummary {
        self.0.latency_diagnostics.summary()
    }

    /// Reserve the one native prepared-session picker/verification operation.
    /// The WebView is not trusted to serialize command invocations, so this
    /// guard must span both the dialog callback and the blocking verifier.
    pub fn begin_prepared_session_selection(
        &self,
    ) -> Result<PreparedSessionSelectionGuard, &'static str> {
        self.0
            .prepared_session_selection_in_flight
            .compare_exchange(false, true, Ordering::Acquire, Ordering::Relaxed)
            .map_err(|_| "prepared_session_selection_in_progress")?;
        Ok(PreparedSessionSelectionGuard {
            shared: Arc::clone(&self.0),
        })
    }

    /// Reserve one native schedule inspection and capture the retained package
    /// generation under its authority lock. The caller holds the returned
    /// guard across reverification and compilation.
    #[cfg(test)]
    pub fn begin_prepared_execution_inspection(
        &self,
    ) -> Result<(PreparedExecutionInspectionGuard, PreparedExecutionSource), &'static str> {
        self.0
            .prepared_execution_inspection_in_flight
            .compare_exchange(false, true, Ordering::Acquire, Ordering::Relaxed)
            .map_err(|_| "prepared_execution_inspection_in_progress")?;
        let guard = PreparedExecutionInspectionGuard {
            shared: Arc::clone(&self.0),
        };
        let source = self
            .0
            .authority
            .inspection_source_blocking()
            .map_err(|_| "runtime_unavailable")??;
        Ok((guard, source))
    }

    pub async fn begin_prepared_execution_inspection_async(
        &self,
    ) -> Result<(PreparedExecutionInspectionGuard, PreparedExecutionSource), &'static str> {
        self.0
            .prepared_execution_inspection_in_flight
            .compare_exchange(false, true, Ordering::Acquire, Ordering::Relaxed)
            .map_err(|_| "prepared_execution_inspection_in_progress")?;
        let guard = PreparedExecutionInspectionGuard {
            shared: Arc::clone(&self.0),
        };
        let source = self
            .0
            .authority
            .inspection_source()
            .await
            .map_err(|_| "runtime_unavailable")??;
        Ok((guard, source))
    }

    /// Cache a compiled schedule only if the selected package is still the
    /// exact generation/fingerprint captured before native reverification.
    #[cfg(test)]
    pub fn cache_prepared_execution(
        &self,
        compiled: CompiledPreparedExecution,
    ) -> Result<PreparedExecutionSummary, &'static str> {
        self.0
            .authority
            .cache_compiled_blocking(compiled)
            .map_err(|_| "runtime_unavailable")?
    }

    pub async fn cache_prepared_execution_async(
        &self,
        compiled: CompiledPreparedExecution,
    ) -> Result<PreparedExecutionSummary, &'static str> {
        self.0
            .authority
            .cache_compiled(compiled)
            .await
            .map_err(|_| "runtime_unavailable")?
    }

    /// Reserve one blocking PCM preparation and capture the exact native
    /// package/run fence from the authority actor. The atomic guard is only
    /// adapter-side load shedding; the actor independently validates the
    /// result before it can replace the one-block native cache.
    #[cfg(test)]
    pub fn begin_prepared_audio_preparation(
        &self,
        block_ordinal: u32,
    ) -> Result<PreparedAudioPreparation, &'static str> {
        self.0
            .prepared_audio_preparation_in_flight
            .compare_exchange(false, true, Ordering::Acquire, Ordering::Relaxed)
            .map_err(|_| "prepared_audio_preparation_in_progress")?;
        let guard = PreparedAudioPreparationGuard {
            shared: Arc::clone(&self.0),
        };
        let source = self
            .0
            .authority
            .prepared_audio_source_blocking(block_ordinal)
            .map_err(|_| "runtime_unavailable")??;
        Ok(match source {
            PreparedAudioLookup::Cached(summary) => PreparedAudioPreparation::Cached(summary),
            PreparedAudioLookup::Decode(source) => PreparedAudioPreparation::Decode {
                _guard: guard,
                source,
            },
        })
    }

    pub async fn begin_prepared_audio_preparation_async(
        &self,
        block_ordinal: u32,
    ) -> Result<PreparedAudioPreparation, &'static str> {
        self.0
            .prepared_audio_preparation_in_flight
            .compare_exchange(false, true, Ordering::Acquire, Ordering::Relaxed)
            .map_err(|_| "prepared_audio_preparation_in_progress")?;
        let guard = PreparedAudioPreparationGuard {
            shared: Arc::clone(&self.0),
        };
        let source = self
            .0
            .authority
            .prepared_audio_source(block_ordinal)
            .await
            .map_err(|_| "runtime_unavailable")??;
        Ok(match source {
            PreparedAudioLookup::Cached(summary) => PreparedAudioPreparation::Cached(summary),
            PreparedAudioLookup::Decode(source) => PreparedAudioPreparation::Decode {
                _guard: guard,
                source,
            },
        })
    }

    #[cfg(test)]
    pub fn cache_prepared_audio(
        &self,
        candidate: PreparedAudioCandidate,
    ) -> Result<PreparedAudioSummary, &'static str> {
        self.0
            .authority
            .cache_prepared_audio_blocking(candidate)
            .map_err(|_| "runtime_unavailable")?
    }

    pub async fn cache_prepared_audio_async(
        &self,
        candidate: PreparedAudioCandidate,
    ) -> Result<PreparedAudioSummary, &'static str> {
        self.0
            .authority
            .cache_prepared_audio(candidate)
            .await
            .map_err(|_| "runtime_unavailable")?
    }

    #[cfg(test)]
    pub fn dispatch_local(&self, action: Action, args: Value) -> Result<Applied, String> {
        self.0
            .authority
            .dispatch_local_blocking(action, args)
            .map_err(owner_runtime_error)?
    }

    #[cfg(test)]
    pub async fn dispatch_local_async(
        &self,
        action: Action,
        args: Value,
    ) -> Result<Applied, String> {
        self.0
            .authority
            .dispatch_local(action, args)
            .await
            .map_err(owner_runtime_error)?
    }

    pub async fn dispatch_local_traced_async(
        &self,
        action: Action,
        args: Value,
        trace: LatencyTrace,
    ) -> Result<Applied, String> {
        self.0
            .authority
            .dispatch_local_traced(action, args, trace)
            .await
            .map_err(owner_runtime_error)?
    }

    /// Adopt a path-bearing prepared-session receipt produced by the native
    /// verifier. Only a filesystem-free semantic projection reaches the pure
    /// reducer; the full receipt remains in Rust for the future execution
    /// adapter and must be reverified at that final use boundary.
    #[cfg(test)]
    pub fn adopt_verified_session(
        &self,
        verified: VerifiedPreparedSession,
    ) -> Result<RunnerSnapshot, &'static str> {
        let package = verified_package_projection(&verified)?;
        self.0
            .authority
            .adopt_verified_session_blocking(
                verified,
                package,
                PairingSecret::generate(),
                format!("session_{}", &random_nonce()[..18]),
                u64::from(random_epoch()),
            )
            .map_err(|_| "runtime_unavailable")?
    }

    pub async fn adopt_verified_session_async(
        &self,
        verified: VerifiedPreparedSession,
    ) -> Result<RunnerSnapshot, &'static str> {
        let package = verified_package_projection(&verified)?;
        self.0
            .authority
            .adopt_verified_session(
                verified,
                package,
                PairingSecret::generate(),
                format!("session_{}", &random_nonce()[..18]),
                u64::from(random_epoch()),
            )
            .await
            .map_err(|_| "runtime_unavailable")?
    }

    /// Reserve the single native remote-controller authority for a WebView
    /// transport only after that transport has completed its own BRSP proof
    /// and scope negotiation. The returned owner token is fresh native bearer
    /// material and never enters the public Runner snapshot.
    /// Renew the Rust-owned controller lease after the WebView adapter has
    /// accepted a fresh authenticated BRSP control record. Sequence freshness
    /// is checked again at the native boundary before the deadline moves.
    /// Apply one already-authenticated WebView command through the same remote
    /// reducer origin used by the LAN adapter. This method never falls back to
    /// `dispatch_local` for the requested operation.
    /// Revoke only the exact owner token returned by `claim_remote_session`.
    /// A late pagehide/Stop from an old WebView cannot clear a replacement.
    #[cfg(test)]
    pub fn claim_remote_session(
        &self,
        request: RemoteSessionClaimRequest,
    ) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
        let accepted_scopes = validate_claim_request(&request)?;
        self.0
            .authority
            .claim_webview_blocking(
                request.session_id,
                request.controller_id,
                random_owner_token(),
                accepted_scopes,
                request.ready_sequence,
            )
            .map_err(owner_remote_error)?
    }

    pub async fn claim_remote_session_async(
        &self,
        request: RemoteSessionClaimRequest,
    ) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
        let accepted_scopes = validate_claim_request(&request)?;
        self.0
            .authority
            .claim_webview(
                request.session_id,
                request.controller_id,
                random_owner_token(),
                accepted_scopes,
                request.ready_sequence,
            )
            .await
            .map_err(owner_remote_error)?
    }

    #[cfg(test)]
    pub fn renew_remote_session(
        &self,
        request: RemoteSessionRenewRequest,
    ) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
        validate_owner_request(&request.session_id, &request.owner_token)?;
        self.0
            .authority
            .renew_webview_blocking(
                request.session_id,
                request.owner_token,
                request.control_sequence,
            )
            .map_err(owner_remote_error)?
    }

    pub async fn renew_remote_session_async(
        &self,
        request: RemoteSessionRenewRequest,
    ) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
        validate_owner_request(&request.session_id, &request.owner_token)?;
        self.0
            .authority
            .renew_webview(
                request.session_id,
                request.owner_token,
                request.control_sequence,
            )
            .await
            .map_err(owner_remote_error)?
    }

    #[cfg(test)]
    pub fn dispatch_remote_session(
        &self,
        request: RemoteSessionDispatchRequest,
    ) -> Result<RemoteApplied, RemoteSessionError> {
        validate_owner_request(&request.session_id, &request.owner_token)?;
        self.0
            .authority
            .dispatch_webview_blocking(
                request.session_id,
                request.owner_token,
                request.control_sequence,
                request.command,
            )
            .map_err(owner_remote_error)?
    }

    pub async fn dispatch_remote_session_traced_async(
        &self,
        request: RemoteSessionDispatchRequest,
        trace: LatencyTrace,
    ) -> Result<RemoteApplied, RemoteSessionError> {
        let adapter_validation = validate_owner_request(&request.session_id, &request.owner_token);
        trace.mark(LatencyStage::AdapterValidationComplete);
        adapter_validation?;
        self.0
            .authority
            .dispatch_webview_traced(
                request.session_id,
                request.owner_token,
                request.control_sequence,
                request.command,
                trace,
            )
            .await
            .map_err(owner_remote_error)?
    }

    #[cfg(test)]
    pub fn revoke_remote_session(
        &self,
        request: RemoteSessionOwnerRequest,
    ) -> Result<RemoteSessionRevocationReceipt, RemoteSessionError> {
        validate_owner_request(&request.session_id, &request.owner_token)?;
        self.0
            .authority
            .revoke_webview_blocking(request.session_id, request.owner_token)
            .map_err(owner_remote_error)?
    }

    pub async fn revoke_remote_session_async(
        &self,
        request: RemoteSessionOwnerRequest,
    ) -> Result<RemoteSessionRevocationReceipt, RemoteSessionError> {
        validate_owner_request(&request.session_id, &request.owner_token)?;
        self.0
            .authority
            .revoke_webview(request.session_id, request.owner_token)
            .await
            .map_err(owner_remote_error)?
    }

    #[cfg(test)]
    pub fn status(&self) -> Result<RemoteStatus, String> {
        let view = self
            .0
            .authority
            .view_blocking()
            .map_err(owner_runtime_error)?;
        self.status_from_view(view)
    }

    pub async fn status_async(&self) -> Result<RemoteStatus, String> {
        let view = self.0.authority.view().await.map_err(owner_runtime_error)?;
        self.status_from_view(view)
    }

    fn status_from_view(&self, view: AuthorityView) -> Result<RemoteStatus, String> {
        let snapshot = view.snapshot;
        let remote = view.remote;
        let server = self
            .0
            .remote_server
            .lock()
            .map_err(|_| "remote server lock is poisoned".to_owned())?;
        let bind_address = server
            .bind_addr
            .map(|address| address.to_string())
            .unwrap_or_default();
        let base_url = server
            .bind_addr
            .map(|address| format!("http://{}:{}", self.0.advertised_ip, address.port()))
            .unwrap_or_default();
        let server_available = server.bind_addr.is_some();
        let server_error = server.last_error.clone();
        drop(server);
        let active = view.active_controller;
        let controller_url = if remote.enabled && server_available {
            let secret = remote.secret.expose_base64();
            let mut invitation_scopes = Scope::DEFAULT_REMOTE
                .into_iter()
                .map(Scope::as_str)
                .collect::<Vec<_>>();
            if remote.allow_abort {
                invitation_scopes.push(Scope::SessionAbort.as_str());
            }
            invitation_scopes.sort_unstable();
            format!(
                "{base_url}/companion/#mode=controller&transport=desktop&target_id={}&session_id={}&secret={secret}&scopes={}",
                snapshot.target_id,
                remote.session_id,
                invitation_scopes.join(","),
                secret = secret,
            )
        } else {
            String::new()
        };
        Ok(RemoteStatus {
            enabled: remote.enabled,
            allow_abort: remote.allow_abort,
            bind_address,
            base_url,
            controller_url,
            target_id: snapshot.target_id,
            session_id: remote.session_id.clone(),
            epoch: snapshot.epoch,
            controller_connected: active.is_some(),
            controller_id: active.as_ref().map(|controller| controller.id.clone()),
            granted_scopes: active
                .map(|controller| controller.granted_scopes)
                .unwrap_or_default(),
            server_available,
            server_error,
            transport: "authenticated-lab-lan-ws-preview".to_owned(),
            production_transport_qualified: false,
        })
    }

    #[cfg(test)]
    pub fn configure_remote(
        &self,
        enabled: bool,
        allow_abort: bool,
    ) -> Result<RemoteStatus, String> {
        self.0
            .authority
            .configure_remote_blocking(
                enabled,
                allow_abort,
                PairingSecret::generate(),
                format!("session_{}", &random_nonce()[..18]),
                u64::from(random_epoch()),
            )
            .map_err(owner_runtime_error)?
            .map_err(str::to_owned)?;
        self.status()
    }

    pub async fn configure_remote_async(
        &self,
        enabled: bool,
        allow_abort: bool,
    ) -> Result<RemoteStatus, String> {
        self.0
            .authority
            .configure_remote(
                enabled,
                allow_abort,
                PairingSecret::generate(),
                format!("session_{}", &random_nonce()[..18]),
                u64::from(random_epoch()),
            )
            .await
            .map_err(owner_runtime_error)?
            .map_err(str::to_owned)?;
        self.status_async().await
    }

    #[cfg(test)]
    pub fn rotate_pairing(&self) -> Result<RemoteStatus, String> {
        self.0
            .authority
            .rotate_pairing_blocking(
                PairingSecret::generate(),
                format!("session_{}", &random_nonce()[..18]),
                u64::from(random_epoch()),
            )
            .map_err(owner_runtime_error)?
            .map_err(str::to_owned)?;
        self.status()
    }

    pub async fn rotate_pairing_async(&self) -> Result<RemoteStatus, String> {
        self.0
            .authority
            .rotate_pairing(
                PairingSecret::generate(),
                format!("session_{}", &random_nonce()[..18]),
                u64::from(random_epoch()),
            )
            .await
            .map_err(owner_runtime_error)?
            .map_err(str::to_owned)?;
        self.status_async().await
    }

    pub async fn remote_config_async(&self) -> Result<RemoteConfig, String> {
        self.0
            .authority
            .view()
            .await
            .map(|view| view.remote)
            .map_err(owner_runtime_error)
    }

    pub async fn available_scopes_async(&self) -> Result<Vec<Scope>, String> {
        let remote = self.remote_config_async().await?;
        let mut scopes = Scope::DEFAULT_REMOTE.to_vec();
        if remote.allow_abort {
            scopes.push(Scope::SessionAbort);
        }
        Ok(scopes)
    }

    pub async fn claim_lan_controller(
        &self,
        session_id: String,
        controller_id: String,
        accepted_scopes: BTreeSet<Scope>,
    ) -> Result<LanOwnerReceipt, String> {
        self.0
            .authority
            .claim_lan(
                session_id,
                controller_id,
                random_owner_token(),
                accepted_scopes,
            )
            .await
            .map_err(owner_runtime_error)?
            .map_err(|error| error.code)
    }

    pub async fn renew_lan_controller(
        &self,
        identity: RemoteOwnerIdentity,
    ) -> Result<bool, String> {
        self.0
            .authority
            .renew_lan(identity)
            .await
            .map_err(owner_runtime_error)?
    }

    /// Actor-serialized, non-renewing publication fence for the exact LAN
    /// owner identity/generation. `None` means the socket must close without
    /// publishing state.
    pub(crate) async fn lan_publication_snapshot(
        &self,
        identity: RemoteOwnerIdentity,
    ) -> Result<Option<RemoteRunnerSnapshot>, String> {
        self.0
            .authority
            .lan_publication_snapshot(identity)
            .await
            .map_err(owner_runtime_error)
    }

    pub async fn dispatch_lan_controller_traced(
        &self,
        identity: RemoteOwnerIdentity,
        control_sequence: u32,
        command: CommandBody,
        trace: LatencyTrace,
    ) -> Result<RemoteApplied, String> {
        self.0
            .authority
            .dispatch_lan_traced(identity, control_sequence, command, trace)
            .await
            .map_err(owner_runtime_error)?
    }

    pub async fn revoke_lan_controller(
        &self,
        identity: RemoteOwnerIdentity,
        connection_state: &'static str,
    ) -> Result<bool, String> {
        self.0
            .authority
            .revoke_lan(identity, connection_state)
            .await
            .map_err(owner_runtime_error)?
    }

    pub fn revoke_lan_controller_detached(
        &self,
        identity: RemoteOwnerIdentity,
        connection_state: &'static str,
    ) {
        self.0
            .authority
            .revoke_lan_detached(identity, connection_state);
    }

    /// Reserve the LAN listener only after the user explicitly enables remote
    /// control. Startup and local-only use therefore never bind or trigger a
    /// firewall prompt. A running listener is reused after disable/re-enable.
    pub fn reserve_remote_listener(&self) -> Result<Option<(StdTcpListener, SocketAddr)>, String> {
        let mut server = self
            .0
            .remote_server
            .lock()
            .map_err(|_| "remote server lock is poisoned".to_owned())?;
        if server.bind_addr.is_some() {
            return Ok(None);
        }
        let listener = match StdTcpListener::bind((Ipv4Addr::UNSPECIFIED, 0)) {
            Ok(listener) => listener,
            Err(error) => {
                let message = format!("could not bind the companion server: {error}");
                server.last_error = Some(message.clone());
                return Err(message);
            }
        };
        if let Err(error) = listener.set_nonblocking(true) {
            let message = format!("could not configure the companion server: {error}");
            server.last_error = Some(message.clone());
            return Err(message);
        }
        let bind_addr = match listener.local_addr() {
            Ok(address) => address,
            Err(error) => {
                let message = format!("could not inspect the companion server: {error}");
                server.last_error = Some(message.clone());
                return Err(message);
            }
        };
        server.bind_addr = Some(bind_addr);
        server.last_error = None;
        Ok(Some((listener, bind_addr)))
    }

    pub fn remote_server_failed(&self, bind_addr: SocketAddr, error: String) {
        if let Ok(mut server) = self.0.remote_server.lock() {
            if server.bind_addr == Some(bind_addr) {
                server.bind_addr = None;
                server.last_error = Some(error);
            }
        }
    }
}

fn owner_runtime_error(error: OwnerSubmitError) -> String {
    error.as_runtime_message().to_owned()
}

fn owner_remote_error(error: OwnerSubmitError) -> RemoteSessionError {
    match error {
        OwnerSubmitError::Full => RemoteSessionError::new(
            "runtime_busy",
            "The native Runner authority queue is full; retry the request.",
        ),
        OwnerSubmitError::Closed => RemoteSessionError::unavailable(),
    }
}

fn validate_claim_request(
    request: &RemoteSessionClaimRequest,
) -> Result<BTreeSet<Scope>, RemoteSessionError> {
    if !valid_peer_id(&request.session_id) {
        return Err(RemoteSessionError::new(
            "invalid_session_id",
            "The remote session identifier is malformed.",
        ));
    }
    if !valid_peer_id(&request.controller_id) {
        return Err(RemoteSessionError::new(
            "invalid_controller_id",
            "The remote controller identifier is malformed.",
        ));
    }
    let accepted_scopes = request
        .accepted_scopes
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    if accepted_scopes.is_empty()
        || accepted_scopes.len() != request.accepted_scopes.len()
        || accepted_scopes.len() > MAX_ACCEPTED_SCOPES
    {
        return Err(RemoteSessionError::new(
            "invalid_scopes",
            "Accepted scopes must be a non-empty, unique, bounded set.",
        ));
    }
    Ok(accepted_scopes)
}

fn verified_package_projection(
    verified: &VerifiedPreparedSession,
) -> Result<VerifiedPackageSummary, &'static str> {
    let summary = verified.summary();
    let part_number = summary
        .part_number
        .map(u8::try_from)
        .transpose()
        .map_err(|_| "invalid_verified_package")?;
    let block_count =
        u32::try_from(summary.blocks.len()).map_err(|_| "invalid_verified_package")?;
    Ok(VerifiedPackageSummary {
        fingerprint: verified.manifest_sha256().to_owned(),
        participant_id: summary.participant_id.clone(),
        session_id: summary.session_id.clone(),
        session_group_id: summary.session_group_id.clone(),
        part_number,
        part_session_id: summary.part_session_id.clone(),
        execution_mode: summary.execution_mode.clone(),
        block_count,
    })
}

pub(crate) fn random_owner_token() -> String {
    // BRSP nonces are canonical base64url and may begin with `-` or `_`, while
    // owner-token validation deliberately requires an alphanumeric first byte.
    // Prefix the entropy instead of weakening the closed token grammar.
    format!("owner_{}", random_nonce())
}

fn validate_owner_request(session_id: &str, owner_token: &str) -> Result<(), RemoteSessionError> {
    if !valid_peer_id(session_id) {
        return Err(RemoteSessionError::new(
            "invalid_session_id",
            "The remote session identifier is malformed.",
        ));
    }
    if !valid_peer_id(owner_token) {
        return Err(RemoteSessionError::new(
            "invalid_owner_token",
            "The native remote-session owner token is malformed.",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        latency_diagnostics::{LatencyStage, TraceOutcome},
        prepared_audio::{prepare_verified_audio, MAXIMUM_CACHED_DECODED_BYTES},
        prepared_execution::compile_prepared_execution,
    };
    use pps_contracts::{AppliedStatus, RunnerPhase};
    use pps_session_package::{verify_prepared_session, VerificationRequest};
    use std::{
        fs,
        sync::{mpsc, Arc, Barrier},
        thread,
        time::Duration,
    };

    fn verified_legacy_package(
        participant_id: &str,
    ) -> (std::path::PathBuf, VerifiedPreparedSession) {
        let root = std::env::temp_dir().join(format!("pps-tauri-package-{}", random_nonce()));
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("block.wav"), b"not-played-validation-bytes").unwrap();
        fs::write(root.join("block.csv"), b"Trial_UID\ntrial-1\n").unwrap();
        let manifest_path = root.join("run-session.json");
        let manifest = serde_json::json!({
            "schema": "pps-run-session.v1",
            "participant_id": participant_id,
            "session_id": format!("{participant_id}_session_20260831"),
            "session_group_id": format!("{participant_id}_group_20260831"),
            "part_number": 1,
            "part_session_id": format!("{participant_id}_session_20260831_part_01"),
            "session_dir": root,
            "execution_mode": "design_schedule_blocks",
            "blocks": [{
                "index": 1,
                "label": "Verification block",
                "manifest_path": "block.csv",
                "wav_path": "block.wav",
                "trial_count": 1,
                "duration_s": 1.5,
                "metadata": {}
            }]
        });
        fs::write(
            &manifest_path,
            serde_json::to_vec_pretty(&manifest).unwrap(),
        )
        .unwrap();
        let verified = verify_prepared_session(VerificationRequest::new(&manifest_path)).unwrap();
        (root, verified)
    }

    fn pcm16_wav_bytes(sample_rate_hz: u32, frames: u32, seed: i16) -> Vec<u8> {
        let channels = 2_u16;
        let sample_count = frames * u32::from(channels);
        let data_bytes = sample_count * 2;
        let mut bytes = Vec::with_capacity(44 + data_bytes as usize);
        bytes.extend_from_slice(b"RIFF");
        bytes.extend_from_slice(&(36 + data_bytes).to_le_bytes());
        bytes.extend_from_slice(b"WAVEfmt ");
        bytes.extend_from_slice(&16_u32.to_le_bytes());
        bytes.extend_from_slice(&1_u16.to_le_bytes());
        bytes.extend_from_slice(&channels.to_le_bytes());
        bytes.extend_from_slice(&sample_rate_hz.to_le_bytes());
        bytes.extend_from_slice(&(sample_rate_hz * u32::from(channels) * 2).to_le_bytes());
        bytes.extend_from_slice(&(channels * 2).to_le_bytes());
        bytes.extend_from_slice(&16_u16.to_le_bytes());
        bytes.extend_from_slice(b"data");
        bytes.extend_from_slice(&data_bytes.to_le_bytes());
        for sample in 0..sample_count {
            bytes.extend_from_slice(&seed.wrapping_add(sample as i16).to_le_bytes());
        }
        bytes
    }

    fn verified_audio_package(
        participant_id: &str,
        block_count: u32,
    ) -> (std::path::PathBuf, VerifiedPreparedSession) {
        verified_audio_package_with_terminal_sample(participant_id, block_count, 4)
    }

    fn verified_audio_package_with_terminal_sample(
        participant_id: &str,
        block_count: u32,
        terminal_sample: u64,
    ) -> (std::path::PathBuf, VerifiedPreparedSession) {
        let root = std::env::temp_dir().join(format!("pps-tauri-audio-{}", random_nonce()));
        fs::create_dir_all(&root).unwrap();
        let mut blocks = Vec::new();
        for ordinal in 0..block_count {
            let wav_name = format!("block-{ordinal}.wav");
            let csv_name = format!("block-{ordinal}.csv");
            fs::write(
                root.join(&wav_name),
                pcm16_wav_bytes(48_000, 4 + ordinal, ordinal as i16),
            )
            .unwrap();
            fs::write(
                root.join(&csv_name),
                format!(
                    "Trial_Number,Trial_UID,Trial_Type,Family,Sample_Rate_Hz,Trial_Start_Sample,Looming_Onset_Sample,Tactile_Onset_Sample,Response_Window_Onset_Sample,Trial_End_Sample\n1,B{ordinal}_T1,Catch,catch,48000,0,1,2,1,{terminal_sample}\n"
                ),
            )
            .unwrap();
            blocks.push(serde_json::json!({
                "index": ordinal + 1,
                "label": format!("Audio block {}", ordinal + 1),
                "manifest_path": csv_name,
                "wav_path": wav_name,
                "trial_count": 1,
                "duration_s": 1.0,
                "metadata": {"sample_rate_hz": 48000}
            }));
        }
        let manifest_path = root.join("run-session.json");
        let manifest = serde_json::json!({
            "schema": "pps-run-session.v1",
            "participant_id": participant_id,
            "session_id": format!("{participant_id}_audio_session_20260831"),
            "session_group_id": format!("{participant_id}_audio_group_20260831"),
            "part_number": 1,
            "part_session_id": format!("{participant_id}_audio_part_01"),
            "session_dir": root,
            "execution_mode": "design_schedule_blocks",
            "blocks": blocks
        });
        fs::write(
            &manifest_path,
            serde_json::to_vec_pretty(&manifest).unwrap(),
        )
        .unwrap();
        let verified = verify_prepared_session(VerificationRequest::new(&manifest_path)).unwrap();
        (root, verified)
    }

    fn compile_current_execution(runtime: &AppRuntime) {
        let (guard, source) = runtime.begin_prepared_execution_inspection().unwrap();
        let compiled = compile_prepared_execution(source).unwrap();
        runtime.cache_prepared_execution(compiled).unwrap();
        drop(guard);
    }

    fn begin_audio_decode(
        runtime: &AppRuntime,
        block_ordinal: u32,
    ) -> (PreparedAudioPreparationGuard, PreparedAudioSource) {
        match runtime
            .begin_prepared_audio_preparation(block_ordinal)
            .unwrap()
        {
            PreparedAudioPreparation::Decode { _guard, source } => (_guard, source),
            PreparedAudioPreparation::Cached(_) => {
                panic!("test expected a cache miss and a fenced decode source")
            }
        }
    }

    fn claim_webview_controller(
        runtime: &AppRuntime,
        controller_id: &str,
        accepted_scopes: Vec<Scope>,
    ) -> RemoteSessionLeaseReceipt {
        let session_id = runtime.status().unwrap().session_id;
        runtime
            .claim_remote_session(RemoteSessionClaimRequest {
                session_id,
                controller_id: controller_id.to_owned(),
                accepted_scopes,
                ready_sequence: 2,
            })
            .unwrap()
    }

    fn locally_ready_runtime() -> AppRuntime {
        let runtime = AppRuntime::new();
        runtime.configure_remote(true, false).unwrap();
        runtime
            .dispatch_local(Action::PackagePrepareDemo, serde_json::json!({}))
            .unwrap();
        runtime
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
            )
            .unwrap();
        runtime
            .dispatch_local(Action::TargetArm, serde_json::json!({}))
            .unwrap();
        runtime
    }

    #[test]
    fn public_remote_projection_omits_private_operator_and_participant_fields() {
        let runtime = AppRuntime::new();
        runtime.configure_remote(true, false).unwrap();
        runtime
            .dispatch_local(
                Action::PackagePrepareDemo,
                serde_json::json!({"label": "PRIVATE_PACKAGE_LABEL_7781"}),
            )
            .unwrap();
        runtime
            .dispatch_local(
                Action::SetupSubmit,
                serde_json::json!({
                    "participant_code": "PRIVATE_CODE_7781",
                    "participant_name": "Private Name 7781",
                    "age": 47,
                    "handedness": "left",
                    "gender": "female",
                    "name_sharing_opt_in": true,
                    "part_labels": {"1": "PRIVATE_CONDITION_A", "2": "PRIVATE_CONDITION_B"}
                }),
            )
            .unwrap();
        runtime
            .dispatch_local(
                Action::SessionNote,
                serde_json::json!({"text": "PRIVATE_NOTE_7781"}),
            )
            .unwrap();

        let receipt = claim_webview_controller(
            &runtime,
            "controller_projection",
            Scope::DEFAULT_REMOTE.to_vec(),
        );
        let public_value = serde_json::to_value(&receipt.snapshot).unwrap();
        let public_json = serde_json::to_string(&public_value).unwrap();
        assert_eq!(
            public_value.get("schema").and_then(Value::as_str),
            Some("pps-runner-public-snapshot.v1")
        );
        for required in ["protocol", "target_id", "epoch", "revision"] {
            assert!(public_value.get(required).is_some(), "missing {required}");
        }
        for forbidden_key in [
            "identity",
            "package_label",
            "audit_event_count",
            "last_note",
            "participant_code",
            "participant_name_present",
            "name_sharing_opt_in",
            "age",
            "handedness",
            "gender",
            "part_labels",
            "part_label_options",
            "part_label_controls_visible",
            "controller_lease_id",
        ] {
            assert!(
                !public_json.contains(&format!("\"{forbidden_key}\"")),
                "public projection leaked key {forbidden_key}: {public_json}"
            );
        }
        for private_value in [
            "PRIVATE_PACKAGE_LABEL_7781",
            "PRIVATE_CODE_7781",
            "Private Name 7781",
            "PRIVATE_CONDITION_A",
            "PRIVATE_CONDITION_B",
            "PRIVATE_NOTE_7781",
            receipt.owner_token.as_str(),
        ] {
            assert!(
                !public_json.contains(private_value),
                "public projection leaked private value {private_value}"
            );
        }

        let local = runtime.snapshot().unwrap();
        assert_eq!(local.package_label, "PRIVATE_PACKAGE_LABEL_7781");
        assert_eq!(local.identity.participant_id, "PRIVATE_CODE_7781");
        assert_eq!(local.last_note, "PRIVATE_NOTE_7781");
        assert_eq!(local.safety.controller_lease_id, "controller_projection");
    }

    #[test]
    fn adopting_a_verified_session_rotates_remote_authority_and_retains_native_paths() {
        let runtime = AppRuntime::new();
        runtime.configure_remote(true, false).unwrap();
        let receipt = claim_webview_controller(
            &runtime,
            "controller_package_test",
            Scope::DEFAULT_REMOTE.to_vec(),
        );
        let old_status = runtime.status().unwrap();
        let (fixture_root, verified) = verified_legacy_package("P001");
        let expected_manifest = verified.manifest_path().to_path_buf();

        let adopted = runtime.adopt_verified_session(verified).unwrap();
        assert_eq!(adopted.identity.participant_id, "P001");
        assert_eq!(adopted.run.phase, RunnerPhase::Prepared);
        assert!(!adopted.safety.local_armed);
        assert!(!adopted.allowed_actions.contains(&Action::TargetArm));

        let new_status = runtime.status().unwrap();
        assert_ne!(new_status.session_id, old_status.session_id);
        assert_ne!(new_status.epoch, receipt.snapshot.epoch);
        assert!(!new_status.controller_connected);
        assert_eq!(
            runtime.0.authority.test_view().manifest_path,
            Some(expected_manifest.clone())
        );

        let adopted_status = runtime.status().unwrap();
        let replacement_controller = claim_webview_controller(
            &runtime,
            "controller_after_package_adoption",
            Scope::DEFAULT_REMOTE.to_vec(),
        );
        let replacement = runtime
            .dispatch_remote_session(remote_command(
                &replacement_controller,
                3,
                "replace-verified-plan-with-demo",
                Scope::SessionPrepare,
                Action::PackagePrepareDemo,
                serde_json::json!({}),
            ))
            .unwrap();
        assert_eq!(replacement.status, AppliedStatus::Rejected);
        assert_eq!(replacement.reason, "request_rejected");
        assert_eq!(runtime.snapshot().unwrap().identity.participant_id, "P001");
        assert_eq!(
            runtime.status().unwrap().session_id,
            adopted_status.session_id
        );
        assert_eq!(runtime.status().unwrap().epoch, adopted_status.epoch);
        assert_eq!(
            runtime.0.authority.test_view().manifest_path,
            Some(expected_manifest)
        );

        fs::remove_dir_all(fixture_root).unwrap();
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn stale_lan_reader_cannot_publish_package_or_config_broadcasts() {
        let runtime = AppRuntime::new();
        runtime.configure_remote_async(true, false).await.unwrap();
        let remote = runtime.remote_config_async().await.unwrap();
        let old_package_owner = runtime
            .claim_lan_controller(
                remote.session_id,
                "controller_before_package".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
            )
            .await
            .unwrap();
        let mut package_broadcast = runtime.0.state_tx.subscribe();
        let (fixture_root, verified) = verified_legacy_package("PRIVATE_PACKAGE_PARTICIPANT");

        runtime
            .adopt_verified_session_async(verified)
            .await
            .unwrap();
        let changed = tokio::time::timeout(Duration::from_secs(1), package_broadcast.recv())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(
            changed.identity.participant_id,
            "PRIVATE_PACKAGE_PARTICIPANT"
        );
        assert!(runtime
            .lan_publication_snapshot(old_package_owner.identity)
            .await
            .unwrap()
            .is_none());

        let remote = runtime.remote_config_async().await.unwrap();
        let old_config_owner = runtime
            .claim_lan_controller(
                remote.session_id,
                "controller_before_config".to_owned(),
                Scope::DEFAULT_REMOTE.into_iter().collect(),
            )
            .await
            .unwrap();
        let mut config_broadcast = runtime.0.state_tx.subscribe();
        runtime.configure_remote_async(false, false).await.unwrap();
        let changed = tokio::time::timeout(Duration::from_secs(1), config_broadcast.recv())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(changed.connection_state, "local_only");
        assert!(runtime
            .lan_publication_snapshot(old_config_owner.identity)
            .await
            .unwrap()
            .is_none());

        fs::remove_dir_all(fixture_root).unwrap();
    }

    #[test]
    fn prepared_session_selection_is_native_single_flight() {
        let runtime = AppRuntime::new();
        let first = runtime.begin_prepared_session_selection().unwrap();
        assert!(runtime.0.authority.test_view().manifest_path.is_none());
        assert_eq!(
            runtime.begin_prepared_session_selection().err().unwrap(),
            "prepared_session_selection_in_progress"
        );
        assert!(runtime.0.authority.test_view().manifest_path.is_none());

        drop(first);
        let next = runtime.begin_prepared_session_selection().unwrap();
        drop(next);
    }

    #[test]
    fn prepared_execution_inspection_requires_a_session_and_is_native_single_flight() {
        let runtime = AppRuntime::new();
        assert_eq!(
            runtime.begin_prepared_execution_inspection().err().unwrap(),
            "prepared_session_missing"
        );
        // A failed reservation must release the native single-flight flag.
        assert_eq!(
            runtime.begin_prepared_execution_inspection().err().unwrap(),
            "prepared_session_missing"
        );

        let (fixture_root, verified) = verified_legacy_package("P001");
        runtime.adopt_verified_session(verified).unwrap();
        let (first_guard, first_source) = runtime.begin_prepared_execution_inspection().unwrap();
        assert_eq!(first_source.generation, 1);
        assert_eq!(
            runtime.begin_prepared_execution_inspection().err().unwrap(),
            "prepared_execution_inspection_in_progress"
        );
        drop(first_guard);
        let (next_guard, _) = runtime.begin_prepared_execution_inspection().unwrap();
        drop(next_guard);
        fs::remove_dir_all(fixture_root).unwrap();
    }

    #[test]
    fn adopting_a_new_package_clears_a_cached_schedule_only_plan() {
        let runtime = AppRuntime::new();
        let (first_root, first_verified) = verified_legacy_package("P001");
        runtime.adopt_verified_session(first_verified).unwrap();
        let authority_before_inspection = runtime.snapshot().unwrap();
        let (guard, source) = runtime.begin_prepared_execution_inspection().unwrap();
        let compiled = compile_prepared_execution(source).unwrap();
        let summary = runtime.cache_prepared_execution(compiled).unwrap();
        drop(guard);

        assert_eq!(runtime.snapshot().unwrap(), authority_before_inspection);
        assert_eq!(summary.inspection_scope, "schedule-only");
        assert_eq!(summary.timing_qualification, "unqualified");
        assert!(!summary.executable);
        assert_eq!(
            runtime.0.authority.test_view().compiled_schedule_count,
            Some(1)
        );

        let (replacement_root, replacement) = verified_legacy_package("P001");
        runtime.adopt_verified_session(replacement).unwrap();
        let replacement_view = runtime.0.authority.test_view();
        assert!(replacement_view.compiled_schedule_count.is_none());
        assert_eq!(replacement_view.package_generation, 2);

        fs::remove_dir_all(first_root).unwrap();
        fs::remove_dir_all(replacement_root).unwrap();
    }

    #[test]
    fn stale_compilation_cannot_cross_a_package_generation_fence() {
        let runtime = AppRuntime::new();
        let (first_root, first_verified) = verified_legacy_package("P001");
        runtime.adopt_verified_session(first_verified).unwrap();
        let (guard, source) = runtime.begin_prepared_execution_inspection().unwrap();
        let stale_compilation = compile_prepared_execution(source).unwrap();

        let (replacement_root, replacement) = verified_legacy_package("P001");
        runtime.adopt_verified_session(replacement).unwrap();
        assert_eq!(
            runtime.cache_prepared_execution(stale_compilation),
            Err("prepared_package_replaced")
        );
        assert!(runtime
            .0
            .authority
            .test_view()
            .compiled_schedule_count
            .is_none());
        drop(guard);

        fs::remove_dir_all(first_root).unwrap();
        fs::remove_dir_all(replacement_root).unwrap();
    }

    #[test]
    fn prepared_audio_requires_a_compiled_plan_and_is_native_single_flight() {
        let runtime = AppRuntime::new();
        assert_eq!(
            runtime.begin_prepared_audio_preparation(0).err().unwrap(),
            "prepared_session_missing"
        );
        let (root, verified) = verified_audio_package("P001", 1);
        runtime.adopt_verified_session(verified).unwrap();
        assert_eq!(
            runtime.begin_prepared_audio_preparation(0).err().unwrap(),
            "prepared_execution_missing"
        );
        // The failed actor capture dropped the adapter-only load guard.
        assert_eq!(
            runtime.begin_prepared_audio_preparation(0).err().unwrap(),
            "prepared_execution_missing"
        );
        compile_current_execution(&runtime);
        let before_capture = runtime.0.authority.test_view();
        assert_eq!(before_capture.compiled_schedule_strong_count, Some(1));
        assert_eq!(before_capture.retained_session_strong_count, Some(1));

        let (guard, source) = begin_audio_decode(&runtime, 0);
        let captured = runtime.0.authority.test_view();
        assert_eq!(
            captured.compiled_schedule_strong_count,
            Some(2),
            "capturing a worker source must clone only the immutable Arc schedule handle"
        );
        assert_eq!(
            captured.retained_session_strong_count,
            Some(2),
            "capturing a worker source must clone only the verified-session Arc handle"
        );
        let release = Arc::new(Barrier::new(2));
        let worker_release = Arc::clone(&release);
        let (entered_tx, entered_rx) = mpsc::sync_channel(1);
        let worker = thread::spawn(move || {
            entered_tx.send(()).unwrap();
            worker_release.wait();
            drop(source);
            drop(guard);
        });
        entered_rx.recv().unwrap();
        assert_eq!(
            runtime.begin_prepared_audio_preparation(0).err().unwrap(),
            "prepared_audio_preparation_in_progress"
        );
        release.wait();
        worker.join().unwrap();
        let (next_guard, _) = begin_audio_decode(&runtime, 0);
        drop(next_guard);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn prepared_audio_capture_is_denied_while_a_demo_run_is_active() {
        let runtime = locally_ready_runtime();
        runtime
            .dispatch_local(Action::PartStart, serde_json::json!({"part_number": 1}))
            .unwrap();
        assert_eq!(
            runtime.begin_prepared_audio_preparation(0).err().unwrap(),
            "prepared_audio_active_run"
        );
    }

    #[test]
    fn wav_mutation_after_source_capture_fails_before_actor_cache_admission() {
        let runtime = AppRuntime::new();
        let (root, verified) = verified_audio_package("P001", 1);
        let wav_path = verified.blocks()[0].wav_path().to_path_buf();
        runtime.adopt_verified_session(verified).unwrap();
        compile_current_execution(&runtime);
        let (guard, source) = begin_audio_decode(&runtime, 0);

        let mut changed = fs::read(&wav_path).unwrap();
        let final_byte = changed.last_mut().unwrap();
        *final_byte ^= 0x7f;
        fs::write(&wav_path, changed).unwrap();
        let error = prepare_verified_audio(source).err().unwrap();
        assert_eq!(error.code(), "prepared_audio_changed");
        assert!(runtime
            .0
            .authority
            .test_view()
            .prepared_audio_block_ordinal
            .is_none());
        drop(guard);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn output_plan_worker_failure_cannot_publish_a_prepared_cache() {
        let runtime = AppRuntime::new();
        let (root, verified) = verified_audio_package_with_terminal_sample("P001", 1, 5);
        runtime.adopt_verified_session(verified).unwrap();
        compile_current_execution(&runtime);
        let (guard, source) = begin_audio_decode(&runtime, 0);
        let error = prepare_verified_audio(source).err().unwrap();
        assert_eq!(error.code(), "prepared_audio_schedule_outside_media");
        let view = runtime.0.authority.test_view();
        assert!(view.prepared_audio_block_ordinal.is_none());
        assert!(view.prepared_output_plan_event_count.is_none());
        drop(guard);

        let (retry_guard, retry_source) = begin_audio_decode(&runtime, 0);
        drop(retry_source);
        drop(retry_guard);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn late_audio_result_is_inert_after_package_replacement() {
        let runtime = AppRuntime::new();
        let (first_root, first) = verified_audio_package("P001", 1);
        runtime.adopt_verified_session(first).unwrap();
        compile_current_execution(&runtime);
        let (guard, source) = begin_audio_decode(&runtime, 0);
        let stale_candidate = prepare_verified_audio(source).unwrap();

        let (replacement_root, replacement) = verified_audio_package("P001", 1);
        runtime.adopt_verified_session(replacement).unwrap();
        assert_eq!(
            runtime.cache_prepared_audio(stale_candidate),
            Err("prepared_package_replaced")
        );
        assert!(runtime
            .0
            .authority
            .test_view()
            .prepared_audio_block_ordinal
            .is_none());
        drop(guard);
        fs::remove_dir_all(first_root).unwrap();
        fs::remove_dir_all(replacement_root).unwrap();
    }

    #[test]
    fn late_audio_result_is_inert_after_run_generation_changes() {
        let runtime = AppRuntime::new();
        let (root, verified) = verified_audio_package("P001", 1);
        runtime.adopt_verified_session(verified).unwrap();
        compile_current_execution(&runtime);
        let (guard, source) = begin_audio_decode(&runtime, 0);
        let stale_candidate = prepare_verified_audio(source).unwrap();
        runtime.0.authority.advance_run_generation_for_test();

        assert_eq!(
            runtime.cache_prepared_audio(stale_candidate),
            Err("prepared_audio_run_replaced")
        );
        assert!(runtime
            .0
            .authority
            .test_view()
            .prepared_audio_block_ordinal
            .is_none());
        drop(guard);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn one_block_audio_cache_replaces_old_pcm_with_a_path_free_summary() {
        let runtime = AppRuntime::new();
        let (root, verified) = verified_audio_package("PRIVATE_AUDIO_PARTICIPANT", 2);
        let private_path = verified.blocks()[0].wav_path().display().to_string();
        let private_digest = verified.blocks()[0].block_wav().sha256().to_owned();
        runtime.adopt_verified_session(verified).unwrap();
        compile_current_execution(&runtime);
        let revision_before_preparation = runtime.snapshot().unwrap().revision;

        let (first_guard, first_source) = begin_audio_decode(&runtime, 0);
        let first = runtime
            .cache_prepared_audio(prepare_verified_audio(first_source).unwrap())
            .unwrap();
        drop(first_guard);
        assert_eq!(first.cache_capacity_blocks, 1);
        assert!(first.decoded_bytes <= MAXIMUM_CACHED_DECODED_BYTES);
        assert_eq!(
            runtime.0.authority.test_view().prepared_audio_block_ordinal,
            Some(0)
        );

        match runtime.begin_prepared_audio_preparation(0).unwrap() {
            PreparedAudioPreparation::Cached(cached) => assert_eq!(cached, first),
            PreparedAudioPreparation::Decode { .. } => {
                panic!("an exact sequential cache hit must not decode again")
            }
        }

        let (second_guard, second_source) = begin_audio_decode(&runtime, 1);
        assert!(runtime
            .0
            .authority
            .test_view()
            .prepared_audio_block_ordinal
            .is_none());
        let second = runtime
            .cache_prepared_audio(prepare_verified_audio(second_source).unwrap())
            .unwrap();
        drop(second_guard);
        let cache = runtime.0.authority.test_view();
        assert_eq!(cache.prepared_audio_block_ordinal, Some(1));
        assert_eq!(
            cache.prepared_audio_decoded_bytes,
            Some(second.decoded_bytes)
        );
        assert_ne!(first.decoded_bytes, second.decoded_bytes);
        assert!(second.output_plan_prepared);
        assert_eq!(second.output_route, "legacy-stereo");
        assert!(second.scheduled_event_count > 0);
        assert_eq!(
            cache.prepared_output_plan_event_count,
            Some(second.scheduled_event_count as usize)
        );
        assert_eq!(cache.prepared_output_plan_run_generation, Some(1));
        assert_eq!(
            runtime.snapshot().unwrap().revision,
            revision_before_preparation,
            "native media/output-plan caching must not mutate RunnerCore"
        );

        let summary_json = serde_json::to_string(&second).unwrap();
        for forbidden in [
            private_path.as_str(),
            private_digest.as_str(),
            "PRIVATE_AUDIO_PARTICIPANT",
            "packageFingerprint",
            "runGeneration",
            "interleaved",
        ] {
            assert!(
                !summary_json.contains(forbidden),
                "prepared summary leaked {forbidden}: {summary_json}"
            );
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn late_audio_result_is_inert_after_compiled_plan_replacement() {
        let runtime = AppRuntime::new();
        let (root, verified) = verified_audio_package("P001", 1);
        runtime.adopt_verified_session(verified).unwrap();
        compile_current_execution(&runtime);
        let (guard, source) = begin_audio_decode(&runtime, 0);
        let stale_candidate = prepare_verified_audio(source).unwrap();

        compile_current_execution(&runtime);
        assert_eq!(
            runtime.cache_prepared_audio(stale_candidate),
            Err("prepared_execution_replaced")
        );
        assert!(runtime
            .0
            .authority
            .test_view()
            .prepared_audio_block_ordinal
            .is_none());
        drop(guard);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn newer_block_reservation_makes_an_older_ordinal_completion_inert() {
        let runtime = AppRuntime::new();
        let (root, verified) = verified_audio_package("P001", 2);
        runtime.adopt_verified_session(verified).unwrap();
        compile_current_execution(&runtime);
        let (first_guard, first_source) = begin_audio_decode(&runtime, 0);
        let stale_first = prepare_verified_audio(first_source).unwrap();
        drop(first_guard);

        let (second_guard, second_source) = begin_audio_decode(&runtime, 1);
        let second = runtime
            .cache_prepared_audio(prepare_verified_audio(second_source).unwrap())
            .unwrap();
        assert_eq!(second.block_ordinal, 1);
        assert_eq!(
            runtime.cache_prepared_audio(stale_first),
            Err("prepared_audio_preparation_replaced")
        );
        assert_eq!(
            runtime.0.authority.test_view().prepared_audio_block_ordinal,
            Some(1)
        );
        drop(second_guard);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn newer_receipt_for_the_same_block_makes_an_older_completion_inert() {
        let runtime = AppRuntime::new();
        let (root, verified) = verified_audio_package("P001", 1);
        runtime.adopt_verified_session(verified).unwrap();
        compile_current_execution(&runtime);
        let (first_guard, first_source) = begin_audio_decode(&runtime, 0);
        let stale = prepare_verified_audio(first_source).unwrap();
        drop(first_guard);

        let (second_guard, second_source) = begin_audio_decode(&runtime, 0);
        assert_eq!(
            runtime.cache_prepared_audio(stale),
            Err("prepared_audio_preparation_replaced")
        );
        let current = runtime
            .cache_prepared_audio(prepare_verified_audio(second_source).unwrap())
            .unwrap();
        assert_eq!(current.block_ordinal, 0);
        drop(second_guard);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn active_run_rejects_package_replacement_without_rotating_remote_authority() {
        let runtime = locally_ready_runtime();
        runtime
            .dispatch_local(Action::PartStart, serde_json::json!({"part_number": 1}))
            .unwrap();
        let old_status = runtime.status().unwrap();
        let (fixture_root, verified) = verified_legacy_package("P001");

        assert_eq!(
            runtime.adopt_verified_session(verified),
            Err("cannot_replace_active_package")
        );
        let unchanged = runtime.status().unwrap();
        assert_eq!(unchanged.session_id, old_status.session_id);
        assert_eq!(unchanged.epoch, old_status.epoch);
        assert!(runtime.0.authority.test_view().manifest_path.is_none());

        fs::remove_dir_all(fixture_root).unwrap();
    }

    fn remote_command(
        receipt: &RemoteSessionLeaseReceipt,
        control_sequence: u32,
        command_id: &str,
        scope: Scope,
        action: Action,
        args: Value,
    ) -> RemoteSessionDispatchRequest {
        RemoteSessionDispatchRequest {
            session_id: receipt.session_id.clone(),
            owner_token: receipt.owner_token.clone(),
            control_sequence,
            command: CommandBody {
                command_id: command_id.to_owned(),
                scope,
                action,
                args,
                expected_revision: Some(receipt.snapshot.revision),
            },
        }
    }

    fn remotely_owned_running_runtime() -> AppRuntime {
        let runtime = AppRuntime::new();
        runtime.configure_remote(true, false).unwrap();
        let _owner = claim_webview_controller(
            &runtime,
            "controller_active",
            Scope::DEFAULT_REMOTE.to_vec(),
        );
        runtime
            .dispatch_local(Action::PackagePrepareDemo, serde_json::json!({}))
            .unwrap();
        runtime
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
            )
            .unwrap();
        runtime
            .dispatch_local(Action::TargetArm, serde_json::json!({}))
            .unwrap();
        runtime
            .dispatch_local(Action::PartStart, serde_json::json!({"part_number": 1}))
            .unwrap();
        assert_eq!(runtime.snapshot().unwrap().run.phase, RunnerPhase::Running);
        runtime
    }

    fn assert_running_owner_was_safely_invalidated(runtime: &AppRuntime, state: &str) {
        let snapshot = runtime.snapshot().unwrap();
        assert_eq!(snapshot.run.phase, RunnerPhase::Paused);
        assert_eq!(snapshot.connection_state, state);
        assert!(snapshot.safety.controller_lease_id.is_empty());
        assert!(snapshot.safety.lease_expires_at_unix_ms.is_none());
        assert!(runtime.0.authority.test_view().active_controller.is_none());
    }

    #[test]
    fn local_only_runtime_starts_without_a_listener() {
        let runtime = AppRuntime::new();
        let status = runtime.status().unwrap();
        assert!(!status.enabled);
        assert!(!status.server_available);
        assert!(status.bind_address.is_empty());
        assert!(status.base_url.is_empty());
        assert!(status.controller_url.is_empty());

        let original_session = status.session_id;
        let rotated = runtime.rotate_pairing().unwrap();
        assert_ne!(rotated.session_id, original_session);
        assert!(!rotated.server_available);
        let website_only = runtime.configure_remote(true, false).unwrap();
        assert!(website_only.enabled);
        assert!(!website_only.server_available);
        assert!(website_only.bind_address.is_empty());
        let configured = runtime.configure_remote(false, true).unwrap();
        assert!(!configured.enabled);
        assert!(configured.allow_abort);
        assert!(!configured.server_available);
    }

    #[test]
    fn disabling_remote_pauses_a_run_owned_by_the_displaced_controller() {
        let runtime = remotely_owned_running_runtime();

        let status = runtime.configure_remote(false, false).unwrap();

        assert!(!status.enabled);
        assert_running_owner_was_safely_invalidated(&runtime, "local_only");
    }

    #[test]
    fn rotating_pairing_pauses_a_run_owned_by_the_displaced_controller() {
        let runtime = remotely_owned_running_runtime();
        let original_session = runtime.status().unwrap().session_id;

        let status = runtime.rotate_pairing().unwrap();

        assert_ne!(status.session_id, original_session);
        assert_running_owner_was_safely_invalidated(&runtime, "pairing_rotated");
    }

    #[test]
    fn changing_remote_scopes_pauses_a_run_owned_by_the_displaced_controller() {
        let runtime = remotely_owned_running_runtime();
        let original_session = runtime.status().unwrap().session_id;

        let status = runtime.configure_remote(true, true).unwrap();

        assert!(status.enabled);
        assert!(status.allow_abort);
        assert_ne!(status.session_id, original_session);
        assert_running_owner_was_safely_invalidated(&runtime, "remote_enabled");
    }

    #[test]
    fn late_old_webview_owner_cannot_renew_or_revoke_a_replacement() {
        let runtime = AppRuntime::new();
        runtime.configure_remote(true, false).unwrap();
        let old =
            claim_webview_controller(&runtime, "controller-old", Scope::DEFAULT_REMOTE.to_vec());
        runtime
            .revoke_remote_session(RemoteSessionOwnerRequest {
                session_id: old.session_id.clone(),
                owner_token: old.owner_token.clone(),
            })
            .unwrap();
        claim_webview_controller(&runtime, "controller-new", Scope::DEFAULT_REMOTE.to_vec());

        let renew_error = runtime
            .renew_remote_session(RemoteSessionRenewRequest {
                session_id: old.session_id.clone(),
                owner_token: old.owner_token.clone(),
                control_sequence: 3,
            })
            .unwrap_err();
        assert_eq!(renew_error.code, "stale_owner");
        let revoke_error = runtime
            .revoke_remote_session(RemoteSessionOwnerRequest {
                session_id: old.session_id,
                owner_token: old.owner_token,
            })
            .unwrap_err();
        assert_eq!(revoke_error.code, "stale_owner");

        let active = runtime.0.authority.test_view().active_controller.unwrap();
        assert_eq!(active.id, "controller-new");
        assert_eq!(
            runtime.snapshot().unwrap().safety.controller_lease_id,
            "controller-new"
        );
    }

    #[test]
    fn generated_owner_tokens_always_match_the_remote_token_grammar() {
        for _ in 0..1_024 {
            assert!(valid_peer_id(&random_owner_token()));
        }
    }

    #[test]
    fn webview_renew_requires_a_fresh_brsp_control_sequence() {
        let runtime = AppRuntime::new();
        runtime.configure_remote(true, false).unwrap();
        let receipt =
            claim_webview_controller(&runtime, "controller-renew", Scope::DEFAULT_REMOTE.to_vec());

        let renewed = runtime
            .renew_remote_session(RemoteSessionRenewRequest {
                session_id: receipt.session_id.clone(),
                owner_token: receipt.owner_token.clone(),
                control_sequence: 3,
            })
            .unwrap();
        assert_eq!(renewed.controller_id, "controller-renew");
        assert_eq!(
            renewed.snapshot.safety.lease_expires_at_unix_ms,
            Some(renewed.lease_expires_at_unix_ms)
        );
        assert_eq!(
            runtime.snapshot().unwrap().safety.controller_lease_id,
            "controller-renew"
        );

        let replayed = runtime
            .renew_remote_session(RemoteSessionRenewRequest {
                session_id: receipt.session_id,
                owner_token: receipt.owner_token,
                control_sequence: 3,
            })
            .unwrap_err();
        assert_eq!(replayed.code, "replayed_sequence");
    }

    #[test]
    fn webview_remote_command_never_uses_the_local_origin() {
        let runtime = locally_ready_runtime();
        let receipt = claim_webview_controller(
            &runtime,
            "controller-origin",
            Scope::DEFAULT_REMOTE.to_vec(),
        );
        let request = remote_command(
            &receipt,
            3,
            "command-origin-0001",
            Scope::SessionTransport,
            Action::TargetArm,
            serde_json::json!({}),
        );

        let applied = runtime.dispatch_remote_session(request).unwrap();

        assert_eq!(applied.status, AppliedStatus::Rejected);
        assert_eq!(applied.reason, "request_rejected");
        assert!(applied.snapshot.safety.local_armed);
        let encoded = serde_json::to_string(&applied).unwrap();
        assert!(!encoded.contains("action_is_local_only"));
        assert!(!encoded.contains("controller_lease_id"));
        assert!(!encoded.contains("participant_code"));
    }

    #[test]
    fn explicit_webview_revoke_pauses_a_remotely_started_run() {
        let runtime = locally_ready_runtime();
        let receipt = claim_webview_controller(
            &runtime,
            "controller-revoke",
            Scope::DEFAULT_REMOTE.to_vec(),
        );
        let started = runtime
            .dispatch_remote_session(remote_command(
                &receipt,
                3,
                "command-start-revoke",
                Scope::SessionTransport,
                Action::PartStart,
                serde_json::json!({"part_number": 1}),
            ))
            .unwrap();
        assert_eq!(started.status, AppliedStatus::Accepted);
        assert_eq!(started.snapshot.run.phase, RunnerPhase::Running);

        let revoked = runtime
            .revoke_remote_session(RemoteSessionOwnerRequest {
                session_id: receipt.session_id,
                owner_token: receipt.owner_token,
            })
            .unwrap();

        assert!(revoked.revoked);
        assert_eq!(revoked.snapshot.run.phase, RunnerPhase::Paused);
        assert_eq!(revoked.snapshot.connection_state, "remote_waiting");
        assert!(revoked.snapshot.safety.lease_expires_at_unix_ms.is_none());
        assert!(runtime
            .snapshot()
            .unwrap()
            .safety
            .controller_lease_id
            .is_empty());
        assert!(runtime.0.authority.test_view().active_controller.is_none());
    }

    #[test]
    fn native_webview_lease_timeout_pauses_a_remotely_started_run() {
        let runtime = locally_ready_runtime();
        let receipt = claim_webview_controller(
            &runtime,
            "controller-timeout",
            Scope::DEFAULT_REMOTE.to_vec(),
        );
        let started = runtime
            .dispatch_remote_session(remote_command(
                &receipt,
                3,
                "command-start-timeout",
                Scope::SessionTransport,
                Action::PartStart,
                serde_json::json!({"part_number": 1}),
            ))
            .unwrap();
        assert_eq!(started.snapshot.run.phase, RunnerPhase::Running);
        runtime.0.authority.force_owner_expiry();

        let snapshot = runtime.snapshot().unwrap();
        assert_eq!(snapshot.run.phase, RunnerPhase::Paused);
        assert_eq!(snapshot.connection_state, "remote_lease_expired");
        assert!(snapshot.safety.controller_lease_id.is_empty());
        assert!(runtime.0.authority.test_view().active_controller.is_none());
    }

    #[test]
    fn webview_remote_boundary_rejects_malformed_and_ungranted_requests() {
        let runtime = AppRuntime::new();
        let disabled = runtime
            .claim_remote_session(RemoteSessionClaimRequest {
                session_id: runtime.status().unwrap().session_id,
                controller_id: "controller-disabled".to_owned(),
                accepted_scopes: vec![Scope::SessionRead],
                ready_sequence: 2,
            })
            .unwrap_err();
        assert_eq!(disabled.code, "remote_disabled");

        runtime.configure_remote(true, false).unwrap();
        let unavailable = runtime
            .claim_remote_session(RemoteSessionClaimRequest {
                session_id: runtime.status().unwrap().session_id,
                controller_id: "controller-abort".to_owned(),
                accepted_scopes: vec![Scope::SessionAbort],
                ready_sequence: 2,
            })
            .unwrap_err();
        assert_eq!(unavailable.code, "scope_not_available");

        let receipt = claim_webview_controller(
            &runtime,
            "controller-scopes",
            Scope::DEFAULT_REMOTE.to_vec(),
        );
        let out_of_scope = runtime
            .dispatch_remote_session(remote_command(
                &receipt,
                3,
                "command-abort-0001",
                Scope::SessionAbort,
                Action::RunAbort,
                serde_json::json!({}),
            ))
            .unwrap_err();
        assert_eq!(out_of_scope.code, "scope_not_granted");

        let malformed = serde_json::json!({
            "sessionId": receipt.session_id,
            "ownerToken": receipt.owner_token,
            "controlSequence": 4,
            "command": {
                "commandId": "command-malformed",
                "scope": "session.read",
                "action": "not.a.real.action",
                "args": {},
                "expectedRevision": null
            }
        });
        assert!(serde_json::from_value::<RemoteSessionDispatchRequest>(malformed).is_err());

        let unknown_field = serde_json::json!({
            "sessionId": "session-1234",
            "controllerId": "controller-1234",
            "acceptedScopes": ["session.read"],
            "readySequence": 2,
            "surprise": true
        });
        assert!(serde_json::from_value::<RemoteSessionClaimRequest>(unknown_field).is_err());
    }

    #[tokio::test]
    async fn malformed_webview_owner_trace_stops_before_authority_admission() {
        let runtime = AppRuntime::new();
        let mut trace = runtime.start_latency_trace(LatencyRoute::WebViewVdo);
        let rejected = runtime
            .dispatch_remote_session_traced_async(
                RemoteSessionDispatchRequest {
                    session_id: "session_1234".to_owned(),
                    owner_token: "!".to_owned(),
                    control_sequence: 1,
                    command: CommandBody {
                        command_id: "command-malformed-owner".to_owned(),
                        scope: Scope::SessionTransport,
                        action: Action::PartStart,
                        args: serde_json::json!({"part_number": 1}),
                        expected_revision: Some(0),
                    },
                },
                trace.trace(),
            )
            .await;
        assert_eq!(rejected.unwrap_err().code, "invalid_owner_token");
        // These are the outer Tauri handler's bounded-error return points.
        trace.mark(LatencyStage::ReplyReady);
        trace.mark(LatencyStage::AdapterHandoff);
        trace.finish(TraceOutcome::Rejected);

        let summary = runtime.latency_summary();
        let route = summary
            .routes
            .iter()
            .find(|route| route.route == LatencyRoute::WebViewVdo)
            .unwrap();
        for stage in [
            LatencyStage::AdapterValidationComplete,
            LatencyStage::ReplyReady,
            LatencyStage::AdapterHandoff,
        ] {
            assert_eq!(
                route.stages[stage.index()]
                    .elapsed_from_native_ingress
                    .sample_count,
                1
            );
        }
        for stage in [
            LatencyStage::AuthorityAdmission,
            LatencyStage::AuthorityDequeue,
            LatencyStage::AuthorityAuthorizationComplete,
            LatencyStage::ReducerValidationComplete,
            LatencyStage::ReducerApplied,
        ] {
            assert_eq!(
                route.stages[stage.index()]
                    .elapsed_from_native_ingress
                    .sample_count,
                0
            );
        }
    }

    #[tokio::test]
    async fn native_webview_traces_cover_applied_reducer_rejection_and_old_owner_paths() {
        let (runtime, old, current) = tokio::task::spawn_blocking(|| {
            let runtime = locally_ready_runtime();
            let old = claim_webview_controller(
                &runtime,
                "controller-trace-old",
                Scope::DEFAULT_REMOTE.to_vec(),
            );
            runtime
                .revoke_remote_session(RemoteSessionOwnerRequest {
                    session_id: old.session_id.clone(),
                    owner_token: old.owner_token.clone(),
                })
                .unwrap();
            let current = claim_webview_controller(
                &runtime,
                "controller-trace-current",
                Scope::DEFAULT_REMOTE.to_vec(),
            );
            (runtime, old, current)
        })
        .await
        .unwrap();

        let mut stale_trace = runtime.start_latency_trace(LatencyRoute::WebViewVdo);
        let stale = runtime
            .dispatch_remote_session_traced_async(
                remote_command(
                    &old,
                    3,
                    "trace-old-owner",
                    Scope::SessionTransport,
                    Action::PartStart,
                    serde_json::json!({"part_number": 1}),
                ),
                stale_trace.trace(),
            )
            .await;
        assert_eq!(stale.unwrap_err().code, "stale_owner");
        stale_trace.mark(LatencyStage::AdapterHandoff);
        stale_trace.finish(TraceOutcome::Rejected);

        let mut rejected_trace = runtime.start_latency_trace(LatencyRoute::WebViewVdo);
        let rejected = runtime
            .dispatch_remote_session_traced_async(
                remote_command(
                    &current,
                    3,
                    "trace-reducer-rejection",
                    Scope::SessionTransport,
                    Action::PartStart,
                    serde_json::json!({"part_number": 99}),
                ),
                rejected_trace.trace(),
            )
            .await
            .unwrap();
        assert_eq!(rejected.status, AppliedStatus::Rejected);
        rejected_trace.mark(LatencyStage::AdapterHandoff);
        rejected_trace.finish(TraceOutcome::Rejected);

        let mut applied_trace = runtime.start_latency_trace(LatencyRoute::WebViewVdo);
        let applied = runtime
            .dispatch_remote_session_traced_async(
                remote_command(
                    &current,
                    4,
                    "trace-applied",
                    Scope::SessionTransport,
                    Action::PartStart,
                    serde_json::json!({"part_number": 1}),
                ),
                applied_trace.trace(),
            )
            .await
            .unwrap();
        assert_eq!(applied.status, AppliedStatus::Accepted);
        applied_trace.mark(LatencyStage::AdapterHandoff);
        applied_trace.finish(TraceOutcome::Applied);

        let summary = runtime.latency_summary();
        let route = summary
            .routes
            .iter()
            .find(|route| route.route == LatencyRoute::WebViewVdo)
            .unwrap();
        assert_eq!(summary.count, 3);
        assert_eq!(summary.unfinished_count, 0);
        assert_eq!(route.count, 3);
        assert_eq!(
            route.stages[LatencyStage::AuthorityAuthorizationComplete.index()]
                .elapsed_from_native_ingress
                .sample_count,
            3
        );
        assert_eq!(
            route.stages[LatencyStage::ReducerValidationComplete.index()]
                .elapsed_from_native_ingress
                .sample_count,
            2
        );
        assert_eq!(
            route.stages[LatencyStage::ReducerApplied.index()]
                .elapsed_from_native_ingress
                .sample_count,
            1
        );
        assert_eq!(
            route.stages[LatencyStage::ReplyReady.index()]
                .elapsed_from_native_ingress
                .sample_count,
            3
        );
        assert!(
            route.stages[LatencyStage::ReplyReady.index()]
                .elapsed_from_native_ingress
                .worst_us
                >= route.stages[LatencyStage::ReducerApplied.index()]
                    .elapsed_from_native_ingress
                    .worst_us
        );
        assert_eq!(
            route.stages[LatencyStage::SendCompleted.index()]
                .elapsed_from_native_ingress
                .sample_count,
            0
        );
    }
}
