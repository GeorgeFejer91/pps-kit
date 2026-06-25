param(
    [string]$Version = "",
    [string]$ZenodoPayloadUrl = "",
    [string]$ZenodoDoi = "",
    [switch]$SkipAudit,
    [switch]$SkipRunnerBuild,
    [switch]$SkipDashboardBuild,
    [switch]$SkipDownloaderBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DistDir = Join-Path $Root "dist"

function Get-ProjectVersion {
    $Pyproject = Get-Content -LiteralPath (Join-Path $Root "pyproject.toml")
    $VersionLine = $Pyproject | Where-Object { $_ -match '^\s*version\s*=' } | Select-Object -First 1
    if (-not $VersionLine -or $VersionLine -notmatch '"([^"]+)"') {
        throw "Could not determine project version from pyproject.toml."
    }
    return $Matches[1]
}

function Copy-RepoItem {
    param(
        [string]$RelativePath,
        [string]$DestinationRoot
    )
    $Source = Join-Path $Root $RelativePath
    if (-not (Test-Path -LiteralPath $Source)) {
        return
    }
    $Destination = Join-Path $DestinationRoot $RelativePath
    if ((Get-Item -LiteralPath $Source).PSIsContainer) {
        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        & robocopy $Source $Destination /E /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) {
            throw "robocopy failed while copying $RelativePath with exit code $LASTEXITCODE"
        }
        $global:LASTEXITCODE = 0
    }
    else {
        $DestinationParent = Split-Path -Parent $Destination
        New-Item -ItemType Directory -Force -Path $DestinationParent | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
}

function Get-BuildPython {
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $Python)) {
        powershell -ExecutionPolicy Bypass -File (Join-Path $Root "windows\Setup_Windows_App.ps1")
    }
    if (-not (Test-Path -LiteralPath $Python)) {
        throw "Python environment was not created at $Python"
    }
    return $Python
}

if (-not $Version) {
    $Version = Get-ProjectVersion
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

if (-not $SkipAudit) {
    $Python = Get-BuildPython
    & $Python (Join-Path $Root "tools\release_audit.py")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if (-not $SkipRunnerBuild) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "windows\Build_Experiment_Runner_Exe.ps1")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

if (-not $SkipDashboardBuild) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "windows\Build_Dashboard_Launcher_Exe.ps1")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$Python = Get-BuildPython

$StageName = "PPS-Toolkit-v$Version-offline-lab-windows-x64"
$StageRoot = Join-Path $DistDir "$StageName.stage.$(Get-Date -Format 'yyyyMMddHHmmss')"
$HeavyZip = Join-Path $DistDir "$StageName.zip"

New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null

$Items = @(
    "README.md",
    "LICENSE",
    "CITATION.cff",
    "THIRD_PARTY_LICENSES.md",
    "AGENTS.md",
    "pyproject.toml",
    "index.html",
    ".nojekyll",
    "configs",
    "docs",
    "installer_protocols",
    "src",
    "study_templates",
    "assets",
    "data\sample",
    "third_party\3dti_renderer\bin",
    "third_party\3dti_AudioToolkit",
    "tools",
    "windows"
)

foreach ($Item in $Items) {
    Copy-RepoItem -RelativePath $Item -DestinationRoot $StageRoot
}

$RunnerDir = Join-Path $Root "dist\PPSExperimentRunner"
if (Test-Path -LiteralPath $RunnerDir) {
    $RunnerDestination = Join-Path $StageRoot "dist\PPSExperimentRunner"
    New-Item -ItemType Directory -Force -Path $RunnerDestination | Out-Null
    & robocopy $RunnerDir $RunnerDestination /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed while copying packaged runner with exit code $LASTEXITCODE"
    }
    $global:LASTEXITCODE = 0
}
else {
    Write-Warning "Packaged Focus Mode runner was not found at dist\PPSExperimentRunner."
}

$DashboardLauncherDir = Join-Path $Root "dist\PPSDashboardLauncher"
if (Test-Path -LiteralPath $DashboardLauncherDir) {
    $DashboardLauncherDestination = Join-Path $StageRoot "dist\PPSDashboardLauncher"
    New-Item -ItemType Directory -Force -Path $DashboardLauncherDestination | Out-Null
    & robocopy $DashboardLauncherDir $DashboardLauncherDestination /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed while copying packaged dashboard launcher with exit code $LASTEXITCODE"
    }
    $global:LASTEXITCODE = 0
}
else {
    Write-Warning "Packaged dashboard launcher was not found at dist\PPSDashboardLauncher."
}

$PackageInventoryPath = Join-Path $StageRoot "pps_package_inventory.v1.json"
& $Python (Join-Path $Root "tools\package_inventory.py") --stage-root $StageRoot --output $PackageInventoryPath --strict
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (Test-Path -LiteralPath $HeavyZip) {
    Remove-Item -LiteralPath $HeavyZip -Force
}
& $Python (Join-Path $Root "tools\make_offline_lab_zip.py") --source-dir $StageRoot --output $HeavyZip
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
$HeavyHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $HeavyZip).Hash.ToLowerInvariant()
Write-Host "Built offline lab package:"
Write-Host "  $HeavyZip"
Write-Host "SHA256: $HeavyHash"

if (-not $ZenodoPayloadUrl) {
    $ZenodoPayloadUrl = "https://zenodo.org/records/REPLACE_WITH_RECORD/files/$StageName.zip?download=1"
    Write-Warning "Using placeholder Zenodo payload URL in manifest. Regenerate after uploading the heavy ZIP."
}

$ManifestPath = Join-Path $DistDir "pps_download_manifest.v1.json"
$ManifestArgs = @(
    (Join-Path $Root "tools\make_download_manifest.py"),
    "--payload", $HeavyZip,
    "--payload-url", $ZenodoPayloadUrl,
    "--output", $ManifestPath,
    "--version", $Version,
    "--source-tag", "v$Version",
    "--package-inventory", $PackageInventoryPath
)
if ($ZenodoDoi) {
    $ManifestArgs += @("--zenodo-doi", $ZenodoDoi)
}
& $Python @ManifestArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (-not $SkipDownloaderBuild) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "windows\Build_PPS_Downloader.ps1")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Write-Host "Distribution outputs are in:"
Write-Host "  $DistDir"
