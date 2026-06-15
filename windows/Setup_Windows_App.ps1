$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Venv = Join-Path $Root ".venv"

if (-not (Test-Path $Venv)) {
    $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PythonLauncher) {
        py -3.12 -m venv $Venv
        if ($LASTEXITCODE -ne 0) {
            python -m venv $Venv
        }
    } else {
        python -m venv $Venv
    }
}

$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -e "${Root}[tts,gui,lsl,web,xdf,dev,package]"
if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed with exit code $LASTEXITCODE"
}
& $Python (Join-Path $Root "tools\check_qt_runtime.py")
if ($LASTEXITCODE -ne 0) {
    throw "Qt runtime preflight failed. Recreate .venv with a standard Python install or rerun setup after fixing PySide6."
}

New-Item -ItemType Directory -Force (Join-Path $Root "artifacts") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $Root "local_data\loopback_recordings") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $Root "local_data\sessions") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $Root "local_data\demographics") | Out-Null

$DriverUrl = "https://www.native-instruments.com/en/support/downloads/drivers-other-files/"
$AuditDir = Join-Path $Root "artifacts\validation_runs\setup_pc_software_requirements"
& $Python (Join-Path $Root "validation_protocols\scripts\audit_pc_software_requirements.py") --output-dir $AuditDir
if ($LASTEXITCODE -eq 0) {
    $AuditJson = Join-Path $AuditDir "pc_software_requirements_audit.json"
    if (Test-Path -LiteralPath $AuditJson) {
        $Audit = Get-Content -Raw -LiteralPath $AuditJson | ConvertFrom-Json
        if (-not $Audit.summary.komplete_asio_sounddevice_ready) {
            Write-Warning "Komplete Audio ASIO is not visible as a 3+ channel sounddevice output. Opening the official Native Instruments driver page."
            Start-Process $DriverUrl
        }
    }
}
else {
    Write-Warning "PC software audit failed. Continue setup, then run validation_protocols\scripts\audit_pc_software_requirements.py manually."
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Run windows\Launch_HTML_Dashboard.bat to open the standard local browser dashboard."
Write-Host "Run windows\Launch_Experiment_Runner.bat to open the standalone Experiment Runner picker."
Write-Host "Run windows\Build_Experiment_Runner_Exe.ps1 to package Focus Mode as dist\PPSExperimentRunner\PPSExperimentRunner.exe."
Write-Host "Run windows\Start_Website_Companion.bat when using the GitHub Pages dashboard."
Write-Host "Run windows\Launch_Stimulus_Designer.bat to compare the Qt designer."
Write-Host "Run dist\PPSExperimentRunner\PPSExperimentRunner.exe with no arguments to auto-open the last launchable experiment."
Write-Host "The standardized under-the-hood FABIAN HRIR resource is bundled; use windows\Fetch_FABIAN_HRTF.ps1 only to refresh its manifest."
