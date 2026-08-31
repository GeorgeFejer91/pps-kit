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
    AppliedBody, AppliedStatus, BrspRole, CommandEnvelope, EmptyEnvelope, Envelope, ErrorBody,
    ErrorEnvelope, HelloBody, HelloEnvelope, ProofEnvelope, ReadyBody, ReadyEnvelope, Scope,
    WireEnvelope, MAX_CONTROL_BYTES, MAX_STATE_BYTES, PPS_REMOTE_CAPABILITIES,
};
use serde::{de::DeserializeOwned, Serialize};
use tokio::sync::{mpsc, watch, Mutex as AsyncMutex};
use tower_http::services::ServeDir;

use crate::{
    execution_owner::RemoteOwnerIdentity,
    runtime::{AppRuntime, RemoteApplied, RemoteRunnerSnapshot},
};

const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(12);
const STATE_HEARTBEAT: Duration = Duration::from_millis(250);
const STATE_FLUSH: Duration = Duration::from_millis(16);
const CONTROLLER_LEASE: Duration = Duration::from_secs(5);
const LEASE_CHECK: Duration = Duration::from_millis(100);
const MAX_RELAY_ROOMS: usize = 16;
const MAX_RELAY_MESSAGES_PER_SECOND: u32 = 120;

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
    if claim.snapshot.schema != "pps-runner-public-snapshot.v1" {
        return Err("native public snapshot schema mismatch".to_owned());
    }
    let mut controller_guard = ActiveControllerGuard {
        runtime: runtime.clone(),
        identity: claim.identity,
        armed: true,
    };

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

    loop {
        tokio::select! {
            incoming = socket.recv() => {
                let Some(incoming) = incoming else { break; };
                let message = incoming.map_err(|error| error.to_string())?;
                match message {
                    Message::Text(text) => {
                        if Instant::now() >= lease_deadline {
                            controller_guard.revoke("remote_lease_expired").await?;
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
                                let applied = runtime
                                    .dispatch_lan_controller(
                                        controller_guard.identity.clone(),
                                        frame.sequence,
                                        frame.body,
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
                                send_control(socket, &envelope).await?;
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
                    Message::Ping(payload) => socket.send(Message::Pong(payload)).await.map_err(|error| error.to_string())?,
                    Message::Pong(_) => {}
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
                pending_state = false;
                if !send_state(socket, &target_hello, &mut target_state_sequence, &controller_guard).await? {
                    break;
                }
            }
            _ = heartbeat.tick(), if can_read => {
                pending_state = false;
                if !send_state(socket, &target_hello, &mut target_state_sequence, &controller_guard).await? {
                    break;
                }
            }
            _ = config_check.tick() => {
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
                if Instant::now() >= lease_deadline {
                    controller_guard.revoke("remote_lease_expired").await?;
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
    socket
        .send(Message::Text(encoded.into()))
        .await
        .map_err(|error| error.to_string())?;
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
        .remote_config_async()
        .await
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
                    .remote_config_async()
                    .await
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
    async fn deadman_revocation_clears_authority_and_pauses_a_running_target() {
        let runtime = AppRuntime::new();
        runtime.configure_remote_async(true, false).await.unwrap();
        let (mut guard, connected) = active_guard(&runtime, "controller_deadman").await;
        assert_eq!(connected.connection_state, "remote_connected");
        assert!(connected.safety.lease_expires_at_unix_ms.is_some());

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
