param(
    [ValidateSet("Quick", "Standard", "Deep")]
    [string]$Tier = "Quick",
    [string]$Python = ".\.venv\Scripts\python.exe",
    [switch]$AllowGeneratedArtifacts,
    [switch]$AllowHardware
)

$ErrorActionPreference = "Stop"

function Resolve-Python {
    param([string]$Candidate)
    if (Test-Path -LiteralPath $Candidate) {
        return (Resolve-Path -LiteralPath $Candidate).Path
    }
    return $Candidate
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host ""
    Write-Host "== $Name =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Name"
    }
}

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $RepoRoot
$PythonExe = Resolve-Python $Python

Write-Host "PPS Toolkit checks"
Write-Host "Tier: $Tier"
Write-Host "Python: $PythonExe"

$quickTests = @(
    "tests/test_cli.py",
    "tests/test_release_audit.py",
    "tests/test_package_inventory.py",
    "tests/test_download_manifest.py",
    "tests/test_qt_runtime_check.py",
    "tests/test_runtime_paths.py",
    "tests/test_seed_data.py",
    "tests/test_audio_assets.py",
    "tests/test_focus_launch.py",
    "tests/test_paper_metadata_parser.py::test_paper_audit_package_summarizes_core_pipeline_without_source_artifacts",
    "tests/test_literature_coverage_audit.py::test_literature_coverage_record_schema_and_verdict_semantics"
)

Invoke-Step "compile Python sources" {
    & $PythonExe -m compileall -q src tests tools validation_protocols windows
}

Invoke-Step "parse tracked JSON files" {
    & $PythonExe -c @"
import json
from pathlib import Path
roots = [Path('assets'), Path('configs'), Path('study_templates'), Path('For-AI'), Path('windows')]
count = 0
for root in roots:
    if not root.exists():
        continue
    for path in root.rglob('*.json'):
        json.loads(path.read_text(encoding='utf-8-sig'))
        count += 1
print(f'parsed {count} JSON files')
"@
}

Invoke-Step "release/privacy audit" {
    & $PythonExe tools\release_audit.py
}

Invoke-Step "quick pytest subset" {
    & $PythonExe -m pytest -q @quickTests
}

Invoke-Step "git whitespace check" {
    git diff --check
}

if ($Tier -in @("Standard", "Deep")) {
    Invoke-Step "standard pytest suite" {
        & $PythonExe -m pytest -q
    }
}

if ($Tier -eq "Deep") {
    if ($AllowGeneratedArtifacts) {
        Invoke-Step "paper metadata parser dry inventory" {
            & $PythonExe -m tools.paper_metadata_parser --repo-root . --no-parse-downloaded --refresh
        }
    } else {
        Write-Host ""
        Write-Host "== generated-artifact checks skipped =="
        Write-Host "Pass -AllowGeneratedArtifacts to refresh ignored/generated paper-audit inventories."
    }

    if ($AllowHardware) {
        Write-Host ""
        Write-Host "== hardware checks requested =="
        Write-Host "Run the validation_protocols hardware scripts appropriate for the attached lab PC."
    } else {
        Write-Host ""
        Write-Host "== hardware checks skipped =="
        Write-Host "Pass -AllowHardware only on a configured lab PC with the required ASIO/LSL setup."
    }
}

Write-Host ""
Write-Host "All $Tier checks completed."
