use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::{Deserialize, Serialize};
use std::{
    io::{BufRead, BufReader, Write},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::{Arc, Mutex},
};
use tauri::Manager;

const MAX_BODY_BYTES: usize = 2_800_000;
const WIRE_SCHEMA: &str = "pps-planner-worker-stdio.v1";

#[derive(Deserialize)]
struct PlannerRequest {
    method: String,
    path: String,
    #[serde(default)]
    body: String,
}

#[derive(Deserialize, Serialize)]
struct PlannerReply {
    schema: String,
    id: Option<u64>,
    status: u16,
    #[serde(default)]
    content_type: String,
    #[serde(default)]
    content_disposition: String,
    #[serde(default)]
    body_base64: String,
    #[serde(default)]
    error: String,
}

struct Worker {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

impl Worker {
    fn spawn(app: &tauri::AppHandle) -> Result<Self, String> {
        let data_root = match std::env::var_os("PPS_TOOLKIT_DATA_ROOT") {
            Some(path) => std::path::PathBuf::from(path),
            None => app
                .path()
                .app_local_data_dir()
                .map_err(|_| "Planner data directory is unavailable.")?,
        };
        std::fs::create_dir_all(&data_root)
            .map_err(|_| "Planner data directory could not be created.")?;
        #[cfg(debug_assertions)]
        let mut command = {
            let source = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../../packages/pps-runtime/src");
            let mut command = Command::new("python");
            command
                .args(["-m", "peripersonal_space_toolkit.planner_worker"])
                .env("PYTHONPATH", source);
            command
        };

        #[cfg(not(debug_assertions))]
        let mut command = {
            let executable = app
                .path()
                .resolve(
                    "planner-worker/PPSPlannerWorker.exe",
                    tauri::path::BaseDirectory::Resource,
                )
                .map_err(|_| "Bundled Planner worker path is unavailable.")?;
            Command::new(executable)
        };

        command.env("PPS_TOOLKIT_DATA_ROOT", data_root);
        #[cfg(not(debug_assertions))]
        if let Ok(shared) = app
            .path()
            .resolve("shared", tauri::path::BaseDirectory::Resource)
        {
            if shared.join("study_templates").is_dir() {
                command.env("PPS_TOOLKIT_ROOT", shared);
            }
        }

        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x0800_0000);
        }
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|_| "Planner worker could not start.")?;
        let stdin = child
            .stdin
            .take()
            .ok_or("Planner worker input is unavailable.")?;
        let stdout = child
            .stdout
            .take()
            .ok_or("Planner worker output is unavailable.")?;
        Ok(Self {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            next_id: 0,
        })
    }

    fn request(&mut self, request: PlannerRequest) -> Result<PlannerReply, String> {
        validate_request(&request)?;
        self.next_id = self
            .next_id
            .checked_add(1)
            .ok_or("Planner request count exceeded.")?;
        let frame = serde_json::json!({
            "schema": WIRE_SCHEMA,
            "id": self.next_id,
            "method": request.method,
            "path": request.path,
            "body_base64": STANDARD.encode(request.body.as_bytes()),
        });
        serde_json::to_writer(&mut self.stdin, &frame)
            .map_err(|_| "Planner request could not be encoded.")?;
        self.stdin
            .write_all(b"\n")
            .and_then(|_| self.stdin.flush())
            .map_err(|_| "Planner worker is unavailable.")?;
        let mut line = String::new();
        self.stdout
            .read_line(&mut line)
            .map_err(|_| "Planner worker did not respond.")?;
        let reply: PlannerReply =
            serde_json::from_str(&line).map_err(|_| "Planner worker response is invalid.")?;
        if reply.schema != WIRE_SCHEMA || reply.id != Some(self.next_id) {
            return Err("Planner worker response order is invalid.".into());
        }
        Ok(reply)
    }
}

impl Drop for Worker {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn validate_request(request: &PlannerRequest) -> Result<(), String> {
    if !matches!(request.method.as_str(), "GET" | "POST" | "DELETE")
        || !request.path.starts_with("/api/")
        || request.path.len() > 8_192
        || request.path.contains('#')
        || request.path.contains('\\')
        || request
            .path
            .split('/')
            .any(|segment| segment == "." || segment == "..")
        || request.body.len() > MAX_BODY_BYTES
    {
        return Err("Planner request is outside the local API boundary.".into());
    }
    Ok(())
}

#[tauri::command]
async fn planner_request(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, Arc<Mutex<Worker>>>,
    request: PlannerRequest,
) -> Result<PlannerReply, String> {
    if window.label() != "main" {
        return Err("Planner command is unavailable to this window.".into());
    }
    let worker = Arc::clone(state.inner());
    tauri::async_runtime::spawn_blocking(move || {
        worker
            .lock()
            .map_err(|_| "Planner worker lock is unavailable.".to_string())?
            .request(request)
    })
    .await
    .map_err(|_| "Planner worker task failed.".to_string())?
}

pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let worker = Worker::spawn(app.handle()).map_err(std::io::Error::other)?;
            app.manage(Arc::new(Mutex::new(worker)));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![planner_request])
        .run(tauri::generate_context!())
        .expect("error while running PPS Experiment Planner");
}

#[cfg(test)]
mod tests {
    use super::{validate_request, PlannerRequest};

    #[test]
    fn planner_boundary_rejects_unrelated_paths() {
        let mut request = PlannerRequest {
            method: "GET".into(),
            path: "/api/health".into(),
            body: String::new(),
        };
        assert!(validate_request(&request).is_ok());
        request.path = "/api/../dashboard/index.html".into();
        assert!(validate_request(&request).is_err());
        request.path = "https://elsewhere.example/api/health".into();
        assert!(validate_request(&request).is_err());
    }
}
