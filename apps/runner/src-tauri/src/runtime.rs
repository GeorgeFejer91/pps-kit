use std::{
    collections::BTreeSet,
    net::{IpAddr, Ipv4Addr, SocketAddr, TcpListener as StdTcpListener},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use pps_brsp::{is_newer_sequence, random_epoch, random_nonce, valid_peer_id, PairingSecret};
use pps_contracts::{
    Action, Applied, ClockStamp, CommandBody, RunnerPhase, RunnerSnapshot, Scope, TimingTier,
    JSON_MAX_SAFE_INTEGER,
};
use pps_runner_core::{DispatchOrigin, RunnerCore};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::sync::broadcast;

const WEBVIEW_REMOTE_LEASE: Duration = Duration::from_secs(5);
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
    pub session_id: String,
    pub owner_token: String,
    pub granted_scopes: Vec<Scope>,
}

#[derive(Debug, Clone)]
struct WebviewRemoteSession {
    controller_id: String,
    session_id: String,
    owner_token: String,
    accepted_scopes: BTreeSet<Scope>,
    last_control_sequence: u32,
    lease_deadline: Instant,
}

impl WebviewRemoteSession {
    fn owns(&self, active: &ActiveController, session_id: &str, owner_token: &str) -> bool {
        self.session_id == session_id
            && self.owner_token == owner_token
            && active.id == self.controller_id
            && active.session_id == self.session_id
            && active.owner_token == self.owner_token
    }
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

    fn unavailable() -> Self {
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

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RemoteSessionLeaseReceipt {
    pub session_id: String,
    pub controller_id: String,
    pub owner_token: String,
    pub accepted_scopes: Vec<Scope>,
    pub lease_expires_at_unix_ms: u64,
    pub snapshot: RunnerSnapshot,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RemoteSessionRevocationReceipt {
    pub revoked: bool,
    pub snapshot: RunnerSnapshot,
}

#[derive(Debug, Default)]
pub struct RemoteServerState {
    pub bind_addr: Option<SocketAddr>,
    pub last_error: Option<String>,
}

#[derive(Debug)]
pub struct ClockSource {
    started: Instant,
}

impl ClockSource {
    fn new() -> Self {
        Self {
            started: Instant::now(),
        }
    }

    pub fn stamp(&self) -> ClockStamp {
        let unix_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_millis() as u64)
            .unwrap_or_default()
            .min(JSON_MAX_SAFE_INTEGER);
        let monotonic_ns = self
            .started
            .elapsed()
            .as_nanos()
            .min(JSON_MAX_SAFE_INTEGER as u128) as u64;
        ClockStamp {
            unix_ms,
            monotonic_ns,
        }
    }
}

pub struct RuntimeShared {
    pub authority: Mutex<RunnerCore>,
    pub remote: Mutex<RemoteConfig>,
    pub active_controller: Mutex<Option<ActiveController>>,
    webview_remote_session: Mutex<Option<WebviewRemoteSession>>,
    pub clock: ClockSource,
    pub state_tx: broadcast::Sender<RunnerSnapshot>,
    pub remote_server: Mutex<RemoteServerState>,
    pub advertised_ip: IpAddr,
}

#[derive(Clone)]
pub struct AppRuntime(pub Arc<RuntimeShared>);

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
        let clock = ClockSource::new();
        let core = RunnerCore::new(
            target_id,
            "desktop-tauri-preview",
            epoch,
            TimingTier::DesktopPreview,
            clock.stamp(),
        );
        let (state_tx, _) = broadcast::channel(64);
        let shared = RuntimeShared {
            authority: Mutex::new(core),
            remote: Mutex::new(RemoteConfig {
                enabled: false,
                allow_abort: false,
                secret: PairingSecret::generate(),
                session_id: format!("session_{}", &random_nonce()[..18]),
            }),
            active_controller: Mutex::new(None),
            webview_remote_session: Mutex::new(None),
            clock,
            state_tx,
            remote_server: Mutex::new(RemoteServerState::default()),
            advertised_ip,
        };
        Self(Arc::new(shared))
    }

    pub fn snapshot(&self) -> Result<RunnerSnapshot, String> {
        self.0
            .authority
            .lock()
            .map_err(|_| "runner authority lock is poisoned".to_owned())
            .map(|core| core.snapshot())
    }

    pub fn dispatch_local(&self, action: Action, args: Value) -> Result<Applied, String> {
        let mut core = self
            .0
            .authority
            .lock()
            .map_err(|_| "runner authority lock is poisoned".to_owned())?;
        let previous_revision = core.revision();
        let applied = core.dispatch_local(action, args, self.0.clock.stamp());
        if applied.resulting_revision != previous_revision {
            let _ = self.0.state_tx.send(applied.snapshot.clone());
        }
        Ok(applied)
    }

    pub fn dispatch_remote(
        &self,
        controller_id: String,
        scopes: BTreeSet<Scope>,
        lease_valid: bool,
        command: pps_contracts::CommandRequest,
    ) -> Result<Applied, String> {
        let mut core = self
            .0
            .authority
            .lock()
            .map_err(|_| "runner authority lock is poisoned".to_owned())?;
        let previous_revision = core.revision();
        let applied = core.dispatch(
            DispatchOrigin::Remote {
                controller_id,
                granted_scopes: scopes,
                lease_valid,
            },
            command,
            self.0.clock.stamp(),
        );
        if applied.resulting_revision != previous_revision {
            let _ = self.0.state_tx.send(applied.snapshot.clone());
        }
        Ok(applied)
    }

    /// Reserve the single native remote-controller authority for a WebView
    /// transport only after that transport has completed its own BRSP proof
    /// and scope negotiation. The returned owner token is fresh native bearer
    /// material and never enters the public Runner snapshot.
    pub fn claim_remote_session(
        &self,
        request: RemoteSessionClaimRequest,
    ) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
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

        let remote = self
            .0
            .remote
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        validate_remote_activation(&remote, &request.session_id)?;
        let mut available_scopes = Scope::DEFAULT_REMOTE.into_iter().collect::<BTreeSet<_>>();
        if remote.allow_abort {
            available_scopes.insert(Scope::SessionAbort);
        }
        if !accepted_scopes.is_subset(&available_scopes) {
            return Err(RemoteSessionError::new(
                "scope_not_available",
                "The WebView requested a scope that the local operator did not enable.",
            ));
        }

        let mut active = self
            .0
            .active_controller
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let mut webview = self
            .0
            .webview_remote_session
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        if active.is_some() || webview.is_some() {
            return Err(RemoteSessionError::new(
                "controller_busy",
                "The Runner already has an active remote controller.",
            ));
        }
        let mut core = self
            .0
            .authority
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;

        let owner_token = random_nonce();
        let controller = ActiveController {
            id: request.controller_id.clone(),
            session_id: request.session_id.clone(),
            owner_token: owner_token.clone(),
            granted_scopes: accepted_scopes.iter().copied().collect(),
        };
        let lease = WebviewRemoteSession {
            controller_id: request.controller_id,
            session_id: request.session_id,
            owner_token: owner_token.clone(),
            accepted_scopes,
            last_control_sequence: request.ready_sequence,
            lease_deadline: Instant::now() + WEBVIEW_REMOTE_LEASE,
        };
        *active = Some(controller);
        *webview = Some(lease.clone());

        let now = self.0.clock.stamp();
        core.set_connection_state("remote_connected", now.clone());
        let lease_expires_at_unix_ms = remote_lease_expiry_unix_ms(&now);
        let snapshot = core.set_controller_lease(
            Some(&lease.controller_id),
            Some(lease_expires_at_unix_ms),
            now,
        );
        let _ = self.0.state_tx.send(snapshot.clone());
        drop(core);
        drop(webview);
        drop(active);
        drop(remote);

        if let Err(error) = self.spawn_remote_session_watchdog(owner_token) {
            let _ = self.revoke_remote_session(RemoteSessionOwnerRequest {
                session_id: lease.session_id.clone(),
                owner_token: lease.owner_token.clone(),
            });
            return Err(error);
        }
        Ok(remote_session_receipt(
            &lease,
            lease_expires_at_unix_ms,
            snapshot,
        ))
    }

    /// Renew the Rust-owned controller lease after the WebView adapter has
    /// accepted a fresh authenticated BRSP control record. Sequence freshness
    /// is checked again at the native boundary before the deadline moves.
    pub fn renew_remote_session(
        &self,
        request: RemoteSessionRenewRequest,
    ) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
        validate_owner_request(&request.session_id, &request.owner_token)?;
        let remote = self
            .0
            .remote
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        validate_remote_activation(&remote, &request.session_id)?;
        let active = self
            .0
            .active_controller
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let mut webview = self
            .0
            .webview_remote_session
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let lease = current_owned_lease(
            active.as_ref(),
            webview.as_ref(),
            &request.session_id,
            &request.owner_token,
        )?;
        if Instant::now() >= lease.lease_deadline {
            drop(webview);
            drop(active);
            drop(remote);
            let _ = self.expire_remote_session_if_due(&request.owner_token)?;
            return Err(RemoteSessionError::new(
                "controller_lease_expired",
                "The native remote-controller lease expired.",
            ));
        }
        if !is_newer_sequence(request.control_sequence, lease.last_control_sequence) {
            return Err(RemoteSessionError::new(
                "replayed_sequence",
                "The BRSP control sequence is duplicate, old, or ambiguous.",
            ));
        }
        let lease = webview.as_mut().expect("owned lease was checked above");
        lease.last_control_sequence = request.control_sequence;
        lease.lease_deadline = Instant::now() + WEBVIEW_REMOTE_LEASE;
        let lease = lease.clone();
        let mut core = self
            .0
            .authority
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let now = self.0.clock.stamp();
        let lease_expires_at_unix_ms = remote_lease_expiry_unix_ms(&now);
        let snapshot = core.set_controller_lease(
            Some(&lease.controller_id),
            Some(lease_expires_at_unix_ms),
            now,
        );
        let _ = self.0.state_tx.send(snapshot.clone());
        Ok(remote_session_receipt(
            &lease,
            lease_expires_at_unix_ms,
            snapshot,
        ))
    }

    /// Apply one already-authenticated WebView command through the same remote
    /// reducer origin used by the LAN adapter. This method never falls back to
    /// `dispatch_local` for the requested operation.
    pub fn dispatch_remote_session(
        &self,
        request: RemoteSessionDispatchRequest,
    ) -> Result<Applied, RemoteSessionError> {
        validate_owner_request(&request.session_id, &request.owner_token)?;
        let remote = self
            .0
            .remote
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        validate_remote_activation(&remote, &request.session_id)?;
        let active = self
            .0
            .active_controller
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let mut webview = self
            .0
            .webview_remote_session
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let lease = current_owned_lease(
            active.as_ref(),
            webview.as_ref(),
            &request.session_id,
            &request.owner_token,
        )?;
        if Instant::now() >= lease.lease_deadline {
            drop(webview);
            drop(active);
            drop(remote);
            let _ = self.expire_remote_session_if_due(&request.owner_token)?;
            return Err(RemoteSessionError::new(
                "controller_lease_expired",
                "The native remote-controller lease expired.",
            ));
        }
        if !is_newer_sequence(request.control_sequence, lease.last_control_sequence) {
            return Err(RemoteSessionError::new(
                "replayed_sequence",
                "The BRSP control sequence is duplicate, old, or ambiguous.",
            ));
        }
        if !lease.accepted_scopes.contains(&request.command.scope) {
            return Err(RemoteSessionError::new(
                "scope_not_granted",
                "The command scope was not negotiated for this controller.",
            ));
        }

        let lease = webview.as_mut().expect("owned lease was checked above");
        lease.last_control_sequence = request.control_sequence;
        lease.lease_deadline = Instant::now() + WEBVIEW_REMOTE_LEASE;
        let controller_id = lease.controller_id.clone();
        let accepted_scopes = lease.accepted_scopes.clone();
        let mut core = self
            .0
            .authority
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let now = self.0.clock.stamp();
        let lease_expires_at_unix_ms = remote_lease_expiry_unix_ms(&now);
        let refreshed =
            core.set_controller_lease(Some(&controller_id), Some(lease_expires_at_unix_ms), now);
        let authority_epoch = core.epoch();
        let _ = self.0.state_tx.send(refreshed);
        drop(core);

        let command = request
            .command
            .into_request(authority_epoch, request.control_sequence);
        self.dispatch_remote(controller_id, accepted_scopes, true, command)
            .map_err(|_| RemoteSessionError::unavailable())
    }

    /// Revoke only the exact owner token returned by `claim_remote_session`.
    /// A late pagehide/Stop from an old WebView cannot clear a replacement.
    pub fn revoke_remote_session(
        &self,
        request: RemoteSessionOwnerRequest,
    ) -> Result<RemoteSessionRevocationReceipt, RemoteSessionError> {
        validate_owner_request(&request.session_id, &request.owner_token)?;
        let remote = self
            .0
            .remote
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        validate_remote_activation(&remote, &request.session_id)?;
        let mut active = self
            .0
            .active_controller
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let mut webview = self
            .0
            .webview_remote_session
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        current_owned_lease(
            active.as_ref(),
            webview.as_ref(),
            &request.session_id,
            &request.owner_token,
        )?;
        let mut core = self
            .0
            .authority
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let snapshot = revoke_webview_owner(
            &mut active,
            &mut webview,
            &mut core,
            self.0.clock.stamp(),
            "remote_waiting",
        );
        let _ = self.0.state_tx.send(snapshot.clone());
        Ok(RemoteSessionRevocationReceipt {
            revoked: true,
            snapshot,
        })
    }

    fn spawn_remote_session_watchdog(&self, owner_token: String) -> Result<(), RemoteSessionError> {
        let runtime = self.clone();
        thread::Builder::new()
            .name("pps-remote-lease".to_owned())
            .spawn(move || loop {
                let delay = match runtime.remote_session_watchdog_delay(&owner_token) {
                    Ok(Some(delay)) => delay,
                    Ok(None) | Err(_) => return,
                };
                if !delay.is_zero() {
                    thread::sleep(delay);
                }
                match runtime.expire_remote_session_if_due(&owner_token) {
                    Ok(true) | Err(_) => return,
                    Ok(false) => {}
                }
            })
            .map(|_| ())
            .map_err(|_| {
                RemoteSessionError::new(
                    "lease_watchdog_unavailable",
                    "The native remote-session safety watchdog could not start.",
                )
            })
    }

    fn remote_session_watchdog_delay(
        &self,
        owner_token: &str,
    ) -> Result<Option<Duration>, RemoteSessionError> {
        let webview = self
            .0
            .webview_remote_session
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        Ok(webview
            .as_ref()
            .filter(|lease| lease.owner_token == owner_token)
            .map(|lease| {
                lease
                    .lease_deadline
                    .saturating_duration_since(Instant::now())
            }))
    }

    fn expire_remote_session_if_due(&self, owner_token: &str) -> Result<bool, RemoteSessionError> {
        let remote = self
            .0
            .remote
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let mut active = self
            .0
            .active_controller
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let mut webview = self
            .0
            .webview_remote_session
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let Some(lease) = webview
            .as_ref()
            .filter(|lease| lease.owner_token == owner_token)
        else {
            return Ok(true);
        };
        if !remote.enabled
            || remote.session_id != lease.session_id
            || !active
                .as_ref()
                .is_some_and(|controller| lease.owns(controller, &lease.session_id, owner_token))
        {
            *webview = None;
            return Ok(true);
        }
        if Instant::now() < lease.lease_deadline {
            return Ok(false);
        }
        let mut core = self
            .0
            .authority
            .lock()
            .map_err(|_| RemoteSessionError::unavailable())?;
        let snapshot = revoke_webview_owner(
            &mut active,
            &mut webview,
            &mut core,
            self.0.clock.stamp(),
            "remote_lease_expired",
        );
        let _ = self.0.state_tx.send(snapshot);
        Ok(true)
    }

    pub fn available_scopes(&self) -> Result<Vec<Scope>, String> {
        let remote = self
            .0
            .remote
            .lock()
            .map_err(|_| "remote configuration lock is poisoned".to_owned())?;
        let mut scopes = Scope::DEFAULT_REMOTE.to_vec();
        if remote.allow_abort {
            scopes.push(Scope::SessionAbort);
        }
        Ok(scopes)
    }

    pub fn status(&self) -> Result<RemoteStatus, String> {
        let snapshot = self.snapshot()?;
        let remote = self
            .0
            .remote
            .lock()
            .map_err(|_| "remote configuration lock is poisoned".to_owned())?;
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
        let active = self
            .0
            .active_controller
            .lock()
            .map_err(|_| "controller lock is poisoned".to_owned())?
            .clone();
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

    pub fn configure_remote(
        &self,
        enabled: bool,
        allow_abort: bool,
    ) -> Result<RemoteStatus, String> {
        let changed = {
            let mut remote = self
                .0
                .remote
                .lock()
                .map_err(|_| "remote configuration lock is poisoned".to_owned())?;
            let changed = remote.enabled != enabled || remote.allow_abort != allow_abort;
            remote.enabled = enabled;
            remote.allow_abort = allow_abort;
            if changed {
                remote.secret = PairingSecret::generate();
                remote.session_id = format!("session_{}", &random_nonce()[..18]);
            }
            changed
        };
        if changed {
            self.invalidate_remote_epoch(if enabled {
                "remote_enabled"
            } else {
                "local_only"
            })?;
        }
        self.status()
    }

    pub fn rotate_pairing(&self) -> Result<RemoteStatus, String> {
        {
            let mut remote = self
                .0
                .remote
                .lock()
                .map_err(|_| "remote configuration lock is poisoned".to_owned())?;
            remote.secret = PairingSecret::generate();
            remote.session_id = format!("session_{}", &random_nonce()[..18]);
        }
        self.invalidate_remote_epoch("pairing_rotated")?;
        self.status()
    }

    fn invalidate_remote_epoch(&self, connection_state: &str) -> Result<(), String> {
        let mut active = self
            .0
            .active_controller
            .lock()
            .map_err(|_| "controller lock is poisoned".to_owned())?;
        let displaced_active_owner = active.is_some();
        let mut webview = self
            .0
            .webview_remote_session
            .lock()
            .map_err(|_| "webview remote-session lock is poisoned".to_owned())?;
        let mut core = self
            .0
            .authority
            .lock()
            .map_err(|_| "runner authority lock is poisoned".to_owned())?;
        let now = self.0.clock.stamp();
        core.rotate_epoch(u64::from(random_epoch()), now.clone());
        core.set_controller_lease(None, None, now.clone());
        let mut snapshot = core.set_connection_state(connection_state, now.clone());
        if displaced_active_owner && snapshot.run.phase == RunnerPhase::Running {
            snapshot = core
                .dispatch_local(Action::RunPause, serde_json::json!({}), now)
                .snapshot;
        }
        *active = None;
        *webview = None;
        drop(core);
        drop(webview);
        drop(active);
        let _ = self.0.state_tx.send(snapshot);
        Ok(())
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

fn validate_remote_activation(
    remote: &RemoteConfig,
    session_id: &str,
) -> Result<(), RemoteSessionError> {
    if !remote.enabled {
        return Err(RemoteSessionError::new(
            "remote_disabled",
            "Remote control is not enabled by the local operator.",
        ));
    }
    if remote.session_id != session_id {
        return Err(RemoteSessionError::new(
            "session_mismatch",
            "The remote activation changed; use a fresh invitation.",
        ));
    }
    Ok(())
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

fn current_owned_lease<'a>(
    active: Option<&ActiveController>,
    webview: Option<&'a WebviewRemoteSession>,
    session_id: &str,
    owner_token: &str,
) -> Result<&'a WebviewRemoteSession, RemoteSessionError> {
    let Some(lease) = webview else {
        return Err(RemoteSessionError::new(
            "stale_owner",
            "The WebView no longer owns the native remote session.",
        ));
    };
    if !active.is_some_and(|controller| lease.owns(controller, session_id, owner_token)) {
        return Err(RemoteSessionError::new(
            "stale_owner",
            "The WebView no longer owns the native remote session.",
        ));
    }
    Ok(lease)
}

fn remote_lease_expiry_unix_ms(now: &ClockStamp) -> u64 {
    now.unix_ms
        .saturating_add(WEBVIEW_REMOTE_LEASE.as_millis() as u64)
        .min(JSON_MAX_SAFE_INTEGER)
}

fn remote_session_receipt(
    lease: &WebviewRemoteSession,
    lease_expires_at_unix_ms: u64,
    snapshot: RunnerSnapshot,
) -> RemoteSessionLeaseReceipt {
    RemoteSessionLeaseReceipt {
        session_id: lease.session_id.clone(),
        controller_id: lease.controller_id.clone(),
        owner_token: lease.owner_token.clone(),
        accepted_scopes: lease.accepted_scopes.iter().copied().collect(),
        lease_expires_at_unix_ms,
        snapshot,
    }
}

fn revoke_webview_owner(
    active: &mut Option<ActiveController>,
    webview: &mut Option<WebviewRemoteSession>,
    core: &mut RunnerCore,
    now: ClockStamp,
    connection_state: &str,
) -> RunnerSnapshot {
    *active = None;
    *webview = None;
    core.set_controller_lease(None, None, now.clone());
    core.set_connection_state(connection_state, now.clone());
    core.dispatch_local(Action::RunPause, serde_json::json!({}), now)
        .snapshot
}

impl RuntimeShared {
    pub fn remote_config(&self) -> Result<RemoteConfig, String> {
        self.remote
            .lock()
            .map_err(|_| "remote configuration lock is poisoned".to_owned())
            .map(|config| config.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use pps_contracts::AppliedStatus;

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
        let remote = runtime.0.remote_config().unwrap();
        *runtime.0.active_controller.lock().unwrap() = Some(ActiveController {
            id: "controller_active".to_owned(),
            session_id: remote.session_id,
            owner_token: random_nonce(),
            granted_scopes: Scope::DEFAULT_REMOTE.to_vec(),
        });

        let now = runtime.0.clock.stamp();
        {
            let mut core = runtime.0.authority.lock().unwrap();
            core.set_connection_state("remote_connected", now.clone());
            core.set_controller_lease(
                Some("controller_active"),
                Some(now.unix_ms.saturating_add(5_000)),
                now,
            );
        }
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
        assert!(runtime.0.active_controller.lock().unwrap().is_none());
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
        let replacement =
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

        let active = runtime.0.active_controller.lock().unwrap().clone().unwrap();
        assert_eq!(active.id, "controller-new");
        assert_eq!(active.owner_token, replacement.owner_token);
        assert_eq!(
            runtime.snapshot().unwrap().safety.controller_lease_id,
            "controller-new"
        );
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
            renewed.snapshot.safety.controller_lease_id,
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
        assert_eq!(applied.reason, "action_is_local_only");
        assert!(applied.snapshot.safety.local_armed);
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
        assert!(revoked.snapshot.safety.controller_lease_id.is_empty());
        assert!(runtime.0.active_controller.lock().unwrap().is_none());
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
        runtime
            .0
            .webview_remote_session
            .lock()
            .unwrap()
            .as_mut()
            .unwrap()
            .lease_deadline = Instant::now() - Duration::from_millis(1);

        assert!(runtime
            .expire_remote_session_if_due(&receipt.owner_token)
            .unwrap());

        let snapshot = runtime.snapshot().unwrap();
        assert_eq!(snapshot.run.phase, RunnerPhase::Paused);
        assert_eq!(snapshot.connection_state, "remote_lease_expired");
        assert!(snapshot.safety.controller_lease_id.is_empty());
        assert!(runtime.0.active_controller.lock().unwrap().is_none());
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
}
