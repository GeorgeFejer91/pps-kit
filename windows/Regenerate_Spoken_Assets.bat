@echo off
setlocal
cd /d "%~dp0\.."
if not exist ".venv\Scripts\python.exe" (
  powershell -ExecutionPolicy Bypass -File "windows\Setup_Windows_App.ps1"
)
".venv\Scripts\python.exe" tools\generate_spoken_assets.py
if errorlevel 1 goto done
if not exist "assets\breathing\british_kokoro" mkdir "assets\breathing\british_kokoro"
copy /Y "assets\breathing\*.wav" "assets\breathing\british_kokoro\" >nul
copy /Y "assets\breathing\spoken_assets_manifest.json" "assets\breathing\british_kokoro\spoken_assets_manifest.json" >nul
:done
pause
endlocal
