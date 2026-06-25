param(
    [string]$Configuration = "Release",
    [switch]$PreconvertedHrtfOnly,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$SourceRoot = Join-Path $Root "third_party\3dti_AudioToolkit"
$WrapperRoot = Join-Path $Root "third_party\3dti_renderer"
$WrapperCMake = Join-Path $WrapperRoot "CMakeLists.txt"
$BuildDir = Join-Path $WrapperRoot "build"
$RendererExe = Join-Path $Root "third_party\3dti_renderer\bin\pps-3dti-renderer.exe"
$BundledSofaInclude = Join-Path $SourceRoot "3dti_ResourceManager\third_party_libraries\sofacoustics\libsofa\src"

if ((Test-Path -LiteralPath $RendererExe) -and -not $Force) {
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $RendererExe).Hash.ToLowerInvariant()
    Write-Host "3DTI renderer wrapper already exists:"
    Write-Host "  $RendererExe"
    Write-Host "SHA256: $Hash"
    exit 0
}

if (-not (Test-Path -LiteralPath $SourceRoot)) {
    throw "Pinned 3DTI source snapshot is missing. Run windows\Fetch_3DTI_Backend.ps1 first."
}

if (-not (Test-Path -LiteralPath $WrapperCMake)) {
    Write-Host "Pinned 3DTI source snapshot found:"
    Write-Host "  $SourceRoot"
    Write-Host ""
    Write-Host "The native wrapper CMake project is missing:"
    Write-Host "  $WrapperCMake"
    exit 2
}

$CMake = Get-Command cmake -ErrorAction SilentlyContinue
if (-not $CMake) {
    Write-Host "CMake is not available on PATH."
    Write-Host "Install CMake and a C++17 compiler, then rerun this script."
    Write-Host "The wrapper source and build contract are documented at:"
    Write-Host "  third_party\3dti_renderer\README.md"
    exit 2
}

$CMakeArgs = @(
    "-S", $WrapperRoot,
    "-B", $BuildDir
)
if ($PreconvertedHrtfOnly) {
    $CMakeArgs += "-DPPS_ENABLE_SOFA_READER=OFF"
} else {
    $CMakeArgs += "-DPPS_ENABLE_SOFA_READER=ON"
    $SofaInclude = $env:PPS_SOFA_INCLUDE_DIR
    $SofaLibrary = $env:PPS_SOFA_LIBRARY
    if ($SofaInclude -or $SofaLibrary) {
        if (-not $SofaInclude -or -not (Test-Path -LiteralPath (Join-Path $SofaInclude "SOFA.h"))) {
            Write-Host "PPS_SOFA_INCLUDE_DIR must point to the SOFA C++ include folder containing SOFA.h."
            Write-Host "Alternatively unset PPS_SOFA_INCLUDE_DIR/PPS_SOFA_LIBRARY to use the bundled SOFA reader, or run with -PreconvertedHrtfOnly."
            exit 2
        }
        if (-not $SofaLibrary -or -not (Test-Path -LiteralPath $SofaLibrary)) {
            Write-Host "PPS_SOFA_LIBRARY must point to the SOFA C++ library used by 3DTI."
            Write-Host "Alternatively unset PPS_SOFA_INCLUDE_DIR/PPS_SOFA_LIBRARY to use the bundled SOFA reader, or run with -PreconvertedHrtfOnly."
            exit 2
        }
        $CMakeArgs += "-DSOFA_INCLUDE_DIR=$SofaInclude"
        $CMakeArgs += "-DSOFA_LIBRARY=$SofaLibrary"
    } elseif (Test-Path -LiteralPath (Join-Path $BundledSofaInclude "SOFA.h")) {
        $CMakeArgs += "-DPPS_USE_BUNDLED_SOFA_READER=ON"
    } else {
        Write-Host "Bundled SOFA reader sources are missing:"
        Write-Host "  $BundledSofaInclude"
        Write-Host "Run with -PreconvertedHrtfOnly after adding a .3dti-hrtf cache, or vendor the SOFA submodule."
        exit 2
    }
}

& $CMake.Source @CMakeArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $CMake.Source --build $BuildDir --config $Configuration
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$ConfiguredRendererExe = Join-Path $WrapperRoot "bin\$Configuration\pps-3dti-renderer.exe"
if (Test-Path -LiteralPath $ConfiguredRendererExe) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $RendererExe) | Out-Null
    Copy-Item -LiteralPath $ConfiguredRendererExe -Destination $RendererExe -Force
    Get-ChildItem -LiteralPath (Split-Path -Parent $ConfiguredRendererExe) -Filter "*.dll" -File -ErrorAction SilentlyContinue |
        Copy-Item -Destination (Split-Path -Parent $RendererExe) -Force
} elseif (-not (Test-Path -LiteralPath $RendererExe)) {
    Write-Host "Build finished but expected renderer was not found:"
    Write-Host "  $RendererExe"
    Write-Host "  $ConfiguredRendererExe"
    exit 2
} else {
    Get-ChildItem -LiteralPath (Split-Path -Parent $RendererExe) -Filter "*.dll" -File -ErrorAction SilentlyContinue | Out-Null
}

$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $RendererExe).Hash.ToLowerInvariant()
Write-Host "Built 3DTI renderer wrapper:"
Write-Host "  $RendererExe"
Write-Host "SHA256: $Hash"
