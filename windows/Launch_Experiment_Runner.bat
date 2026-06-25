@echo off
setlocal
cd /d "%~dp0\.."
if "%~1"=="" (
  set "PPS_RUNNER_ARGS=--launcher"
) else (
  set "PPS_RUNNER_ARGS=%*"
)
if exist "dist\PPSExperimentRunner\PPSExperimentRunner.exe" (
  "dist\PPSExperimentRunner\PPSExperimentRunner.exe" %PPS_RUNNER_ARGS%
) else (
  echo PPSExperimentRunner.exe was not found.
  echo Build the active experiment runner with:
  echo   powershell -ExecutionPolicy Bypass -File windows\Build_Experiment_Runner_Exe.ps1
  exit /b 2
)
endlocal
