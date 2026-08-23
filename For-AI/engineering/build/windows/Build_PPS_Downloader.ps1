param(
    [string]$Version = "",
    [ValidateSet("all", "designer", "runner", "full")]
    [string]$Component = "all",
    [string]$ManifestBaseUrl = "https://github.com/GeorgeFejer91/pps-kit/releases/latest/download",
    [switch]$SkipIconResource
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$DownloaderDir = Join-Path $Root "distributions\downloader"
$DistDir = Join-Path $Root "dist"
$IconPath = Join-Path $Root "packages\pps-resources\assets\app\pps_toolkit_icon.ico"

if (-not $Version) {
    $VersionLine = Get-Content -LiteralPath (Join-Path $Root "pyproject.toml") |
        Where-Object { $_ -match '^\s*version\s*=' } | Select-Object -First 1
    if (-not $VersionLine -or $VersionLine -notmatch '"([^"]+)"') {
        throw "Could not determine project version from pyproject.toml."
    }
    $Version = $Matches[1]
}

$Go = Get-Command go -ErrorAction SilentlyContinue
if (-not $Go -and (Test-Path -LiteralPath "C:\Program Files\Go\bin\go.exe")) {
    $Go = Get-Item -LiteralPath "C:\Program Files\Go\bin\go.exe"
}
if (-not $Go) {
    throw "Go is required to build the three lightweight PPS downloaders."
}
$GoExe = if ($Go.Source) { $Go.Source } else { $Go.FullName }

$Products = @(
    [pscustomobject]@{ Id = "designer"; Name = "PPS Experiment Designer"; File = "PPS-Designer-Downloader"; Manifest = "pps_designer_download_manifest.v1.json"; Payload = "designer_windows_x64" },
    [pscustomobject]@{ Id = "runner"; Name = "PPS Experiment Runner"; File = "PPS-Experiment-Runner-Downloader"; Manifest = "pps_runner_download_manifest.v1.json"; Payload = "runner_windows_x64" },
    [pscustomobject]@{ Id = "full"; Name = "PPS Toolkit"; File = "PPS-Toolkit-Downloader"; Manifest = "pps_toolkit_download_manifest.v1.json"; Payload = "full_windows_x64" }
)
if ($Component -ne "all") {
    $Products = @($Products | Where-Object { $_.Id -eq $Component })
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
$Syso = Join-Path $DownloaderDir "pps_downloader.syso"

Push-Location $DownloaderDir
try {
    if (-not $SkipIconResource) {
        if (-not (Test-Path -LiteralPath $IconPath)) { throw "PPS icon not found: $IconPath" }
        & $GoExe run github.com/akavel/rsrc@latest -ico $IconPath -o $Syso
        if ($LASTEXITCODE -ne 0) { throw "Could not generate Windows icon resource for downloader." }
    }

    foreach ($Product in $Products) {
        $ManifestUrl = "$($ManifestBaseUrl.TrimEnd('/'))/$($Product.Manifest)"
        $VersionedExe = Join-Path $DistDir "$($Product.File)-v$Version.exe"
        $LatestExe = Join-Path $DistDir "$($Product.File).exe"
        $LdFlags = "-s -w -H=windowsgui -X 'main.defaultManifestURL=$ManifestUrl' -X 'main.defaultPayloadKind=$($Product.Payload)' -X 'main.productID=$($Product.Id)' -X 'main.productName=$($Product.Name)' -X 'main.buildVersion=$Version'"
        $env:CGO_ENABLED = "0"
        & $GoExe build -trimpath -ldflags $LdFlags -o $VersionedExe .
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Copy-Item -LiteralPath $VersionedExe -Destination $LatestExe -Force
        $SizeBytes = (Get-Item -LiteralPath $VersionedExe).Length
        if ($SizeBytes -ge 100MB) { throw "$($Product.File) exceeds GitHub's 100 MiB limit." }
        $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $VersionedExe).Hash.ToLowerInvariant()
        Write-Host "$($Product.File).exe SHA256: $Hash"
    }
}
finally {
    Pop-Location
    if (Test-Path -LiteralPath $Syso) { Remove-Item -LiteralPath $Syso -Force }
}
