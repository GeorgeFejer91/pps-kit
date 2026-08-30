param(
    [ValidateSet("Core", "Desktop", "Browser")]
    [string]$Mode = "Core"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path

Push-Location $RepoRoot
try {
    if ($Mode -eq "Core") {
        cargo fmt --all -- --check
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        cargo check --locked -p pps-contracts -p pps-brsp -p pps-runner-core -p pps-session-package
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        cargo clippy --locked -p pps-contracts -p pps-brsp -p pps-runner-core -p pps-session-package --all-targets -- -D warnings
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        cargo test --locked -p pps-contracts -p pps-brsp -p pps-runner-core -p pps-session-package
        exit $LASTEXITCODE
    }

    if ($Mode -eq "Desktop") {
        cargo check --locked -p pps-experiment-runner --all-targets
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        cargo clippy --locked -p pps-experiment-runner --all-targets -- -D warnings
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        cargo test --locked -p pps-experiment-runner --all-targets
        exit $LASTEXITCODE
    }

    npm --prefix apps/runner ci
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    npm --prefix apps/runner run check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    git diff --exit-code -- apps/runner/compiled
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
