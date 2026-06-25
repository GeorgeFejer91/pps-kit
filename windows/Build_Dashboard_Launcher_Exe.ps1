$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Spec = Join-Path $Root "windows\PPSDashboardLauncher.spec"
$Exe = Join-Path $Root "dist\PPSDashboardLauncher\PPSDashboardLauncher.exe"

Set-Location $Root

if (-not (Test-Path $Python)) {
  powershell -ExecutionPolicy Bypass -File (Join-Path $Root "windows\Setup_Windows_App.ps1")
}

& $Python -m pip install -e ".[web,lsl,xdf,package]"
if ($LASTEXITCODE -ne 0) {
  throw "Editable package install failed with exit code $LASTEXITCODE"
}

$env:PPS_DASHBOARD_LAUNCHER_DISABLE_ICON = $null
& $Python -m PyInstaller --noconfirm --clean $Spec
if ($LASTEXITCODE -ne 0) {
  $StandardBuildExitCode = $LASTEXITCODE
  Write-Warning "Standard branded PyInstaller dashboard launcher build failed with exit code $StandardBuildExitCode. Retrying once without embedding the .ico resource."
  $env:PPS_DASHBOARD_LAUNCHER_DISABLE_ICON = "1"
  & $Python -m PyInstaller --noconfirm --clean $Spec
  $env:PPS_DASHBOARD_LAUNCHER_DISABLE_ICON = $null
  if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller dashboard launcher build failed with exit code $LASTEXITCODE after iconless fallback retry. Standard build exit code was $StandardBuildExitCode."
  }
}

if (-not (Test-Path $Exe)) {
  throw "Expected packaged dashboard launcher was not created: $Exe"
}

& $Exe --help | Out-Host
Write-Host "Built PPS Dashboard Launcher: $Exe"
