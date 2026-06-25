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
$args = @("--quiet", "--manifest", "http://127.0.0.1:8788/pps_download_manifest.v1.json", "--install-dir", $installDir, "--force", "--no-shortcuts")
$proc = Start-Process -FilePath ".\dist\PPS-Toolkit-Downloader.exe" -ArgumentList $args -Wait -PassThru
$proc.ExitCode
```

Use `Start-Process -Wait -PassThru` when capturing exit codes from the lightweight downloader because it is built as a Windows GUI-subsystem executable.

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
