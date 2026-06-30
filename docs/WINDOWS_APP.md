# Windows App Guide

This toolkit is designed to run as a local Windows experiment app from a cloned or downloaded repository.

## Setup

Run once:

```powershell
.\windows\Setup_Windows_App.ps1
```

The script creates `.venv`, installs the toolkit in editable mode, installs test and TTS extras, and creates local runtime folders.

## Launch

```bat
windows\Launch_HTML_Dashboard.bat
```

Create a desktop shortcut:

```powershell
.\windows\Create_Desktop_Shortcut.ps1
```

The source shortcut uses the packaged PPS Toolkit icon and opens the standard
local browser dashboard through the Python development environment. Finished
installer builds use `dist\PPSDashboardLauncher\PPSDashboardLauncher.exe`
instead, so installed end users can open the local dashboard and companion
without Python. The shortcut also creates a `PPS Experiment Runner` shortcut
that opens the standalone Experiment Runner picker for resuming the last
session, resuming a chosen session folder from metadata, or starting a new
session from a parent folder/profile/name dialog. The Qt designer and native
Focus Mode set the same icon at runtime so their
window/taskbar entries do not fall back to the generic Python icon.

Build the packaged local dashboard launcher:

```powershell
.\windows\Build_Dashboard_Launcher_Exe.ps1
```

The build writes `dist\PPSDashboardLauncher\PPSDashboardLauncher.exe` as an
onedir app that starts the local companion backend and opens the browser UI.
When frozen, launcher startup and server logs are written under
`local_data\logs\pps_dashboard_launcher.log` and
`local_data\logs\pps_dashboard_launcher_stream.log` so installer smoke tests
can diagnose failures even though the executable uses the Windows GUI
subsystem.

Build the native participant runner as a Windows program when you want the
runner to appear as its own app rather than as Python:

```powershell
.\windows\Build_Experiment_Runner_Exe.ps1
```

The build writes `dist\PPSExperimentRunner\PPSExperimentRunner.exe` as an
onedir PyInstaller app with no console window and the packaged PPS Toolkit icon
embedded. This exe is the only active operator experiment runner. The
`windows\Launch_Experiment_Runner.bat` wrapper only activates that exe and
fails with build instructions if it is missing; it does not fall back to a
Python module runner, and direct module launch exits with retirement guidance.
With no batch arguments, the wrapper opens the standalone Experiment Runner
session decision gate. Running `PPSExperimentRunner.exe` directly with no
arguments must show the same first window with three bottom choices:
`Resume Last Session`, `Resume Custom Session`, and `Start New Session`.
The custom resume path asks only for the session folder and scans PPS diary and
bridge metadata. The new-session path is the only path that opens a setup dialog
for parent folder, experiment profile, and session name. Explicit flags such as
`--session-manifest`, `--last-experiment`, `--latest-dashboard-setup`, and
`--profile` are reserved for dashboard handoff, validation, and scripted
workflows that intentionally bypass that gate.

Focus Mode starts a local Android companion service by default on LAN port
`8767` and shows an unobtrusive `Companion Android App (Experimental)` tab with
the QR pairing code. The service is protected by a per-run
`X-PPS-Companion-Token`; the laptop remains the timing and command authority.
The phone can request setup submission, Start Part 01/02, separate Pause and
Resume commands, and instruction continuation only when the runner advertises
those commands. The Pause and Resume controls are mutually exclusive and the
phone shows play/pause state only after a runner snapshot confirms it. Use
`--no-companion` to disable it, or `--companion-host`, `--companion-port`, and
`--companion-advertise-ip` when the laptop has multiple network interfaces.
See [Android Runner Companion](ANDROID_RUNNER_COMPANION.md) for phone pairing,
firewall, privacy, and APK build steps.

Build the native Android companion debug APK:

```powershell
.\windows\Build_Android_Companion.ps1
```

For finished public releases, build the lightweight downloader separately:

```powershell
.\windows\Build_PPS_Downloader.ps1
```

That creates a small `dist\PPS-Toolkit-Downloader.exe` intended for GitHub
release upload. The full offline lab ZIP is built separately and hosted on
Zenodo; the downloader verifies its SHA256 from `pps_download_manifest.v1.json`
before extracting to `%LOCALAPPDATA%\PPS Toolkit\versions\` and launching the
packaged dashboard launcher. See
[PPS Download Distribution](PPS_DOWNLOADS.md).

Open the Qt stimulus design layer for comparison:

```bat
windows\Launch_Stimulus_Designer.bat
```

Run the native Focus Mode participant app directly when reopening a prepared
dashboard experiment or choosing a finished study/profile preset:

```bat
windows\Launch_Experiment_Runner.bat
```

The HTML dashboard is the standard researcher-facing interface. It runs as a
local browser UI on `127.0.0.1`, launched by Python/FastAPI, and keeps
rendering, session packaging, audio stress tests, and participant running in
Python/native backend code rather than in an online service. The Qt designer
remains available as a comparison and fallback path. The dashboard keeps a
fixed floating one-page navigation rail, exposes panel sizing controls in that
rail, and uses a sequential custom-design workflow before run actions unlock.

The same HTML interface can be hosted on GitHub Pages. For that workflow, start
the local companion backend and use the website as the visible UI:

```bat
windows\Start_Website_Companion.bat
```

See [GitHub Pages Dashboard](GITHUB_PAGES_DASHBOARD.md).

Useful launch variants:

```bat
windows\Launch_HTML_Dashboard.bat --port 8770
windows\Launch_HTML_Dashboard.bat --no-browser
windows\Launch_Experiment_Runner.bat --participant-id P001
dist\PPSExperimentRunner\PPSExperimentRunner.exe --launcher
windows\Start_Website_Companion.bat --web-origin https://example.github.io
```

Segment 6 in the dashboard includes **Preload Instruction Audio Clips** for
run-level messages before/after the experiment, before/after blocks, and between
conditions. Imported clips are stored locally under the active project, copied
into prepared participant sessions, and played by Focus Mode through the
auditory channels only.

## Audio Device Check

```bat
windows\List_Audio_Devices.bat
```

For rendered binaural+tactile files, run the silent routing stress test:

```bat
windows\Stress_Audio_Device.bat
```

The retired two-channel Study 5 WAV layout used the original stereo routing:

- left channel: tactile/vibration output
- right channel: auditory stimulus output

The configurable trajectory renderer writes generated looming WAVs with three
channels:

- channel 0: binaural left ear
- channel 1: binaural right ear
- channel 2: vibrotactile cue track

Those rendered files require one synchronized 3+ channel output device. On the
lab Komplete setup, use `Komplete Audio ASIO Driver`; the Windows `Output 1/2`
and `Output 3/4` pairs are legacy-only. See
[Audio Routing And Stress Test](AUDIO_ROUTING_STRESS_TEST.md).

The runner keeps one persistent ASIO output stream open and mixes instructions,
blocks, background audio, and click/tactile feedback into that stream. This is
required because the Komplete ASIO driver is effectively single-client in this
setup.

Focus Mode can optionally write a fail-safe local recording WAV from the mixed output buffers. This is the normal data-heavy software safety copy for experiment runs; WASAPI loopback remains an optional diagnostic on Windows and may not capture ASIO multichannel playback.

## Local Data

The app writes runtime settings, demographics, session outputs, event logs, LSL marker mirrors, and optional fail-safe local recording WAVs under `local_data\` by default. That folder is ignored by Git and should not be published.
The resume ledger lives in `local_data\dashboard_state\` as append-only
`experiment_activity_log.jsonl` plus the fast pointer `last_experiment.v1.json`.
