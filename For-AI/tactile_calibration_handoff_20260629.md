# Tactile Calibration Runner Handoff - 2026-06-29

## Current State

- Source changes are implemented in `src/peripersonal_space_toolkit/tactile_calibration/`, `src/peripersonal_space_toolkit/focus_app.py`, and the matching tests.
- The active tactile calibration protocol keeps the 2-down/1-up staircase as the detection-threshold estimator, then runs a final confirmation phase before saving a participant preset.
- The saved staircase estimate is `detection_threshold_output_34_percent`; the confirmed task preset is `recommended_output_34_percent`, with `final_output_34_percent` retained as the legacy-compatible alias.
- Confirmation accepts only after 10 consecutive tactile hits and 5 clean confirmation catch trials using the shared 100-1300 ms tactile response window.
- Confirmation misses reset the hit streak, raise the level by +0.01% Output 3/4, and continue until the 0.5% cap. A miss at the cap fails with `failed_confirmation_at_max`.
- Confirmation catch false alarms show the red warning `Only press when you feel the tactile pulse.`, reset only the clean-catch streak, do not change intensity, and fail on the third cumulative false alarm.
- Successful calibration no longer auto-returns to the Experiment Control tab. The monitor displays the saved-value summary and enables `Continue`, which returns to the PPS runner UI.

## Validation Notes

- Focused validation for this implementation should include:
  - `.\.venv\Scripts\python.exe -m pytest -q tests\test_tactile_calibration.py`
  - `.\.venv\Scripts\python.exe -m pytest -q tests\test_focus_app.py -k "tactile_calibration"`
  - Packaged-runner visual validation after rebuilding `dist/PPSExperimentRunner/PPSExperimentRunner.exe`.
- On this PC, visible runner validation may pin the PC runner window to Display 2 with `PPS_FOCUS_VALIDATION_DISPLAY=display2` or an exact runner window rectangle. Do not resize, widen, or repeatedly reposition the Android emulator to make companion UI checks pass; Android emulator validation must use the AVD's fixed phone viewport and treat clipping, scroll burden, or hidden controls as app findings.

## Historical Supersession

The earlier same-day handoff documented the previous success-return behavior (`Calibration successful` plus automatic return). That behavior is superseded by the confirmation counters, red catch-warning state, success summary, and explicit `Continue` button described above.
