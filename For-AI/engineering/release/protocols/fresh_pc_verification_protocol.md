# Fresh-PC Verification Protocol

Qualify each exact-revision component package on clean Windows. A fresh folder
on a development PC is a smoke test, not proof of independence from a checkout,
Python, build tools or previously installed runtime DLLs. The current component
builder still builds V1; the Python-free Rust/Tauri candidate must pass its own
installed journey before replacing that release.

## Build-machine checks

Follow [release build protocol](release_build_protocol.md). Run Standard,
applicable Rust/browser checks, release/privacy audit and downloader tests.
Record source commit, exact tool versions, artifact SHA256 and inventory.
Use `distributions/manifests/`; do not install a repository checkout.

## Local Release Smoke

1. Build the Designer, Runner and Full component payloads with
   `-PayloadBaseUrl "http://127.0.0.1:8788"` and matching download manifests.
2. Serve `dist/` locally, for example:

```powershell
.\.venv\Scripts\python.exe -m http.server 8788 --directory dist
```

3. Build a smoke downloader with `Build_PPS_Downloader.ps1 -Component full
   -ManifestBaseUrl "http://127.0.0.1:8788"`, or pass its matching manifest
   through `--manifest`. Repeat independently for Designer and Runner.
4. Install into a new, uniquely named destination; preserve earlier runs:

```powershell
$smokeRoot = Join-Path (Get-Location) "local_data\installer_smoke"
New-Item -ItemType Directory -Force $smokeRoot | Out-Null
$installDir = Join-Path $smokeRoot ("installed-" + [Guid]::NewGuid().ToString("N"))
$smokeArgs = @("--quiet", "--manifest", "http://127.0.0.1:8788/pps_toolkit_download_manifest.v1.json", "--install-dir", $installDir, "--no-shortcuts")
$proc = Start-Process -WindowStyle Hidden -FilePath ".\dist\PPS-Toolkit-Downloader.exe" -ArgumentList $smokeArgs -Wait -PassThru
if ($proc.ExitCode -ne 0) { throw "Downloader failed: $($proc.ExitCode)" }
```

Use `Start-Process -Wait -PassThru` when capturing exit codes from the lightweight downloader because it is built as a Windows GUI-subsystem executable.

For a custom `--install-dir`, create only the parent folder before invoking the downloader. Do not pre-create the install directory itself. The downloader intentionally refuses to replace an already-existing custom install directory outside `%LOCALAPPDATA%\PPS Toolkit\versions`, even with `--force`, so it exits nonzero instead of deleting an unexpected folder.

5. Verify the installed folder contains:

- `pps_install_manifest.json`
- `pps_package_inventory.v1.json`
- `apps/PPSDesigner/PPSDesigner.exe`
- `apps/PPSExperimentRunner/PPSExperimentRunner.exe`
- `shared/docs/`, `shared/assets/`, `shared/study_templates/` and shared licenses

The V1 Runner additionally requires its packaged Qt platform plugin.
Designer-only and Runner-only installations must launch independently with
compatible Shared resources. No installed `For-AI/`, private data, generated
research sessions or experimental Android APK is permitted.

6. Open the installed programs through these exact entrypoints. Inspect
   startup, resource lookup, actionable errors and logs. A working `--help`
   invocation alone does not verify their user workflows.

## Clean Windows candidate journey

Use a clean Windows VM or PC with no checkout or Python. Record OS/WebView
versions, installer hashes and the exact source revision.

1. Download and verify public artifacts, install each advertised component
   combination, and confirm shortcuts and offline startup.
2. Online: select premade assets, preview, save/reload, and export all audio,
   including instructions. Transfer the bundle to the clean offline machine.
3. Native: import and verify assets, customize an endpoint trajectory, generate
   with Rust/3DTI, inspect all manifest-ordered blocks, run the full session and
   independently validate its result files.
4. Exercise corrupt/missing assets, unavailable renderer/HRTF resources,
   cancellation, edits during generation, failed writes and interrupted runs.
   No partial or stale output may be shown as a completed experiment.
5. Inspect filesystem/process activity for checkout dependencies and Python
   invocation. Confirm the package includes all approved native resources.
6. Qualify advertised device/LSL/phone routes. Electrical timing, tactile onset,
   calibration and behavioral replication remain separately measured claims.

## 2026-06-25 Localhost Smoke Evidence (historical)

This retained report describes an older packaging layout. It is not current
release qualification. Its statements about installed For-AI contents conflict;
re-establish that privacy claim from the new package inventory.

Current local smoke result on this fresh PC:

- `For-AI\engineering\build\windows\Setup_Windows_App.ps1` completed; it warned that the Komplete Audio ASIO driver is not installed.
- `.\For-AI\engineering\automation\check_all.ps1 -Tier Quick` passed: 25 pytest tests plus compile, JSON parse, release/privacy audit, and whitespace check.
- `go test ./...` in `distributions/downloader` passed.
- Rebuilt `dist/PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip` from current `HEAD` with localhost payload URL.
- Rebuilt `dist/PPS-Toolkit-Downloader.exe` with default manifest URL `http://127.0.0.1:8788/pps_download_manifest.v1.json`; size was 6.43 MiB.
- Served `dist/` from `http://127.0.0.1:8788/`.
- Ran the downloader with `--quiet --manifest http://127.0.0.1:8788/pps_download_manifest.v1.json --install-dir local_data\installer_smoke\installed --force --no-shortcuts`; exit code was `0`.
- Download cache was `%LOCALAPPDATA%\PPS Toolkit\downloads\PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip`, size `442928793`, SHA256 `359549779c35d878b0a50ad73e93c91961e4115863751737c97bac99044fb74d`, matching the manifest.
- Installed package inventory reported `missing_required_count = 0`.
- Installed payload contained `dist/PPSDashboardLauncher/PPSDashboardLauncher.exe`, `dist/PPSExperimentRunner/PPSExperimentRunner.exe`, Qt `qwindows.dll`, Windows batch launchers, docs, assets, source, study templates, and `For-AI/engineering/release/protocols/`.
- Installed payload did not include `For-AI/`.
- Installed `PPSDashboardLauncher.exe --no-browser --port 8799` answered `/api/health` with `status = ok`.
- Installed `PPSExperimentRunner.exe --help` exited `0`.

This proves the lightweight downloader, manifest, SHA256 verification, ZIP extraction, package inventory, packaged dashboard launcher, and packaged experiment runner work through a localhost release-server smoke. Public GitHub Release + Zenodo proof is still pending until those release URLs exist.

## Optional Android Emulator Evidence

If the release needs experimental Android WebView evidence, follow `For-AI/experiments/android-companion/protocols/android_emulator_verification_protocol.md`. This is an internal experiment smoke and does not replace the Windows downloader install smoke.

Current 2026-06-25 fresh-PC blocker: the Android SDK and AVDs can be installed locally, but this non-elevated shell cannot install the Android Emulator Hypervisor Driver. `x86_64` emulator images exit without hardware acceleration, and ARM64 images are rejected on the x86_64 host.
