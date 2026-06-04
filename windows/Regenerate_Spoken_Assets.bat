@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  powershell -ExecutionPolicy Bypass -File "windows\Setup_Windows_App.ps1"
)
".venv\Scripts\python.exe" tools\generate_spoken_assets.py
pause
endlocal
