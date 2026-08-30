mod remote;
mod runtime;

use std::{path::PathBuf, str::FromStr};

use pps_contracts::{Action, Applied, RunnerSnapshot};
use runtime::{
    AppRuntime, RemoteSessionClaimRequest, RemoteSessionDispatchRequest, RemoteSessionError,
    RemoteSessionLeaseReceipt, RemoteSessionOwnerRequest, RemoteSessionRenewRequest,
    RemoteSessionRevocationReceipt, RemoteStatus,
};
use serde_json::Value;
use tauri::Manager;

#[tauri::command]
fn runner_snapshot(state: tauri::State<'_, AppRuntime>) -> Result<RunnerSnapshot, String> {
    state.snapshot()
}

#[tauri::command]
fn runner_dispatch(
    action: String,
    args: Value,
    state: tauri::State<'_, AppRuntime>,
) -> Result<Applied, String> {
    let action = Action::from_str(&action).map_err(|error| error.to_string())?;
    state.dispatch_local(action, args)
}

#[tauri::command]
fn remote_status(state: tauri::State<'_, AppRuntime>) -> Result<RemoteStatus, String> {
    state.status()
}

#[tauri::command]
fn configure_remote(
    enabled: bool,
    allow_abort: bool,
    lan_listener: bool,
    app: tauri::AppHandle,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RemoteStatus, String> {
    if enabled && lan_listener {
        remote::ensure_started(state.inner().clone(), companion_web_root(&app))?;
    }
    state.configure_remote(enabled, allow_abort)
}

#[tauri::command]
fn rotate_pairing(state: tauri::State<'_, AppRuntime>) -> Result<RemoteStatus, String> {
    state.rotate_pairing()
}

fn require_main_window(window: &tauri::WebviewWindow) -> Result<(), RemoteSessionError> {
    if window.label() == "main" {
        Ok(())
    } else {
        Err(RemoteSessionError::new(
            "window_not_allowed",
            "Only the bundled main Runner window may bridge a browser remote session.",
        ))
    }
}

#[tauri::command]
fn remote_session_claim(
    request: RemoteSessionClaimRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
    require_main_window(&window)?;
    state.claim_remote_session(request)
}

#[tauri::command]
fn remote_session_renew(
    request: RemoteSessionRenewRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
    require_main_window(&window)?;
    state.renew_remote_session(request)
}

#[tauri::command]
fn remote_session_dispatch(
    request: RemoteSessionDispatchRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<Applied, RemoteSessionError> {
    require_main_window(&window)?;
    state.dispatch_remote_session(request)
}

#[tauri::command]
fn remote_session_revoke(
    request: RemoteSessionOwnerRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RemoteSessionRevocationReceipt, RemoteSessionError> {
    require_main_window(&window)?;
    state.revoke_remote_session(request)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let runtime = AppRuntime::new();
    tauri::Builder::default()
        .manage(runtime)
        .invoke_handler(tauri::generate_handler![
            runner_snapshot,
            runner_dispatch,
            remote_status,
            configure_remote,
            rotate_pairing,
            remote_session_claim,
            remote_session_renew,
            remote_session_dispatch,
            remote_session_revoke
        ])
        .run(tauri::generate_context!())
        .expect("error while running PPS Experiment Runner preview");
}

fn companion_web_root(app: &tauri::AppHandle) -> PathBuf {
    if cfg!(debug_assertions) {
        return PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../compiled");
    }
    app.path()
        .resource_dir()
        .map(|root| root.join("web"))
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../compiled"))
}
