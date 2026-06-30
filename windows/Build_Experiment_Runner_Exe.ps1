$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Spec = Join-Path $Root "windows\PPSExperimentRunner.spec"
$Exe = Join-Path $Root "dist\PPSExperimentRunner\PPSExperimentRunner.exe"

Set-Location $Root

if (-not (Test-Path $Python)) {
  powershell -ExecutionPolicy Bypass -File (Join-Path $Root "windows\Setup_Windows_App.ps1")
}

& $Python -m pip install -e ".[gui,web,lsl,xdf,package]"
if ($LASTEXITCODE -ne 0) {
  throw "Editable package install failed with exit code $LASTEXITCODE"
}
& $Python (Join-Path $Root "tools\check_qt_runtime.py")
if ($LASTEXITCODE -ne 0) {
  throw "Qt runtime preflight failed. The packaged runner would be unable to initialize Qt."
}
$env:PPS_EXPERIMENT_RUNNER_DISABLE_ICON = $null
& $Python -m PyInstaller --noconfirm --clean $Spec
if ($LASTEXITCODE -ne 0) {
  $StandardBuildExitCode = $LASTEXITCODE
  Write-Warning "Standard branded PyInstaller build failed with exit code $StandardBuildExitCode. Retrying once without embedding the .ico resource; this avoids Windows Defender false positives during BeginUpdateResource while preserving the runner code path."
  $env:PPS_EXPERIMENT_RUNNER_DISABLE_ICON = "1"
  & $Python -m PyInstaller --noconfirm --clean $Spec
  $env:PPS_EXPERIMENT_RUNNER_DISABLE_ICON = $null
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE after iconless fallback retry. Standard build exit code was $StandardBuildExitCode."
  }
}

if (-not (Test-Path $Exe)) {
  throw "Expected packaged runner was not created: $Exe"
}

& $Python (Join-Path $Root "tools\check_qt_runtime.py") --packaged-runner (Join-Path $Root "dist\PPSExperimentRunner")
if ($LASTEXITCODE -ne 0) {
  throw "Packaged runner Qt runtime validation failed."
}

& $Exe --help | Out-Host
Write-Host "Built PPS Experiment Runner: $Exe"
