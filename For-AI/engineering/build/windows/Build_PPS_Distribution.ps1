param(
    [string]$Version = "",
    [string]$PayloadBaseUrl = "",
    [string]$ZenodoDoi = "",
    [switch]$SkipAudit,
    [switch]$SkipApplicationBuilds,
    [switch]$SkipDownloaderBuild
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$DistDir = Join-Path $Root "dist"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "For-AI\engineering\build\windows\Setup_Windows_App.ps1")
}
if (-not (Test-Path -LiteralPath $Python)) { throw "Python environment was not created at $Python" }

if (-not $Version) {
    $VersionLine = Get-Content -LiteralPath (Join-Path $Root "pyproject.toml") |
        Where-Object { $_ -match '^\s*version\s*=' } | Select-Object -First 1
    if (-not $VersionLine -or $VersionLine -notmatch '"([^"]+)"') { throw "Could not read project version." }
    $Version = $Matches[1]
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
if (-not $SkipAudit) {
    & $Python (Join-Path $Root "For-AI\engineering\release\tools\release_audit.py")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if (-not $SkipApplicationBuilds) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "For-AI\engineering\build\windows\Build_PPS_Designer.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "For-AI\engineering\build\windows\Build_Experiment_Runner_Exe.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$Products = @(
    [pscustomobject]@{ Id = "designer"; Stem = "PPS-Designer"; Manifest = "pps_designer_download_manifest.v1.json" },
    [pscustomobject]@{ Id = "runner"; Stem = "PPS-Experiment-Runner"; Manifest = "pps_runner_download_manifest.v1.json" },
    [pscustomobject]@{ Id = "full"; Stem = "PPS-Toolkit"; Manifest = "pps_toolkit_download_manifest.v1.json" }
)

foreach ($Product in $Products) {
    $PackageName = "$($Product.Stem)-v$Version-windows-x64"
    $StageRoot = Join-Path $DistDir "$PackageName.stage"
    $Zip = Join-Path $DistDir "$PackageName.zip"
    & $Python (Join-Path $Root "For-AI\engineering\release\tools\assemble_component.py") --component $Product.Id --output $StageRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python (Join-Path $Root "For-AI\engineering\release\tools\make_offline_lab_zip.py") --source-dir $StageRoot --output $Zip
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $PayloadUrl = if ($PayloadBaseUrl) {
        "$($PayloadBaseUrl.TrimEnd('/'))/$PackageName.zip"
    } else {
        "https://zenodo.org/records/REPLACE_WITH_RECORD/files/$PackageName.zip?download=1"
    }
    $ManifestPath = Join-Path $DistDir $Product.Manifest
    $ManifestArgs = @(
        (Join-Path $Root "For-AI\engineering\release\tools\make_download_manifest.py"),
        "--component", $Product.Id,
        "--payload", $Zip,
        "--payload-url", $PayloadUrl,
        "--output", $ManifestPath,
        "--version", $Version,
        "--source-tag", "v$Version",
        "--package-inventory", (Join-Path $StageRoot "pps_package_inventory.v1.json")
    )
    if ($ZenodoDoi) { $ManifestArgs += @("--zenodo-doi", $ZenodoDoi) }
    & $Python @ManifestArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not $SkipDownloaderBuild) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "For-AI\engineering\build\windows\Build_PPS_Downloader.ps1") -Version $Version
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$DownloaderStatus = if ($SkipDownloaderBuild) { "bootstrapper build skipped" } else { "bootstrapper variants built" }
Write-Host "Built Designer, Runner, and Full payloads, inventories, and download manifests in $DistDir ($DownloaderStatus)"
