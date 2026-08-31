mod execution_owner;
mod latency_diagnostics;
mod prepared_audio;
mod prepared_execution;
mod remote;
mod runtime;

use std::{path::PathBuf, str::FromStr};

use latency_diagnostics::{LatencyRoute, LatencyStage, NativeLatencySummary, TraceOutcome};
use pps_contracts::{Action, Applied, AppliedStatus, RunnerSnapshot};
use pps_session_package::{verify_prepared_session, PreparedSessionSummary, VerificationRequest};
use prepared_audio::{prepare_verified_audio, PreparedAudioError, PreparedAudioSummary};
use prepared_execution::{
    compile_prepared_execution, PreparedExecutionError, PreparedExecutionSummary,
};
use runtime::{
    AppRuntime, PreparedAudioPreparation, RemoteApplied, RemoteSessionClaimRequest,
    RemoteSessionDispatchRequest, RemoteSessionError, RemoteSessionLeaseReceipt,
    RemoteSessionOwnerRequest, RemoteSessionRenewRequest, RemoteSessionRevocationReceipt,
    RemoteStatus,
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
async fn runner_snapshot(state: tauri::State<'_, AppRuntime>) -> Result<RunnerSnapshot, String> {
    state.snapshot_async().await
}

#[tauri::command]
async fn runner_dispatch(
    action: String,
    args: Value,
    state: tauri::State<'_, AppRuntime>,
) -> Result<Applied, String> {
    let mut trace = state.start_latency_trace(LatencyRoute::LocalTauri);
    let parsed_action = Action::from_str(&action);
    trace.mark(LatencyStage::AdapterValidationComplete);
    let result = match parsed_action {
        Ok(action) => {
            state
                .dispatch_local_traced_async(action, args, trace.trace())
                .await
        }
        Err(error) => Err(error.to_string()),
    };
    trace.mark(LatencyStage::ReplyReady);
    trace.mark(LatencyStage::AdapterHandoff);
    trace.finish(match &result {
        Ok(applied) if applied.status == AppliedStatus::Accepted => TraceOutcome::Applied,
        Ok(_) | Err(_) => TraceOutcome::Rejected,
    });
    result
}

#[tauri::command]
async fn remote_status(state: tauri::State<'_, AppRuntime>) -> Result<RemoteStatus, String> {
    state.status_async().await
}

#[tauri::command]
async fn configure_remote(
    enabled: bool,
    allow_abort: bool,
    lan_listener: bool,
    app: tauri::AppHandle,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RemoteStatus, String> {
    if enabled && lan_listener {
        remote::ensure_started(state.inner().clone(), companion_web_root(&app))?;
    }
    state.configure_remote_async(enabled, allow_abort).await
}

#[tauri::command]
async fn rotate_pairing(state: tauri::State<'_, AppRuntime>) -> Result<RemoteStatus, String> {
    state.rotate_pairing_async().await
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
                .snapshot_async()
                .await
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
        .adopt_verified_session_async(verified)
        .await
        .map_err(prepared_session_adoption_error)?;

    Ok(PreparedSessionSelection {
        cancelled: false,
        summary: Some(summary),
        snapshot,
    })
}

#[tauri::command]
async fn inspect_prepared_execution(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<PreparedExecutionSummary, PreparedSessionCommandError> {
    require_main_window(&window)
        .map_err(|error| PreparedSessionCommandError::new(&error.code, &error.message))?;
    let runtime = state.inner().clone();
    let (inspection_guard, source) = runtime
        .begin_prepared_execution_inspection_async()
        .await
        .map_err(prepared_execution_runtime_error)?;

    // Reverification and CSV schedule compilation are blocking native work.
    // The WebView supplies no path or package identity and receives no raw
    // events; those path-bearing schedules remain in managed Rust state.
    let compiled = tauri::async_runtime::spawn_blocking(move || compile_prepared_execution(source))
        .await
        .map_err(|_| PreparedSessionCommandError::runtime())?
        .map_err(prepared_execution_compile_error)?;
    let summary = runtime
        .cache_prepared_execution_async(compiled)
        .await
        .map_err(prepared_execution_runtime_error)?;
    drop(inspection_guard);
    Ok(summary)
}

#[tauri::command]
async fn prepare_first_audio_block(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<PreparedAudioSummary, PreparedSessionCommandError> {
    require_main_window(&window)
        .map_err(|error| PreparedSessionCommandError::new(&error.code, &error.message))?;
    let runtime = state.inner().clone();
    let preparation = runtime
        .begin_prepared_audio_preparation_async(0)
        .await
        .map_err(prepared_audio_runtime_error)?;
    let (_preparation_guard, source) = match preparation {
        PreparedAudioPreparation::Cached(summary) => return Ok(summary),
        PreparedAudioPreparation::Decode { _guard, source } => (_guard, source),
    };

    // PCM hashing/decoding may be large and blocking. It runs outside the
    // authority thread; the actor accepts the immutable result only if every
    // captured package, run, block, schedule, and receipt fence still matches.
    let (_preparation_guard, candidate) = tauri::async_runtime::spawn_blocking(move || {
        (
            _preparation_guard,
            prepare_verified_audio(source).map_err(prepared_audio_preparation_error),
        )
    })
    .await
    .map_err(|_| PreparedSessionCommandError::runtime())?;
    let candidate = candidate?;
    runtime
        .cache_prepared_audio_async(candidate)
        .await
        .map_err(prepared_audio_runtime_error)
}

fn prepared_audio_preparation_error(error: PreparedAudioError) -> PreparedSessionCommandError {
    PreparedSessionCommandError::new(error.code(), error.public_message())
}

fn prepared_audio_runtime_error(reason: &'static str) -> PreparedSessionCommandError {
    match reason {
        "prepared_audio_preparation_in_progress" => PreparedSessionCommandError::new(
            reason,
            "A native audio preload is already in progress.",
        ),
        "prepared_audio_active_run" => PreparedSessionCommandError::new(
            reason,
            "Audio preloading is unavailable while a run is active.",
        ),
        "prepared_session_missing" => PreparedSessionCommandError::new(
            reason,
            "Select and verify a prepared session before loading its audio.",
        ),
        "prepared_execution_missing" => PreparedSessionCommandError::new(
            reason,
            "Inspect the prepared schedules before loading their audio.",
        ),
        "prepared_package_replaced"
        | "prepared_execution_replaced"
        | "prepared_audio_run_replaced"
        | "prepared_audio_block_replaced" => PreparedSessionCommandError::new(
            "prepared_audio_stale",
            "The selected package changed during audio loading; load it again.",
        ),
        "prepared_audio_block_missing" => PreparedSessionCommandError::new(
            reason,
            "The verified package does not contain a first audio block.",
        ),
        "prepared_audio_sample_rate_invalid" => PreparedSessionCommandError::new(
            reason,
            "The prepared schedule does not provide a supported audio sample rate.",
        ),
        "prepared_audio_resource_limit" => PreparedSessionCommandError::new(
            reason,
            "The prepared audio exceeds the native preload resource limit.",
        ),
        "runtime_unavailable" => PreparedSessionCommandError::runtime(),
        _ => PreparedSessionCommandError::new(
            "prepared_audio_unavailable",
            "The prepared audio could not be loaded by the native Runner.",
        ),
    }
}

fn prepared_execution_compile_error(error: PreparedExecutionError) -> PreparedSessionCommandError {
    PreparedSessionCommandError::new(error.code(), error.public_message())
}

fn prepared_execution_runtime_error(reason: &'static str) -> PreparedSessionCommandError {
    match reason {
        "prepared_execution_inspection_in_progress" => PreparedSessionCommandError::new(
            reason,
            "A native prepared-execution inspection is already in progress.",
        ),
        "prepared_session_missing" => PreparedSessionCommandError::new(
            reason,
            "Select and verify a prepared session before inspecting its schedules.",
        ),
        "prepared_package_replaced" => PreparedSessionCommandError::new(
            reason,
            "The selected prepared package was replaced during inspection; inspect it again.",
        ),
        "runtime_unavailable" => PreparedSessionCommandError::runtime(),
        _ => PreparedSessionCommandError::new(
            "prepared_execution_unavailable",
            "The prepared execution schedules could not be inspected.",
        ),
    }
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
async fn remote_session_claim(
    request: RemoteSessionClaimRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
    require_main_window(&window)?;
    state.claim_remote_session_async(request).await
}

#[tauri::command]
async fn remote_session_renew(
    request: RemoteSessionRenewRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RemoteSessionLeaseReceipt, RemoteSessionError> {
    require_main_window(&window)?;
    state.renew_remote_session_async(request).await
}

#[tauri::command]
async fn remote_session_dispatch(
    request: RemoteSessionDispatchRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RemoteApplied, RemoteSessionError> {
    let mut trace = state.start_latency_trace(LatencyRoute::WebViewVdo);
    let window_validation = require_main_window(&window);
    let result = match window_validation {
        Ok(()) => {
            state
                .dispatch_remote_session_traced_async(request, trace.trace())
                .await
        }
        Err(error) => {
            trace.mark(LatencyStage::AdapterValidationComplete);
            Err(error)
        }
    };
    trace.mark(LatencyStage::ReplyReady);
    trace.mark(LatencyStage::AdapterHandoff);
    trace.finish(match &result {
        Ok(applied) if applied.status == AppliedStatus::Accepted => TraceOutcome::Applied,
        Ok(_) | Err(_) => TraceOutcome::Rejected,
    });
    result
}

#[tauri::command]
async fn native_latency_diagnostics(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<NativeLatencySummary, RemoteSessionError> {
    require_main_window(&window)?;
    Ok(state.latency_summary())
}

#[tauri::command]
async fn remote_session_revoke(
    request: RemoteSessionOwnerRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RemoteSessionRevocationReceipt, RemoteSessionError> {
    require_main_window(&window)?;
    state.revoke_remote_session_async(request).await
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
            inspect_prepared_execution,
            prepare_first_audio_block,
            remote_session_claim,
            remote_session_renew,
            remote_session_dispatch,
            remote_session_revoke,
            native_latency_diagnostics
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
