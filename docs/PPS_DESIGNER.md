# PPS Experiment Designer

PPS Experiment Designer is a standalone authoring applet with one compiled
frontend delivered in two capability modes.

- `desktop_full`: `pps-designer` starts FastAPI on `127.0.0.1`, exchanges a
  per-launch bootstrap token for an HttpOnly same-site cookie, and opens the UI
  in pywebview. Windows uses WebView2; Linux uses GTK/WebKitGTK.
- `hosted_compose`: GitHub Pages can inspect immutable templates, create
  browser-local drafts, use redistribution-cleared hosted assets, retain fixed
  user audio in IndexedDB, preview stored trajectories, and export a portable
  `.pps-profile`. Selected files are not uploaded.
- `hosted_connected`: a hosted page may explicitly connect to an installed
  local companion. Backend URL/token controls remain an advanced compatibility
  surface, not part of ordinary desktop use.

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
npm --prefix src/peripersonal_space_toolkit/dashboard ci
npm --prefix src/peripersonal_space_toolkit/dashboard run build
```

The output is `src/peripersonal_space_toolkit/dashboard/compiled/`; both FastAPI
and the root GitHub Pages wrapper use this directory.

Windows x64:

```powershell
.\windows\Build_PPS_Designer.ps1
```

Linux source launcher and package builder are under `packaging/linux/`.
`build_designer_packages.sh` uses a clean virtual environment, PyInstaller, and
`fpm` to emit DEB/RPM staging packages. Runtime systems need GTK 3 and a current
WebKitGTK package. Qt, CEF, Electron, and bundled Chromium are excluded.
