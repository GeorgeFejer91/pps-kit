@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  powershell -ExecutionPolicy Bypass -File "windows\Setup_Windows_App.ps1"
)
".venv\Scripts\python.exe" -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -e ".[web]"
)
".venv\Scripts\python.exe" -m peripersonal_space_toolkit.dashboard_app %*
endlocal
