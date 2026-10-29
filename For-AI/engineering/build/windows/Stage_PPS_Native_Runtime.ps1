param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$SevenZipPath,
    [string]$LockPath = (Join-Path $PSScriptRoot 'native-runtime-lock.json')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Development/CI only. Never execute a redistributable or read installed CRTs.
function Assert-Hash([string]$Path, [string]$Expected) {
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Expected) {
        throw "Runtime SHA256 mismatch: $([IO.Path]::GetFileName($Path))"
    }
}
function Expand-Selected([string]$Archive, [string]$Directory, [string[]]$Names) {
    $arguments = @('e', '-y', '-bd', '-bso0', '-bsp0', "-o$Directory", $Archive) + $Names
    & $SevenZipPath @arguments
    if ($LASTEXITCODE -ne 0) { throw "7z extraction failed: $([IO.Path]::GetFileName($Archive))" }
}
function Download-Locked($Origin, [string]$Path) {
    $uri = [Uri]$Origin.url
    if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'download.visualstudio.microsoft.com') {
        throw 'Runtime origin must be the locked official Microsoft HTTPS endpoint.'
    }
    Add-Type -AssemblyName System.Net.Http
    $client = [Net.Http.HttpClient]::new()
    $response = $null; $source = $null; $target = $null
    try {
        $response = $client.GetAsync($uri, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
        $response.EnsureSuccessStatusCode() | Out-Null
        $source = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $target = [IO.File]::Open($Path, [IO.FileMode]::CreateNew)
        $buffer = New-Object byte[] 65536
        $total = 0L
        while (($count = $source.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $total += $count
            if ($total -gt [long]$Origin.size_bytes) { throw 'Runtime download exceeds locked size.' }
            $target.Write($buffer, 0, $count)
        }
        if ($total -ne [long]$Origin.size_bytes) { throw 'Runtime download is truncated.' }
    } finally {
        if ($target) { $target.Dispose() }; if ($source) { $source.Dispose() }
        if ($response) { $response.Dispose() }; $client.Dispose()
    }
    Assert-Hash $Path $Origin.sha256
}

if (-not $SevenZipPath) {
    $command = Get-Command 7z -ErrorAction SilentlyContinue
    $SevenZipPath = if ($command) { $command.Source } else { Join-Path $env:ProgramFiles '7-Zip/7z.exe' }
}
$SevenZipPath = (Resolve-Path -LiteralPath $SevenZipPath).Path
$lock = Get-Content -LiteralPath $LockPath -Raw | ConvertFrom-Json
if ($lock.schema -ne 'pps-native-windows-runtime-lock.v1' -or $lock.architecture -ne 'x64' -or $lock.files.Count -ne 6) {
    throw 'Unexpected native runtime lock contract.'
}
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Runtime output must be a fresh directory.' }
$work = Join-Path $output '.staging'
New-Item -ItemType Directory -Path $work | Out-Null
$work = (Resolve-Path -LiteralPath $work).Path
$receipt = [ordered]@{schema='pps-native-runtime-stage.v1'; lock_sha256=(Get-FileHash -LiteralPath $LockPath -Algorithm SHA256).Hash.ToLowerInvariant(); origins=@(); files=@()}
try {
    foreach ($name in @('vc2013', 'vc14')) {
        $origin = $lock.origins.$name
        $directory = Join-Path $work $name
        New-Item -ItemType Directory -Path $directory | Out-Null
        $executable = Join-Path $directory 'redistributable.exe'
        Download-Locked $origin $executable
        $cabinet = Join-Path $directory 'attached.cab'
        $inputStream = [IO.File]::OpenRead($executable)
        $outputStream = [IO.File]::Open($cabinet, [IO.FileMode]::CreateNew)
        try {
            $inputStream.Position = [long]$origin.attached_cabinet.offset
            $remaining = [long]$origin.attached_cabinet.size_bytes
            if ($remaining -le 0 -or $inputStream.Position + $remaining -gt $inputStream.Length) { throw 'Locked CAB bounds invalid.' }
            $buffer = New-Object byte[] 65536
            while ($remaining -gt 0) {
                $count = $inputStream.Read($buffer, 0, [int][Math]::Min($remaining, $buffer.Length))
                if ($count -eq 0) { throw 'Truncated embedded CAB.' }
                $outputStream.Write($buffer, 0, $count); $remaining -= $count
            }
        } finally { $inputStream.Dispose(); $outputStream.Dispose() }
        Assert-Hash $cabinet $origin.attached_cabinet.sha256
        $licenseDirectory = Join-Path $directory 'license'
        $payloadDirectory = Join-Path $directory 'payload'
        $runtimeDirectory = Join-Path $directory 'runtime'
        Expand-Selected $executable $licenseDirectory @($origin.license_payload)
        Expand-Selected $cabinet $payloadDirectory @($origin.runtime_payload)
        Expand-Selected (Join-Path $payloadDirectory $origin.runtime_payload) $runtimeDirectory @()
        $candidates = @(Get-ChildItem -LiteralPath $licenseDirectory,$runtimeDirectory -File -Recurse | ForEach-Object {
            [pscustomobject]@{Path=$_.FullName; Hash=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
        })
        foreach ($entry in @($lock.files | Where-Object origin -eq $name)) {
            if ([IO.Path]::GetFileName($entry.file) -cne $entry.file) { throw 'Runtime lock filename must be a basename.' }
            $matches = @($candidates | Where-Object Hash -CEQ $entry.sha256)
            if ($matches.Count -ne 1) { throw "Expected exactly one locked payload: $($entry.file)" }
            $destination = Join-Path $output $entry.file
            Copy-Item -LiteralPath $matches[0].Path -Destination $destination
            Assert-Hash $destination $entry.sha256
            $receipt.files += [ordered]@{file=$entry.file; sha256=$entry.sha256; origin=$name}
        }
        $receipt.origins += [ordered]@{origin=$name; url=$origin.url; sha256=$origin.sha256}
        # This directory was created by this invocation under its fresh output.
        $resolved = (Resolve-Path -LiteralPath $directory).Path
        if (-not $resolved.StartsWith($work + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Scratch containment check failed.' }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $output 'runtime-stage.json') -Encoding UTF8
    Write-Output "Staged and hash-verified all six locked runtime files: $output"
} finally {
    # No pre-existing artifacts, caches or installation directories are removed.
    $resolvedOutput = (Resolve-Path -LiteralPath $output).Path
    if ($work -ne (Join-Path $resolvedOutput '.staging')) { throw 'Scratch root containment check failed.' }
    if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
}
