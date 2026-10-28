[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OutputDirectory,
    [Parameter(Mandatory)][string]$RendererDirectory,
    [Parameter(Mandatory)][string]$RuntimeDirectory,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{64}$')][string]$RendererSha256,
    [Parameter(Mandatory)][ValidatePattern('^[a-fA-F0-9]{40}$')][string]$RendererSourceCommit,
    [ValidateSet('designer','runner')][string[]]$Apps = @('designer','runner'),
    [string]$NpmCliPath = '',
    [switch]$ValidateOnly
)

# Build an unsigned local candidate, never install or publish it. This script
# consumes the separately rebuilt/verified 3DTI executable and its pinned DLLs.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Build native Windows candidates on Windows.' }
if (-not $Apps.Count) { throw 'Select at least one native application.' }
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../../..')).Path
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
$RendererDirectory = (Resolve-Path -LiteralPath $RendererDirectory).Path
$RuntimeDirectory = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Candidate output must be a new directory.' }
if ($env:CARGO_TARGET_DIR) { throw 'Unset CARGO_TARGET_DIR so native bundle output has one known owner.' }
$Node = (Get-Command node -ErrorAction Stop).Source
$Npm = if ($NpmCliPath) { (Resolve-Path -LiteralPath $NpmCliPath).Path } else { (Get-Command npm -ErrorAction Stop).Source }
function Invoke-Npm([string[]]$Arguments) {
    if ($NpmCliPath) { & $Node $Npm @Arguments } else { & $Npm @Arguments }
    if ($LASTEXITCODE -ne 0) { throw "npm failed with exit code $LASTEXITCODE" }
}
function Assert-Exit([string]$Operation) {
    if ($LASTEXITCODE -ne 0) { throw "$Operation failed with exit code $LASTEXITCODE" }
}
function Hash([string]$Path) { (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
$PreviousEncodedRustFlags = $env:CARGO_ENCODED_RUSTFLAGS
# Panic locations include Cargo registry paths even when release symbols are
# stripped. Map both Windows spellings before compiling public executables.
$RemappedFlags = @($PreviousEncodedRustFlags -split [char]31 | Where-Object { $_ })
foreach ($Mapping in @(@($env:USERPROFILE, '/build/user'), @($Root, '/build/pps-kit'))) {
    foreach ($Source in @($Mapping[0], $Mapping[0].Replace('\', '/')) | Select-Object -Unique) {
        $Flag = '--remap-path-prefix=' + $Source + '=' + $Mapping[1]
        if ($Flag -notin $RemappedFlags) { $RemappedFlags += $Flag }
    }
}
$env:CARGO_ENCODED_RUSTFLAGS = $RemappedFlags -join [char]31
Push-Location -LiteralPath $Root
try {
    $Commit = (git rev-parse HEAD).Trim(); Assert-Exit 'Read source revision'
    git diff --quiet HEAD -- Cargo.toml Cargo.lock apps packages third_party
    Assert-Exit 'Native candidate source must be committed'
    $UntrackedSource = @(git ls-files --others --exclude-standard -- Cargo.toml Cargo.lock apps packages third_party)
    Assert-Exit 'Check native candidate source inventory'
    if ($UntrackedSource.Count) { throw 'Commit untracked product source before packaging.' }
    git diff --quiet $RendererSourceCommit HEAD -- third_party/3dti_renderer third_party/3dti_AudioToolkit third_party/nlohmann_json
    Assert-Exit 'Renderer source must match its verified build revision'
    $NodeVersion = (& $Node --version).Trim(); Assert-Exit 'Read Node version'
    $NpmVersion = (Invoke-Npm @('--version')).Trim()
    $RustVersion = (rustc --version).Trim(); Assert-Exit 'Read Rust version'
    if ($NodeVersion -ne 'v24.19.0' -or $NpmVersion -ne '10.9.4' -or $RustVersion -notmatch '^rustc 1\.96\.0 ') {
        throw 'Native candidate builds require Node 24.19.0, npm 10.9.4 and Rust 1.96.0.'
    }
    $RendererFiles = @('pps-3dti-renderer.exe','hdf5_hl.dll','hdf5.dll','libcurl.dll','netcdf.dll','zlib1.dll')
    foreach ($Name in $RendererFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $RendererDirectory $Name) -PathType Leaf)) { throw "Missing renderer resource: $Name" }
    }
    if ((Hash (Join-Path $RendererDirectory $RendererFiles[0])) -ne $RendererSha256.ToLowerInvariant()) { throw 'Renderer SHA256 mismatch.' }
    $RendererInventory = @($RendererFiles | ForEach-Object {
        @{file=$_; sha256=(Hash (Join-Path $RendererDirectory $_)); bytes=(Get-Item -LiteralPath (Join-Path $RendererDirectory $_)).Length}
    })
    $RuntimeLock = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'native-runtime-lock.json') -Raw | ConvertFrom-Json
    foreach ($File in $RuntimeLock.files) {
        $InputFile = Join-Path $RuntimeDirectory $File.file
        if ((Hash $InputFile) -ne $File.sha256) { throw "Pinned native runtime mismatch: $($File.file)" }
    }
    $RunnerLock = Get-Content -LiteralPath 'apps/runner/package-lock.json' -Raw | ConvertFrom-Json -AsHashtable
    if ($RunnerLock.packages.'node_modules/@tauri-apps/cli'.version -ne '2.11.4') { throw 'Expected locked Tauri CLI 2.11.4.' }
    $Designer = Get-Content -LiteralPath 'apps/designer/src-tauri/tauri.conf.json' -Raw | ConvertFrom-Json
    $Runner = Get-Content -LiteralPath 'apps/runner/src-tauri/tauri.conf.json' -Raw | ConvertFrom-Json
    $Preflight = [ordered]@{ source_commit=$Commit; node=$NodeVersion; npm=$NpmVersion; rust=$RustVersion; tauri_cli='2.11.4';
        designer_identifier=$Designer.identifier; runner_identifier=$Runner.identifier; renderer_sha256=$RendererSha256.ToLowerInvariant();
        renderer_source_commit=$RendererSourceCommit; renderer_files=$RendererInventory; selected_apps=@($Apps | Select-Object -Unique);
        microsoft_runtime=$RuntimeLock;
        builder_sha256=(Hash $PSCommandPath); runtime_lock_sha256=(Hash (Join-Path $PSScriptRoot 'native-runtime-lock.json'));
        signing='unsigned'; webview2='offlineInstaller'; python_runtime=$false; rust_source_paths_remapped=$true }
    if ($ValidateOnly) { $Preflight | ConvertTo-Json -Depth 8; return }
    New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
    # CAB-extracted Microsoft notices can be read-only. Tauri preserves that
    # attribute when copying resources, which otherwise breaks the next build.
    # Normalize only our staging copies; preserve the pinned source inputs.
    $StagedRuntime = Join-Path $OutputDirectory 'native-runtime'
    New-Item -ItemType Directory -Path $StagedRuntime | Out-Null
    foreach ($File in $RuntimeLock.files) {
        $Copy = Join-Path $StagedRuntime $File.file
        Copy-Item -LiteralPath (Join-Path $RuntimeDirectory $File.file) -Destination $Copy
        (Get-Item -LiteralPath $Copy).IsReadOnly = $false
        if ((Hash $Copy) -ne $File.sha256) { throw "Staged runtime mismatch: $($File.file)" }
        # Repair an identical read-only build resource left by an older builder.
        $RelativeTarget = if ($File.kind -eq 'license') { 'licenses/' + $File.file } else { $File.file }
        $OldTarget = Join-Path $Root ('target/release/' + $RelativeTarget)
        if (Test-Path -LiteralPath $OldTarget -PathType Leaf) {
            $OldItem = Get-Item -LiteralPath $OldTarget
            if ($OldItem.IsReadOnly) {
                for ($Ancestor = $OldItem; $Ancestor.FullName -ne $Root; $Ancestor = Get-Item -LiteralPath (Split-Path -Parent $Ancestor.FullName)) {
                    if ($Ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to modify a linked build resource.' }
                }
                if ((Hash $OldTarget) -ne $File.sha256) { throw "Read-only build resource differs from the lock: $RelativeTarget" }
                $OldItem.IsReadOnly = $false
            }
        }
    }
    foreach ($Frontend in @('apps/runner','apps/designer/frontend')) {
        Invoke-Npm @('--prefix', $Frontend, 'ci')
        Invoke-Npm @('--prefix', $Frontend, 'run', 'build')
    }
    git diff --quiet HEAD -- Cargo.lock apps/runner/package-lock.json apps/designer/frontend/package-lock.json apps/runner/compiled apps/designer/frontend/compiled
    Assert-Exit 'Locked dependencies/canonical frontend drift; verify and commit before packaging'
    $Cli = Join-Path $Root 'apps/runner/node_modules/@tauri-apps/cli/tauri.js'
    $LicenseResources = @{}
    $LicenseFiles = @(git ls-files third_party | Where-Object { [IO.Path]::GetFileName($_) -match '(?i)(^|[_-])(licen[cs]e|copying|copyright)' })
    Assert-Exit 'Read third-party notices'
    foreach ($File in $LicenseFiles) { $LicenseResources[(Join-Path $Root $File)] = ('licenses/' + $File) }
    $Artifacts = @()
    foreach ($App in @(@{name='designer'; config=$Designer}, @{name='runner'; config=$Runner}) | Where-Object { $_.name -in $Apps }) {
        $Resources = @{}
        $ConfigDirectory = Join-Path $Root ('apps/' + $App.name + '/src-tauri')
        foreach ($Resource in $App.config.bundle.resources.PSObject.Properties) {
            # Tauri's final JSON Merge Patch removes these original map keys.
            # A separate reset config is folded before the base is loaded and
            # cannot clear it; retain each null in this one patch instead.
            $Resources[$Resource.Name] = $null
            $SourcePath = [IO.Path]::GetFullPath((Join-Path $ConfigDirectory $Resource.Name))
            if (-not (Test-Path -LiteralPath $SourcePath)) { throw "Missing native bundle resource: $($Resource.Name)" }
            $Resources[$SourcePath] = $Resource.Value
        }
        foreach ($File in $RuntimeLock.files) {
            $InputFile = Join-Path $StagedRuntime $File.file
            if ($File.kind -eq 'license') { $Resources[$InputFile] = ('licenses/' + $File.file) }
            elseif ($File.app_root) { $Resources[$InputFile] = $File.file }
            if ($App.name -eq 'designer' -and $File.kind -eq 'dll') {
                # The child process resolves its own adjacent DLLs. Stage a second
                # copy so Tauri's source-to-destination map has no duplicate keys.
                $ChildRuntime = Join-Path $OutputDirectory 'renderer-runtime'
                New-Item -ItemType Directory -Path $ChildRuntime -Force | Out-Null
                $Copy = Join-Path $ChildRuntime $File.file
                Copy-Item -LiteralPath $InputFile -Destination $Copy
                $Resources[$Copy] = ('renderer/' + $File.file)
            }
        }
        if ($App.name -eq 'designer') {
            foreach ($Name in $RendererFiles) { $Resources[(Join-Path $RendererDirectory $Name)] = "renderer/$Name" }
            foreach ($File in $LicenseResources.Keys) { $Resources[$File] = $LicenseResources[$File] }
            $HrtfManifest = 'packages/pps-resources/assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.manifest.json'
            $Resources[(Join-Path $Root $HrtfManifest)] = 'resources/assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.manifest.json'
        }
        $Overlay = @{build=@{beforeBuildCommand=$null}; bundle=@{active=$true; targets=@('nsis'); createUpdaterArtifacts=$false;
            windows=@{webviewInstallMode=@{type='offlineInstaller'}; nsis=@{installMode='currentUser'}}}}
        if ($Resources.Count) { $Overlay.bundle.resources = $Resources }
        $OverlayPath = Join-Path $OutputDirectory ($App.name + '.candidate.conf.json')
        $Overlay | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OverlayPath -Encoding utf8
        $Started = Get-Date
        Push-Location -LiteralPath (Join-Path $Root ('apps/' + $App.name))
        try {
            & $Node $Cli build --ci --bundles nsis --no-sign --config $OverlayPath -- --locked
            Assert-Exit 'Native Tauri candidate build'
        } finally { Pop-Location }
        $Product = $App.config.productName
        $Bundles = @(Get-ChildItem -LiteralPath (Join-Path $Root 'target/release/bundle/nsis') -File |
            Where-Object { $_.Name.StartsWith($Product + '_') -and $_.Extension -eq '.exe' -and $_.LastWriteTime -ge $Started })
        if ($Bundles.Count -ne 1) { throw "Expected one freshly built $Product installer." }
        $Destination = Join-Path $OutputDirectory $Bundles[0].Name
        Copy-Item -LiteralPath $Bundles[0].FullName -Destination $Destination
        $Artifacts += @{file=$Bundles[0].Name; sha256=(Hash $Destination); bytes=$Bundles[0].Length; app=$App.name}
    }
    # Corresponding renderer source is a separate download, never part of the
    # runtime install. The replaceable renderer can be rebuilt with its CMake project.
    $SourceZip = Join-Path $OutputDirectory 'pps-native-renderer-source.zip'
    # The wrapper directory also retains legacy prebuilt executables. They are
    # not corresponding source and may contain the original build user's paths.
    git archive --format=zip --output=$SourceZip HEAD -- third_party/3dti_AudioToolkit third_party/3dti_renderer/CMakeLists.txt third_party/3dti_renderer/README.md third_party/3dti_renderer/src third_party/nlohmann_json LICENSE THIRD_PARTY_LICENSES.md
    Assert-Exit 'Archive corresponding renderer source'
    $Artifacts += @{file=[IO.Path]::GetFileName($SourceZip); sha256=(Hash $SourceZip); bytes=(Get-Item -LiteralPath $SourceZip).Length; app='renderer-source'}
    $Preflight['schema'] = 'pps-native-windows-candidate.v1'
    $Preflight['cargo_lock_sha256'] = Hash (Join-Path $Root 'Cargo.lock')
    $Preflight['artifacts'] = $Artifacts
    $Preflight['installed_verification'] = 'not_assessed'
    $Preflight['physical_timing_qualification'] = 'not_assessed'
    $Preflight['publication_status'] = 'local_candidate_only'
    $Preflight | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'candidate-manifest.json') -Encoding utf8
    $Artifacts | ForEach-Object { "$($_.sha256)  $($_.file)" } | Set-Content -LiteralPath (Join-Path $OutputDirectory 'SHA256SUMS') -Encoding ascii
    Write-Host "Built unsigned native candidates in $OutputDirectory; installation and publication remain separate checks."
} finally {
    Pop-Location
    $env:CARGO_ENCODED_RUSTFLAGS = $PreviousEncodedRustFlags
}
