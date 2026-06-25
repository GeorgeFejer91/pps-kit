# Fresh-PC Verification Protocol

Use this protocol to prove that the lightweight downloader installs a working local PPS Toolkit on a clean Windows folder.

## Build-Machine Bootstrap

```powershell
winget install --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements
winget install --id GoLang.Go --source winget --accept-package-agreements --accept-source-agreements
py -3.12 --version
go version
```

## Repository Checks

```powershell
powershell -ExecutionPolicy Bypass -File windows\Setup_Windows_App.ps1
.\tools\check_all.ps1 -Tier Quick
pushd windows\downloader
go test ./...
popd
```

## Local Release Smoke

1. Build `PPSExperimentRunner.exe`, `PPSDashboardLauncher.exe`, the offline ZIP, the manifest, and the downloader.
2. Serve `dist/` locally, for example:

```powershell
.\.venv\Scripts\python.exe -m http.server 8788 --directory dist
```

3. Rebuild the downloader with `-ManifestUrl "http://127.0.0.1:8788/pps_download_manifest.v1.json"` or pass the local manifest with `--manifest`.
4. Install into an ignored clean folder:

```powershell
$installDir = Join-Path (Resolve-Path .) "local_data\installer_smoke\installed"
$smokeRoot = Split-Path -Parent $installDir
New-Item -ItemType Directory -Force $smokeRoot | Out-Null
Remove-Item -LiteralPath $installDir -Recurse -Force -ErrorAction SilentlyContinue
$args = @("--quiet", "--manifest", "http://127.0.0.1:8788/pps_download_manifest.v1.json", "--install-dir", $installDir, "--force", "--no-shortcuts")
$proc = Start-Process -FilePath ".\dist\PPS-Toolkit-Downloader.exe" -ArgumentList $args -Wait -PassThru
$proc.ExitCode
```

Use `Start-Process -Wait -PassThru` when capturing exit codes from the lightweight downloader because it is built as a Windows GUI-subsystem executable.

For a custom `--install-dir`, create only the parent folder before invoking the downloader. Do not pre-create the install directory itself. The downloader intentionally refuses to replace an already-existing custom install directory outside `%LOCALAPPDATA%\PPS Toolkit\versions`, even with `--force`, so it exits nonzero instead of deleting an unexpected folder.

5. Verify the installed folder contains:

- `pps_install_manifest.json`
- `pps_package_inventory.v1.json`
- `dist/PPSDashboardLauncher/PPSDashboardLauncher.exe`
- `dist/PPSExperimentRunner/PPSExperimentRunner.exe`
- `dist/PPSExperimentRunner/_internal/PySide6/plugins/platforms/qwindows.dll`
- `windows/Launch_HTML_Dashboard.bat`
- `windows/Start_Website_Companion.bat`
- `windows/Launch_Experiment_Runner.bat`
- `docs/`, `assets/`, `src/`, `study_templates/`, and `installer_protocols/`

6. Health-check the installed dashboard launcher:

```powershell
$installed = Resolve-Path .\local_data\installer_smoke\installed
$proc = Start-Process -WindowStyle Hidden -FilePath "$installed\dist\PPSDashboardLauncher\PPSDashboardLauncher.exe" -ArgumentList "--no-browser --port 8799" -PassThru
Start-Sleep -Seconds 8
Invoke-RestMethod http://127.0.0.1:8799/api/health
Stop-Process -Id $proc.Id -Force
```

If the dashboard does not bind, inspect `$installed\local_data\logs\pps_dashboard_launcher.log` and `$installed\local_data\logs\pps_dashboard_launcher_stream.log`.

7. Check the installed runner help path:

```powershell
$runner = Join-Path $installed "dist\PPSExperimentRunner\PPSExperimentRunner.exe"
$proc = Start-Process -FilePath $runner -ArgumentList "--help" -Wait -PassThru
$proc.ExitCode
```

Hardware readiness remains a separate lab-PC validation. A green installer state does not prove Komplete ASIO, LSL/XDF, or loopback readiness.

## 2026-06-25 Localhost Smoke Evidence

Current local smoke result on this fresh PC:

- `windows\Setup_Windows_App.ps1` completed; it warned that the Komplete Audio ASIO driver is not installed.
- `.\tools\check_all.ps1 -Tier Quick` passed: 25 pytest tests plus compile, JSON parse, release/privacy audit, and whitespace check.
- `go test ./...` in `windows/downloader` passed.
- Rebuilt `dist/PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip` from current `HEAD` with localhost payload URL.
- Rebuilt `dist/PPS-Toolkit-Downloader.exe` with default manifest URL `http://127.0.0.1:8788/pps_download_manifest.v1.json`; size was 6.43 MiB.
- Served `dist/` from `http://127.0.0.1:8788/`.
- Ran the downloader with `--quiet --manifest http://127.0.0.1:8788/pps_download_manifest.v1.json --install-dir local_data\installer_smoke\installed --force --no-shortcuts`; exit code was `0`.
- Download cache was `C:\Users\gfeje\AppData\Local\PPS Toolkit\downloads\PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip`, size `442928793`, SHA256 `359549779c35d878b0a50ad73e93c91961e4115863751737c97bac99044fb74d`, matching the manifest.
- Installed package inventory reported `missing_required_count = 0`.
- Installed payload contained `dist/PPSDashboardLauncher/PPSDashboardLauncher.exe`, `dist/PPSExperimentRunner/PPSExperimentRunner.exe`, Qt `qwindows.dll`, Windows batch launchers, docs, assets, source, study templates, and `installer_protocols/`.
- Installed payload did not include `For-AI/`.
- Installed `PPSDashboardLauncher.exe --no-browser --port 8799` answered `/api/health` with `status = ok`.
- Installed `PPSExperimentRunner.exe --help` exited `0`.

This proves the lightweight downloader, manifest, SHA256 verification, ZIP extraction, package inventory, packaged dashboard launcher, and packaged experiment runner work through a localhost release-server smoke. Public GitHub Release + Zenodo proof is still pending until those release URLs exist.

## Optional Android Emulator Evidence

If the release needs mobile-page or Android WebView evidence for the hosted download page/local dashboard shell, follow `installer_protocols/android_emulator_verification_protocol.md`. This is an optional browser/app-surface smoke and does not replace the Windows downloader install smoke.

Current 2026-06-25 fresh-PC blocker: the Android SDK and AVDs can be installed locally, but this non-elevated shell cannot install the Android Emulator Hypervisor Driver. `x86_64` emulator images exit without hardware acceleration, and ARM64 images are rejected on the x86_64 host.
