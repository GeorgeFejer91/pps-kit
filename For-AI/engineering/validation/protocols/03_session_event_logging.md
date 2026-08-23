# Protocol 03: Session Event Logging

## Purpose

Verify that the native runner writes complete local timing logs for a prepared
session and that the logs match expected block/sample timing.

## Procedure

1. Prepare a deterministic validation session from the dashboard or an existing
   Segment 6 run-setup manifest.
2. Run the session in the native runner with a test participant ID.
3. Confirm the session folder contains:
   - `events.csv`
   - `events.xdf`
   - `analysis/timing_qc.csv`
   - `analysis/analysis_summary.txt`
   - block CSVs under `blocks/`
   - block WAVs under `blocks/`
4. Run:

```powershell
python .\For-AI/engineering/validation\scripts\summarize_validation_run.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS
```

5. Compare event counts and planned sample timing against each block CSV.

## Acceptance Criteria

- `session_start`, `block_start`, `audio_sample_zero`, `block_end`, and
  `session_end` are present.
- Planned trial events exist for trial start, looming onset, tactile onset,
  response-window onset, and trial end where applicable.
- No duplicate `event_id` values exist in `events.csv`.
- No `timing_anchor_fallback` occurs in official timing runs.
- Actual mouse clicks are logged as `mouse_click`.
- Response markers are logged as `response_marker_start` when clicks occur
  during playback and the audio engine supports the marker.

## Failure Classification

- Missing `audio_sample_zero`: audio callback anchoring problem.
- Missing planned trial events: block CSV parsing or session logging problem.
- Missing `events.xdf`: local XDF writer problem.
- Missing timing QC: analysis/export problem.
- Duplicate event IDs: logger integrity problem.
