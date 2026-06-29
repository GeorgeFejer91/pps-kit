# Tactile Calibration Runner Handoff - 2026-06-29

## Current State

- Source changes are implemented in `src/peripersonal_space_toolkit/focus_app.py`.
- Successful tactile calibration now shows `Calibration successful`, displays the adopted Output 3/4 value, updates the final reversal count, adopts the value via `_set_output_volume("output_3_4", final_percent)`, then automatically returns to the Experiment Control tab and focuses the Start button when setup is already submitted.
- GUI coverage is in `tests/test_focus_app.py::test_focus_mode_calibrate_tactile_button_click_saves_and_applies_value`.
- Validation already run successfully:
  - `python -m compileall -q src/peripersonal_space_toolkit/focus_app.py src/peripersonal_space_toolkit/tactile_calibration`
  - `python -m pytest -q tests/test_tactile_calibration.py tests/test_focus_app.py`

## What Remains

The packaged runner still needs to be rebuilt and smoke-validated after these source changes. The rebuild was started but interrupted at the user's request. Before rebuilding, make sure no old packaged runner or PyInstaller process is holding files in `dist/PPSExperimentRunner`.

Recommended finish sequence:

1. Check and close stale runner/build processes:
   `Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*PPS*' -or $_.Name -like '*pyinstaller*' -or $_.CommandLine -like '*Build_Experiment_Runner*' -or $_.CommandLine -like '*PPSExperimentRunner*' }`
2. If needed, stop only the stale `PPSExperimentRunner.exe`, PyInstaller, or `Build_Experiment_Runner_Exe.ps1` processes. Do not stop unrelated Python/http-server work.
3. Rebuild the packaged runner:
   `powershell -ExecutionPolicy Bypass -File .\windows\Build_Experiment_Runner_Exe.ps1`
4. Run packaged-runner smoke validation:
   `python validation_protocols/scripts/run_study5_end_to_end_ui_mouse_validation.py --packaged-standalone-app --output-dir artifacts/validation_runs/tactile_calibration_success_return_packaged_runner_20260629 --participant-id P901 --timeout-s 240`
5. Commit and push the rebuild-confirmation follow-up if any tracked files are changed. `dist/` and validation artifacts are ignored, so record validation status in the final response or a relevant `For-AI/` note if the handoff is completed later.

## Build Blocker Seen

Two rebuild attempts failed before the user interruption because a running `PPSExperimentRunner.exe` locked files under `dist/PPSExperimentRunner/_internal`, especially `charset_normalizer/cd.cp312-win_amd64.pyd`. After the interruption, the lingering `Build_Experiment_Runner_Exe.ps1`, PyInstaller Python processes, and `PPSExperimentRunner.exe` were stopped.
