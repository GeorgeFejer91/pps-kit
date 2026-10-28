[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$CandidateDirectory,
    [Parameter(Mandatory)][string]$OutputDirectory
)

# This destructive-to-its-own-test-profile check runs only on a disposable CI
# account. Never redirect an existing user's app data to make a test pass.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true') { throw 'Run installed candidate checks on the disposable GitHub Windows account.' }
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../..')).Path
$CandidateDirectory = (Resolve-Path -LiteralPath $CandidateDirectory).Path
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Installed evidence directory must be new.' }
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$Node = (Get-Command node -ErrorAction Stop).Source
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$manifest = Get-Content -LiteralPath (Join-Path $CandidateDirectory 'candidate-manifest.json') -Raw | ConvertFrom-Json
$revision = (git -C $Root rev-parse HEAD).Trim()
if ($LASTEXITCODE -or $manifest.source_commit -ne $revision) { throw 'Candidate is not from this verified source revision.' }
$report = [ordered]@{schema='pps-native-installed-software.v1'; source_commit=$revision; applications=@(); passed=$false;
    scope='Fresh CI account: exact installed payloads, actual native WebView controls and startup. Complete synthetic execution is audited separately.';
    physical_timing_qualified=$false; native_file_dialogs='not_assessed'; clean_windows_without_webview='not_assessed'}
try {
    New-Item -ItemType Directory -Force -Path (Join-Path $Root 'artifacts/ui-workflow-check') | Out-Null
    foreach ($app in @('designer', 'runner')) {
        $config = Get-Content -LiteralPath (Join-Path $Root "apps/$app/src-tauri/tauri.conf.json") -Raw | ConvertFrom-Json
        $data = Join-Path $env:LOCALAPPDATA $config.identifier
        if (Test-Path -LiteralPath $data) { throw "Existing $app profile must be preserved; use a fresh CI account." }
        $asset = @($manifest.artifacts | Where-Object { $_.app -eq $app })
        if ($asset.Count -ne 1) { throw "Expected exactly one $app installer" }
        $installer = Join-Path $CandidateDirectory $asset[0].file
        if ((Hash $installer) -ne $asset[0].sha256) { throw 'Installer digest changed.' }
        $install = Join-Path $OutputDirectory "apps/$app"
        $process = Start-Process -FilePath $installer -ArgumentList @('/S', "/D=$install") -PassThru -Wait -WindowStyle Hidden
        if ($process.ExitCode) { throw "$app installer failed: $($process.ExitCode)" }
        $overlay = Get-Content -LiteralPath (Join-Path $CandidateDirectory "$app.candidate.conf.json") -Raw | ConvertFrom-Json -AsHashtable
        $expected = @{}
        foreach ($source in $overlay.bundle.resources.Keys) {
            $destination = $overlay.bundle.resources[$source]
            if ($null -eq $destination) { continue }
            $item = Get-Item -LiteralPath $source
            if ($item.PSIsContainer) {
                foreach ($file in Get-ChildItem -LiteralPath $source -Recurse -File) {
                    $relative = Join-Path $destination ([IO.Path]::GetRelativePath($item.FullName, $file.FullName))
                    $expected[$relative.Replace('\', '/')] = Hash $file.FullName
                }
            } else { $expected[$destination.Replace('\', '/')] = Hash $source }
        }
        $exeName = "pps-experiment-$app.exe"
        $expected[$exeName] = Hash (Join-Path $Root "target/release/$exeName")
        foreach ($relative in $expected.Keys) {
            $installed = [IO.Path]::GetFullPath((Join-Path $install $relative))
            if (-not $installed.StartsWith($install + [IO.Path]::DirectorySeparatorChar)) { throw 'Invalid installed resource destination.' }
            if ((Hash $installed) -ne $expected[$relative]) { throw "Installed resource differs: $relative" }
        }
        foreach ($file in Get-ChildItem -LiteralPath $install -Recurse -File) {
            $relative = [IO.Path]::GetRelativePath($install, $file.FullName).Replace('\', '/')
            if ($file.Extension -match '^\.(py|pyc|pyd|pdb)$' -or $relative -match '(^|[\\/])(For-AI|node_modules|site-packages)([\\/]|$)') {
                throw "Development input in runtime payload: $relative"
            }
            if ($relative -notin $expected.Keys -and $relative -ne 'uninstall.exe') { throw "Unexpected installed payload: $relative" }
        }
        $binaryNames = @($exeName)
        if ($app -eq 'designer') { $binaryNames += 'renderer/pps-3dti-renderer.exe' }
        foreach ($name in $binaryNames) {
            $bytes = [IO.File]::ReadAllBytes((Join-Path $install $name))
            foreach ($text in @([Text.Encoding]::UTF8.GetString($bytes), [Text.Encoding]::Unicode.GetString($bytes))) {
                foreach ($prefix in @($env:USERPROFILE, $env:USERPROFILE.Replace('\', '/'))) {
                    if ($text.Contains($prefix)) { throw "Private build-home path in public executable: $name" }
                }
            }
        }
        $port = if ($app -eq 'designer') { 19225 } else { 19227 }
        if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw 'Test CDP port is already owned.' }
        $start = [Diagnostics.ProcessStartInfo]::new((Join-Path $install $exeName))
        $start.UseShellExecute = $false
        $start.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
        $start.WorkingDirectory = $install
        $start.Environment['PATH'] = "$env:SystemRoot\System32;$env:SystemRoot"
        foreach ($key in @($start.Environment.Keys)) {
            if ($key -match '^(PPS_|PYTHON|VIRTUAL_ENV)') { [void]$start.Environment.Remove($key) }
        }
        $start.Environment['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = "--remote-debugging-address=127.0.0.1 --remote-debugging-port=$port --mute-audio"
        $start.Environment['WEBVIEW2_USER_DATA_FOLDER'] = Join-Path $OutputDirectory "webview-$app"
        $native = [Diagnostics.Process]::Start($start)
        try {
            $ready = $false
            for ($attempt=0; $attempt -lt 60; $attempt++) {
                if ($native.HasExited) { throw "$app exited before WebView verification" }
                try { $null = Invoke-RestMethod "http://127.0.0.1:$port/json/version"; $ready=$true; break } catch { Start-Sleep -Milliseconds 500 }
            }
            if (-not $ready) { throw "$app WebView did not become available" }
            Push-Location -LiteralPath $Root
            try {
                if ($app -eq 'designer') { & $Node apps/designer/frontend/tests/verify-native-webview.mjs }
                else { & $Node apps/runner/frontend/tests/verify-native-webview.mjs --startup-only --packaged-only }
                if ($LASTEXITCODE) { throw "$app installed WebView check failed" }
            } finally { Pop-Location }
        } finally {
            if (-not $native.HasExited) { $native.Kill(); $native.WaitForExit() }
            $native.Dispose()
        }
        $report.applications += @{app=$app; installer_sha256=$asset[0].sha256; payload_files=$expected.Count;
            exact_payload_hashes=$true; runtime_python_files=0; system_only_path=$true; actual_webview_check='passed'}
    }
    $report.passed = $true
} finally {
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'installed-report.json') -Encoding utf8
}
