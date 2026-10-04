param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
Push-Location $root
try {
    & $Python -m pip install --disable-pip-version-check -e ".[designer,package]"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python -m PyInstaller --noconfirm --clean "apps/designer/packaging/PPSPlannerWorker.spec"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $worker = Join-Path $root "dist/PPSPlannerWorker/PPSPlannerWorker.exe"
    if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) {
        throw "Planner worker executable was not produced."
    }
    Write-Host "Built the private Planner worker: $worker"
}
finally {
    Pop-Location
}
