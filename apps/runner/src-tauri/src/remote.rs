use std::{
    collections::{BTreeSet, HashMap},
    future::Future,
    path::PathBuf,
    sync::Arc,
    time::{Duration, Instant},
};

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        Path, State,
    },
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Router,
};
use futures_util::SinkExt;
use pps_brsp::{
    create_proof_envelope, negotiate_session, random_epoch, random_nonce, ready_matches,
    valid_peer_id, validate_common, validate_hello, SequenceDecision, SequenceGuard,
};
use pps_contracts::{
    AppliedBody, AppliedStatus, BrspRole, CommandEnvelope, EmptyEnvelope, Envelope, ErrorBody,
    ErrorEnvelope, HelloBody, HelloEnvelope, ProofEnvelope, ReadyBody, ReadyEnvelope, Scope,
    WireEnvelope, MAX_CONTROL_BYTES, MAX_STATE_BYTES, PPS_REMOTE_CAPABILITIES,
};
use serde::{de::DeserializeOwned, Serialize};
use tokio::sync::{mpsc, watch, Mutex as AsyncMutex, OwnedSemaphorePermit, Semaphore};
use tower_http::services::ServeDir;

use crate::{
    execution_owner::RemoteOwnerIdentity,
    latency_diagnostics::{LatencyRoute, LatencyStage, LatencyTraceGuard, TraceOutcome},
    runtime::{AppRuntime, RemoteApplied, RemoteRunnerSnapshot},
};

const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(12);
const SOCKET_WRITE_TIMEOUT: Duration = Duration::from_secs(2);
const SOCKET_CLOSE_TIMEOUT: Duration = Duration::from_secs(1);
const TRANSPORT_PING_INTERVAL: Duration = Duration::from_secs(2);
const TRANSPORT_PONG_TIMEOUT: Duration = Duration::from_secs(3);
const SOCKET_WRITE_BUFFER_SIZE: usize = MAX_CONTROL_BYTES;
const MAX_SOCKET_WRITE_BUFFER_SIZE: usize = MAX_CONTROL_BYTES * 4;
const STATE_HEARTBEAT: Duration = Duration::from_millis(250);
const STATE_FLUSH: Duration = Duration::from_millis(16);
const CONTROLLER_LEASE: Duration = Duration::from_secs(5);
const LEASE_CHECK: Duration = Duration::from_millis(100);
const MAX_RELAY_ROOMS: usize = 16;
const MAX_RELAY_MESSAGES_PER_SECOND: u32 = 120;
const RELAY_CONTROL_QUEUE_CAPACITY: usize = 32;
const MAX_CONCURRENT_DESKTOP_SESSIONS: usize = 8;
const MAX_CONCURRENT_RELAY_SESSIONS: usize = MAX_RELAY_ROOMS * 2;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TransportDeadline {
    HandshakeRead,
    SocketWrite,
    SocketClose,
    Pong,
}

impl TransportDeadline {
    const fn code(self) -> &'static str {
        match self {
            Self::HandshakeRead => "handshake_read_timeout",
            Self::SocketWrite => "socket_write_timeout",
            Self::SocketClose => "socket_close_timeout",
            Self::Pong => "transport_pong_timeout",
        }
    }

    const fn message(self) -> &'static str {
        match self {
            Self::HandshakeRead => "BRSP handshake read timed out",
            Self::SocketWrite => "WebSocket write timed out",
            Self::SocketClose => "WebSocket close timed out",
            Self::Pong => "WebSocket peer did not answer the transport ping",
        }
    }
}

fn transport_timeout_error(deadline: TransportDeadline) -> String {
    format!("{} ({})", deadline.message(), deadline.code())
}

async fn with_transport_deadline<T, F>(
    deadline: TransportDeadline,
    duration: Duration,
    future: F,
) -> Result<T, String>
where
    F: Future<Output = Result<T, String>>,
{
    tokio::time::timeout(duration, future)
        .await
        .map_err(|_| transport_timeout_error(deadline))?
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct PendingPong {
    payload: [u8; 8],
    deadline: Instant,
}

/// Connection-level health only. This type deliberately has no access to the
/// BRSP controller owner or its semantic lease, so a Ping/Pong can never renew
/// command authority.
#[derive(Debug)]
struct TransportLiveness {
    connection_nonce: u32,
    next_sequence: u32,
    pending_pong: Option<PendingPong>,
}

impl TransportLiveness {
    fn new() -> Self {
        Self::with_nonce(random_epoch())
    }

    fn with_nonce(connection_nonce: u32) -> Self {
        Self {
            connection_nonce,
            next_sequence: 1,
            pending_pong: None,
        }
    }

    fn next_ping_payload(&self) -> Option<[u8; 8]> {
        if self.pending_pong.is_some() {
            return None;
        }
        let mut payload = [0_u8; 8];
        payload[..4].copy_from_slice(&self.connection_nonce.to_be_bytes());
        payload[4..].copy_from_slice(&self.next_sequence.to_be_bytes());
        Some(payload)
    }

    fn ping_sent(&mut self, payload: [u8; 8], now: Instant) {
        debug_assert!(self.pending_pong.is_none());
        self.next_sequence = self.next_sequence.wrapping_add(1);
        self.pending_pong = Some(PendingPong {
            payload,
            deadline: now + TRANSPORT_PONG_TIMEOUT,
        });
    }

    fn accept_pong(&mut self, payload: &[u8], now: Instant) -> bool {
        let matches = self
            .pending_pong
            .as_ref()
            .is_some_and(|pending| payload == pending.payload && now < pending.deadline);
        if matches {
            self.pending_pong = None;
        }
        matches
    }

    fn has_pending_pong(&self) -> bool {
        self.pending_pong.is_some()
    }

    fn pong_wait(&self, now: Instant) -> Duration {
        self.pending_pong
            .map(|pending| pending.deadline.saturating_duration_since(now))
            .unwrap_or(TRANSPORT_PONG_TIMEOUT)
    }

    fn pong_timed_out(&self, now: Instant) -> bool {
        self.pending_pong
            .is_some_and(|pending| now >= pending.deadline)
    }
}

fn require_live_transport(liveness: &TransportLiveness, now: Instant) -> Result<(), String> {
    if liveness.pong_timed_out(now) {
        Err(transport_timeout_error(TransportDeadline::Pong))
    } else {
        Ok(())
    }
}

#[derive(Debug, Serialize)]
struct RemoteSnapshotBody {
    revision: u64,
    state: RemoteRunnerSnapshot,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct RemoteAppliedResult {
    action: pps_contracts::Action,
    status: AppliedStatus,
    reason: &'static str,
    accepted_revision: u64,
    resulting_revision: u64,
}

fn remote_applied_body(applied: &RemoteApplied) -> AppliedBody {
    let rejected = matches!(applied.status, AppliedStatus::Rejected);
    let result = RemoteAppliedResult {
        action: applied.action,
        status: applied.status,
        reason: if rejected {
            "request_rejected"
        } else {
            "request_accepted"
        },
        accepted_revision: applied.accepted_revision,
        resulting_revision: applied.resulting_revision,
    };
    AppliedBody {
        command_id: applied.id.clone(),
        ok: !rejected,
        revision: applied.resulting_revision,
        result: serde_json::to_value(result).ok(),
        error: rejected.then(|| "request_rejected".to_owned()),
    }
}

#[derive(Clone)]
struct ServerState {
    runtime: AppRuntime,
    relay: Arc<AsyncMutex<RelayRegistry>>,
    desktop_admission: SocketAdmission,
    relay_admission: SocketAdmission,
}

/// Bounds upgraded desktop tasks before any unauthenticated BRSP handshake
/// read begins. The owned permit stays alive through handshake, session, and
/// the bounded close attempt.
#[derive(Clone)]
struct SocketAdmission {
    permits: Arc<Semaphore>,
}

impl SocketAdmission {
    fn new(capacity: usize) -> Self {
        Self {
            permits: Arc::new(Semaphore::new(capacity)),
        }
    }

    fn try_acquire(&self) -> Option<OwnedSemaphorePermit> {
        Arc::clone(&self.permits).try_acquire_owned().ok()
    }
}

/// Bind and launch the LAN server only after an explicit user activation.
/// Binding failures are returned to the command/UI rather than crashing app
/// startup; a previously launched server is reused across disable/re-enable.
pub fn ensure_started(runtime: AppRuntime, web_root: PathBuf) -> Result<(), String> {
    let Some((listener, bind_addr)) = runtime.reserve_remote_listener()? else {
        return Ok(());
    };
    let failure_runtime = runtime.clone();
    tauri::async_runtime::spawn(async move {
        if let Err(error) = serve(runtime, listener, web_root).await {
            failure_runtime.remote_server_failed(bind_addr, error);
        }
    });
    Ok(())
}

pub async fn serve(
    runtime: AppRuntime,
    listener: std::net::TcpListener,
    web_root: PathBuf,
) -> Result<(), String> {
    let listener = tokio::net::TcpListener::from_std(listener)
        .map_err(|error| format!("could not start the companion server: {error}"))?;
    let state = ServerState {
        runtime,
        relay: Arc::new(AsyncMutex::new(RelayRegistry::default())),
        desktop_admission: SocketAdmission::new(MAX_CONCURRENT_DESKTOP_SESSIONS),
        relay_admission: SocketAdmission::new(MAX_CONCURRENT_RELAY_SESSIONS),
    };
    let static_files = ServeDir::new(web_root).append_index_html_on_directories(true);
    let router = Router::new()
        .route("/ws/desktop", get(desktop_upgrade))
        .route("/ws/relay/{room}/{role}", get(relay_upgrade))
        .fallback_service(static_files)
        .with_state(state);
    axum::serve(listener, router)
        .await
        .map_err(|error| format!("companion server stopped: {error}"))
}

async fn desktop_upgrade(ws: WebSocketUpgrade, State(state): State<ServerState>) -> Response {
    let Some(admission_permit) = state.desktop_admission.try_acquire() else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            "Desktop remote capacity reached; retry after another session closes.",
        )
            .into_response();
    };
    ws.max_message_size(MAX_CONTROL_BYTES)
        .max_frame_size(MAX_CONTROL_BYTES)
        .write_buffer_size(SOCKET_WRITE_BUFFER_SIZE)
        .max_write_buffer_size(MAX_SOCKET_WRITE_BUFFER_SIZE)
        .on_upgrade(move |mut socket| async move {
            let _admission_permit = admission_permit;
            // Proof failures intentionally fail closed without returning details
            // useful for online secret guessing.
            let _ = desktop_session(&mut socket, &state.runtime).await;
            let _ = close_socket(&mut socket).await;
        })
}

async fn desktop_session(socket: &mut WebSocket, runtime: &AppRuntime) -> Result<(), String> {
    let remote = runtime.remote_config_async().await?;
    if !remote.enabled {
        return Err("phone remote is disabled".to_owned());
    }
    let mut available_scopes = runtime.available_scopes_async().await?;
    available_scopes.sort();
    let target_sender_id = format!("target_{}", &random_nonce()[..18]);
    let target_sender_epoch = random_epoch();
    let target_hello = Envelope::new(
        "hello",
        remote.session_id.clone(),
        target_sender_id.clone(),
        target_sender_epoch,
        0,
        HelloBody {
            role: BrspRole::Target,
            nonce: random_nonce(),
            capabilities: PPS_REMOTE_CAPABILITIES
                .iter()
                .map(|capability| (*capability).to_owned())
                .collect(),
            requested_scopes: vec![],
            granted_scopes: available_scopes.clone(),
        },
    );
    validate_hello(&target_hello).map_err(|error| error.to_string())?;
    send_control(socket, &target_hello).await?;

    let controller_hello: HelloEnvelope = receive_typed(socket, "hello", HANDSHAKE_TIMEOUT).await?;
    validate_hello(&controller_hello).map_err(|error| error.to_string())?;
    if controller_hello.body.role != BrspRole::Controller
        || controller_hello.session_id != remote.session_id
        || !valid_peer_id(&controller_hello.sender_id)
    {
        return Err("invalid controller hello".to_owned());
    }

    let target_proof = create_proof_envelope(&remote.secret, &target_hello, &controller_hello, 1)
        .map_err(|error| error.to_string())?;
    send_control(socket, &target_proof).await?;
    let controller_proof: ProofEnvelope = receive_typed(socket, "proof", HANDSHAKE_TIMEOUT).await?;
    assert_remote_sender(&controller_proof, &controller_hello)?;
    if controller_proof.sequence != 1
        || !remote
            .secret
            .verify_proof(&controller_proof, &target_hello, &controller_hello)
    {
        return Err("pairing proof failed".to_owned());
    }

    let negotiated =
        negotiate_session(&target_hello, &controller_hello).map_err(|error| error.to_string())?;
    if negotiated.accepted_scopes.is_empty() {
        return Err("no requested scope was granted".to_owned());
    }
    let target_ready = Envelope::new(
        "ready",
        remote.session_id.clone(),
        target_sender_id.clone(),
        target_sender_epoch,
        2,
        ReadyBody {
            capabilities: negotiated.capabilities.clone(),
            accepted_scopes: negotiated.accepted_scopes.clone(),
        },
    );
    send_control(socket, &target_ready).await?;
    let controller_ready: ReadyEnvelope = receive_typed(socket, "ready", HANDSHAKE_TIMEOUT).await?;
    assert_remote_sender(&controller_ready, &controller_hello)?;
    if controller_ready.sequence != 2 || !ready_matches(&controller_ready.body, &negotiated) {
        return Err("controller ready did not match negotiation".to_owned());
    }

    // `controllerConnected` means the complete mutual hello/proof/ready
    // exchange succeeded. Reserve the single-controller authority only now,
    // so a stalled or invalid ready cannot appear as an authenticated owner.
    let claim = runtime
        .claim_lan_controller(
            remote.session_id.clone(),
            controller_hello.sender_id.clone(),
            negotiated.accepted_scopes.iter().copied().collect(),
        )
        .await?;
    let mut controller_guard = ActiveControllerGuard {
        runtime: runtime.clone(),
        identity: claim.identity,
        armed: true,
    };
    require_claimed_public_schema(&mut controller_guard, &claim.snapshot.schema).await?;

    let session_result: Result<(), String> = async {
        let mut lease_deadline = Instant::now() + CONTROLLER_LEASE;
    let mut target_control_sequence = 2_u32;
    let mut target_state_sequence = 0_u32;
    let scope_set = negotiated
        .accepted_scopes
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    let can_read = grants_state_read(&scope_set);
    if can_read {
        if !send_snapshot(
            socket,
            &target_hello,
            &mut target_control_sequence,
            &controller_guard,
        )
        .await?
        {
            return Ok(());
        }
        if !send_state(
            socket,
            &target_hello,
            &mut target_state_sequence,
            &controller_guard,
        )
        .await?
        {
            return Ok(());
        }
    }

    let mut remote_control_sequence = SequenceGuard::after(controller_ready.sequence);
    let mut state_rx = runtime.0.state_tx.subscribe();
    let mut pending_state = false;
    let mut state_flush = tokio::time::interval(STATE_FLUSH);
    state_flush.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut heartbeat = tokio::time::interval(STATE_HEARTBEAT);
    heartbeat.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut config_check = tokio::time::interval(Duration::from_millis(500));
    config_check.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut lease_check = tokio::time::interval(LEASE_CHECK);
    lease_check.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut transport_ping = tokio::time::interval_at(
        tokio::time::Instant::now() + TRANSPORT_PING_INTERVAL,
        TRANSPORT_PING_INTERVAL,
    );
    transport_ping.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut transport_liveness = TransportLiveness::new();

    loop {
        require_live_transport(&transport_liveness, Instant::now())?;
        tokio::select! {
            incoming = socket.recv() => {
                require_live_transport(&transport_liveness, Instant::now())?;
                let Some(incoming) = incoming else {
                    return Err("WebSocket connection closed".to_owned());
                };
                let message = incoming.map_err(|_| "WebSocket read failed".to_owned())?;
                match message {
                    Message::Text(text) => {
                        // This is the earliest native boundary after Axum has
                        // yielded the complete frame. It does not include the
                        // browser, radio, WebRTC, or remote-host clock.
                        let ingress = runtime.capture_latency_ingress();
                        if Instant::now() >= lease_deadline {
                            return Err("controller lease expired".to_owned());
                        }
                        if text.len() > MAX_CONTROL_BYTES {
                            return Err("control message exceeds 16 KiB".to_owned());
                        }
                        let wire: WireEnvelope = serde_json::from_str(&text)
                            .map_err(|_| "malformed BRSP control envelope".to_owned())?;
                        let mut command_trace = (wire.message_type == "command").then(|| {
                            runtime.start_latency_trace_from(LatencyRoute::LanWebSocket, ingress)
                        });
                        if let Err(error) = validate_wire_identity(&wire, &controller_hello) {
                            if let Some(trace) = command_trace.as_mut() {
                                trace.mark(LatencyStage::AdapterValidationComplete);
                                trace.finish(TraceOutcome::Rejected);
                            }
                            return Err(error);
                        }
                        if remote_control_sequence.accept(wire.sequence) != SequenceDecision::Fresh {
                            if let Some(trace) = command_trace.as_ref() {
                                trace.mark(LatencyStage::AdapterValidationComplete);
                            }
                            let envelope = prepare_traced_protocol_error(
                                &target_hello,
                                &mut target_control_sequence,
                                "replayed_sequence",
                                "Control sequence is duplicate, old, or half-range ambiguous.",
                                command_trace.as_ref(),
                            );
                            let send_result = send_control(socket, &envelope).await;
                            finish_rejected_protocol_trace(
                                command_trace.as_mut(),
                                send_result.is_ok(),
                            );
                            send_result?;
                            continue;
                        }
                        match wire.message_type.as_str() {
                            "command" => {
                                let mut trace = command_trace
                                    .take()
                                    .expect("a command frame creates one native trace");
                                let frame: CommandEnvelope = match typed_from_wire(wire, "command") {
                                    Ok(frame) => frame,
                                    Err(error) => {
                                        trace.mark(LatencyStage::AdapterValidationComplete);
                                        trace.finish(TraceOutcome::Rejected);
                                        return Err(error);
                                    }
                                };
                                trace.mark(LatencyStage::AdapterValidationComplete);
                                let applied = runtime
                                    .dispatch_lan_controller_traced(
                                        controller_guard.identity.clone(),
                                        frame.sequence,
                                        frame.body,
                                        trace.trace(),
                                    )
                                    .await?;
                                lease_deadline = Instant::now() + CONTROLLER_LEASE;
                                let envelope = Envelope::new(
                                    "applied",
                                    target_hello.session_id.clone(),
                                    target_hello.sender_id.clone(),
                                    target_hello.sender_epoch,
                                    next_sequence(&mut target_control_sequence),
                                    remote_applied_body(&applied),
                                );
                                trace.mark(LatencyStage::AdapterHandoff);
                                let send_result = send_control(socket, &envelope).await;
                                if send_result.is_ok() {
                                    trace.mark(LatencyStage::SendCompleted);
                                }
                                trace.finish(if send_result.is_err() {
                                    TraceOutcome::Failed
                                } else if applied.status == AppliedStatus::Accepted {
                                    TraceOutcome::Applied
                                } else {
                                    TraceOutcome::Rejected
                                });
                                send_result?;
                                if can_read {
                                    pending_state = true;
                                }
                            }
                            "snapshot-request" => {
                                let _: EmptyEnvelope = typed_from_wire(wire, "snapshot-request")?;
                                if !controller_guard.refresh_lease().await? {
                                    break;
                                }
                                lease_deadline = Instant::now() + CONTROLLER_LEASE;
                                if can_read {
                                    if !send_snapshot(
                                        socket,
                                        &target_hello,
                                        &mut target_control_sequence,
                                        &controller_guard,
                                    ).await? {
                                        break;
                                    }
                                } else {
                                    send_protocol_error(
                                        socket,
                                        &target_hello,
                                        &mut target_control_sequence,
                                        "scope_required",
                                        "session.read is required for snapshots.",
                                    ).await?;
                                }
                            }
                            "bye" => {
                                let _: EmptyEnvelope = typed_from_wire(wire, "bye")?;
                                break;
                            }
                            "error" => {
                                let _: ErrorEnvelope = typed_from_wire(wire, "error")?;
                                if !controller_guard.refresh_lease().await? {
                                    break;
                                }
                                lease_deadline = Instant::now() + CONTROLLER_LEASE;
                                // A bounded peer diagnostic does not mutate target state.
                            }
                            _ => {
                                send_protocol_error(
                                    socket,
                                    &target_hello,
                                    &mut target_control_sequence,
                                    "unsupported_message",
                                    "Message type is not valid from a ready controller.",
                                ).await?;
                            }
                        }
                    }
                    Message::Ping(payload) => send_socket_message(socket, Message::Pong(payload)).await?,
                    Message::Pong(payload) => {
                        // Transport health is intentionally independent from
                        // the actor-owned five-second semantic controller lease.
                        transport_liveness.accept_pong(payload.as_ref(), Instant::now());
                    }
                    Message::Close(_) => break,
                    Message::Binary(_) => return Err("BRSP/1 JSON envelopes must use text frames".to_owned()),
                }
            }
            changed = state_rx.recv(), if can_read => {
                match changed {
                    Ok(_) => {
                        pending_state = true;
                        while state_rx.try_recv().is_ok() {
                        }
                    }
                    Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => {
                        pending_state = true;
                    }
                    Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
                }
            }
            _ = state_flush.tick(), if can_read && pending_state => {
                require_live_transport(&transport_liveness, Instant::now())?;
                pending_state = false;
                if !send_state(socket, &target_hello, &mut target_state_sequence, &controller_guard).await? {
                    break;
                }
            }
            _ = heartbeat.tick(), if can_read => {
                require_live_transport(&transport_liveness, Instant::now())?;
                pending_state = false;
                if !send_state(socket, &target_hello, &mut target_state_sequence, &controller_guard).await? {
                    break;
                }
            }
            _ = config_check.tick() => {
                require_live_transport(&transport_liveness, Instant::now())?;
                let config = runtime.remote_config_async().await?;
                if !config.enabled || config.session_id != remote.session_id {
                    send_protocol_error(
                        socket,
                        &target_hello,
                        &mut target_control_sequence,
                        "session_rotated",
                        "Remote activation changed; use a fresh invitation.",
                    ).await?;
                    break;
                }
            }
            _ = lease_check.tick() => {
                require_live_transport(&transport_liveness, Instant::now())?;
                if Instant::now() >= lease_deadline {
                    return Err("controller lease expired".to_owned());
                }
            }
            _ = transport_ping.tick() => {
                require_live_transport(&transport_liveness, Instant::now())?;
                if let Some(payload) = transport_liveness.next_ping_payload() {
                    send_socket_message(socket, Message::Ping(payload.to_vec().into())).await?;
                    transport_liveness.ping_sent(payload, Instant::now());
                }
            }
            _ = tokio::time::sleep(transport_liveness.pong_wait(Instant::now())), if transport_liveness.has_pending_pong() => {
                if transport_liveness.pong_timed_out(Instant::now()) {
                    return Err(transport_timeout_error(TransportDeadline::Pong));
                }
            }
        }
    }
    Ok(())
    }
    .await;

    finish_claimed_session(&mut controller_guard, session_result).await
}

async fn finish_claimed_session(
    controller_guard: &mut ActiveControllerGuard,
    session_result: Result<(), String>,
) -> Result<(), String> {
    let connection_state = claimed_session_connection_state(&session_result);
    controller_guard.revoke(connection_state).await?;
    session_result
}

async fn require_claimed_public_schema(
    controller_guard: &mut ActiveControllerGuard,
    schema: &str,
) -> Result<(), String> {
    if schema == "pps-runner-public-snapshot.v1" {
        return Ok(());
    }
    finish_claimed_session(
        controller_guard,
        Err("native public snapshot schema mismatch".to_owned()),
    )
    .await
}

fn claimed_session_connection_state(result: &Result<(), String>) -> &'static str {
    let Err(error) = result else {
        return "remote_waiting";
    };
    if error == "controller lease expired" {
        return "remote_lease_expired";
    }
    if matches!(
        error.as_str(),
        "WebSocket connection closed" | "WebSocket read failed" | "WebSocket write failed"
    ) || error.ends_with("(socket_write_timeout)")
        || error.ends_with("(transport_pong_timeout)")
    {
        return "remote_transport_unresponsive";
    }
    "remote_waiting"
}

fn next_sequence(sequence: &mut u32) -> u32 {
    *sequence = sequence.wrapping_add(1);
    *sequence
}

fn assert_remote_sender<T>(
    envelope: &Envelope<T>,
    remote_hello: &HelloEnvelope,
) -> Result<(), String> {
    if envelope.session_id != remote_hello.session_id
        || envelope.sender_id != remote_hello.sender_id
        || envelope.sender_epoch != remote_hello.sender_epoch
    {
        return Err("BRSP sender does not match the authenticated hello".to_owned());
    }
    Ok(())
}

fn validate_wire_identity(
    envelope: &WireEnvelope,
    remote_hello: &HelloEnvelope,
) -> Result<(), String> {
    validate_common(envelope, &envelope.message_type).map_err(|error| error.to_string())?;
    assert_remote_sender(envelope, remote_hello)
}

fn typed_from_wire<T: DeserializeOwned>(
    wire: WireEnvelope,
    expected_type: &str,
) -> Result<Envelope<T>, String> {
    if wire.message_type != expected_type {
        return Err("wrong BRSP message type".to_owned());
    }
    serde_json::from_value(serde_json::to_value(wire).map_err(|error| error.to_string())?)
        .map_err(|_| format!("invalid {expected_type} body"))
}

async fn receive_typed<T: DeserializeOwned>(
    socket: &mut WebSocket,
    expected_type: &str,
    timeout: Duration,
) -> Result<Envelope<T>, String> {
    let text = with_transport_deadline(
        TransportDeadline::HandshakeRead,
        timeout,
        receive_text(socket),
    )
    .await?;
    let envelope: Envelope<T> =
        serde_json::from_str(&text).map_err(|_| format!("malformed {expected_type} envelope"))?;
    validate_common(&envelope, expected_type).map_err(|error| error.to_string())?;
    Ok(envelope)
}

async fn receive_text(socket: &mut WebSocket) -> Result<String, String> {
    match socket.recv().await {
        Some(Ok(Message::Text(text))) if text.len() <= MAX_CONTROL_BYTES => Ok(text.to_string()),
        Some(Ok(_)) => Err("expected a bounded BRSP JSON text message".to_owned()),
        Some(Err(error)) => Err(error.to_string()),
        None => Err("connection closed during BRSP handshake".to_owned()),
    }
}

async fn send_control<T: serde::Serialize>(
    socket: &mut WebSocket,
    value: &T,
) -> Result<(), String> {
    let encoded = serde_json::to_string(value).map_err(|error| error.to_string())?;
    if encoded.len() > MAX_CONTROL_BYTES {
        return Err("serialized BRSP control exceeds 16 KiB".to_owned());
    }
    send_socket_message(socket, Message::Text(encoded.into())).await
}

async fn send_socket_message(socket: &mut WebSocket, message: Message) -> Result<(), String> {
    with_transport_deadline(
        TransportDeadline::SocketWrite,
        SOCKET_WRITE_TIMEOUT,
        async {
            socket
                .send(message)
                .await
                .map_err(|_| "WebSocket write failed".to_owned())
        },
    )
    .await
}

async fn close_socket(socket: &mut WebSocket) -> Result<(), String> {
    with_transport_deadline(
        TransportDeadline::SocketClose,
        SOCKET_CLOSE_TIMEOUT,
        async {
            SinkExt::close(socket)
                .await
                .map_err(|_| "WebSocket close failed".to_owned())
        },
    )
    .await
}

async fn send_snapshot(
    socket: &mut WebSocket,
    target_hello: &HelloEnvelope,
    control_sequence: &mut u32,
    controller: &ActiveControllerGuard,
) -> Result<bool, String> {
    let Some(snapshot) = controller.current_snapshot().await? else {
        return Ok(false);
    };
    let envelope = Envelope::new(
        "snapshot",
        target_hello.session_id.clone(),
        target_hello.sender_id.clone(),
        target_hello.sender_epoch,
        next_sequence(control_sequence),
        RemoteSnapshotBody {
            revision: snapshot.revision,
            state: snapshot,
        },
    );
    send_control(socket, &envelope).await?;
    Ok(true)
}

async fn send_state(
    socket: &mut WebSocket,
    target_hello: &HelloEnvelope,
    state_sequence: &mut u32,
    controller: &ActiveControllerGuard,
) -> Result<bool, String> {
    let Some(snapshot) = controller.current_snapshot().await? else {
        return Ok(false);
    };
    let envelope = Envelope::new(
        "state",
        target_hello.session_id.clone(),
        target_hello.sender_id.clone(),
        target_hello.sender_epoch,
        next_sequence(state_sequence),
        RemoteSnapshotBody {
            revision: snapshot.revision,
            state: snapshot,
        },
    );
    let encoded = serde_json::to_string(&envelope).map_err(|error| error.to_string())?;
    if encoded.len() > MAX_STATE_BYTES {
        return Err("serialized BRSP state exceeds 8 KiB".to_owned());
    }
    send_socket_message(socket, Message::Text(encoded.into())).await?;
    Ok(true)
}

async fn send_protocol_error(
    socket: &mut WebSocket,
    target_hello: &HelloEnvelope,
    control_sequence: &mut u32,
    code: &str,
    message: &str,
) -> Result<(), String> {
    send_control(
        socket,
        &Envelope::new(
            "error",
            target_hello.session_id.clone(),
            target_hello.sender_id.clone(),
            target_hello.sender_epoch,
            next_sequence(control_sequence),
            ErrorBody {
                code: code.to_owned(),
                message: message.to_owned(),
            },
        ),
    )
    .await
}

fn prepare_traced_protocol_error(
    target_hello: &HelloEnvelope,
    control_sequence: &mut u32,
    code: &str,
    message: &str,
    trace: Option<&LatencyTraceGuard>,
) -> ErrorEnvelope {
    let envelope = Envelope::new(
        "error",
        target_hello.session_id.clone(),
        target_hello.sender_id.clone(),
        target_hello.sender_epoch,
        next_sequence(control_sequence),
        ErrorBody {
            code: code.to_owned(),
            message: message.to_owned(),
        },
    );
    if let Some(trace) = trace {
        trace.mark(LatencyStage::ReplyReady);
        trace.mark(LatencyStage::AdapterHandoff);
    }
    envelope
}

fn finish_rejected_protocol_trace(trace: Option<&mut LatencyTraceGuard>, send_succeeded: bool) {
    if let Some(trace) = trace {
        if send_succeeded {
            trace.mark(LatencyStage::SendCompleted);
        }
        trace.finish(if send_succeeded {
            TraceOutcome::Rejected
        } else {
            TraceOutcome::Failed
        });
    }
}

struct ActiveControllerGuard {
    runtime: AppRuntime,
    identity: RemoteOwnerIdentity,
    armed: bool,
}

impl ActiveControllerGuard {
    async fn refresh_lease(&self) -> Result<bool, String> {
        self.runtime
            .renew_lan_controller(self.identity.clone())
            .await
    }

    async fn current_snapshot(&self) -> Result<Option<RemoteRunnerSnapshot>, String> {
        self.runtime
            .lan_publication_snapshot(self.identity.clone())
            .await
    }

    async fn revoke(&mut self, connection_state: &'static str) -> Result<bool, String> {
        if !self.armed {
            return Ok(false);
        }
        let revoked = self
            .runtime
            .revoke_lan_controller(self.identity.clone(), connection_state)
            .await?;
        self.armed = false;
        Ok(revoked)
    }
}

impl Drop for ActiveControllerGuard {
    fn drop(&mut self) {
        if self.armed {
            self.runtime
                .revoke_lan_controller_detached(self.identity.clone(), "remote_waiting");
            self.armed = false;
        }
    }
}

fn grants_state_read(scopes: &BTreeSet<Scope>) -> bool {
    scopes.contains(&Scope::SessionRead)
}

// --- Bounded application-blind LAN relay ---------------------------------

#[derive(Default)]
struct RelayRegistry {
    rooms: HashMap<String, RelayRoom>,
}

impl RelayRegistry {
    fn remove_exact(
        &mut self,
        room_id: &str,
        role: RelayRole,
        connection_id: &str,
    ) -> Option<RelaySenders> {
        let mut peer = None;
        let mut remove_room = false;
        if let Some(room) = self.rooms.get_mut(room_id) {
            if room
                .slot(role)
                .as_ref()
                .is_some_and(|slot| slot.connection_id == connection_id)
            {
                *room.slot_mut(role) = None;
                peer = room
                    .slot(role.opposite())
                    .as_ref()
                    .map(|slot| slot.senders.clone());
            }
            remove_room = room.empty();
        }
        if remove_room {
            self.rooms.remove(room_id);
        }
        peer
    }
}

#[derive(Default)]
struct RelayRoom {
    target: Option<RelaySlot>,
    controller: Option<RelaySlot>,
}

#[derive(Clone)]
struct RelaySenders {
    control: mpsc::Sender<RelayOrderedText>,
    state: watch::Sender<Option<RelayOrderedText>>,
    shutdown: watch::Sender<Option<RelayShutdownReason>>,
    next_order: Arc<std::sync::Mutex<u64>>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RelayOrderedText {
    order: u64,
    text: String,
}

impl RelaySenders {
    fn try_control(&self, text: String) -> Result<(), ()> {
        let mut next_order = self
            .next_order
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        let following_order = next_order.checked_add(1).ok_or(())?;
        let message = RelayOrderedText {
            order: *next_order,
            text,
        };
        *next_order = following_order;
        self.control.try_send(message).map_err(|_| ())
    }

    fn replace_state(&self, text: String) -> Result<(), ()> {
        let mut next_order = self
            .next_order
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        let following_order = next_order.checked_add(1).ok_or(())?;
        let message = RelayOrderedText {
            order: *next_order,
            text,
        };
        *next_order = following_order;
        self.state.send_replace(Some(message));
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RelayShutdownReason {
    ReliableBackpressure,
    PeerDisconnected,
}

impl RelayShutdownReason {
    const fn code(self) -> &'static str {
        match self {
            Self::ReliableBackpressure => "relay_backpressure",
            Self::PeerDisconnected => "peer_disconnected",
        }
    }

    const fn message(self) -> &'static str {
        match self {
            Self::ReliableBackpressure => {
                "Reliable peer queue is full; the relay route was closed."
            }
            Self::PeerDisconnected => {
                "Relay peer disconnected; create a fresh authenticated session."
            }
        }
    }
}

fn signal_relay_shutdown(peer: &RelaySenders, reason: RelayShutdownReason) {
    let unset = peer.shutdown.borrow().is_none();
    if unset {
        peer.shutdown.send_replace(Some(reason));
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RelayForwardOutcome {
    Delivered,
    ReliableOverflow,
    Closed,
}

/// Per-socket forwarding fence. Once a reliable control cannot be admitted,
/// this route is permanently closed so a later control can never overtake the
/// dropped frame even if queue capacity becomes available again.
#[derive(Default)]
struct RelayForwarder {
    closed: bool,
}

impl RelayForwarder {
    fn forward(
        &mut self,
        peer: &RelaySenders,
        text: String,
        replaceable: bool,
    ) -> RelayForwardOutcome {
        if self.closed {
            return RelayForwardOutcome::Closed;
        }
        if replaceable {
            if peer.replace_state(text).is_ok() {
                return RelayForwardOutcome::Delivered;
            }
            self.closed = true;
            signal_relay_shutdown(peer, RelayShutdownReason::ReliableBackpressure);
            return RelayForwardOutcome::ReliableOverflow;
        }
        if peer.try_control(text).is_ok() {
            return RelayForwardOutcome::Delivered;
        }
        self.closed = true;
        signal_relay_shutdown(peer, RelayShutdownReason::ReliableBackpressure);
        RelayForwardOutcome::ReliableOverflow
    }
}

fn take_next_relay_outbound(
    control: &mut Option<RelayOrderedText>,
    state: &mut Option<RelayOrderedText>,
    shutdown: Option<RelayShutdownReason>,
) -> Option<RelayOrderedText> {
    if shutdown.is_some() {
        *control = None;
        *state = None;
        return None;
    }
    match (control.as_ref(), state.as_ref()) {
        (Some(control_message), Some(state_message)) => {
            if control_message.order <= state_message.order {
                control.take()
            } else {
                state.take()
            }
        }
        (Some(_), None) => control.take(),
        (None, Some(_)) => state.take(),
        (None, None) => None,
    }
}

struct RelaySlot {
    connection_id: String,
    senders: RelaySenders,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RelayRole {
    Target,
    Controller,
}

impl RelayRole {
    fn parse(value: &str) -> Option<Self> {
        match value {
            "target" => Some(Self::Target),
            "controller" => Some(Self::Controller),
            _ => None,
        }
    }

    fn label(self) -> &'static str {
        match self {
            Self::Target => "target",
            Self::Controller => "controller",
        }
    }

    fn opposite(self) -> Self {
        match self {
            Self::Target => Self::Controller,
            Self::Controller => Self::Target,
        }
    }
}

impl RelayRoom {
    fn slot(&self, role: RelayRole) -> &Option<RelaySlot> {
        match role {
            RelayRole::Target => &self.target,
            RelayRole::Controller => &self.controller,
        }
    }

    fn slot_mut(&mut self, role: RelayRole) -> &mut Option<RelaySlot> {
        match role {
            RelayRole::Target => &mut self.target,
            RelayRole::Controller => &mut self.controller,
        }
    }

    fn empty(&self) -> bool {
        self.target.is_none() && self.controller.is_none()
    }
}

async fn relay_upgrade(
    ws: WebSocketUpgrade,
    Path((room, role)): Path<(String, String)>,
    State(state): State<ServerState>,
) -> Response {
    let Some(admission_permit) = state.relay_admission.try_acquire() else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            "LAN relay capacity reached; retry after another session closes.",
        )
            .into_response();
    };
    ws.max_message_size(MAX_CONTROL_BYTES)
        .max_frame_size(MAX_CONTROL_BYTES)
        .write_buffer_size(SOCKET_WRITE_BUFFER_SIZE)
        .max_write_buffer_size(MAX_SOCKET_WRITE_BUFFER_SIZE)
        .on_upgrade(move |mut socket| async move {
            let _admission_permit = admission_permit;
            relay_socket(&mut socket, state, room, role).await;
            let _ = close_socket(&mut socket).await;
        })
}

async fn relay_socket(
    socket: &mut WebSocket,
    state: ServerState,
    room_id: String,
    role_text: String,
) {
    let enabled = state
        .runtime
        .remote_config_async()
        .await
        .map(|config| config.enabled)
        .unwrap_or(false);
    if !enabled {
        let _ = send_relay_text(
            socket,
            relay_error_message(
                "remote_disabled",
                "Enable phone remote on the desktop host first.",
            ),
        )
        .await;
        return;
    }
    if !valid_room_id(&room_id) {
        let _ = send_relay_text(
            socket,
            relay_error_message("invalid_room", "Relay room id is invalid."),
        )
        .await;
        return;
    }
    let Some(role) = RelayRole::parse(&role_text) else {
        let _ = send_relay_text(
            socket,
            relay_error_message("invalid_role", "Relay role must be target or controller."),
        )
        .await;
        return;
    };

    let connection_id = random_nonce();
    let (control_tx, mut control_rx) =
        mpsc::channel::<RelayOrderedText>(RELAY_CONTROL_QUEUE_CAPACITY);
    let (state_tx, mut state_rx) = watch::channel::<Option<RelayOrderedText>>(None);
    let (shutdown_tx, mut shutdown_rx) = watch::channel::<Option<RelayShutdownReason>>(None);
    let local_senders = RelaySenders {
        control: control_tx,
        state: state_tx,
        shutdown: shutdown_tx,
        next_order: Arc::new(std::sync::Mutex::new(0)),
    };
    let peer = {
        let mut registry = state.relay.lock().await;
        if !registry.rooms.contains_key(&room_id) && registry.rooms.len() >= MAX_RELAY_ROOMS {
            drop(registry);
            let _ = send_relay_text(
                socket,
                relay_error_message(
                    "relay_capacity",
                    "The bounded lab relay has reached its room limit.",
                ),
            )
            .await;
            return;
        }
        let room = registry.rooms.entry(room_id.clone()).or_default();
        if room.slot(role).is_some() {
            drop(registry);
            let _ = send_relay_text(
                socket,
                relay_error_message("relay_role_busy", "This relay role is already occupied."),
            )
            .await;
            return;
        }
        let peer = room
            .slot(role.opposite())
            .as_ref()
            .map(|slot| slot.senders.clone());
        *room.slot_mut(role) = Some(RelaySlot {
            connection_id: connection_id.clone(),
            senders: local_senders,
        });
        peer
    };
    let initial_write_succeeded = send_socket_message(
        socket,
        Message::Text(relay_peer_message(role.opposite().label(), peer.is_some()).into()),
    )
    .await
    .is_ok();
    if initial_write_succeeded {
        if let Some(peer) = &peer {
            if peer
                .try_control(relay_peer_message(role.label(), true))
                .is_err()
            {
                signal_relay_shutdown(peer, RelayShutdownReason::ReliableBackpressure);
            }
        }

        let mut rate_window = Instant::now();
        let mut rate_count = 0_u32;
        let mut config_check = tokio::time::interval(Duration::from_millis(500));
        config_check.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        let mut transport_ping = tokio::time::interval_at(
            tokio::time::Instant::now() + TRANSPORT_PING_INTERVAL,
            TRANSPORT_PING_INTERVAL,
        );
        transport_ping.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        let mut transport_liveness = TransportLiveness::new();
        let mut forwarder = RelayForwarder::default();
        let mut pending_control = None;
        let mut pending_state = None;
        loop {
            let shutdown_reason = *shutdown_rx.borrow();
            if let Some(reason) = shutdown_reason {
                let _ = take_next_relay_outbound(
                    &mut pending_control,
                    &mut pending_state,
                    shutdown_reason,
                );
                let _ =
                    send_relay_text(socket, relay_error_message(reason.code(), reason.message()))
                        .await;
                break;
            }
            if require_live_transport(&transport_liveness, Instant::now()).is_err() {
                break;
            }
            if pending_control.is_none() {
                match control_rx.try_recv() {
                    Ok(message) => pending_control = Some(message),
                    Err(mpsc::error::TryRecvError::Empty) => {}
                    Err(mpsc::error::TryRecvError::Disconnected) => break,
                }
            }
            match state_rx.has_changed() {
                Ok(true) => pending_state = state_rx.borrow_and_update().clone(),
                Ok(false) => {}
                Err(_) => break,
            }
            if let Some(outgoing) =
                take_next_relay_outbound(&mut pending_control, &mut pending_state, None)
            {
                if send_socket_message(socket, Message::Text(outgoing.text.into()))
                    .await
                    .is_err()
                {
                    break;
                }
                continue;
            }

            tokio::select! {
                biased;
                changed = shutdown_rx.changed() => {
                    if changed.is_err() { break; }
                    let _ = *shutdown_rx.borrow_and_update();
                    continue;
                }
                inbound = socket.recv() => {
                    if require_live_transport(&transport_liveness, Instant::now()).is_err() {
                        break;
                    }
                    let Some(Ok(inbound)) = inbound else { break; };
                    match inbound {
                        Message::Text(text) if text.len() <= MAX_CONTROL_BYTES => {
                            if rate_window.elapsed() >= Duration::from_secs(1) {
                                rate_window = Instant::now();
                                rate_count = 0;
                            }
                            rate_count = rate_count.saturating_add(1);
                            if rate_count > MAX_RELAY_MESSAGES_PER_SECOND {
                                let _ = send_relay_text(socket, relay_error_message("relay_rate_limit", "Relay message rate exceeded the bounded lab limit.")).await;
                                break;
                            }
                            let classification = classify_relay_envelope(&text, role);
                            let Ok(replaceable) = classification else {
                                if !relay_diagnostic_allows_continue(send_relay_text(socket, relay_error_message("relay_direction_rejected", "Envelope is invalid for this BRSP role/lane.")).await) {
                                    break;
                                }
                                continue;
                            };
                            let peer = {
                                let registry = state.relay.lock().await;
                                registry.rooms
                                    .get(&room_id)
                                    .and_then(|room| room.slot(role.opposite()).as_ref())
                                    .map(|slot| slot.senders.clone())
                            };
                            if let Some(peer) = peer {
                                match forwarder.forward(&peer, text.to_string(), replaceable) {
                                    RelayForwardOutcome::Delivered => {}
                                    RelayForwardOutcome::ReliableOverflow | RelayForwardOutcome::Closed => {
                                        let _ = send_relay_text(
                                            socket,
                                            relay_error_message(
                                                RelayShutdownReason::ReliableBackpressure.code(),
                                                RelayShutdownReason::ReliableBackpressure.message(),
                                            ),
                                        )
                                        .await;
                                        break;
                                    }
                                }
                            } else if !relay_diagnostic_allows_continue(send_relay_text(socket, relay_error_message("peer_absent", "The other relay role is not connected yet.")).await) {
                                break;
                            }
                        }
                        Message::Ping(payload) => {
                            if send_socket_message(socket, Message::Pong(payload)).await.is_err() { break; }
                        }
                        Message::Pong(payload) => {
                            transport_liveness.accept_pong(payload.as_ref(), Instant::now());
                        }
                        Message::Close(_) => break,
                        Message::Text(_) | Message::Binary(_) => {
                            if !relay_diagnostic_allows_continue(send_relay_text(socket, relay_error_message("message_rejected", "Relay accepts bounded BRSP JSON text.")).await) {
                                break;
                            }
                        }
                    }
                }
                outgoing = control_rx.recv() => {
                    let Some(outgoing) = outgoing else { break; };
                    pending_control = Some(outgoing);
                }
                changed = state_rx.changed() => {
                    if changed.is_err() { break; }
                    pending_state = state_rx.borrow_and_update().clone();
                }
                _ = config_check.tick() => {
                    if require_live_transport(&transport_liveness, Instant::now()).is_err() {
                        break;
                    }
                    let enabled = state
                        .runtime
                        .remote_config_async()
                        .await
                        .map(|config| config.enabled)
                        .unwrap_or(false);
                    if !enabled {
                        let _ = send_relay_text(
                            socket,
                            relay_error_message(
                                "remote_disabled",
                                "Phone remote was disabled on the desktop host.",
                            ),
                        )
                        .await;
                        break;
                    }
                }
                _ = transport_ping.tick() => {
                    if require_live_transport(&transport_liveness, Instant::now()).is_err() {
                        break;
                    }
                    if let Some(payload) = transport_liveness.next_ping_payload() {
                        if send_socket_message(socket, Message::Ping(payload.to_vec().into())).await.is_err() {
                            break;
                        }
                        transport_liveness.ping_sent(payload, Instant::now());
                    }
                }
                _ = tokio::time::sleep(transport_liveness.pong_wait(Instant::now())), if transport_liveness.has_pending_pong() => {
                    if transport_liveness.pong_timed_out(Instant::now()) {
                        break;
                    }
                }
            }
        }
    }

    let peer = state
        .relay
        .lock()
        .await
        .remove_exact(&room_id, role, &connection_id);
    if let Some(peer) = peer {
        signal_relay_shutdown(&peer, RelayShutdownReason::PeerDisconnected);
    }
}

fn classify_relay_envelope(text: &str, role: RelayRole) -> Result<bool, ()> {
    let envelope: WireEnvelope = serde_json::from_str(text).map_err(|_| ())?;
    validate_common(&envelope, &envelope.message_type).map_err(|_| ())?;
    let replaceable = envelope.message_type == "state";
    if replaceable && text.len() > MAX_STATE_BYTES {
        return Err(());
    }
    let allowed = match role {
        RelayRole::Target => matches!(
            envelope.message_type.as_str(),
            "hello" | "proof" | "ready" | "applied" | "snapshot" | "state" | "error" | "bye"
        ),
        RelayRole::Controller => matches!(
            envelope.message_type.as_str(),
            "hello" | "proof" | "ready" | "command" | "snapshot-request" | "error" | "bye"
        ),
    };
    allowed.then_some(replaceable).ok_or(())
}

fn valid_room_id(value: &str) -> bool {
    (8..=64).contains(&value.len())
        && value
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || matches!(character, '-' | '_'))
}

fn relay_peer_message(role: &str, present: bool) -> String {
    serde_json::json!({"kind": "relay.peer", "role": role, "present": present}).to_string()
}

fn relay_error_message(code: &str, message: &str) -> String {
    serde_json::json!({"kind": "relay.error", "code": code, "message": message}).to_string()
}

fn relay_diagnostic_allows_continue(result: Result<(), String>) -> bool {
    result.is_ok()
}

async fn send_relay_text(socket: &mut WebSocket, text: String) -> Result<(), String> {
    send_socket_message(socket, Message::Text(text.into())).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::latency_diagnostics::NativeLatencyDiagnostics;
    use pps_contracts::{Action, RunnerPhase};

    async fn active_guard(
        runtime: &AppRuntime,
        controller_id: &str,
    ) -> (ActiveControllerGuard, RemoteRunnerSnapshot) {
        let remote = runtime.remote_config_async().await.unwrap();
        let claim = runtime
            .claim_lan_controller(
                remote.session_id,
                controller_id.to_owned(),
                BTreeSet::from([Scope::SessionRead, Scope::SessionTransport]),
            )
            .await
            .unwrap();
        (
            ActiveControllerGuard {
                runtime: runtime.clone(),
                identity: claim.identity,
                armed: true,
            },
            claim.snapshot,
        )
    }

    async fn start_demo_run(runtime: &AppRuntime) {
        runtime
            .dispatch_local_async(Action::PackagePrepareDemo, serde_json::json!({}))
            .await
            .unwrap();
        runtime
            .dispatch_local_async(
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
            .await
            .unwrap();
        runtime
            .dispatch_local_async(Action::TargetArm, serde_json::json!({}))
            .await
            .unwrap();
        runtime
            .dispatch_local_async(Action::PartStart, serde_json::json!({"part_number": 1}))
            .await
            .unwrap();
        assert_eq!(
            runtime.snapshot_async().await.unwrap().run.phase,
            RunnerPhase::Running
        );
    }

    #[test]
    fn relay_ids_are_closed_tokens() {
        assert!(valid_room_id("room-1234"));
        assert!(!valid_room_id("../escape"));
        assert!(!valid_room_id("tiny"));
    }

    #[test]
    fn exact_relay_cleanup_releases_registered_role_and_notifies_peer() {
        let make_senders = || {
            let (control, _control_rx) =
                mpsc::channel::<RelayOrderedText>(RELAY_CONTROL_QUEUE_CAPACITY);
            let (state, _state_rx) = watch::channel::<Option<RelayOrderedText>>(None);
            let (shutdown, shutdown_rx) = watch::channel::<Option<RelayShutdownReason>>(None);
            (
                RelaySenders {
                    control,
                    state,
                    shutdown,
                    next_order: Arc::new(std::sync::Mutex::new(0)),
                },
                shutdown_rx,
            )
        };
        let (target, _) = make_senders();
        let (controller, mut controller_shutdown) = make_senders();
        let mut registry = RelayRegistry::default();
        registry.rooms.insert(
            "room-1234".to_owned(),
            RelayRoom {
                target: Some(RelaySlot {
                    connection_id: "target-old".to_owned(),
                    senders: target,
                }),
                controller: Some(RelaySlot {
                    connection_id: "controller-current".to_owned(),
                    senders: controller,
                }),
            },
        );

        assert!(registry
            .remove_exact("room-1234", RelayRole::Target, "target-stale")
            .is_none());
        let peer = registry
            .remove_exact("room-1234", RelayRole::Target, "target-old")
            .unwrap();
        signal_relay_shutdown(&peer, RelayShutdownReason::PeerDisconnected);
        assert_eq!(
            *controller_shutdown.borrow_and_update(),
            Some(RelayShutdownReason::PeerDisconnected)
        );

        let room = registry.rooms.get_mut("room-1234").unwrap();
        assert!(room.target.is_none());
        let (replacement, _) = make_senders();
        *room.slot_mut(RelayRole::Target) = Some(RelaySlot {
            connection_id: "target-replacement".to_owned(),
            senders: replacement,
        });
        assert_eq!(
            room.target.as_ref().unwrap().connection_id,
            "target-replacement"
        );
    }

    #[test]
    fn transport_deadlines_have_distinct_stable_classifications() {
        assert_eq!(
            TransportDeadline::HandshakeRead.code(),
            "handshake_read_timeout"
        );
        assert_eq!(
            TransportDeadline::SocketWrite.code(),
            "socket_write_timeout"
        );
        assert_eq!(
            TransportDeadline::SocketClose.code(),
            "socket_close_timeout"
        );
        assert_eq!(TransportDeadline::Pong.code(), "transport_pong_timeout");
    }

    #[tokio::test]
    async fn stuck_handshake_write_and_close_futures_are_bounded() {
        for deadline in [
            TransportDeadline::HandshakeRead,
            TransportDeadline::SocketWrite,
            TransportDeadline::SocketClose,
        ] {
            let result = with_transport_deadline(
                deadline,
                Duration::from_millis(1),
                std::future::pending::<Result<(), String>>(),
            )
            .await;
            assert_eq!(result.unwrap_err(), transport_timeout_error(deadline));
        }
    }

    #[test]
    fn socket_admission_is_bounded_releases_and_keeps_routes_isolated() {
        let admission = SocketAdmission::new(MAX_CONCURRENT_DESKTOP_SESSIONS);
        let mut permits = Vec::new();
        for _ in 0..MAX_CONCURRENT_DESKTOP_SESSIONS {
            permits.push(admission.try_acquire().unwrap());
        }
        assert!(admission.try_acquire().is_none());

        drop(permits.pop());
        assert!(admission.try_acquire().is_some());

        let desktop = SocketAdmission::new(1);
        let relay = SocketAdmission::new(1);
        let relay_permit = relay.try_acquire().unwrap();
        assert!(relay.try_acquire().is_none());
        assert!(desktop.try_acquire().is_some());
        drop(relay_permit);
        assert!(relay.try_acquire().is_some());
    }

    #[test]
    fn transport_pong_requires_exact_payload_strictly_before_deadline() {
        let now = Instant::now();
        let mut liveness = TransportLiveness::with_nonce(0x1234_5678);
        let first = liveness.next_ping_payload().unwrap();
        assert_eq!(&first[..4], &0x1234_5678_u32.to_be_bytes());
        liveness.ping_sent(first, now);
        assert!(liveness.next_ping_payload().is_none());
        let deadline = now + TRANSPORT_PONG_TIMEOUT;
        assert!(!liveness.accept_pong(b"wrong", deadline - Duration::from_nanos(1)));
        assert!(liveness.accept_pong(&first, deadline - Duration::from_nanos(1)));
        assert!(!liveness.has_pending_pong());
        assert_ne!(liveness.next_ping_payload().unwrap(), first);

        let mut at_deadline = TransportLiveness::with_nonce(1);
        let at_payload = at_deadline.next_ping_payload().unwrap();
        at_deadline.ping_sent(at_payload, now);
        assert!(!at_deadline.accept_pong(&at_payload, deadline));
        assert!(at_deadline.pong_timed_out(deadline));

        let mut after_deadline = TransportLiveness::with_nonce(2);
        let after_payload = after_deadline.next_ping_payload().unwrap();
        after_deadline.ping_sent(after_payload, now);
        assert!(!after_deadline.accept_pong(&after_payload, deadline + Duration::from_nanos(1)));
        assert!(after_deadline.pong_timed_out(deadline + Duration::from_nanos(1)));
    }

    #[test]
    fn expired_transport_gate_prevents_ready_command_or_control_work() {
        let now = Instant::now();
        let deadline = now + TRANSPORT_PONG_TIMEOUT;
        let mut liveness = TransportLiveness::with_nonce(3);
        let payload = liveness.next_ping_payload().unwrap();
        liveness.ping_sent(payload, now);

        let mut forwarded = 0_u8;
        for frame_time in [deadline, deadline + Duration::from_nanos(1)] {
            if require_live_transport(&liveness, frame_time).is_ok() {
                forwarded += 1;
            }
        }
        assert_eq!(forwarded, 0);
        assert_eq!(
            require_live_transport(&liveness, deadline).unwrap_err(),
            transport_timeout_error(TransportDeadline::Pong)
        );
    }

    #[test]
    fn relay_reliable_overflow_closes_route_and_later_control_cannot_overtake() {
        let (control_tx, mut control_rx) =
            mpsc::channel::<RelayOrderedText>(RELAY_CONTROL_QUEUE_CAPACITY);
        let (state_tx, _) = watch::channel::<Option<RelayOrderedText>>(None);
        let (shutdown_tx, mut shutdown_rx) = watch::channel::<Option<RelayShutdownReason>>(None);
        let peer = RelaySenders {
            control: control_tx,
            state: state_tx,
            shutdown: shutdown_tx,
            next_order: Arc::new(std::sync::Mutex::new(0)),
        };
        for value in 0..RELAY_CONTROL_QUEUE_CAPACITY {
            peer.try_control(format!("queued-{value}")).unwrap();
        }
        let mut forwarder = RelayForwarder::default();
        assert_eq!(
            forwarder.forward(&peer, "overflow".to_owned(), false),
            RelayForwardOutcome::ReliableOverflow
        );
        assert_eq!(
            *shutdown_rx.borrow_and_update(),
            Some(RelayShutdownReason::ReliableBackpressure)
        );

        assert_eq!(control_rx.try_recv().unwrap().text, "queued-0");
        assert_eq!(
            forwarder.forward(&peer, "later".to_owned(), false),
            RelayForwardOutcome::Closed
        );
        let remaining = std::iter::from_fn(|| control_rx.try_recv().ok()).collect::<Vec<_>>();
        assert_eq!(remaining.len(), RELAY_CONTROL_QUEUE_CAPACITY - 1);
        assert!(!remaining.iter().any(|message| message.text == "later"));
    }

    #[test]
    fn relay_state_lane_is_one_replaceable_latest_value() {
        let (state_tx, mut state_rx) = watch::channel::<Option<&'static str>>(None);
        state_tx.send_replace(Some("A"));
        state_tx.send_replace(Some("B"));
        state_tx.send_replace(Some("C"));
        assert_eq!(*state_rx.borrow_and_update(), Some("C"));
    }

    #[test]
    fn relay_writer_preserves_ready_before_later_replaceable_state() {
        let (control_tx, mut control_rx) =
            mpsc::channel::<RelayOrderedText>(RELAY_CONTROL_QUEUE_CAPACITY);
        let (state_tx, mut state_rx) = watch::channel::<Option<RelayOrderedText>>(None);
        let (shutdown_tx, _) = watch::channel::<Option<RelayShutdownReason>>(None);
        let peer = RelaySenders {
            control: control_tx,
            state: state_tx,
            shutdown: shutdown_tx,
            next_order: Arc::new(std::sync::Mutex::new(0)),
        };
        peer.try_control("ready".to_owned()).unwrap();
        peer.replace_state("state".to_owned()).unwrap();

        let mut pending_control = Some(control_rx.try_recv().unwrap());
        let mut pending_state = state_rx.borrow_and_update().clone();
        assert_eq!(
            take_next_relay_outbound(&mut pending_control, &mut pending_state, None)
                .unwrap()
                .text,
            "ready"
        );
        assert_eq!(
            take_next_relay_outbound(&mut pending_control, &mut pending_state, None)
                .unwrap()
                .text,
            "state"
        );
    }

    #[test]
    fn fatal_relay_shutdown_discards_pending_work_before_another_send() {
        let mut pending_control = Some(RelayOrderedText {
            order: 1,
            text: "older-control".to_owned(),
        });
        let mut pending_state = Some(RelayOrderedText {
            order: 2,
            text: "latest-state".to_owned(),
        });
        assert!(take_next_relay_outbound(
            &mut pending_control,
            &mut pending_state,
            Some(RelayShutdownReason::ReliableBackpressure),
        )
        .is_none());
        assert!(pending_control.is_none());
        assert!(pending_state.is_none());
    }

    #[test]
    fn relay_diagnostic_write_failure_is_fatal_to_the_registered_session() {
        assert!(relay_diagnostic_allows_continue(Ok(())));
        assert!(!relay_diagnostic_allows_continue(Err(
            transport_timeout_error(TransportDeadline::SocketWrite)
        )));
    }

    #[test]
    fn replay_error_trace_is_ready_before_handoff_and_never_enters_authority() {
        let diagnostics = NativeLatencyDiagnostics::new();
        let mut trace = diagnostics.start_trace(LatencyRoute::LanWebSocket);
        trace.mark(LatencyStage::AdapterValidationComplete);
        let target = Envelope::new(
            "hello",
            "session_1234",
            "target_12345",
            1,
            0,
            HelloBody {
                role: BrspRole::Target,
                nonce: "dGFyZ2V0LW5vbmNlLTEyMzQ1Ng".to_owned(),
                capabilities: vec![],
                requested_scopes: vec![],
                granted_scopes: vec![],
            },
        );
        let mut sequence = 0;
        let _ = prepare_traced_protocol_error(
            &target,
            &mut sequence,
            "replayed_sequence",
            "A bounded public error.",
            Some(&trace),
        );
        finish_rejected_protocol_trace(Some(&mut trace), true);

        let summary = diagnostics.summary();
        let route = summary
            .routes
            .iter()
            .find(|route| route.route == LatencyRoute::LanWebSocket)
            .unwrap();
        for stage in [
            LatencyStage::AdapterValidationComplete,
            LatencyStage::ReplyReady,
            LatencyStage::AdapterHandoff,
            LatencyStage::SendCompleted,
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
        let elapsed = |stage: LatencyStage| {
            route.stages[stage.index()]
                .elapsed_from_native_ingress
                .p50_us
        };
        assert!(
            elapsed(LatencyStage::AdapterValidationComplete) <= elapsed(LatencyStage::ReplyReady)
        );
        assert!(elapsed(LatencyStage::ReplyReady) <= elapsed(LatencyStage::AdapterHandoff));
        assert!(elapsed(LatencyStage::AdapterHandoff) <= elapsed(LatencyStage::SendCompleted));
    }

    #[test]
    fn failed_reply_write_never_records_send_completed() {
        let diagnostics = NativeLatencyDiagnostics::new();
        let mut trace = diagnostics.start_trace(LatencyRoute::LanWebSocket);
        trace.mark(LatencyStage::AdapterValidationComplete);
        let target = Envelope::new(
            "hello",
            "session_1234",
            "target_12345",
            1,
            0,
            HelloBody {
                role: BrspRole::Target,
                nonce: "dGFyZ2V0LW5vbmNlLTEyMzQ1Ng".to_owned(),
                capabilities: vec![],
                requested_scopes: vec![],
                granted_scopes: vec![],
            },
        );
        let mut sequence = 0;
        let _ = prepare_traced_protocol_error(
            &target,
            &mut sequence,
            "replayed_sequence",
            "A bounded public error.",
            Some(&trace),
        );
        finish_rejected_protocol_trace(Some(&mut trace), false);

        let summary = diagnostics.summary();
        let route = summary
            .routes
            .iter()
            .find(|route| route.route == LatencyRoute::LanWebSocket)
            .unwrap();
        assert_eq!(route.count, 1);
        assert_eq!(
            route.stages[LatencyStage::AdapterHandoff.index()]
                .elapsed_from_native_ingress
                .sample_count,
            1
        );
        assert_eq!(
            route.stages[LatencyStage::SendCompleted.index()]
                .elapsed_from_native_ingress
                .sample_count,
            0
        );
    }

    #[test]
    fn relay_directions_use_canonical_envelope_type() {
        let target = Envelope::new(
            "hello",
            "session_1234",
            "target_12345",
            1,
            0,
            HelloBody {
                role: BrspRole::Target,
                nonce: "dGFyZ2V0LW5vbmNlLTEyMzQ1Ng".to_owned(),
                capabilities: vec![],
                requested_scopes: vec![],
                granted_scopes: vec![],
            },
        );
        assert_eq!(
            classify_relay_envelope(&serde_json::to_string(&target).unwrap(), RelayRole::Target),
            Ok(false)
        );
        let command = Envelope::new(
            "command",
            "session_1234",
            "controller_1",
            2,
            3,
            serde_json::Value::Object(Default::default()),
        );
        assert!(classify_relay_envelope(
            &serde_json::to_string(&command).unwrap(),
            RelayRole::Target
        )
        .is_err());
        assert_eq!(
            classify_relay_envelope(
                &serde_json::to_string(&command).unwrap(),
                RelayRole::Controller
            ),
            Ok(false)
        );
        let state = Envelope::new(
            "state",
            "session_1234",
            "target_12345",
            1,
            4,
            serde_json::json!({"revision": 1}),
        );
        assert_eq!(
            classify_relay_envelope(&serde_json::to_string(&state).unwrap(), RelayRole::Target),
            Ok(true)
        );
        assert!(classify_relay_envelope(
            &serde_json::to_string(&state).unwrap(),
            RelayRole::Controller
        )
        .is_err());
        let intent = Envelope::new(
            "intent",
            "session_1234",
            "controller_1",
            2,
            5,
            serde_json::json!({"value": 1}),
        );
        assert!(classify_relay_envelope(
            &serde_json::to_string(&intent).unwrap(),
            RelayRole::Controller
        )
        .is_err());
    }

    #[test]
    fn state_publication_requires_the_read_scope() {
        assert!(!grants_state_read(&BTreeSet::from([
            Scope::SessionTransport
        ])));
        assert!(grants_state_read(&BTreeSet::from([
            Scope::SessionRead,
            Scope::SessionTransport,
        ])));
    }

    #[test]
    fn lan_applied_body_redacts_reducer_rejection_details() {
        let snapshot = AppRuntime::new().snapshot().unwrap().into();
        let applied = RemoteApplied {
            id: "command-redaction-0001".to_owned(),
            action: Action::PartStart,
            status: AppliedStatus::Rejected,
            reason: "PRIVATE_PATH_C:\\participants\\P001\\manifest.json".to_owned(),
            accepted_revision: 4,
            resulting_revision: 4,
            snapshot,
        };
        let body = remote_applied_body(&applied);
        let encoded = serde_json::to_string(&body).unwrap();
        assert!(!body.ok);
        assert_eq!(body.error.as_deref(), Some("request_rejected"));
        assert!(encoded.contains("request_rejected"));
        assert!(!encoded.contains("PRIVATE_PATH"));
        assert!(!encoded.contains("participants"));
        assert!(!encoded.contains("snapshot"));
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn transport_ping_pong_does_not_renew_the_semantic_controller_lease() {
        let runtime = AppRuntime::new();
        runtime.configure_remote_async(true, false).await.unwrap();
        let (guard, connected) = active_guard(&runtime, "controller_transport_ping").await;
        let lease_before = connected.safety.lease_expires_at_unix_ms.unwrap();

        let now = Instant::now();
        let mut liveness = TransportLiveness::with_nonce(7);
        let payload = liveness.next_ping_payload().unwrap();
        liveness.ping_sent(payload, now);
        assert!(liveness.accept_pong(&payload, now + Duration::from_millis(1)));

        let after_pong = guard.current_snapshot().await.unwrap().unwrap();
        assert_eq!(
            after_pong.safety.lease_expires_at_unix_ms,
            Some(lease_before)
        );
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn transport_pong_timeout_revokes_exact_owner_and_pauses() {
        let runtime = AppRuntime::new();
        runtime.configure_remote_async(true, false).await.unwrap();
        let (mut guard, _) = active_guard(&runtime, "controller_pong_timeout").await;
        start_demo_run(&runtime).await;

        let now = Instant::now();
        let mut liveness = TransportLiveness::with_nonce(9);
        let payload = liveness.next_ping_payload().unwrap();
        liveness.ping_sent(payload, now);
        assert!(liveness.pong_timed_out(now + TRANSPORT_PONG_TIMEOUT));
        assert!(guard.revoke("remote_transport_unresponsive").await.unwrap());

        let cleaned = runtime.snapshot_async().await.unwrap();
        assert_eq!(cleaned.run.phase, RunnerPhase::Paused);
        assert_eq!(cleaned.connection_state, "remote_transport_unresponsive");
        assert!(cleaned.safety.controller_lease_id.is_empty());
        assert!(cleaned.safety.lease_expires_at_unix_ms.is_none());
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn post_claim_schema_failure_awaits_exact_owner_revocation() {
        let runtime = AppRuntime::new();
        runtime.configure_remote_async(true, false).await.unwrap();
        let (mut guard, _) = active_guard(&runtime, "controller_bad_schema").await;

        assert_eq!(
            require_claimed_public_schema(&mut guard, "unexpected-private-schema")
                .await
                .unwrap_err(),
            "native public snapshot schema mismatch"
        );
        let cleaned = runtime.snapshot_async().await.unwrap();
        assert_eq!(cleaned.connection_state, "remote_waiting");
        assert!(cleaned.safety.controller_lease_id.is_empty());
        assert!(cleaned.safety.lease_expires_at_unix_ms.is_none());
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn stuck_write_scope_exit_revokes_exact_owner_and_pauses() {
        let runtime = AppRuntime::new();
        runtime.configure_remote_async(true, false).await.unwrap();
        let (mut guard, _) = active_guard(&runtime, "controller_stuck_write").await;
        start_demo_run(&runtime).await;

        let result = with_transport_deadline(
            TransportDeadline::SocketWrite,
            Duration::from_millis(1),
            std::future::pending::<Result<(), String>>(),
        )
        .await;
        let error = result.unwrap_err();
        assert_eq!(
            error,
            transport_timeout_error(TransportDeadline::SocketWrite)
        );
        assert_eq!(
            finish_claimed_session(&mut guard, Err(error.clone()))
                .await
                .unwrap_err(),
            error
        );
        let cleaned = runtime.snapshot_async().await.unwrap();
        assert_eq!(cleaned.run.phase, RunnerPhase::Paused);
        assert_eq!(cleaned.connection_state, "remote_transport_unresponsive");
        assert!(cleaned.safety.controller_lease_id.is_empty());
        assert!(cleaned.safety.lease_expires_at_unix_ms.is_none());
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn deadman_revocation_clears_authority_and_pauses_a_running_target() {
        let runtime = AppRuntime::new();
        runtime.configure_remote_async(true, false).await.unwrap();
        let (mut guard, connected) = active_guard(&runtime, "controller_deadman").await;
        assert_eq!(connected.connection_state, "remote_connected");
        assert!(connected.safety.lease_expires_at_unix_ms.is_some());
        start_demo_run(&runtime).await;

        assert!(guard.revoke("remote_lease_expired").await.unwrap());
        let expired = runtime.snapshot_async().await.unwrap();
        assert_eq!(expired.run.phase, RunnerPhase::Paused);
        assert_eq!(expired.connection_state, "remote_lease_expired");
        assert!(expired.safety.controller_lease_id.is_empty());
        assert!(expired.safety.lease_expires_at_unix_ms.is_none());
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn stale_guard_cannot_reset_a_new_session_or_disabled_state() {
        let runtime = AppRuntime::new();
        runtime.configure_remote_async(true, false).await.unwrap();
        let (old_guard, _) = active_guard(&runtime, "controller_old").await;
        runtime
            .revoke_lan_controller(old_guard.identity.clone(), "remote_waiting")
            .await
            .unwrap();

        let (same_session_guard, _) = active_guard(&runtime, "controller_replacement").await;
        let before_old_drop = runtime.snapshot_async().await.unwrap();
        drop(old_guard);
        assert_eq!(runtime.snapshot_async().await.unwrap(), before_old_drop);
        assert_eq!(
            runtime
                .snapshot_async()
                .await
                .unwrap()
                .safety
                .controller_lease_id,
            "controller_replacement"
        );

        runtime.configure_remote_async(false, false).await.unwrap();
        runtime.configure_remote_async(true, false).await.unwrap();
        let (new_guard, _) = active_guard(&runtime, "controller_new").await;
        let before_stale_session_drop = runtime.snapshot_async().await.unwrap();
        drop(same_session_guard);
        assert_eq!(
            runtime.snapshot_async().await.unwrap(),
            before_stale_session_drop
        );
        assert_eq!(
            runtime
                .snapshot_async()
                .await
                .unwrap()
                .safety
                .controller_lease_id,
            "controller_new"
        );

        runtime.configure_remote_async(false, false).await.unwrap();
        let disabled = runtime.snapshot_async().await.unwrap();
        assert_eq!(disabled.connection_state, "local_only");
        drop(new_guard);
        assert_eq!(runtime.snapshot_async().await.unwrap(), disabled);
    }
}
