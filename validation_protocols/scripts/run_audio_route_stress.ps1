[CmdletBinding()]
param(
    [string]$DeviceQuery = "Komplete",
    [int]$SampleRate = 44100,
    [int[]]$Channels = @(3),
    [string[]]$Latencies = @("0.010"),
    [int[]]$Blocksizes = @(256),
    [double]$DurationS = 10.0,
    [ValidateSet("write", "callback", "both")]
    [string]$Mode = "callback",
    [int]$Iterations = 5,
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

if (-not $OutputRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputRoot = Join-Path $RepoRoot "artifacts\validation_runs\audio_route_stress_$stamp"
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$manifest = [ordered]@{
    schema = "pps-internal-validation-run.v1"
    protocol = "audio_route_stress"
    created_at = (Get-Date).ToString("o")
    output_root = (Resolve-Path $OutputRoot).Path
    device_query = $DeviceQuery
    sample_rate = $SampleRate
    channels = $Channels
    latencies = $Latencies
    blocksizes = $Blocksizes
    duration_s = $DurationS
    mode = $Mode
    iterations = $Iterations
    notes = "Internal stress protocol wrapper around peripersonal_space_toolkit.audio_device_stress."
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $OutputRoot "validation_run_manifest.json")

$argsList = @(
    "-m", "peripersonal_space_toolkit.audio_device_stress",
    "--device-query", $DeviceQuery,
    "--output-dir", $OutputRoot,
    "--sample-rate", "$SampleRate",
    "--channels"
)
$argsList += $Channels | ForEach-Object { "$_" }
$argsList += @("--latencies")
$argsList += $Latencies
$argsList += @("--blocksizes")
$argsList += $Blocksizes | ForEach-Object { "$_" }
$argsList += @(
    "--duration-s", "$DurationS",
    "--mode", $Mode,
    "--iterations", "$Iterations"
)

Write-Host "Running audio route stress. Output: $OutputRoot"
& python @argsList
if ($LASTEXITCODE -ne 0) {
    throw "audio_device_stress failed with exit code $LASTEXITCODE"
}

Write-Host "Audio route stress complete: $OutputRoot"
