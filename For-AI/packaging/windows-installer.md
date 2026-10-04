# Full Windows installer plan

This is the execution contract for the target two-app Tauri package. Its Full
validation configuration and V2 component catalog are source candidates;
installed and acquisition claims require the gates below.
The user selected the stable Planner bundle identifier
`org.peripersonalspace.planner` on 2026-10-04.

## Inputs and ownership

| Input | Product owner | Installer treatment |
|---|---|---|
| Planner Rust executable and bundled HTML | `apps/designer/` | Install as **Experiment Planner** with its own shortcut; no remote UI dependency. |
| Runner Rust executable and bundled HTML | `apps/runner/` | Install as **Experiment Runner** with its own shortcut; no remote UI dependency. |
| Shared templates, assets, configs, sample data, reviewed third-party material, docs, licenses | `packages/pps-resources/`, `third_party/`, `docs/` and root licenses | Install once under a versioned Shared layout; keep logical `assets/...` and `study_templates/...` resolution. |
| Component definitions | `distributions/manifests/` | Extend or version the manifests for the Tauri layout; one file owner and an exact Full composition. |
| Build and inventory logic | `For-AI/engineering/build/`, `For-AI/engineering/release/` | Reuse and adapt existing scripts instead of creating a second manifest or audit implementation. |

The Full Planner worker serves only private `/api/*` calls through stdio;
its dashboard factory skips static frontend mounting. Tauri embeds the Planner
HTML, and Full installs the Shared resources once outside the worker.

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
   The V2 Planner executable mapping declares Tauri's NSIS bundle-marker patch:
   the installed executable must match the build executable with exactly one
   `__TAURI_BUNDLE_TYPE_VAR_UNK` to `__TAURI_BUNDLE_TYPE_VAR_NSS` substitution.
   The inventory rejects every other byte difference.
4. Build one Full Windows installer over that audited composition. It must
   provide separate **Experiment Planner** and **Experiment Runner** shortcuts,
   support uninstall/repair without corrupting Shared ownership, and reject an
   incompatible pre-existing Shared component.
   Record source revision, versions, component hashes, and installer hash.
5. Test from a clean Windows install path: launch both apps; create/export a
   profile in Designer; import/prepare it in Runner; inspect local resources,
   controls, permissions, output preflight, results, and error paths. Inspect
   representative bounded text at widths, zoom, long/localized labels, and
   text-spacing overrides in the actual installed WebViews. Test offline
   operation, then a second install/upgrade and uninstall in a clean test path.
6. Use the verified Full installer to reinstall both apps on this PC. Inspect
   the existing installation and preserve user/participant data before any
   replacement. Confirm the installed version and hash, both shortcuts and
   windows, offline launch, and the Planner-to-Runner profile handoff.
7. Treat device routes, physical timing, calibration, participant evidence,
   and published-effect replication as additional qualification gates. Only
   publish installer assets after the [release workflow](../WORKFLOW.md) and
   matching protocol are satisfied.

Do not label the existing V1 ZIP/downloader route as this Full Tauri installer.
Until the installed Full package and acquisition gates pass, the V1 scripts and
[inventory](../download_package_inventory.md) remain the qualified compatibility
path.
