# Full Windows installer plan

This is the execution contract for the target two-app Tauri package. It is a
plan, not a claim that the installer or Designer Tauri shell exists today.

## Inputs and ownership

| Input | Product owner | Installer treatment |
|---|---|---|
| Designer Rust executable and bundled HTML | `apps/designer/` | One local application and shortcut; no remote UI dependency. |
| Runner Rust executable and bundled HTML | `apps/runner/` | One local application and shortcut; no remote UI dependency. |
| Shared templates, assets, configs, sample data, reviewed third-party material, docs, licenses | `packages/pps-resources/`, `third_party/`, `docs/` and root licenses | Install once under a versioned Shared layout; keep logical `assets/...` and `study_templates/...` resolution. |
| Component definitions | `distributions/manifests/` | Extend or version the manifests for the Tauri layout; one file owner and an exact Full composition. |
| Build and inventory logic | `For-AI/engineering/build/`, `For-AI/engineering/release/` | Reuse and adapt existing scripts instead of creating a second manifest or audit implementation. |

## Build sequence

1. Select a verified source revision. Complete both local Tauri shells, their
   typed IPC/capabilities, offline resource paths, and one compatible Shared
   version. Preserve the existing profile and result formats.
2. Build both canonical frontends and Tauri production bundles from that same
   revision. Confirm each installed WebView loads its bundled HTML without a
   network connection or Pages route. Do not include development URLs,
   localhost servers, or desktop privileges in public Pages assets.
3. Update the component manifests for the actual Tauri file layout. Assemble
   Designer, Runner, and one Shared tree; audit ownership, exclusions, runtime
   dependencies, licenses, hashes, and installed paths. Keep private files,
   generated sessions, and all of `For-AI/` out of the payload.
4. Build one Full Windows installer over that audited composition. It must
   provide two separate shortcuts, support uninstall/repair without corrupting
   Shared ownership, and reject an incompatible pre-existing Shared component.
   Record source revision, versions, component hashes, and installer hash.
5. Test from a clean Windows install path: launch both apps; create/export a
   profile in Designer; import/prepare it in Runner; inspect local resources,
   controls, permissions, output preflight, results, and error paths. Inspect
   representative bounded text at widths, zoom, long/localized labels, and
   text-spacing overrides in the actual installed WebViews. Test offline
   operation, then a second install/upgrade and uninstall.
6. Treat device routes, physical timing, calibration, participant evidence,
   and published-effect replication as additional qualification gates. Only
   publish installer assets after the [release workflow](../WORKFLOW.md) and
   matching protocol are satisfied.

Do not label the existing V1 ZIP/downloader route as this Full Tauri installer.
Until step 1 is complete, the V1 scripts and
[inventory](../download_package_inventory.md) remain the reproducible Windows
packaging path.
