param(
    [switch]$Refresh
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ThirdParty = Join-Path $Root "third_party"
$Destination = Join-Path $ThirdParty "3dti_AudioToolkit"
$PinnedCommit = "6bfee08705675308a8c348b4c3a4d582586d2f99"
$ExpectedSha256 = "a96038866bf9d86420c6f871e611b1888add245d2cc3307341fedcb41cef6b82"
$ArchiveUrl = "https://github.com/3DTune-In/3dti_AudioToolkit/archive/$PinnedCommit.zip"
$Downloads = Join-Path $ThirdParty "_downloads"
$ArchivePath = Join-Path $Downloads "3dti_AudioToolkit-$PinnedCommit.zip"
$ExtractRoot = Join-Path $Downloads "3dti_AudioToolkit-$PinnedCommit-extract"

function Assert-UnderRoot {
    param(
        [string]$Path,
        [string]$AllowedRoot
    )
    $RootFull = (Resolve-Path -LiteralPath $AllowedRoot).Path
    $Full = [System.IO.Path]::GetFullPath($Path)
    if (-not $Full.StartsWith($RootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify path outside repository: $Full"
    }
}

New-Item -ItemType Directory -Force $ThirdParty | Out-Null

if ((Test-Path -LiteralPath $Destination) -and -not $Refresh) {
    Write-Host "3DTI source snapshot already exists:"
    Write-Host "  $Destination"
    Write-Host "Use -Refresh to replace it from the pinned archive."
    exit 0
}

New-Item -ItemType Directory -Force $Downloads | Out-Null
if (-not (Test-Path -LiteralPath $ArchivePath)) {
    Write-Host "Downloading pinned 3DTI archive..."
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ArchivePath
}

$ActualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToLowerInvariant()
if ($ActualSha256 -ne $ExpectedSha256) {
    throw "3DTI archive hash mismatch. Expected $ExpectedSha256 but got $ActualSha256."
}

if (Test-Path -LiteralPath $ExtractRoot) {
    Assert-UnderRoot -Path $ExtractRoot -AllowedRoot $ThirdParty
    Remove-Item -LiteralPath $ExtractRoot -Recurse -Force
}
New-Item -ItemType Directory -Force $ExtractRoot | Out-Null
Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExtractRoot

$ArchiveRoot = Get-ChildItem -LiteralPath $ExtractRoot -Directory | Select-Object -First 1
if (-not $ArchiveRoot) {
    throw "Pinned 3DTI archive did not contain a source directory."
}

if (Test-Path -LiteralPath $Destination) {
    Assert-UnderRoot -Path $Destination -AllowedRoot $ThirdParty
    Remove-Item -LiteralPath $Destination -Recurse -Force
}
New-Item -ItemType Directory -Force $Destination | Out-Null

$VendoredItems = @(
    "3dti_Toolkit",
    "3dti_ResourceManager",
    "docs",
    "3DTI_AUDIOTOOLKIT_LICENSE",
    "LICENSE",
    "Readme.md",
    "CHANGELOG.md",
    ".gitmodules"
)

foreach ($Item in $VendoredItems) {
    $Source = Join-Path $ArchiveRoot.FullName $Item
    if (Test-Path -LiteralPath $Source) {
        Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
    }
}

$UnreviewedAssetExtensions = @(".wav", ".mp3", ".flac", ".ogg", ".m4a", ".sofa")
Get-ChildItem -LiteralPath $Destination -Force -Recurse -File | Where-Object {
    $UnreviewedAssetExtensions -contains $_.Extension.ToLowerInvariant()
} | ForEach-Object {
    Assert-UnderRoot -Path $_.FullName -AllowedRoot $Destination
    Remove-Item -LiteralPath $_.FullName -Force
}

Get-ChildItem -LiteralPath $Destination -Force -Recurse -Directory -Filter ".vs" | ForEach-Object {
    Assert-UnderRoot -Path $_.FullName -AllowedRoot $ThirdParty
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
}

Write-Host "Pinned 3DTI source snapshot is ready:"
Write-Host "  $Destination"
Write-Host "Commit: $PinnedCommit"
Write-Host "Archive SHA256: $ActualSha256"
