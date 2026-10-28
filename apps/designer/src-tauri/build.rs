fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "designer_open_external",
            "designer_snapshot",
            "designer_invalidate",
            "designer_save",
            "designer_generate",
            "designer_baseline",
            "designer_review",
            "designer_accept_review",
            "designer_prepare",
            "designer_open_prepared",
            "designer_job",
            "designer_cancel",
            "designer_pick_audio",
            "designer_import_profile",
            "designer_export_profile",
            "designer_export_audio",
        ]),
    ))
    .expect("failed to build the Designer command manifest");
}
