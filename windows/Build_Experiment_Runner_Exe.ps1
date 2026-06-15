$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Spec = Join-Path $Root "windows\PPSExperimentRunner.spec"
$Exe = Join-Path $Root "dist\PPSExperimentRunner\PPSExperimentRunner.exe"

Set-Location $Root

if (-not (Test-Path $Python)) {
  powershell -ExecutionPolicy Bypass -File (Join-Path $Root "windows\Setup_Windows_App.ps1")
}

& $Python -m pip install -e ".[gui,package]"
if ($LASTEXITCODE -ne 0) {
  throw "Editable package install failed with exit code $LASTEXITCODE"
}
& $Python -m PyInstaller --noconfirm --clean $Spec
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $Exe)) {
  throw "Expected packaged runner was not created: $Exe"
}

& $Exe --help | Out-Host
Write-Host "Built PPS Experiment Runner: $Exe"
