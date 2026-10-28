mod assembly_host;
mod external_links;
mod generation;
mod jobs;
#[path = "../../../native_file_dialogs.rs"]
mod native_file_dialogs;
mod service;
use pps_designer_core::design::GenerationOptIn;
use serde_json::Value;
use service::{DesignerService, Shared};
#[cfg(debug_assertions)]
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tauri::Manager;
use tauri_plugin_dialog::DialogExt;

fn main_window(window: &tauri::WebviewWindow) -> Result<(), String> {
    if window.label() == "main" {
        Ok(())
    } else {
        Err("caller_not_allowed".into())
    }
}
fn lock(shared: &Shared) -> Result<std::sync::MutexGuard<'_, DesignerService>, String> {
    shared.lock().map_err(|_| "host_unavailable".into())
}

#[tauri::command]
async fn designer_open_external(window: tauri::WebviewWindow, url: String) -> Result<bool, String> {
    main_window(&window)?;
    let url = external_links::web_url(&url)?;
    tauri::async_runtime::spawn_blocking(move || {
        tauri_plugin_opener::open_url(url, None::<&str>)
            .map(|_| true)
            .map_err(|_| "external_browser_unavailable".to_owned())
    })
    .await
    .map_err(|_| "external_browser_worker_failed")?
}

#[tauri::command]
async fn designer_snapshot(
    window: tauri::WebviewWindow,
    owner: tauri::State<'_, Shared>,
) -> Result<Value, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || Ok(lock(&owner)?.snapshot()))
        .await
        .map_err(|_| "snapshot_worker_failed")?
}
#[tauri::command]
async fn designer_invalidate(
    window: tauri::WebviewWindow,
    owner: tauri::State<'_, Shared>,
    expected_revision: u64,
) -> Result<u64, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || lock(&owner)?.invalidate(expected_revision))
        .await
        .map_err(|_| "invalidate_worker_failed")?
}
#[tauri::command]
async fn designer_save(
    window: tauri::WebviewWindow,
    owner: tauri::State<'_, Shared>,
    expected_revision: u64,
    snapshot: Value,
) -> Result<u64, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || lock(&owner)?.save(expected_revision, snapshot))
        .await
        .map_err(|_| "save_worker_failed")?
}
#[tauri::command]
async fn designer_generate(
    window: tauri::WebviewWindow,
    owner: tauri::State<'_, Shared>,
    expected_revision: u64,
    snapshot: Value,
    payload: Value,
    opt_in: GenerationOptIn,
) -> Result<jobs::JobSnapshot, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (job, work) = lock(&owner)?.begin(expected_revision, snapshot, payload, opt_in)?;
        tauri::async_runtime::spawn_blocking(move || service::execute(owner, work));
        Ok(job)
    })
    .await
    .map_err(|_| "generation_worker_failed")?
}

#[tauri::command]
async fn designer_baseline(
    window: tauri::WebviewWindow,
    owner: tauri::State<'_, Shared>,
    expected_revision: u64,
    snapshot: Value,
    source: String,
    opt_in: pps_designer_core::baseline::BaselineGenerationOptIn,
) -> Result<jobs::JobSnapshot, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (job, work) =
            lock(&owner)?.begin_baseline(expected_revision, snapshot, &source, &opt_in)?;
        tauri::async_runtime::spawn_blocking(move || service::execute(owner, work));
        Ok(job)
    })
    .await
    .map_err(|_| "baseline_worker_failed")?
}

#[tauri::command]
async fn designer_review(
    window: tauri::WebviewWindow,
    owner: tauri::State<'_, Shared>,
    expected_revision: u64,
    snapshot: Value,
    variants: Value,
) -> Result<jobs::JobSnapshot, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (job, work) = lock(&owner)?.begin_review(expected_revision, snapshot, variants)?;
        tauri::async_runtime::spawn_blocking(move || assembly_host::review(owner, work));
        Ok(job)
    })
    .await
    .map_err(|_| "review_worker_failed")?
}

#[tauri::command]
async fn designer_accept_review(
    window: tauri::WebviewWindow,
    owner: tauri::State<'_, Shared>,
    expected_revision: u64,
    hashes: Value,
) -> Result<Value, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        lock(&owner)?.accept_review(expected_revision, &hashes)
    })
    .await
    .map_err(|_| "acceptance_worker_failed")?
}

#[tauri::command]
async fn designer_prepare(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    owner: tauri::State<'_, Shared>,
    expected_revision: u64,
    participant: usize,
    identity: String,
) -> Result<Option<jobs::JobSnapshot>, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let Some(folder) = app
            .dialog()
            .file()
            .set_title("Choose a folder for immutable participant files")
            .blocking_pick_folder()
        else {
            return Ok(None);
        };
        let parent =
            std::fs::canonicalize(folder.into_path().map_err(|_| "local_folder_required")?)
                .map_err(|_| "local_folder_required")?;
        // The identifier is checked by begin_prepare before this native-generated child is created.
        let sequence = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map_err(|_| "clock_unavailable")?
            .as_nanos();
        let directory = parent.join(format!("pps-participant-{}-{sequence}", std::process::id()));
        let (job, work) =
            lock(&owner)?.begin_prepare(expected_revision, participant, identity, directory)?;
        tauri::async_runtime::spawn_blocking(move || assembly_host::prepare(owner, work));
        Ok(Some(job))
    })
    .await
    .map_err(|_| "preparation_worker_failed")?
}

#[tauri::command]
async fn designer_open_prepared(
    window: tauri::WebviewWindow,
    owner: tauri::State<'_, Shared>,
) -> Result<(), String> {
    main_window(&window)?;
    let path = lock(owner.inner())?
        .prepared_directory
        .clone()
        .ok_or("prepared_output_required")?;
    #[cfg(windows)]
    {
        std::process::Command::new("explorer.exe")
            .arg(path)
            .spawn()
            .map_err(|_| "folder_open_failed")?;
        Ok(())
    }
    #[cfg(not(windows))]
    {
        let _ = path;
        Err("windows_required".into())
    }
}
#[tauri::command]
async fn designer_job(
    window: tauri::WebviewWindow,
    owner: tauri::State<'_, Shared>,
    job_id: String,
) -> Result<jobs::JobSnapshot, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        lock(&owner)?
            .jobs
            .snapshot(&job_id)
            .ok_or_else(|| "job_not_found".into())
    })
    .await
    .map_err(|_| "job_worker_failed")?
}
#[tauri::command]
async fn designer_cancel(
    window: tauri::WebviewWindow,
    owner: tauri::State<'_, Shared>,
) -> Result<(), String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        lock(&owner)?.jobs.cancel();
        Ok(())
    })
    .await
    .map_err(|_| "cancel_worker_failed")?
}
#[tauri::command]
async fn designer_pick_audio(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    owner: tauri::State<'_, Shared>,
) -> Result<Option<Value>, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app
            .dialog()
            .file()
            .add_filter("WAV audio", &["wav"])
            .blocking_pick_file()
        else {
            return Ok(None);
        };
        let path = file.into_path().map_err(|_| "local_file_required")?;
        lock(&owner)?.register_picked_audio(&path).map(Some)
    })
    .await
    .map_err(|_| "audio_picker_failed")?
}
#[tauri::command]
async fn designer_import_profile(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    owner: tauri::State<'_, Shared>,
    expected_revision: u64,
) -> Result<Option<Value>, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app
            .dialog()
            .file()
            .add_filter("Portable PPS profile", &["pps-profile"])
            .blocking_pick_file()
        else {
            return Ok(None);
        };
        let path = file.into_path().map_err(|_| "local_file_required")?;
        lock(&owner)?
            .import_bundle(expected_revision, &path)
            .map(Some)
    })
    .await
    .map_err(|_| "profile_import_failed")?
}

#[tauri::command]
async fn designer_export_profile(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    request: tauri::ipc::Request<'_>,
) -> Result<bool, String> {
    main_window(&window)?;
    let tauri::ipc::InvokeBody::Raw(bytes) = request.body() else {
        return Err("binary_profile_required".into());
    };
    if bytes.len() > 270 * 1024 * 1024 || !bytes.starts_with(b"PK\x03\x04") {
        return Err("invalid_profile_export".into());
    }
    let bytes = bytes.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let Some(file) = app
            .dialog()
            .file()
            .add_filter("Portable PPS profile", &["pps-profile"])
            .set_file_name("custom-profile.pps-profile")
            .blocking_save_file()
        else {
            return Ok(false);
        };
        let path = file.into_path().map_err(|_| "local_file_required")?;
        write_selected_file(&path, &bytes, "pps-profile.partial")?;
        Ok(true)
    })
    .await
    .map_err(|_| "export_worker_failed")?
}

#[tauri::command]
async fn designer_export_audio(
    window: tauri::WebviewWindow,
    app: tauri::AppHandle,
    owner: tauri::State<'_, Shared>,
    reference: String,
) -> Result<bool, String> {
    main_window(&window)?;
    let owner = owner.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (bytes, mime) = lock(&owner)?.resource(&reference)?;
        if mime != "audio/wav" {
            return Err("audio_receipt_required".into());
        }
        let Some(file) = app
            .dialog()
            .file()
            .add_filter("WAV audio", &["wav"])
            .set_file_name("stimulus.wav")
            .blocking_save_file()
        else {
            return Ok(false);
        };
        let path = file.into_path().map_err(|_| "local_file_required")?;
        write_selected_file(&path, &bytes, "wav.partial")?;
        Ok(true)
    })
    .await
    .map_err(|_| "audio_export_worker_failed")?
}

// Called only with the exact destination returned by a native save dialog.
fn write_selected_file(
    path: &std::path::Path,
    bytes: &[u8],
    staging_extension: &str,
) -> Result<(), String> {
    use std::io::Write;
    let temporary = path.with_extension(staging_extension);
    let mut output = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)
        .map_err(|_| "export_staging_unavailable")?;
    let result = output.write_all(bytes).and_then(|_| output.sync_all());
    drop(output);
    if result.is_err() || std::fs::rename(&temporary, path).is_err() {
        let _ = std::fs::remove_file(&temporary);
        return Err("export_commit_failed".into());
    }
    Ok(())
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(native_file_dialogs::init())
        .setup(|app| {
            #[cfg(debug_assertions)]
            let resources =
                PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../packages/pps-resources");
            #[cfg(not(debug_assertions))]
            let resources = app.path().resource_dir()?.join("resources");
            let bundled_renderer = app
                .path()
                .resource_dir()?
                .join("renderer/pps-3dti-renderer.exe");
            #[cfg(debug_assertions)]
            let renderer = std::env::var_os("PPS_DESIGNER_RENDERER")
                .map(PathBuf::from)
                .unwrap_or(bundled_renderer);
            #[cfg(not(debug_assertions))]
            let renderer = bundled_renderer;
            let default_data = app.path().app_local_data_dir()?;
            #[cfg(debug_assertions)]
            let data = std::env::var_os("PPS_DESIGNER_TEST_DATA")
                .map(PathBuf::from)
                .unwrap_or(default_data);
            #[cfg(not(debug_assertions))]
            let data = default_data;
            let service =
                DesignerService::open(data, resources, renderer).map_err(std::io::Error::other)?;
            app.manage(Arc::new(Mutex::new(service)) as Shared);
            let hidden_test =
                cfg!(debug_assertions) && std::env::var_os("PPS_DESIGNER_TEST_DATA").is_some();
            if !hidden_test {
                if let Some(window) = app.get_webview_window("main") {
                    window.show()?;
                }
            }
            Ok(())
        })
        .register_asynchronous_uri_scheme_protocol("pps-resource", |context, request, responder| {
            let owner = context.app_handle().state::<Shared>().inner().clone();
            let key =
                percent_encoding::percent_decode_str(request.uri().path().trim_start_matches('/'))
                    .decode_utf8()
                    .map(|s| s.into_owned());
            tauri::async_runtime::spawn_blocking(move || {
                let result = key
                    .map_err(|_| "invalid_resource".to_owned())
                    .and_then(|key| lock(&owner)?.resource(&key));
                let (status, bytes, mime) = match result {
                    Ok((bytes, mime)) => (200, bytes, mime),
                    Err(_) => (404, Vec::new(), "text/plain"),
                };
                let response = tauri::http::Response::builder()
                    .status(status)
                    .header("Content-Type", mime)
                    .header("Access-Control-Allow-Origin", "http://tauri.localhost")
                    .header("Cache-Control", "no-store")
                    .body(bytes)
                    .expect("fixed response headers");
                responder.respond(response);
            });
        })
        .invoke_handler(tauri::generate_handler![
            designer_open_external,
            designer_snapshot,
            designer_invalidate,
            designer_save,
            designer_generate,
            designer_baseline,
            designer_review,
            designer_accept_review,
            designer_prepare,
            designer_open_prepared,
            designer_job,
            designer_cancel,
            designer_pick_audio,
            designer_import_profile,
            designer_export_profile,
            designer_export_audio
        ])
        .build(tauri::generate_context!())
        .expect("error while building PPS Experiment Designer");
    app.run(|handle, event| {
        if matches!(event, tauri::RunEvent::ExitRequested { .. }) {
            if let Some(owner) = handle.try_state::<Shared>() {
                if let Ok(mut service) = owner.lock() {
                    service.jobs.cancel();
                }
            }
        }
    });
}
