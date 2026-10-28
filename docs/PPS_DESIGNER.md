# PPS Experiment Designer

PPS Experiment Designer uses one compiled frontend with three explicit adapters.

- Hosted Designer: GitHub Pages can inspect immutable templates, create
  browser-local drafts, use redistribution-cleared hosted assets, retain fixed
  user audio in IndexedDB, preview stored trajectories, and export a portable
  `.pps-profile`. Selected files are not uploaded.
- Native Designer preview: Rust/Tauri imports and verifies portable bundles,
  generates custom endpoint trajectories through Rust/3DTI, reviews schedules
  and prepares immutable experiments without Python. Native errors remain
  explicit; they do not switch to hosted generation. See the
  [Windows preview guide](NATIVE_WINDOWS_PREVIEW.md) for its capability limits.
- V1 local Designer: `pps-designer` starts FastAPI on loopback, exchanges a
  per-launch bootstrap token for an HttpOnly same-site cookie, and opens the UI
  in pywebview. The companion adapter requires a loopback `/dashboard/` origin;
  a hosted page does not connect to it. Windows uses WebView2; Linux uses
  GTK/WebKitGTK. These are V1 compatibility products, separate from the native
  Windows preview.

Hosted compose cannot generate or spatialize looming audio, mutate stored
trajectories, write folders, materialize acquisition CSVs, or launch the
Experiment Runner.

## Copy-to-edit lifecycle

Built-in templates and finalized profiles are immutable. Activating any edit
path opens the naming dialog first. The derived display name retains the source
profile ID, and the backend records the source profile/project lineage. Draft
decisions autosave. A scientific edit invalidates artifacts below the earliest
changed Segment, so the affected later decisions must be accepted again.

`Done — Lock Profile` finalizes the profile and makes it read-only. A later edit
creates another named copy. Only finalized profiles with accepted Segment 0-5
artifacts enter the Runner catalogue; the Runner materializes participant order
and session artifacts when needed.

## Portable profiles

`.pps-profile` is ZIP-compatible `pps-profile-bundle.v1`. It contains
`manifest.json`, `profile.json`, content-addressed audio under `assets/`, stored
trajectory snapshots/provenance, and SHA-256 hashes. Import validates schemas,
paths, inventory completeness, logical IDs, hashes, sizes, and audio signatures
before registration.

## Build and package

Build the shared frontend:

```text
npm --prefix apps/designer/frontend ci
npm --prefix apps/designer/frontend run build
```

The output is `apps/designer/frontend/compiled/`; FastAPI and local packaging
consume it directly, while Pages assembly copies the same bytes into ignored
deployment staging.

The following packaging commands build the V1 Python compatibility products.
For the separate Rust/Tauri preview, use the
[native candidate build record](../For-AI/engineering/validation/docs/native-windows-candidate-build.md).

V1 Windows x64:

```powershell
.\For-AI\engineering\build\windows\Build_PPS_Designer.ps1
```

Linux source launcher and package builder are under
`apps/designer/packaging/linux/`.
`build_designer_packages.sh` uses a clean virtual environment, PyInstaller, and
`fpm` to emit DEB/RPM staging packages. Runtime systems need GTK 3 and a current
WebKitGTK package. Qt, CEF, Electron, and bundled Chromium are excluded.
