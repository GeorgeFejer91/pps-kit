$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root
if (-not (Test-Path $Python)) {
  powershell -ExecutionPolicy Bypass -File (Join-Path $Root "windows\Setup_Windows_App.ps1")
}
& $Python -m pip install -e ".[designer,package]"
& $Python -m PyInstaller --noconfirm --clean (Join-Path $Root "windows\PPSDesigner.spec")
if ($LASTEXITCODE -ne 0) { throw "PPS Designer build failed with exit code $LASTEXITCODE" }
Write-Host "Built Windows x64 PPS Designer at dist\PPSDesigner\PPSDesigner.exe"
