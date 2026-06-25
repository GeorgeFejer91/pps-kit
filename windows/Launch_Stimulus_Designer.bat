@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  powershell -ExecutionPolicy Bypass -File "windows\Setup_Windows_App.ps1"
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m peripersonal_space_toolkit.qt_designer_app %*
) else (
  ".venv\Scripts\python.exe" -m peripersonal_space_toolkit.qt_designer_app %*
)
endlocal
