[CmdletBinding()]
param([Parameter(Mandatory)][ValidatePattern('^[0-9]+$')][string]$SourceRunId)

# Recheck immutable, already verified installers on a fresh disposable account.
# Local user profiles are never removed or redirected to satisfy this check.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:GITHUB_ACTIONS -ne 'true' -or [Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Packaged layout verification requires a disposable GitHub Windows account.'
}
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../..')).Path
$Evidence = Join-Path $Root 'artifacts/packaged-layout-source'
$Output = Join-Path $Root 'artifacts/packaged-layout-installed'
if ((Test-Path -LiteralPath $Evidence) -or (Test-Path -LiteralPath $Output)) { throw 'Preserve existing verification output.' }
function Assert-Exit([string]$Operation) { if ($LASTEXITCODE) { throw "$Operation failed: $LASTEXITCODE" } }
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$Node = (Get-Command node -ErrorAction Stop).Source
$Run = gh run view $SourceRunId --repo $env:GITHUB_REPOSITORY --json headSha,status,conclusion | ConvertFrom-Json
Assert-Exit 'Read candidate run'
if ($Run.status -ne 'completed' -or $Run.conclusion -ne 'success' -or $Run.headSha -notmatch '^[a-f0-9]{40}$') {
    throw 'Use a successful complete Windows candidate run.'
}
gh run download $SourceRunId --repo $env:GITHUB_REPOSITORY --name "pps-native-windows-candidate-$($Run.headSha)" --dir $Evidence
Assert-Exit 'Download exact candidate evidence'
$Candidate = Join-Path $Evidence 'dist/native-windows-candidate'
$Manifest = Get-Content -LiteralPath (Join-Path $Candidate 'candidate-manifest.json') -Raw | ConvertFrom-Json
$Installed = Get-Content -LiteralPath (Join-Path $Evidence 'artifacts/installed-native-candidate/installed-report.json') -Raw | ConvertFrom-Json
if ($Manifest.source_commit -ne $Run.headSha -or $Installed.source_commit -ne $Run.headSha -or $Installed.passed -ne $true) {
    throw 'Candidate and installed evidence attribution disagree.'
}
git -C $Root fetch --no-tags --depth=1 origin $Run.headSha
Assert-Exit 'Fetch exact product source'
git -C $Root diff --quiet $Run.headSha HEAD -- Cargo.toml Cargo.lock apps packages third_party ':(exclude)apps/designer/frontend/tests/**' ':(exclude)apps/runner/frontend/tests/**'
Assert-Exit 'Layout follow-up must preserve the candidate product source'
New-Item -ItemType Directory -Path $Output | Out-Null
$Report = [ordered]@{schema='pps-native-packaged-layout-followup.v1'; source_commit=$Run.headSha;
    source_run_id=$SourceRunId; validation_commit=(git -C $Root rev-parse HEAD).Trim();
    ci_run_url="https://github.com/$env:GITHUB_REPOSITORY/actions/runs/$env:GITHUB_RUN_ID";
    scope='Fresh Windows CI account; exact installed executables; CDP CSS viewports and CSS zoom in actual WebView2. No OS-window dragging, acquisition or physical qualification.';
    applications=@(); passed=$false}
try {
    foreach ($App in @('designer','runner')) {
        $Config = Get-Content -LiteralPath (Join-Path $Root "apps/$App/src-tauri/tauri.conf.json") -Raw | ConvertFrom-Json
        if (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA $Config.identifier)) { throw "Preserve existing $App data; use a fresh CI account." }
        $Assets = @($Manifest.artifacts | Where-Object app -eq $App)
        $Prior = @($Installed.applications | Where-Object app -eq $App)
        if ($Assets.Count -ne 1 -or $Prior.Count -ne 1 -or $Prior[0].exact_payload_hashes -ne $true) { throw 'Missing exact installed application evidence.' }
        $Asset = $Assets[0]
        if ($Asset.file -ne "$($Config.productName)_$($Config.version)_x64-setup.exe" -or
            $Asset.sha256 -notmatch '^[a-f0-9]{64}$' -or $Prior[0].executable_sha256 -notmatch '^[a-f0-9]{64}$' -or
            $Prior[0].installer_sha256 -ne $Asset.sha256) { throw 'Unexpected installer identity.' }
        $Installer = Join-Path $Candidate $Asset.file
        if ((Hash $Installer) -ne $Asset.sha256) { throw 'Installer digest differs from the candidate.' }
        $Install = Join-Path $Output $App
        $Setup = Start-Process -FilePath $Installer -ArgumentList @('/S', "/D=$Install") -PassThru -Wait -WindowStyle Hidden
        if ($Setup.ExitCode) { throw "$App installation failed: $($Setup.ExitCode)" }
        $Executable = Join-Path $Install "pps-experiment-$App.exe"
        if ((Hash $Executable) -ne $Prior[0].executable_sha256) { throw 'Installed executable differs from the complete candidate run.' }
        $Port = if ($App -eq 'designer') { 19225 } else { 19227 }
        if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw 'Verification port is already owned.' }
        $Start = [Diagnostics.ProcessStartInfo]::new($Executable)
        $Start.UseShellExecute = $false
        $Start.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
        $Start.WorkingDirectory = $Install
        $Start.Environment['PATH'] = "$env:SystemRoot\System32;$env:SystemRoot"
        foreach ($Key in @($Start.Environment.Keys)) {
            if ($Key -match '^(PPS_|PYTHON|VIRTUAL_ENV)') { [void]$Start.Environment.Remove($Key) }
        }
        $Start.Environment['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = "--remote-debugging-address=127.0.0.1 --remote-debugging-port=$Port --mute-audio"
        $Start.Environment['WEBVIEW2_USER_DATA_FOLDER'] = Join-Path $Output "webview-$App"
        $Native = [Diagnostics.Process]::Start($Start)
        try {
            $Ready = $false
            for ($Attempt=0; $Attempt -lt 60; $Attempt++) {
                if ($Native.HasExited) { throw "$App exited before WebView verification." }
                try { $null = Invoke-RestMethod "http://127.0.0.1:$Port/json/version"; $Ready=$true; break } catch { Start-Sleep -Milliseconds 500 }
            }
            if (-not $Ready) { throw "$App WebView endpoint did not become ready." }
            $Script = if ($App -eq 'designer') { 'apps/designer/frontend/tests/verify-native-webview.mjs' } else { 'apps/runner/frontend/tests/verify-native-webview.mjs' }
            Push-Location -LiteralPath $Root
            try { & $Node $Script --layout-only --packaged-only; Assert-Exit "$App packaged layout checks" }
            finally { Pop-Location }
        } finally {
            if (-not $Native.HasExited) { $Native.Kill(); $Native.WaitForExit() }
            $Native.Dispose()
        }
        $LayoutPath = Join-Path $Root "artifacts/ui-workflow-check/$App-native-layout/report.json"
        $Layout = Get-Content -LiteralPath $LayoutPath -Raw | ConvertFrom-Json
        if ($Layout.mode -ne 'packaged-read-only-layout' -or $Layout.passed -ne $true) {
            throw 'The native check did not produce verified read-only layout evidence.'
        }
        $Report.applications += @{app=$App; installer_sha256=$Asset.sha256; executable_sha256=$Prior[0].executable_sha256;
            actual_packaged_webview_layout='passed'; layout_report_sha256=(Hash $LayoutPath); system_only_path=$true}
    }
    $Report.passed = $true
} finally {
    $Report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Output 'packaged-layout-report.json') -Encoding utf8
}
