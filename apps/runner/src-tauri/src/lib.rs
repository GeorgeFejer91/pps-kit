mod event_journal;
mod execution_owner;
mod latency_diagnostics;
mod native_output;
mod native_playback;
mod prepared_audio;
mod prepared_execution;
mod remote;
mod runtime;
mod trial_capture;

use std::{
    path::PathBuf,
    str::FromStr,
    time::{SystemTime, UNIX_EPOCH},
};

use latency_diagnostics::{LatencyRoute, LatencyStage, NativeLatencySummary, TraceOutcome};
use native_output::{
    NativeExecutionActivationRequest, NativeOutputCommandError, NativeOutputInventory,
    NativeOutputReleaseRequest, NativeOutputReservation, NativeOutputReserveRequest,
    NativeOutputStatus,
};
use pps_contracts::{Action, Applied, AppliedStatus, RunnerSnapshot};
use pps_experiment_media::package::prepare_standard_profile_package;
use pps_session_package::experiment_profile::verify_experiment_profile_inventory;
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
use tauri::{Emitter, EventTarget, Manager};
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

async fn cancelled_prepared_selection(
    runtime: &AppRuntime,
) -> Result<PreparedSessionSelection, PreparedSessionCommandError> {
    Ok(PreparedSessionSelection {
        cancelled: true,
        summary: None,
        snapshot: runtime
            .snapshot_async()
            .await
            .map_err(|_| PreparedSessionCommandError::runtime())?,
    })
}

fn profile_preparation_error(code: &str) -> PreparedSessionCommandError {
    let message = match code {
        "profile_block_transform_unsupported" => {
            "This profile requires a media transform that the native Runner cannot prepare yet."
        }
        "profile_block_resource_limit" | "profile_package_limit" => {
            "This profile exceeds the native package preparation limit."
        }
        "profile_block_storage_unavailable" => {
            "The selected folder's available storage could not be confirmed. Choose a local folder and retry."
        }
        "profile_block_storage_low" => {
            "The selected folder does not have enough free space to prepare this block. Free space and retry."
        }
        "profile_ingredient_changed"
        | "profile_block_media_changed"
        | "profile_plan_source_changed" => {
            "A Planner ingredient changed. Export a fresh JSON profile before preparing it."
        }
        "profile_package_output_exists" => {
            "A package with this session name already exists in the selected folder. Try again."
        }
        "profile_package_output_failed" => {
            "The package could not be written. Check the selected folder and available storage."
        }
        _ => "The selected Planner JSON profile could not be prepared by the native Runner.",
    };
    PreparedSessionCommandError::new(code, message)
}

#[tauri::command]
async fn runner_snapshot(state: tauri::State<'_, AppRuntime>) -> Result<RunnerSnapshot, String> {
    state.snapshot_async().await
}

#[tauri::command]
async fn runner_record_response(
    request: trial_capture::NativeResponseRequest,
    state: tauri::State<'_, AppRuntime>,
) -> Result<String, String> {
    state
        .record_native_response(request)
        .await
        .map(|id| id.to_string())
        .map_err(str::to_owned)
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
        return cancelled_prepared_selection(&runtime).await;
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
async fn prepare_experiment_profile(
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
                "A native package selection or preparation is already in progress.",
            )
        })?;
    let initial = runtime
        .snapshot_async()
        .await
        .map_err(|_| PreparedSessionCommandError::runtime())?;
    if !initial.setup.submitted || initial.setup.participant_code.is_empty() {
        return Err(PreparedSessionCommandError::new(
            "participant_setup_required",
            "Submit participant setup before preparing a Planner JSON profile.",
        ));
    }
    let participant_id = initial.setup.participant_code;

    // Both paths come from native dialogs. The WebView sends no path or
    // participant identity and receives only the existing path-free summary.
    let (sender, receiver) = tokio::sync::oneshot::channel();
    app.dialog()
        .file()
        .add_filter("PPS Planner JSON profile", &["json"])
        .pick_file(move |selection| {
            let _ = sender.send(selection);
        });
    let selection = receiver.await.map_err(|_| {
        PreparedSessionCommandError::new(
            "dialog_unavailable",
            "The native profile chooser could not complete.",
        )
    })?;
    let Some(selection) = selection else {
        return cancelled_prepared_selection(&runtime).await;
    };
    let profile_path = selection.into_path().map_err(|_| {
        PreparedSessionCommandError::new(
            "invalid_local_path",
            "The selected profile is not a local JSON file.",
        )
    })?;
    let profile = tauri::async_runtime::spawn_blocking(move || {
        verify_experiment_profile_inventory(&profile_path)
    })
    .await
    .map_err(|_| PreparedSessionCommandError::runtime())?
    .map_err(|error| profile_preparation_error(error.code()))?;

    let (sender, receiver) = tokio::sync::oneshot::channel();
    app.dialog().file().pick_folder(move |selection| {
        let _ = sender.send(selection);
    });
    let selection = receiver.await.map_err(|_| {
        PreparedSessionCommandError::new(
            "dialog_unavailable",
            "The native output-folder chooser could not complete.",
        )
    })?;
    let Some(selection) = selection else {
        return cancelled_prepared_selection(&runtime).await;
    };
    let output_parent = selection.into_path().map_err(|_| {
        PreparedSessionCommandError::new(
            "invalid_local_path",
            "The selected output folder is not a local directory.",
        )
    })?;
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| PreparedSessionCommandError::runtime())?
        .as_nanos();
    let output_dir = output_parent.join(format!("{participant_id}_{timestamp}"));
    let verified = tauri::async_runtime::spawn_blocking(move || {
        prepare_standard_profile_package(&profile, &participant_id, &output_dir, initial.revision)
    })
    .await
    .map_err(|_| PreparedSessionCommandError::runtime())?
    .map_err(|error| profile_preparation_error(error.code()))?;
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
async fn prepare_current_audio_block(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<PreparedAudioSummary, PreparedSessionCommandError> {
    require_main_window(&window)
        .map_err(|error| PreparedSessionCommandError::new(&error.code, &error.message))?;
    let runtime = state.inner().clone();
    let preparation = runtime
        .begin_prepared_audio_preparation_async()
        .await
        .map_err(prepared_audio_runtime_error)?;
    let (_preparation_guard, summary) = match preparation {
        PreparedAudioPreparation::Cached { _guard, summary } => (_guard, summary),
        PreparedAudioPreparation::Decode { _guard, source } => {
            // Hash/decode outside the actor. Its completion must still match
            // every package/run/block/schedule/preparation/receipt fence.
            let (_guard, candidate) = tauri::async_runtime::spawn_blocking(move || {
                (
                    _guard,
                    prepare_verified_audio(source).map_err(prepared_audio_preparation_error),
                )
            })
            .await
            .map_err(|_| PreparedSessionCommandError::runtime())?;
            let summary = runtime
                .cache_prepared_audio_async(candidate?)
                .await
                .map_err(prepared_audio_runtime_error)?;
            (_guard, summary)
        }
    };
    runtime
        .ensure_execution_journal()
        .await
        .map_err(prepared_audio_runtime_error)?;
    Ok(summary)
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
        | "prepared_audio_block_replaced"
        | "prepared_audio_preparation_replaced" => PreparedSessionCommandError::new(
            "prepared_audio_stale",
            "The selected package changed during audio loading; load it again.",
        ),
        "prepared_audio_block_missing" => PreparedSessionCommandError::new(
            reason,
            "The verified package does not contain the current audio block.",
        ),
        "prepared_audio_block_out_of_order" => PreparedSessionCommandError::new(
            reason,
            "Only the next verified block can be prepared; reselect the package to start a new run.",
        ),
        "prepared_audio_sample_rate_invalid" => PreparedSessionCommandError::new(
            reason,
            "The prepared schedule does not provide a supported audio sample rate.",
        ),
        "prepared_audio_resource_limit" => PreparedSessionCommandError::new(
            reason,
            "The prepared audio exceeds the native preload resource limit.",
        ),
        "native_journal_unavailable" => PreparedSessionCommandError::new(
            reason,
            "The native event journal could not be prepared; audio remains disabled. Check available storage and the selected session folder.",
        ),
        "native_journal_cleanup_pending" => PreparedSessionCommandError::new(
            reason,
            "The previous package's event journal is still closing; wait before preloading again.",
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
        "prepared_execution_active_run" => PreparedSessionCommandError::new(
            reason,
            "The current run has begun; reselect the package before recompiling its schedules.",
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

fn require_native_output_main(
    window: &tauri::WebviewWindow,
) -> Result<(), NativeOutputCommandError> {
    require_main_window(window)
        .map_err(|error| NativeOutputCommandError::new(&error.code, &error.message))
}

#[tauri::command]
async fn native_output_status(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<NativeOutputStatus, NativeOutputCommandError> {
    require_native_output_main(&window)?;
    state.native_output_status().await
}

#[tauri::command]
async fn native_output_enumerate(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<NativeOutputInventory, NativeOutputCommandError> {
    require_native_output_main(&window)?;
    let receive = state.start_native_output_enumerate()?;
    match tokio::time::timeout(AppRuntime::native_output_client_deadline(), receive).await {
        Ok(Ok(result)) => result,
        Ok(Err(_)) => Err(NativeOutputCommandError::runtime()),
        Err(_) => Err(NativeOutputCommandError::timeout()),
    }
}

#[tauri::command]
async fn activate_native_execution(
    request: NativeExecutionActivationRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<RunnerSnapshot, NativeOutputCommandError> {
    require_native_output_main(&window)?;
    state.activate_native_execution(request).await
}

#[tauri::command]
async fn native_output_reserve_silence(
    request: NativeOutputReserveRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<NativeOutputReservation, NativeOutputCommandError> {
    require_native_output_main(&window)?;
    let receive = state.start_native_output_reserve(request)?;
    match tokio::time::timeout(AppRuntime::native_output_client_deadline(), receive).await {
        Ok(Ok(result)) => result,
        Ok(Err(_)) => Err(NativeOutputCommandError::runtime()),
        Err(_) => Err(NativeOutputCommandError::timeout()),
    }
}

#[tauri::command]
async fn native_output_release(
    request: NativeOutputReleaseRequest,
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<NativeOutputStatus, NativeOutputCommandError> {
    require_native_output_main(&window)?;
    state.release_native_output(request).await
}

#[tauri::command]
async fn native_output_disable(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, AppRuntime>,
) -> Result<NativeOutputStatus, NativeOutputCommandError> {
    require_native_output_main(&window)?;
    state.disable_native_output().await
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
        .setup(|app| {
            // Observe the existing authority; never run or time an experiment
            // in a WebView. Private local snapshots go only to the main window.
            let mut updates = app.state::<AppRuntime>().inner().0.state_tx.subscribe();
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                loop {
                    match updates.recv().await {
                        Ok(snapshot) => {
                            if handle.get_webview_window("main").is_none()
                                || handle
                                    .emit_to(
                                        EventTarget::webview_window("main"),
                                        "runner-snapshot",
                                        snapshot,
                                    )
                                    .is_err()
                            {
                                break;
                            }
                        }
                        // Polling reconciles a lagged UI with current state.
                        Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                        Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
                    }
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            runner_snapshot,
            runner_record_response,
            runner_dispatch,
            remote_status,
            configure_remote,
            rotate_pairing,
            select_prepared_session,
            prepare_experiment_profile,
            inspect_prepared_execution,
            prepare_current_audio_block,
            remote_session_claim,
            remote_session_renew,
            remote_session_dispatch,
            remote_session_revoke,
            native_latency_diagnostics,
            native_output_status,
            activate_native_execution,
            native_output_enumerate,
            native_output_reserve_silence,
            native_output_release,
            native_output_disable
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
