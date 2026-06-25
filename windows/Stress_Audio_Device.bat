@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  powershell -ExecutionPolicy Bypass -File "windows\Setup_Windows_App.ps1"
)
".venv\Scripts\python.exe" -m peripersonal_space_toolkit.audio_device_stress --device-query Komplete --output-dir artifacts\audio_device_stress --mode callback --iterations 2 --duration-s 5 --channels 3 4 2 --latencies 0.003 0.010 0.020 low --blocksizes 64 256 512
pause
endlocal
