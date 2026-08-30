mod remote;
mod runtime;

use std::{path::PathBuf, str::FromStr};

use pps_contracts::{Action, Applied, RunnerSnapshot};
use pps_session_package::{verify_prepared_session, PreparedSessionSummary, VerificationRequest};
use runtime::{
    AppRuntime, RemoteSessionClaimRequest, RemoteSessionDispatchRequest, RemoteSessionError,
    RemoteSessionLeaseReceipt, RemoteSessionOwnerRequest, RemoteSessionRenewRequest,
    RemoteSessionRevocationReceipt, RemoteStatus,
};
use serde::Serialize;
use serde_json::Value;
use tauri::Manager;
use tauri_plugin_dialog::DialogExt;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
struct PreparedSessionCommandError {
    code: String,
    message: String,
}

impl PreparedSessionCommandError {
    fn new(code: &str, message: &str) -> Self {
        Self {
            code: code.to_owned(),
            message: message.to_owned(),
        }
    }

    fn runtime() -> Self {
        Self::new(
            "runtime_unavailable",
            "The native Runner authority is unavailable.",
        )
    }
}

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(rename_all = "camelCase")]
struct PreparedSessionSelection {
    cancelled: bool,
    summary: Option<PreparedSessionSummary>,
    snapshot: RunnerSnapshot,
}

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

#[tauri::command]
async fn select_prepared_session(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<PreparedSessionSelection, PreparedSessionCommandError> {
    require_main_window(&window)
        .map_err(|error| PreparedSessionCommandError::new(&error.code, &error.message))?;
    let runtime = state.inner().clone();
    let _selection_guard = runtime
        .begin_prepared_session_selection()
        .map_err(|reason| {
            PreparedSessionCommandError::new(
                reason,
                "A native prepared-session selection is already in progress.",
            )
        })?;

    // The WebView supplies no path. The native target owns the selection
    // gesture, and only a sanitized summary is ever returned across IPC.
    let (sender, receiver) = tokio::sync::oneshot::channel();
    app.dialog()
        .file()
        .add_filter("PPS prepared session", &["json"])
        .pick_file(move |selection| {
            let _ = sender.send(selection);
        });
    let selection = receiver.await.map_err(|_| {
        PreparedSessionCommandError::new(
            "dialog_unavailable",
            "The native file chooser could not complete.",
        )
    })?;

    let Some(selection) = selection else {
        return Ok(PreparedSessionSelection {
            cancelled: true,
            summary: None,
            snapshot: runtime
                .snapshot()
                .map_err(|_| PreparedSessionCommandError::runtime())?,
        });
    };
    let manifest_path = selection.into_path().map_err(|_| {
        PreparedSessionCommandError::new(
            "invalid_local_path",
            "The selected item is not a local prepared-session manifest.",
        )
    })?;

    let verified = tauri::async_runtime::spawn_blocking(move || {
        verify_prepared_session(VerificationRequest::new(&manifest_path))
    })
    .await
    .map_err(|_| PreparedSessionCommandError::runtime())?
    .map_err(|error| PreparedSessionCommandError::new(error.code(), error.public_message()))?;
    let summary = verified.summary().clone();
    let snapshot = runtime
        .adopt_verified_session(verified)
        .map_err(prepared_session_adoption_error)?;

    Ok(PreparedSessionSelection {
        cancelled: false,
        summary: Some(summary),
        snapshot,
    })
}

fn prepared_session_adoption_error(reason: &'static str) -> PreparedSessionCommandError {
    match reason {
        "cannot_replace_active_package" => PreparedSessionCommandError::new(
            reason,
            "Stop the active run before selecting another prepared session.",
        ),
        "prepared_package_participant_mismatch" => PreparedSessionCommandError::new(
            reason,
            "The prepared package participant does not match the submitted setup.",
        ),
        "runtime_unavailable" => PreparedSessionCommandError::runtime(),
        _ => PreparedSessionCommandError::new(
            "invalid_verified_package",
            "The verified package metadata is not supported by this Runner preview.",
        ),
    }
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
        .plugin(tauri_plugin_dialog::init())
        .manage(runtime)
        .invoke_handler(tauri::generate_handler![
            runner_snapshot,
            runner_dispatch,
            remote_status,
            configure_remote,
            rotate_pairing,
            select_prepared_session,
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
