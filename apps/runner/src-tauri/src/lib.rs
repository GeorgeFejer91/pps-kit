mod remote;
mod runtime;

use std::{path::PathBuf, str::FromStr};

use pps_contracts::{Action, Applied, RunnerSnapshot};
use runtime::{AppRuntime, RemoteStatus};
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
    app: tauri::AppHandle,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RemoteStatus, String> {
    if enabled {
        remote::ensure_started(state.inner().clone(), companion_web_root(&app))?;
    }
    state.configure_remote(enabled, allow_abort)
}

#[tauri::command]
fn rotate_pairing(state: tauri::State<'_, AppRuntime>) -> Result<RemoteStatus, String> {
    state.rotate_pairing()
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
            rotate_pairing
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
