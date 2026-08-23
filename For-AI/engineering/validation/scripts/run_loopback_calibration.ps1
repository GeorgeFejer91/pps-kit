[CmdletBinding()]
param(
    [string]$DeviceQuery = "Komplete",
    [int]$SampleRate = 44100,
    [int]$Channels = 3,
    [double]$Latency = 0.010,
    [int]$Blocksize = 256,
    [int]$SmokePulseCount = 5,
    [double]$SmokeAmplitude = 0.03,
    [int]$PulseCount = 30,
    [double]$Amplitude = 0.05,
    [double]$MaxSafeAmplitude = 0.10,
    [int]$Repeats = 5,
    [switch]$EstablishBaseline,
    [string]$SessionDir = "",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

if ($SmokeAmplitude -le 0 -or $Amplitude -le 0) {
    throw "Validation amplitudes must be positive."
}
if ($SmokeAmplitude -gt $MaxSafeAmplitude -or $Amplitude -gt $MaxSafeAmplitude) {
    throw "Refusing hardware playback above MaxSafeAmplitude=$MaxSafeAmplitude. Lower interface/input gain or fix routing instead of raising the digital test level."
}

if (-not $OutputRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputRoot = Join-Path $RepoRoot "artifacts\validation_runs\loopback_calibration_$stamp"
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$manifest = [ordered]@{
    schema = "pps-internal-validation-run.v1"
    protocol = "loopback_calibration"
    created_at = (Get-Date).ToString("o")
    output_root = (Resolve-Path $OutputRoot).Path
    device_query = $DeviceQuery
    sample_rate = $SampleRate
    channels = $Channels
    latency = $Latency
    blocksize = $Blocksize
    smoke_pulse_count = $SmokePulseCount
    smoke_amplitude = $SmokeAmplitude
    pulse_count = $PulseCount
    amplitude = $Amplitude
    repeats = $Repeats
    establish_baseline = [bool]$EstablishBaseline
    session_dir = $SessionDir
    notes = "Internal wrapper around pps-latency-validate; measures electrical route, not Woojer mechanical onset."
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 (Join-Path $OutputRoot "validation_run_manifest.json")

function Invoke-CheckedPython {
    param([string[]]$Arguments)
    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "python $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

Write-Host "Writing route specs..."
Invoke-CheckedPython @(
    "-m", "peripersonal_space_toolkit.latency_validation",
    "specs",
    "--output-dir", $OutputRoot,
    "--device-query", $DeviceQuery
)

Write-Host "Running low-amplitude smoke calibration..."
Invoke-CheckedPython @(
    "-m", "peripersonal_space_toolkit.latency_validation",
    "calibrate",
    "--output-dir", $OutputRoot,
    "--device-query", $DeviceQuery,
    "--sample-rate", "$SampleRate",
    "--channels", "$Channels",
    "--latency", "$Latency",
    "--blocksize", "$Blocksize",
    "--pulse-count", "$SmokePulseCount",
    "--amplitude", "$SmokeAmplitude"
)

if ($EstablishBaseline) {
    Write-Host "Establishing official baseline..."
    Invoke-CheckedPython @(
        "-m", "peripersonal_space_toolkit.latency_validation",
        "calibrate",
        "--output-dir", $OutputRoot,
        "--device-query", $DeviceQuery,
        "--sample-rate", "$SampleRate",
        "--channels", "$Channels",
        "--latency", "$Latency",
        "--blocksize", "$Blocksize",
        "--pulse-count", "$PulseCount",
        "--amplitude", "$Amplitude",
        "--establish-baseline"
    )
}

for ($i = 1; $i -le $Repeats; $i++) {
    Write-Host "Running calibration repeat $i of $Repeats..."
    Invoke-CheckedPython @(
        "-m", "peripersonal_space_toolkit.latency_validation",
        "calibrate",
        "--output-dir", $OutputRoot,
        "--device-query", $DeviceQuery,
        "--sample-rate", "$SampleRate",
        "--channels", "$Channels",
        "--latency", "$Latency",
        "--blocksize", "$Blocksize",
        "--pulse-count", "$PulseCount",
        "--amplitude", "$Amplitude"
    )
}

if ($SessionDir) {
    $SessionAnalysis = Join-Path $OutputRoot "session_validation"
    New-Item -ItemType Directory -Force -Path $SessionAnalysis | Out-Null
    Write-Host "Validating session loopback recordings from $SessionDir..."
    Invoke-CheckedPython @(
        "-m", "peripersonal_space_toolkit.latency_validation",
        "validate-session",
        "--session-dir", $SessionDir,
        "--output-dir", $SessionAnalysis
    )
}

Write-Host "Loopback calibration protocol complete: $OutputRoot"
