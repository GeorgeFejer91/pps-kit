use std::{
    collections::{BTreeSet, HashMap},
    path::PathBuf,
    sync::Arc,
    time::{Duration, Instant},
};

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        Path, State,
    },
    response::Response,
    routing::get,
    Router,
};
use pps_brsp::{
    create_proof_envelope, negotiate_session, random_epoch, random_nonce, ready_matches,
    valid_peer_id, validate_common, validate_hello, SequenceDecision, SequenceGuard,
};
use pps_contracts::{
    Action, AppliedBody, BrspRole, ClockStamp, CommandEnvelope, EmptyEnvelope, Envelope, ErrorBody,
    ErrorEnvelope, HelloBody, HelloEnvelope, ProofEnvelope, ReadyBody, ReadyEnvelope, Scope,
    SnapshotBody, SnapshotEnvelope, StateBody, StateEnvelope, WireEnvelope, JSON_MAX_SAFE_INTEGER,
    MAX_CONTROL_BYTES, MAX_STATE_BYTES, PPS_REMOTE_CAPABILITIES,
};
use serde::de::DeserializeOwned;
use tokio::sync::{mpsc, watch, Mutex as AsyncMutex};
use tower_http::services::ServeDir;

use crate::runtime::{random_owner_token, ActiveController, AppRuntime};

const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(12);
const STATE_HEARTBEAT: Duration = Duration::from_millis(250);
const STATE_FLUSH: Duration = Duration::from_millis(16);
const CONTROLLER_LEASE: Duration = Duration::from_secs(5);
const LEASE_CHECK: Duration = Duration::from_millis(100);
const MAX_RELAY_ROOMS: usize = 16;
const MAX_RELAY_MESSAGES_PER_SECOND: u32 = 120;

#[derive(Clone)]
struct ServerState {
    runtime: AppRuntime,
    relay: Arc<AsyncMutex<RelayRegistry>>,
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
    ws.max_message_size(MAX_CONTROL_BYTES)
        .max_frame_size(MAX_CONTROL_BYTES)
        .on_upgrade(move |mut socket| async move {
            // Proof failures intentionally fail closed without returning details
            // useful for online secret guessing.
            let _ = desktop_session(&mut socket, &state.runtime).await;
        })
}

async fn desktop_session(socket: &mut WebSocket, runtime: &AppRuntime) -> Result<(), String> {
    let remote = runtime.0.remote_config()?;
    if !remote.enabled {
        return Err("phone remote is disabled".to_owned());
    }
    let mut available_scopes = runtime.available_scopes()?;
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
    let owner_token = random_owner_token();
    {
        let current = runtime.0.remote_config()?;
        if !current.enabled || current.session_id != remote.session_id {
            return Err("remote activation changed during authentication".to_owned());
        }
        let mut active = runtime
            .0
            .active_controller
            .lock()
            .map_err(|_| "controller lock failed".to_owned())?;
        if active.is_some() {
            return Err("target already has an active controller".to_owned());
        }
        *active = Some(ActiveController {
            id: controller_hello.sender_id.clone(),
            session_id: remote.session_id.clone(),
            owner_token: owner_token.clone(),
            granted_scopes: negotiated.accepted_scopes.clone(),
        });
    }
    let mut controller_guard = ActiveControllerGuard {
        runtime: runtime.clone(),
        controller_id: controller_hello.sender_id.clone(),
        session_id: remote.session_id.clone(),
        owner_token,
        armed: true,
    };

    let ready_snapshot = controller_guard.mark_connected()?;
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
        send_snapshot(
            socket,
            &target_hello,
            &mut target_control_sequence,
            ready_snapshot.clone(),
        )
        .await?;
        send_state(
            socket,
            &target_hello,
            &mut target_state_sequence,
            ready_snapshot,
        )
        .await?;
    }

    let mut remote_control_sequence = SequenceGuard::after(controller_ready.sequence);
    let mut state_rx = runtime.0.state_tx.subscribe();
    let mut pending_state = None;
    let mut state_flush = tokio::time::interval(STATE_FLUSH);
    state_flush.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut heartbeat = tokio::time::interval(STATE_HEARTBEAT);
    heartbeat.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut config_check = tokio::time::interval(Duration::from_millis(500));
    config_check.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    let mut lease_check = tokio::time::interval(LEASE_CHECK);
    lease_check.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

    loop {
        tokio::select! {
            incoming = socket.recv() => {
                let Some(incoming) = incoming else { break; };
                let message = incoming.map_err(|error| error.to_string())?;
                match message {
                    Message::Text(text) => {
                        if Instant::now() >= lease_deadline {
                            controller_guard.revoke("remote_lease_expired")?;
                            return Err("controller lease expired".to_owned());
                        }
                        if text.len() > MAX_CONTROL_BYTES {
                            return Err("control message exceeds 16 KiB".to_owned());
                        }
                        let wire: WireEnvelope = serde_json::from_str(&text)
                            .map_err(|_| "malformed BRSP control envelope".to_owned())?;
                        validate_wire_identity(&wire, &controller_hello)?;
                        if remote_control_sequence.accept(wire.sequence) != SequenceDecision::Fresh {
                            send_protocol_error(
                                socket,
                                &target_hello,
                                &mut target_control_sequence,
                                "replayed_sequence",
                                "Control sequence is duplicate, old, or half-range ambiguous.",
                            ).await?;
                            continue;
                        }
                        match wire.message_type.as_str() {
                            "command" => {
                                let frame: CommandEnvelope = typed_from_wire(wire, "command")?;
                                let lease_valid = controller_guard.refresh_lease()?;
                                if !lease_valid {
                                    break;
                                }
                                lease_deadline = Instant::now() + CONTROLLER_LEASE;
                                let command = frame.body.into_request(runtime.snapshot()?.epoch, frame.sequence);
                                let applied = runtime.dispatch_remote(
                                    controller_hello.sender_id.clone(),
                                    scope_set.clone(),
                                    lease_valid,
                                    command,
                                )?;
                                let envelope = Envelope::new(
                                    "applied",
                                    target_hello.session_id.clone(),
                                    target_hello.sender_id.clone(),
                                    target_hello.sender_epoch,
                                    next_sequence(&mut target_control_sequence),
                                    AppliedBody::from(&applied),
                                );
                                send_control(socket, &envelope).await?;
                                if can_read {
                                    pending_state = Some(applied.snapshot);
                                }
                            }
                            "snapshot-request" => {
                                let _: EmptyEnvelope = typed_from_wire(wire, "snapshot-request")?;
                                if !controller_guard.refresh_lease()? {
                                    break;
                                }
                                lease_deadline = Instant::now() + CONTROLLER_LEASE;
                                if can_read {
                                    send_snapshot(
                                        socket,
                                        &target_hello,
                                        &mut target_control_sequence,
                                        runtime.snapshot()?,
                                    ).await?;
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
                                if !controller_guard.refresh_lease()? {
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
                    Message::Ping(payload) => socket.send(Message::Pong(payload)).await.map_err(|error| error.to_string())?,
                    Message::Pong(_) => {}
                    Message::Close(_) => break,
                    Message::Binary(_) => return Err("BRSP/1 JSON envelopes must use text frames".to_owned()),
                }
            }
            changed = state_rx.recv(), if can_read => {
                match changed {
                    Ok(changed) => {
                        pending_state = Some(changed);
                        while let Ok(newer) = state_rx.try_recv() {
                            pending_state = Some(newer);
                        }
                    }
                    Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => {
                        pending_state = Some(runtime.snapshot()?);
                    }
                    Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
                }
            }
            _ = state_flush.tick(), if can_read && pending_state.is_some() => {
                let newest = pending_state.take().expect("guarded by select condition");
                send_state(socket, &target_hello, &mut target_state_sequence, newest).await?;
            }
            _ = heartbeat.tick(), if can_read => {
                let current = pending_state.take().unwrap_or(runtime.snapshot()?);
                send_state(socket, &target_hello, &mut target_state_sequence, current).await?;
            }
            _ = config_check.tick() => {
                let config = runtime.0.remote_config()?;
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
                if Instant::now() >= lease_deadline {
                    controller_guard.revoke("remote_lease_expired")?;
                    return Err("controller lease expired".to_owned());
                }
            }
        }
    }
    Ok(())
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
    let text = tokio::time::timeout(timeout, receive_text(socket))
        .await
        .map_err(|_| format!("{expected_type} timed out"))??;
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
    socket
        .send(Message::Text(encoded.into()))
        .await
        .map_err(|error| error.to_string())
}

async fn send_snapshot(
    socket: &mut WebSocket,
    target_hello: &HelloEnvelope,
    control_sequence: &mut u32,
    snapshot: pps_contracts::RunnerSnapshot,
) -> Result<(), String> {
    let envelope: SnapshotEnvelope = Envelope::new(
        "snapshot",
        target_hello.session_id.clone(),
        target_hello.sender_id.clone(),
        target_hello.sender_epoch,
        next_sequence(control_sequence),
        SnapshotBody {
            revision: snapshot.revision,
            state: snapshot,
        },
    );
    send_control(socket, &envelope).await
}

async fn send_state(
    socket: &mut WebSocket,
    target_hello: &HelloEnvelope,
    state_sequence: &mut u32,
    snapshot: pps_contracts::RunnerSnapshot,
) -> Result<(), String> {
    let envelope: StateEnvelope = Envelope::new(
        "state",
        target_hello.session_id.clone(),
        target_hello.sender_id.clone(),
        target_hello.sender_epoch,
        next_sequence(state_sequence),
        StateBody {
            revision: snapshot.revision,
            state: snapshot,
        },
    );
    let encoded = serde_json::to_string(&envelope).map_err(|error| error.to_string())?;
    if encoded.len() > MAX_STATE_BYTES {
        return Err("serialized BRSP state exceeds 8 KiB".to_owned());
    }
    socket
        .send(Message::Text(encoded.into()))
        .await
        .map_err(|error| error.to_string())
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

struct ActiveControllerGuard {
    runtime: AppRuntime,
    controller_id: String,
    session_id: String,
    owner_token: String,
    armed: bool,
}

impl ActiveControllerGuard {
    fn owns(&self, controller: &ActiveController) -> bool {
        controller.id == self.controller_id
            && controller.session_id == self.session_id
            && controller.owner_token == self.owner_token
    }

    fn mark_connected(&self) -> Result<pps_contracts::RunnerSnapshot, String> {
        let remote = self
            .runtime
            .0
            .remote
            .lock()
            .map_err(|_| "remote configuration lock failed".to_owned())?;
        if !remote.enabled || remote.session_id != self.session_id {
            return Err("remote activation changed during authentication".to_owned());
        }
        let active = self
            .runtime
            .0
            .active_controller
            .lock()
            .map_err(|_| "controller lock failed".to_owned())?;
        if !active
            .as_ref()
            .is_some_and(|controller| self.owns(controller))
        {
            return Err("controller authority changed during authentication".to_owned());
        }
        let mut core = self
            .runtime
            .0
            .authority
            .lock()
            .map_err(|_| "authority lock failed".to_owned())?;
        let now = self.runtime.0.clock.stamp();
        core.set_connection_state("remote_connected", now.clone());
        let state = core.set_controller_lease(
            Some(&self.controller_id),
            Some(lease_expiry_unix_ms(&now)),
            now,
        );
        let _ = self.runtime.0.state_tx.send(state.clone());
        Ok(state)
    }

    /// Refresh only while this socket still owns the exact active
    /// controller/session reservation. The returned value is the reducer's
    /// lease validity input; callers must not substitute a constant `true`.
    fn refresh_lease(&self) -> Result<bool, String> {
        let remote = self
            .runtime
            .0
            .remote
            .lock()
            .map_err(|_| "remote configuration lock failed".to_owned())?;
        if !remote.enabled || remote.session_id != self.session_id {
            return Ok(false);
        }
        let active = self
            .runtime
            .0
            .active_controller
            .lock()
            .map_err(|_| "controller lock failed".to_owned())?;
        if !active
            .as_ref()
            .is_some_and(|controller| self.owns(controller))
        {
            return Ok(false);
        }
        let mut core = self
            .runtime
            .0
            .authority
            .lock()
            .map_err(|_| "authority lock failed".to_owned())?;
        let now = self.runtime.0.clock.stamp();
        let state = core.set_controller_lease(
            Some(&self.controller_id),
            Some(lease_expiry_unix_ms(&now)),
            now,
        );
        let _ = self.runtime.0.state_tx.send(state);
        Ok(true)
    }

    /// Revoke and pause only if this guard still owns the active controller in
    /// the same enabled session. Holding the remote/owner locks through the
    /// authority update prevents an old socket racing a rotation or disable
    /// from resetting a newer controller or overwriting `local_only` state.
    fn revoke(&mut self, connection_state: &str) -> Result<bool, String> {
        if !self.armed {
            return Ok(false);
        }
        let remote = self
            .runtime
            .0
            .remote
            .lock()
            .map_err(|_| "remote configuration lock failed".to_owned())?;
        if !remote.enabled || remote.session_id != self.session_id {
            self.armed = false;
            return Ok(false);
        }
        let mut active = self
            .runtime
            .0
            .active_controller
            .lock()
            .map_err(|_| "controller lock failed".to_owned())?;
        if !active
            .as_ref()
            .is_some_and(|controller| self.owns(controller))
        {
            self.armed = false;
            return Ok(false);
        }
        let mut core = self
            .runtime
            .0
            .authority
            .lock()
            .map_err(|_| "authority lock failed".to_owned())?;
        *active = None;
        let now = self.runtime.0.clock.stamp();
        core.set_controller_lease(None, None, now.clone());
        core.set_connection_state(connection_state, now.clone());
        let paused = core.dispatch_local(Action::RunPause, serde_json::json!({}), now);
        let _ = self.runtime.0.state_tx.send(paused.snapshot);
        self.armed = false;
        Ok(true)
    }
}

impl Drop for ActiveControllerGuard {
    fn drop(&mut self) {
        // Drop cannot surface lock failures. The ownership/session predicates
        // inside `revoke` still guarantee stale guards are inert.
        let _ = self.revoke("remote_waiting");
    }
}

fn lease_expiry_unix_ms(now: &ClockStamp) -> u64 {
    now.unix_ms
        .saturating_add(CONTROLLER_LEASE.as_millis() as u64)
        .min(JSON_MAX_SAFE_INTEGER)
}

fn grants_state_read(scopes: &BTreeSet<Scope>) -> bool {
    scopes.contains(&Scope::SessionRead)
}

// --- Bounded application-blind LAN relay ---------------------------------

#[derive(Default)]
struct RelayRegistry {
    rooms: HashMap<String, RelayRoom>,
}

#[derive(Default)]
struct RelayRoom {
    target: Option<RelaySlot>,
    controller: Option<RelaySlot>,
}

#[derive(Clone)]
struct RelaySenders {
    control: mpsc::Sender<String>,
    state: watch::Sender<Option<String>>,
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
    ws.max_message_size(MAX_CONTROL_BYTES)
        .max_frame_size(MAX_CONTROL_BYTES)
        .on_upgrade(move |socket| relay_socket(socket, state, room, role))
}

async fn relay_socket(
    mut socket: WebSocket,
    state: ServerState,
    room_id: String,
    role_text: String,
) {
    let enabled = state
        .runtime
        .0
        .remote_config()
        .map(|config| config.enabled)
        .unwrap_or(false);
    if !enabled {
        send_relay_text(
            &mut socket,
            relay_error_message(
                "remote_disabled",
                "Enable phone remote on the desktop host first.",
            ),
        )
        .await;
        return;
    }
    if !valid_room_id(&room_id) {
        send_relay_text(
            &mut socket,
            relay_error_message("invalid_room", "Relay room id is invalid."),
        )
        .await;
        return;
    }
    let Some(role) = RelayRole::parse(&role_text) else {
        send_relay_text(
            &mut socket,
            relay_error_message("invalid_role", "Relay role must be target or controller."),
        )
        .await;
        return;
    };

    let connection_id = random_nonce();
    let (control_tx, mut control_rx) = mpsc::channel::<String>(32);
    let (state_tx, mut state_rx) = watch::channel::<Option<String>>(None);
    let local_senders = RelaySenders {
        control: control_tx.clone(),
        state: state_tx,
    };
    let peer = {
        let mut registry = state.relay.lock().await;
        if !registry.rooms.contains_key(&room_id) && registry.rooms.len() >= MAX_RELAY_ROOMS {
            drop(registry);
            send_relay_text(
                &mut socket,
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
            send_relay_text(
                &mut socket,
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
    let _ = control_tx.try_send(relay_peer_message(role.opposite().label(), peer.is_some()));
    if let Some(peer) = &peer {
        let _ = peer
            .control
            .try_send(relay_peer_message(role.label(), true));
    }

    let mut rate_window = Instant::now();
    let mut rate_count = 0_u32;
    let mut config_check = tokio::time::interval(Duration::from_millis(500));
    config_check.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    loop {
        tokio::select! {
            inbound = socket.recv() => {
                let Some(Ok(inbound)) = inbound else { break; };
                match inbound {
                    Message::Text(text) if text.len() <= MAX_CONTROL_BYTES => {
                        if rate_window.elapsed() >= Duration::from_secs(1) {
                            rate_window = Instant::now();
                            rate_count = 0;
                        }
                        rate_count = rate_count.saturating_add(1);
                        if rate_count > MAX_RELAY_MESSAGES_PER_SECOND {
                            let _ = control_tx.try_send(relay_error_message("relay_rate_limit", "Relay message rate exceeded the bounded lab limit."));
                            break;
                        }
                        let classification = classify_relay_envelope(&text, role);
                        let Ok(replaceable) = classification else {
                            let _ = control_tx.try_send(relay_error_message("relay_direction_rejected", "Envelope is invalid for this BRSP role/lane."));
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
                            let delivered = if replaceable {
                                peer.state.send_replace(Some(text.to_string()));
                                true
                            } else {
                                peer.control.try_send(text.to_string()).is_ok()
                            };
                            if !delivered {
                                let _ = control_tx.try_send(relay_error_message("relay_backpressure", "Reliable peer queue is full; reconnect."));
                            }
                        } else {
                            let _ = control_tx.try_send(relay_error_message("peer_absent", "The other relay role is not connected yet."));
                        }
                    }
                    Message::Ping(payload) => {
                        if socket.send(Message::Pong(payload)).await.is_err() { break; }
                    }
                    Message::Pong(_) => {}
                    Message::Close(_) => break,
                    Message::Text(_) | Message::Binary(_) => {
                        let _ = control_tx.try_send(relay_error_message("message_rejected", "Relay accepts bounded BRSP JSON text."));
                    }
                }
            }
            outgoing = control_rx.recv() => {
                let Some(outgoing) = outgoing else { break; };
                if socket.send(Message::Text(outgoing.into())).await.is_err() { break; }
            }
            changed = state_rx.changed() => {
                if changed.is_err() { break; }
                let newest = state_rx.borrow_and_update().clone();
                if let Some(newest) = newest {
                    if socket.send(Message::Text(newest.into())).await.is_err() { break; }
                }
            }
            _ = config_check.tick() => {
                let enabled = state
                    .runtime
                    .0
                    .remote_config()
                    .map(|config| config.enabled)
                    .unwrap_or(false);
                if !enabled {
                    send_relay_text(
                        &mut socket,
                        relay_error_message(
                            "remote_disabled",
                            "Phone remote was disabled on the desktop host.",
                        ),
                    )
                    .await;
                    break;
                }
            }
        }
    }

    let peer = {
        let mut registry = state.relay.lock().await;
        let mut peer = None;
        let mut remove_room = false;
        if let Some(room) = registry.rooms.get_mut(&room_id) {
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
            registry.rooms.remove(&room_id);
        }
        peer
    };
    if let Some(peer) = peer {
        let _ = peer
            .control
            .try_send(relay_peer_message(role.label(), false));
        let _ = peer.control.try_send(relay_error_message(
            "peer_disconnected",
            "Relay peer disconnected; create a fresh authenticated session.",
        ));
    }
}

fn classify_relay_envelope(text: &str, role: RelayRole) -> Result<bool, ()> {
    let envelope: WireEnvelope = serde_json::from_str(text).map_err(|_| ())?;
    validate_common(&envelope, &envelope.message_type).map_err(|_| ())?;
    let replaceable = matches!(envelope.message_type.as_str(), "state" | "intent");
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
            "hello"
                | "proof"
                | "ready"
                | "command"
                | "snapshot-request"
                | "intent"
                | "error"
                | "bye"
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

async fn send_relay_text(socket: &mut WebSocket, text: String) {
    let _ = socket.send(Message::Text(text.into())).await;
}

#[cfg(test)]
mod tests {
    use super::*;
    use pps_contracts::RunnerPhase;

    fn active_guard(runtime: &AppRuntime, controller_id: &str) -> ActiveControllerGuard {
        let remote = runtime.0.remote_config().unwrap();
        let owner_token = random_owner_token();
        *runtime.0.active_controller.lock().unwrap() = Some(ActiveController {
            id: controller_id.to_owned(),
            session_id: remote.session_id.clone(),
            owner_token: owner_token.clone(),
            granted_scopes: vec![Scope::SessionRead, Scope::SessionTransport],
        });
        ActiveControllerGuard {
            runtime: runtime.clone(),
            controller_id: controller_id.to_owned(),
            session_id: remote.session_id,
            owner_token,
            armed: true,
        }
    }

    #[test]
    fn relay_ids_are_closed_tokens() {
        assert!(valid_room_id("room-1234"));
        assert!(!valid_room_id("../escape"));
        assert!(!valid_room_id("tiny"));
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
    fn deadman_revocation_clears_authority_and_pauses_a_running_target() {
        let runtime = AppRuntime::new();
        runtime.configure_remote(true, false).unwrap();
        let mut guard = active_guard(&runtime, "controller_deadman");
        let connected = guard.mark_connected().unwrap();
        assert_eq!(connected.connection_state, "remote_connected");
        assert!(connected.safety.lease_expires_at_unix_ms.is_some());

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

        assert!(guard.revoke("remote_lease_expired").unwrap());
        let expired = runtime.snapshot().unwrap();
        assert_eq!(expired.run.phase, RunnerPhase::Paused);
        assert_eq!(expired.connection_state, "remote_lease_expired");
        assert!(expired.safety.controller_lease_id.is_empty());
        assert!(expired.safety.lease_expires_at_unix_ms.is_none());
        assert!(runtime.0.active_controller.lock().unwrap().is_none());
    }

    #[test]
    fn stale_guard_cannot_reset_a_new_session_or_disabled_state() {
        let runtime = AppRuntime::new();
        runtime.configure_remote(true, false).unwrap();
        let old_guard = active_guard(&runtime, "controller_old");

        let same_session_guard = active_guard(&runtime, "controller_replacement");
        let before_old_drop = same_session_guard.mark_connected().unwrap();
        drop(old_guard);
        assert_eq!(runtime.snapshot().unwrap(), before_old_drop);
        assert_eq!(
            runtime
                .0
                .active_controller
                .lock()
                .unwrap()
                .as_ref()
                .map(|controller| controller.id.as_str()),
            Some("controller_replacement")
        );

        runtime.configure_remote(false, false).unwrap();
        runtime.configure_remote(true, false).unwrap();
        let new_guard = active_guard(&runtime, "controller_new");
        let before_stale_session_drop = new_guard.mark_connected().unwrap();
        drop(same_session_guard);
        assert_eq!(runtime.snapshot().unwrap(), before_stale_session_drop);
        assert_eq!(
            runtime
                .0
                .active_controller
                .lock()
                .unwrap()
                .as_ref()
                .map(|controller| controller.id.as_str()),
            Some("controller_new")
        );

        runtime.configure_remote(false, false).unwrap();
        let disabled = runtime.snapshot().unwrap();
        assert_eq!(disabled.connection_state, "local_only");
        drop(new_guard);
        assert_eq!(runtime.snapshot().unwrap(), disabled);
    }
}
