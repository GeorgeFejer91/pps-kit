//! Native-only renderer process. All paths are selected by the host, never IPC.
use pps_designer_core::{self as core, design::IngredientGenerationPlan};
use serde_json::Value;
use std::{
    fs,
    io::Cursor,
    path::Path,
    process::{Command, Stdio},
    sync::atomic::{AtomicBool, Ordering},
    time::{Duration, Instant},
};

pub fn render(
    plan: &IngredientGenerationPlan,
    directory: &Path,
    executable: &Path,
    hrtf: &Path,
    imported: Option<&[u8]>,
    cancelled: &AtomicBool,
) -> Result<(Vec<u8>, core::GeneratedStimulus, Value), String> {
    let prepared = match imported {
        Some(bytes) => core::prepare_imported_wav(&plan.request, bytes, cancelled),
        None => core::prepare(&plan.request, cancelled),
    }
    .map_err(|error| error.to_string())?;
    let options = core::SpatializerOptions {
        hrtf_path: hrtf.to_string_lossy().into_owned(),
        hrtf_format: core::HrtfFormat::Sofa,
        head_radius_m: plan.renderer.head_radius_m,
        distance_attenuation: plan.renderer.distance_attenuation,
        near_field: plan.renderer.near_field,
        propagation_delay: plan.renderer.propagation_delay,
    };
    let dry = fs::File::create(directory.join("dry.f32")).map_err(|_| "staging_write_failed")?;
    let config = core::write_spatializer_input(&prepared, dry, &options, cancelled)
        .map_err(|e| e.to_string())?;
    fs::write(
        directory.join("config.json"),
        serde_json::to_vec(&config).map_err(|_| "config_serialization_failed")?,
    )
    .map_err(|_| "staging_write_failed")?;
    let mut command = Command::new(executable);
    command
        .arg("--config")
        .arg(directory.join("config.json"))
        .arg("--output-dir")
        .arg(directory)
        .arg("--manifest")
        .arg(directory.join("manifest.json"))
        .arg("--qc")
        .arg(directory.join("qc.csv"))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    run_bounded(command, cancelled, Duration::from_secs(180))?;
    let stereo = core::read_stereo_wav(
        fs::File::open(directory.join("stereo.wav")).map_err(|_| "renderer_output_missing")?,
        plan.request.sample_rate_hz,
        prepared.dry_pcm().len(),
        cancelled,
    )
    .map_err(|e| e.to_string())?;
    let stimulus =
        core::compose_spatial_output(prepared, stereo, cancelled).map_err(|e| e.to_string())?;
    let mut wav = Cursor::new(Vec::new());
    core::write_ingredient_wav(&mut wav, &stimulus, cancelled).map_err(|e| e.to_string())?;
    let report_path = directory.join("manifest.json");
    if fs::metadata(&report_path)
        .map_err(|_| "renderer_report_missing")?
        .len()
        > 1024 * 1024
    {
        return Err("renderer_report_limit".into());
    }
    let report =
        serde_json::from_slice(&fs::read(report_path).map_err(|_| "renderer_report_missing")?)
            .map_err(|_| "invalid_renderer_report")?;
    Ok((wav.into_inner(), stimulus, report))
}

fn run_bounded(
    mut command: Command,
    cancelled: &AtomicBool,
    timeout: Duration,
) -> Result<(), String> {
    if cancelled.load(Ordering::Acquire) {
        return Err("generation_cancelled".into());
    }
    let mut child = command.spawn().map_err(|_| "renderer_unavailable")?;
    #[cfg(windows)]
    let _lifetime = match ChildLifetime::attach(&child) {
        Ok(lifetime) => lifetime,
        Err(error) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error);
        }
    };
    let deadline = Instant::now() + timeout;
    let result = loop {
        if cancelled.load(Ordering::Acquire) {
            break Err("generation_cancelled".into());
        }
        if Instant::now() >= deadline {
            break Err("renderer_timeout".into());
        }
        match child.try_wait() {
            Ok(Some(status)) => {
                break if status.success() {
                    Ok(())
                } else {
                    Err("renderer_failed".into())
                }
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(20)),
            Err(_) => break Err("renderer_wait_failed".into()),
        }
    };
    if result.is_err() {
        let _ = child.kill();
    }
    let _ = child.wait();
    result
}

/// Closing the process handle on crash/exit also terminates the owned renderer.
#[cfg(windows)]
struct ChildLifetime(windows_sys::Win32::Foundation::HANDLE);
#[cfg(windows)]
impl ChildLifetime {
    fn attach(child: &std::process::Child) -> Result<Self, String> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::System::JobObjects::*;
        // SAFETY: initialized POD limits, owned job handle, live child process handle.
        unsafe {
            let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if handle.is_null() {
                return Err("renderer_lifetime_unavailable".into());
            }
            let owner = Self(handle);
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const _,
                std::mem::size_of_val(&limits) as u32,
            ) == 0
                || AssignProcessToJobObject(handle, child.as_raw_handle()) == 0
            {
                return Err("renderer_lifetime_unavailable".into());
            }
            Ok(owner)
        }
    }
}
#[cfg(windows)]
impl Drop for ChildLifetime {
    fn drop(&mut self) {
        // SAFETY: this object exclusively owns the successful CreateJobObjectW handle.
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cancellation_does_not_spawn_a_child() {
        assert_eq!(
            run_bounded(
                Command::new("nonexistent-renderer"),
                &AtomicBool::new(true),
                Duration::from_secs(1)
            )
            .unwrap_err(),
            "generation_cancelled"
        );
    }
    #[test]
    #[cfg(windows)]
    fn running_child_is_cancelled_and_reaped() {
        let flag = std::sync::Arc::new(AtomicBool::new(false));
        let cancel = flag.clone();
        let trigger = std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(100));
            cancel.store(true, Ordering::Release);
        });
        let mut command = Command::new("powershell.exe");
        command.args([
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Start-Sleep -Seconds 10",
        ]);
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
        let started = Instant::now();
        assert_eq!(
            run_bounded(command, &flag, Duration::from_secs(2)).unwrap_err(),
            "generation_cancelled"
        );
        trigger.join().unwrap();
        assert!(started.elapsed() < Duration::from_secs(3));
    }
}
