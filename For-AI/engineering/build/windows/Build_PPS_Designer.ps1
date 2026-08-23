$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root
if (-not (Test-Path $Python)) {
  powershell -ExecutionPolicy Bypass -File (Join-Path $Root "For-AI\engineering\build\windows\Setup_Windows_App.ps1")
}
& $Python -m pip install -e ".[designer,package]"
& $Python -m PyInstaller --noconfirm --clean (Join-Path $Root "apps\designer\packaging\PPSDesigner.spec")
if ($LASTEXITCODE -ne 0) { throw "PPS Designer build failed with exit code $LASTEXITCODE" }
Write-Host "Built Windows x64 PPS Designer at dist\PPSDesigner\PPSDesigner.exe"
