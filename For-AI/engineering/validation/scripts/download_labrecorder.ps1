param(
    [string]$OutputDir = "local_data\software_installers\labrecorder",
    [string]$ExtractDir = "local_data\software_tools\labrecorder"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null

$headers = @{ "User-Agent" = "pps-validation-dependency-audit" }
$release = Invoke-RestMethod `
    -Uri "https://api.github.com/repos/labstreaminglayer/App-LabRecorder/releases/latest" `
    -Headers $headers

$releaseJson = Join-Path $OutputDir "latest_release.json"
$release | ConvertTo-Json -Depth 8 | Set-Content -Path $releaseJson -Encoding UTF8

$assets = @($release.assets)
$windowsAsset = $assets |
    Where-Object { $_.name -match "(?i)win.*\.zip$|windows.*\.zip$" } |
    Select-Object -First 1

if ($null -eq $windowsAsset) {
    $assets |
        Select-Object name,browser_download_url,size,content_type |
        ConvertTo-Json -Depth 4 |
        Set-Content -Path (Join-Path $OutputDir "available_assets.json") -Encoding UTF8
    throw "No Windows LabRecorder zip was found in the latest release assets."
}

$zipPath = Join-Path $OutputDir $windowsAsset.name
Invoke-WebRequest -Uri $windowsAsset.browser_download_url -OutFile $zipPath -Headers $headers

$hash = Get-FileHash -Algorithm SHA256 -Path $zipPath
$hash | Select-Object Algorithm,Hash,Path |
    ConvertTo-Json |
    Set-Content -Path (Join-Path $OutputDir "downloaded_asset_sha256.json") -Encoding UTF8

@{
    downloaded_asset = $windowsAsset.name
    source = $windowsAsset.browser_download_url
    path = $zipPath
    sha256 = $hash.Hash
    downloaded_at = (Get-Date).ToString("s")
} | ConvertTo-Json | Set-Content -Path (Join-Path $OutputDir "download_manifest.json") -Encoding UTF8

Expand-Archive -LiteralPath $zipPath -DestinationPath $ExtractDir -Force

Get-ChildItem -Path $ExtractDir -Recurse -Filter "LabRecorder*.exe" |
    Select-Object FullName,Length,LastWriteTime |
    Format-Table
