$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Venv = Join-Path $Root ".venv"

if (-not (Test-Path $Venv)) {
    $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PythonLauncher) {
        py -3.12 -m venv $Venv
        if ($LASTEXITCODE -ne 0) {
            python -m venv $Venv
        }
    } else {
        python -m venv $Venv
    }
}

$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -e "${Root}[tts,dev]"

New-Item -ItemType Directory -Force (Join-Path $Root "artifacts") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $Root "local_data\loopback_recordings") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $Root "local_data\demographics") | Out-Null

Write-Host ""
Write-Host "Setup complete."
Write-Host "Run windows\Launch_PPS_App.bat to start the experiment app."
Write-Host "Run windows\Launch_Stimulus_Designer.bat to design custom looming stimuli."
