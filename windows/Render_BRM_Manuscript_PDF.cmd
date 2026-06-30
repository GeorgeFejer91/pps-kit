@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Render_BRM_Manuscript_PDF.ps1" %*
endlocal
