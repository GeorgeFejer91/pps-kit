fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "runner_snapshot",
            "runner_record_response",
            "runner_dispatch",
            "remote_status",
            "configure_remote",
            "rotate_pairing",
            "select_prepared_session",
            "prepare_experiment_profile",
            "inspect_prepared_execution",
            "prepare_current_audio_block",
            "remote_session_claim",
            "remote_session_renew",
            "remote_session_dispatch",
            "remote_session_revoke",
            "native_latency_diagnostics",
            "native_output_status",
            "activate_native_execution",
            "native_output_enumerate",
            "native_output_reserve_silence",
            "native_output_release",
            "native_output_disable",
        ]),
    ))
    .expect("failed to build the PPS Runner command manifest")
}
