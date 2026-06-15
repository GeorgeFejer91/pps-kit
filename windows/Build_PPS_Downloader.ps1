param(
    [string]$Version = "",
    [string]$ManifestUrl = "https://github.com/GeorgeFejer91/peripersonal-space-toolkit/releases/latest/download/pps_download_manifest.v1.json",
    [switch]$SkipIconResource
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DownloaderDir = Join-Path $Root "windows\downloader"
$DistDir = Join-Path $Root "dist"
$IconPath = Join-Path $Root "src\peripersonal_space_toolkit\assets\pps_toolkit_icon.ico"

if (-not $Version) {
    $Pyproject = Get-Content -LiteralPath (Join-Path $Root "pyproject.toml")
    $VersionLine = $Pyproject | Where-Object { $_ -match '^\s*version\s*=' } | Select-Object -First 1
    if (-not $VersionLine -or $VersionLine -notmatch '"([^"]+)"') {
        throw "Could not determine project version from pyproject.toml."
    }
    $Version = $Matches[1]
}

$Go = Get-Command go -ErrorAction SilentlyContinue
if (-not $Go) {
    throw "Go is required to build the lightweight downloader. Install Go for Windows, then rerun windows\Build_PPS_Downloader.ps1."
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
$VersionedExe = Join-Path $DistDir "PPS-Toolkit-Downloader-v$Version.exe"
$LatestExe = Join-Path $DistDir "PPS-Toolkit-Downloader.exe"
$Syso = Join-Path $DownloaderDir "pps_downloader.syso"

Push-Location $DownloaderDir
try {
    if (-not $SkipIconResource) {
        if (-not (Test-Path -LiteralPath $IconPath)) {
            throw "PPS icon not found: $IconPath"
        }
        Write-Host "Embedding PPS icon resource..."
        & $Go.Source run github.com/akavel/rsrc@latest -ico $IconPath -o $Syso
        if ($LASTEXITCODE -ne 0) {
            throw "Could not generate Windows icon resource for downloader."
        }
    }

    Write-Host "Building PPS lightweight downloader..."
    $env:CGO_ENABLED = "0"
    $LdFlags = "-s -w -H=windowsgui -X main.defaultManifestURL=$ManifestUrl -X main.buildVersion=$Version"
    & $Go.Source build -trimpath -ldflags $LdFlags -o $VersionedExe .
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $Syso) {
        Remove-Item -LiteralPath $Syso -Force
    }
}

if (-not (Test-Path -LiteralPath $VersionedExe)) {
    throw "Expected downloader was not created: $VersionedExe"
}

Copy-Item -LiteralPath $VersionedExe -Destination $LatestExe -Force
$SizeBytes = (Get-Item -LiteralPath $VersionedExe).Length
$SizeMiB = [Math]::Round($SizeBytes / 1MB, 2)

if ($SizeBytes -ge 100MB) {
    throw "Downloader is $SizeMiB MiB, which exceeds the hard 100 MiB GitHub file limit."
}
elseif ($SizeBytes -ge 50MB) {
    Write-Warning "Downloader is $SizeMiB MiB. It is under 100 MiB but above GitHub's 50 MiB warning threshold."
}
elseif ($SizeBytes -lt 25MB) {
    Write-Host "Downloader size check passed: $SizeMiB MiB (<25 MiB preferred target)."
}
else {
    Write-Host "Downloader size check passed: $SizeMiB MiB (<50 MiB warning threshold)."
}

$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $VersionedExe).Hash.ToLowerInvariant()
Write-Host "Built PPS lightweight downloader:"
Write-Host "  $VersionedExe"
Write-Host "  $LatestExe"
Write-Host "SHA256: $Hash"

