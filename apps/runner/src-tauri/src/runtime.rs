use std::{
    collections::BTreeSet,
    net::{IpAddr, Ipv4Addr, SocketAddr, TcpListener as StdTcpListener},
    sync::{Arc, Mutex},
    time::{Instant, SystemTime, UNIX_EPOCH},
};

use pps_brsp::{random_epoch, random_nonce, PairingSecret};
use pps_contracts::{
    Action, Applied, ClockStamp, RunnerPhase, RunnerSnapshot, Scope, TimingTier,
    JSON_MAX_SAFE_INTEGER,
};
use pps_runner_core::{DispatchOrigin, RunnerCore};
use serde::Serialize;
use serde_json::Value;
use tokio::sync::broadcast;

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
        drop(core);
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
}
