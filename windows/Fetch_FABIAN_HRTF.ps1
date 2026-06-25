param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$AssetDir = Join-Path $Root "assets\0. Head-Related Impulse Response (HRIR) model"
$SofaFile = Join-Path $AssetDir "FABIAN_HRIR_measured_HATO_0.sofa"
$ManifestPath = Join-Path $AssetDir "FABIAN_HRIR_measured_HATO_0.manifest.json"
$SofaUrl = "https://sofacoustics.org/data/database/tu-berlin/FABIAN_HRIR_measured_HATO_0.sofa"
$DepositOnceRecord = "https://depositonce.tu-berlin.de/items/3b423df7-a764-4ce1-9065-4e6034bba759"

New-Item -ItemType Directory -Force $AssetDir | Out-Null

if ((Test-Path -LiteralPath $SofaFile) -and -not $Force) {
    Write-Host "FABIAN SOFA file already exists:"
    Write-Host "  $SofaFile"
    Write-Host "Use -Force to download it again."
} else {
    Write-Host "Downloading standardized FABIAN HRIR resource..."
    Write-Host "  $SofaUrl"
    Invoke-WebRequest -Uri $SofaUrl -OutFile $SofaFile
}

$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $SofaFile).Hash.ToLowerInvariant()
$Length = (Get-Item -LiteralPath $SofaFile).Length
$Manifest = [ordered]@{
    id = "fabian_tu_berlin_hato_0"
    label = "FABIAN neutral HRIR, HATO 0"
    role = "fixed_standard_listener_hrir"
    experimenter_visible = $false
    file = "assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa"
    sha256 = $Hash
    bytes = $Length
    source_record = $DepositOnceRecord
    sofa_mirror = $SofaUrl
    license = "CC BY 4.0 according to the DepositOnce FABIAN record"
}
$Manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

Write-Host "FABIAN HRIR resource ready:"
Write-Host "  $SofaFile"
Write-Host "SHA256: $Hash"
Write-Host "Manifest:"
Write-Host "  $ManifestPath"
