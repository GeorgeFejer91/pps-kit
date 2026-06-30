# Peripersonal Space Toolkit

A Windows-ready toolkit for running and reproducing the Study 5 audio-tactile peripersonal-space experiment. The repository packages the experiment runner, stimulus-generation pipeline, decoding helpers, small deidentified sample data, and bundled spoken instruction asset variants.

The default layout keeps source files public and keeps participant data local. Runtime recordings, demographics, generated stimuli, and model downloads are written to ignored folders.

## Quick Start On Windows

1. Open PowerShell in the repository root.
2. Run:

```powershell
.\windows\Setup_Windows_App.ps1
```

3. List audio devices:

```bat
windows\List_Audio_Devices.bat
```

For rendered binaural+tactile stimuli, verify one synchronized 3+ channel output
stream:

```bat
windows\Stress_Audio_Device.bat
```

4. Generate experiment stimuli. The standardized FABIAN/TU HRIR file is bundled
   under:

```text
assets\0. Head-Related Impulse Response (HRIR) model\FABIAN_HRIR_measured_HATO_0.sofa
```

Then run:

```powershell
.\.venv\Scripts\pps-generate.exe --participants 50
```

5. Launch the standard local dashboard:

```bat
windows\Launch_HTML_Dashboard.bat
```

The dashboard opens in your default browser from `127.0.0.1`. It is a local
researcher-facing UI for study/profile selection, custom designs, trajectory
controls, trial assembly, render, prepare, audio stress, packaged experiment
runner launch, and review.

Build the active native participant runner:

```powershell
.\windows\Build_Experiment_Runner_Exe.ps1
```

This creates `dist\PPSExperimentRunner\PPSExperimentRunner.exe` with the PPS
Toolkit icon embedded. `windows\Launch_Experiment_Runner.bat` only activates
this packaged exe. `focus_app.py` is importable for the exe and validation
harnesses, but direct Python/module runner invocation exits with retirement
guidance instead of opening Focus Mode. The build runs a Qt runtime preflight
and fails if the Windows Qt platform plugin is not packaged.

Focus Mode also hosts a token-gated Android runner companion service on the
local LAN by default. The QR pairing panel in the runner lets a trusted phone
submit setup fields, start Part 01/Part 02 when the runner allows it, continue
instruction gates, and display the live timeline without becoming the timing
authority. See [docs/ANDROID_RUNNER_COMPANION.md](docs/ANDROID_RUNNER_COMPANION.md).

Optional: build the lightweight release downloader and offline-lab distribution
manifest. Public Windows releases use a GitHub-hosted downloader plus a
Zenodo-hosted payload:

```powershell
.\windows\Build_Experiment_Runner_Exe.ps1
.\windows\Build_Dashboard_Launcher_Exe.ps1
.\windows\Build_PPS_Downloader.ps1
.\windows\Build_PPS_Distribution.ps1 -Version 0.1.0 -ZenodoPayloadUrl "https://zenodo.org/records/<record>/files/PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip?download=1" -ZenodoDoi "10.5281/zenodo.<record>"
```

`PPS-Toolkit-Downloader.exe` is the small GitHub-hosted bootstrapper and must
stay below 100 MiB. The heavyweight offline lab ZIP belongs on Zenodo and is
verified by `pps_download_manifest.v1.json` before extraction or launch. The
installed dashboard opens through `dist\PPSDashboardLauncher\PPSDashboardLauncher.exe`
so end users do not need Python for the local GUI.

The same HTML interface can also be published as a static GitHub Pages site.
In that mode, start the trusted local companion backend first:

```bat
windows\Start_Website_Companion.bat
```

Then open the public dashboard at
[https://ppskit.qzz.io/](https://ppskit.qzz.io/) or
[https://georgefejer91.github.io/pps-kit/](https://georgefejer91.github.io/pps-kit/).
The hosted page connects back to
`http://127.0.0.1:8766` for local render/session/focus operations; the website
itself cannot silently install packages or run experiments without the local
companion. It also does not upload selected stimulus files, generated WAVs, or
experiment outputs online; audio import and all experiment operations stay on
the research PC. See [docs/GITHUB_PAGES_DASHBOARD.md](docs/GITHUB_PAGES_DASHBOARD.md).

Open the Qt stimulus designer for comparison:

```bat
windows\Launch_Stimulus_Designer.bat
```

Run the native Focus Mode participant app directly when you want to reopen the
latest prepared dashboard experiment:

```bat
windows\Launch_Experiment_Runner.bat
```

The standalone runner launcher defaults to the Study 5 finished profile. Its
participant control is a numbered dropdown, not a free-text field; each row
shows whether that participant's local audio/session package is generated. Use
`Generate Audio Assets` for the selected participant, or enter an explicit range
such as `1-10` before pressing `Generate Range`. Range generation is deliberately
manual so a lab PC does not fill with all 50 Study 5 participant packages unless
the operator asks for them.

The designer can preload bundled study profiles from `study_templates\`; the current catalog contains the unpublished Study 5 workflow plus 20 published-study profiles. Each profile has a matching local preload folder under `assets\preloads\<template_id>\` with segment metadata and prebaked auditory-only looming WAVs while the standardized FABIAN HRIR renderer resource stays under the hood. See [docs/PARADIGM_LIBRARY.md](docs/PARADIGM_LIBRARY.md) and [docs/PUBLISHED_PARADIGM_STRESS_TEST.md](docs/PUBLISHED_PARADIGM_STRESS_TEST.md).

Optional: create a desktop shortcut for the launcher:

```powershell
.\windows\Create_Desktop_Shortcut.ps1
```

## Spoken Audio Assets

The bundled spoken instruction WAV files include both the British Kokoro `bf_emma` voice set and the original Study 5 instruction audio decoded from local lab MP3 assets. The active root files and `assets\breathing\british_kokoro\` are exact 4.000-second British TTS WAVs. `assets\breathing\original_study5\` preserves the original Study 5 instruction messages as WAVs, with the inhale/exhale trial-window clips normalized to exactly 4.000 seconds for the Study 5 8-second trial unit. To regenerate the British set:

```bat
windows\Regenerate_Spoken_Assets.bat
```

The Kokoro model files download into `models\kokoro\`, which is ignored by Git. Only the generated study WAV files and manifest are intended for publication.

Segment 2 owns within-trial inhale/exhale clips. Segment 6 now has a separate
**Preload Instruction Audio Clips** panel for run-level messages before the
experiment, before/after each block, between conditions, and after the
experiment. Custom clips are imported by the local backend into the active
project's Segment 6 instruction library, saved into the run setup manifest, and
copied into each participant session under `instructions\`.

## Public Commands

```powershell
pps-generate --dry-run
pps-generate --participants 50
pps-dashboard
pps-design
pps-audio-stress --device-query Komplete
pps-latency-validate specs
pps-latency-validate calibrate --establish-baseline
pps-render-design --design study_templates\pfeiffer_2018_lateral_perihead_left_to_right.json --output-dir artifacts\rendered_pfeiffer --seed 2018
pps-decode --input-dir local_data\loopback_recordings
pps-analyze --sample
```

`pps-render-design` writes a render config, trajectory samples, QC CSV, manifest, and generated WAVs. It uses the native 3DTI executable when available; otherwise it uses the bundled Python SOFA/FABIAN reference renderer and marks the manifest as `rendered_reference`.

`pps-latency-validate` writes the Komplete/Woojer wiring plan and runs electrical loopback validation for the synchronized output 1/2/3 route. See [docs/EXPERIMENT_LATENCY_VALIDATION.md](docs/EXPERIMENT_LATENCY_VALIDATION.md).

`pps-dashboard` starts a local-only browser dashboard at `127.0.0.1` for researcher-facing design, render, prepare, and review decisions. The dashboard uses a fixed one-page navigation rail, adjustable preview/panel sizing controls, and a sequential custom-design workflow that blocks run actions until the minimum runnable experiment profile is filled in. The existing Qt designer remains available as `pps-design`; the only active operator experiment runner is the packaged native `dist\PPSExperimentRunner\PPSExperimentRunner.exe`.

`PPSExperimentRunner.exe` opens a three-choice session gate by default:
`Resume Last Session` reopens the remembered environment from
`local_data\dashboard_state\`, `Resume Custom Session` asks for an existing
session folder and scans its diary/bridge metadata, and `Start New Session`
opens the only setup dialog for parent folder, profile, and session name.
Explicit `--session-manifest`, `--last-experiment`, `--latest-dashboard-setup`,
and `--profile` launches are reserved for dashboard handoff, validation, and
scripted workflows that intentionally bypass that first gate.

Verify the bundled Pfeiffer-style profile and render handoff:

```powershell
python tools\verify_pfeiffer_profile.py
```

## One-Bundle Release

For a public archive or Zenodo deposit, create a reviewed source-and-assets bundle:

```powershell
python tools\make_release_bundle.py
```

The bundle includes the app source, Windows launch/setup scripts, study profiles,
the pinned 3DTI source snapshot, the bundled FABIAN SOFA file, attribution/license
notes, and a `bundle_manifest.json` with SHA256 hashes. It excludes local runtime
data, generated render outputs, downloaded model files, and private reference
archives.

## Download Distribution

Finished Windows releases use a two-layer download strategy. GitHub hosts the
lightweight `PPS-Toolkit-Downloader.exe`; Zenodo hosts the heavyweight
`PPS-Toolkit-vX.Y.Z-offline-lab-windows-x64.zip`. The downloader reads
`pps_download_manifest.v1.json`, downloads the Zenodo payload, verifies SHA256,
extracts to `%LOCALAPPDATA%\PPS Toolkit\versions\vX.Y.Z`, creates shortcuts, and
launches the packaged dashboard only after verification. See
[docs/PPS_DOWNLOADS.md](docs/PPS_DOWNLOADS.md).

The repo contains the installer package source in `windows\downloader\` and the
tracked offline-package inventory at `windows\installer_package_inventory.v1.json`;
release binaries and ZIPs are generated into ignored `dist\` for GitHub
Releases/Zenodo. Installer build and missing-link protocols live in
`installer_protocols\`.

## Repository Layout

```text
assets\breathing\        Spoken instruction WAVs plus British/original variants
assets\click\            Click/tactile cue seed asset
assets\0. Head-Related...\FABIAN_HRIR_measured_HATO_0.sofa
                         Bundled standardized FABIAN/TU HRIR resource
assets\master_blocks\    Study block templates
assets\preloads\         Profile file-cabinet catalogs and prebaked looming WAVs
android\runner-companion\ Native Kotlin/Compose Android phone companion source
configs\                 Example experiment and stimulus-design configs
data\sample\             Deidentified sample analysis CSVs
docs\                    Hardware setup, replication, privacy, Windows, protocol, and paradigm notes
For-AI\                  Project memory and required context for future AI agents
installer_protocols\     Installer build, content, smoke-test, and missing-link protocols
src\                     Python package and command entry points
study_templates\         Literature-backed preloadable study profiles
tests\                   Smoke and release-readiness tests
third_party\             Pinned third-party source snapshots and renderer wrapper boundary
tools\                   Asset generation and release audit scripts
validation_protocols\    Internal lab stress-test protocols, scripts, and templates
windows\                 Ready-to-use Windows setup and launch scripts
```

## AI Agent Context

Future AI agents and maintainers should start with [AGENTS.md](AGENTS.md) and [For-AI/README.md](For-AI/README.md). The `For-AI\` folder records current project aims, scope, evolving goals, and update rules for keeping that context current.

## Validation Tiers

Use the repo-local check entrypoint for routine validation:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_all.ps1 -Tier Quick
```

`Quick` is the fresh-clone-safe path for ordinary changes. `Standard` adds the full tracked pytest suite, and `Deep` is reserved for generated paper-audit artifacts, packaged-runner checks, or lab hardware evidence when the required local state is present. See [docs/VALIDATION.md](docs/VALIDATION.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Privacy And Release Boundaries

Do not commit participant recordings, demographics, raw exports, or generated local experiment output. The ignored folders `local_data\`, `artifacts\`, and `models\` are intended for local use only. See [docs/hardware_setup.md](docs/hardware_setup.md), [docs/AUDIO_ROUTING_STRESS_TEST.md](docs/AUDIO_ROUTING_STRESS_TEST.md), [docs/replication_workflow.md](docs/replication_workflow.md), and [docs/privacy_boundary.md](docs/privacy_boundary.md). Run this before publishing a release:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_all.ps1 -Tier Standard
python tools\release_audit.py
python tools\make_release_bundle.py
```

## License

Source code is released under the MIT License. Deidentified sample data and documentation are released under CC BY 4.0 unless a file states otherwise. Third-party source snapshots and redistributable HRTF assets have their own license and attribution notes in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
