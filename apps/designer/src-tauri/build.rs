fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["planner_request"])),
    )
    .expect("failed to build the PPS Planner command manifest");
}
