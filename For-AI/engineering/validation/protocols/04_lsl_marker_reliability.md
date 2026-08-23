# Protocol 04: LSL Marker Reliability

## Purpose

Validate that the optional LSL marker stream receives the same actual events as
the local event logger. This protocol uses an external probe so the runtime code
remains the system under test.

## Setup

Install the optional LSL dependency:

```powershell
python -m pip install -e ".[lsl]"
```

Start the LSL probe before starting the native runner:

```powershell
python .\For-AI/engineering/validation\scripts\lsl_marker_probe.py --stream-name PPSMarkersV2 --duration-s 120 --output-dir artifacts\validation_runs\lsl_probe
```

When validating the dual-stream setup, start a second probe for numeric trigger
codes:

```powershell
python .\For-AI/engineering/validation\scripts\lsl_marker_probe.py --stream-name PPSTriggerCodes --duration-s 120 --output-dir artifacts\validation_runs\lsl_probe_numeric
```

The current rich marker stream name is `PPSMarkersV2`. The runner may also
publish the numeric `PPSTriggerCodes` stream for EEG-style trigger-code
pipelines, but the rich stream is the one that should be complete enough to
reconstruct the experiment from LSL alone.

For an external-recorder check, install or extract LabRecorder and make sure
`LabRecorderCLI.exe` is available on `PATH` or under
`local_data/software_tools/labrecorder/`. The repository-local downloader can
fetch the official Windows release into ignored local folders:

```powershell
.\For-AI/engineering/validation\scripts\download_labrecorder.ps1
```

## Procedure

1. Start the probe.
2. Run a deterministic validation session.
3. Stop or wait for the probe to finish.
4. Reconcile the external LSL captures against the local logs:

```powershell
python .\For-AI/engineering/validation\scripts\reconcile_lsl_with_local_events.py `
  --events-csv local_data\sessions\P001_YYYYMMDD_HHMMSS\events.csv `
  --lsl-markers-csv local_data\sessions\P001_YYYYMMDD_HHMMSS\lsl_markers.csv `
  --rich-lsl-probe-csv artifacts\validation_runs\lsl_probe\lsl_marker_probe.csv `
  --numeric-lsl-probe-csv artifacts\validation_runs\lsl_probe_numeric\lsl_marker_probe.csv `
  --output-dir artifacts\validation_runs\lsl_reconciliation
```

5. Summarize the session and probe output:

```powershell
python .\For-AI/engineering/validation\scripts\summarize_validation_run.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS --lsl-probe-csv artifacts\validation_runs\lsl_probe\lsl_marker_probe.csv
```

6. For an XDF preservation stress test, run the LabRecorder harness:

```powershell
python .\For-AI/engineering/validation\scripts\run_labrecorder_lsl_xdf_stress.py `
  --output-dir artifacts\validation_runs\labrecorder_lsl_xdf_current `
  --count 12 `
  --interval-s 0.05
```

This script emits the PPS rich and numeric streams, records them with
LabRecorderCLI, loads the resulting `.xdf` with `pyxdf`, and compares recorded
samples against the local `lsl_markers.csv` and `trigger_dictionary.json`.

## Acceptance Criteria

- The probe resolves exactly the intended `PPSMarkersV2` stream for the run.
- Every actual event pushed to LSL is present in the probe CSV.
- Event IDs, event types, trigger keys, trigger codes, trial IDs, sample
  indices, and timestamp-quality labels match local `events.csv`,
  `lsl_markers.csv`, and `trigger_dictionary.json`.
- No duplicate LSL event IDs occur.
- Rich stream reconciliation reports zero missing IDs, zero extra IDs, zero
  duplicate IDs, and zero metadata field mismatches.
- Numeric stream reconciliation reports no missing or extra trigger-code counts.
- Arrival-minus-marker timestamp behavior is stable enough for monitoring.
- LabRecorder/XDF stress reports all expected rich and numeric samples, zero
  missing event IDs, zero extra event IDs, zero duplicate event IDs, zero field
  mismatches, and matching numeric trigger-code counts.

## Notes

Planned future events should remain local unless runtime behavior changes. LSL
markers are expected to represent actual events at the time they happen.

If LabRecorder is used, keep raw `.xdf` output under ignored local folders. XDF
preservation validates the software recording path; it does not prove physical
audio or tactile signal arrival at the output jacks.
