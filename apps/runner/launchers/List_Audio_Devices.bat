@echo off
setlocal
cd /d "%~dp0\..\..\.."
if not exist ".venv\Scripts\python.exe" (
  powershell -ExecutionPolicy Bypass -File "For-AI\engineering\build\windows\Setup_Windows_App.ps1"
)
".venv\Scripts\python.exe" -m peripersonal_space_toolkit.audio_device_stress --dry-run --device-query Komplete
pause
endlocal
