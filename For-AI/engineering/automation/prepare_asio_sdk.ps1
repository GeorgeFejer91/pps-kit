$ErrorActionPreference = 'Stop'

$sdkUrl = 'https://download.steinberg.net/sdk_downloads/ASIO-SDK_2.3.4_2025-10-15.zip'
$expectedSha256 = 'd5ebf0c20dd2c5f43771fd0c1418f4b361bf52434ee670097cfa6b3a335e2eca'
if (-not $env:RUNNER_TEMP -or -not $env:GITHUB_ENV) {
    throw 'This pinned ASIO SDK setup requires a GitHub Actions runner.'
}

$root = Join-Path $env:RUNNER_TEMP 'pps-asio-sdk-2.3.4'
$archive = Join-Path $root 'ASIO-SDK_2.3.4_2025-10-15.zip'
New-Item -ItemType Directory -Force -Path $root | Out-Null
Invoke-WebRequest -Uri $sdkUrl -OutFile $archive -TimeoutSec 120
$actualSha256 = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha256 -ne $expectedSha256) {
    throw "Steinberg ASIO SDK archive hash mismatch: $actualSha256"
}

Expand-Archive -LiteralPath $archive -DestinationPath $root -Force
$sdk = Join-Path $root 'ASIOSDK'
foreach ($relative in @('LICENSE.txt', 'common/asio.h', 'common/asiosys.h', 'host/asiodrivers.h')) {
    if (-not (Test-Path -LiteralPath (Join-Path $sdk $relative) -PathType Leaf)) {
        throw "Pinned ASIO SDK lacks $relative"
    }
}
"CPAL_ASIO_DIR=$sdk" | Out-File -FilePath $env:GITHUB_ENV -Encoding utf8 -Append
@(
    'schema=pps-asio-sdk-build-input.v1'
    'sdk_version=2.3.4'
    "archive_url=$sdkUrl"
    "archive_sha256=$actualSha256"
    'distribution_license_choice=pending'
) | Set-Content -LiteralPath (Join-Path $env:RUNNER_TEMP 'pps-asio-sdk-provenance.txt') -Encoding ascii
