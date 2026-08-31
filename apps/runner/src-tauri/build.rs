fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "runner_snapshot",
            "runner_dispatch",
            "remote_status",
            "configure_remote",
            "rotate_pairing",
            "select_prepared_session",
            "inspect_prepared_execution",
            "prepare_first_audio_block",
            "remote_session_claim",
            "remote_session_renew",
            "remote_session_dispatch",
            "remote_session_revoke",
            "native_latency_diagnostics",
        ]),
    ))
    .expect("failed to build the PPS Runner command manifest")
}
