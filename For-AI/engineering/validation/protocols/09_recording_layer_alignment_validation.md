# Protocol 09: Recording Layer Alignment Validation

## Purpose

Validate the two recording layers intended for normal experiments against a
temporary physical electrical loopback reference:

- lightweight callback-derived LSL/event records for trial reconstruction,
  triggers, tactile cue timing, mouse clicks, response timing, and misses
- optional local full-audio evidence WAV from the runner output callback

The physical loopback is the validation reference only. It is not required
during participant experiments.

## Setup

Use one actual Segment 5/6 prepared block under the same route intended for the
experiment. Enable:

- LSL streams
- internal `events.xdf`
- `lsl_markers.csv` and local `lsl_markers.xdf`
- analysis CSVs
- local audio evidence WAV
- validation-only full-duplex physical loopback capture

Use conservative gains. Do not raise digital playback levels above the safety
ceilings defined by the validation scripts.

## Procedure

1. Run the actual-condition one-block validation harness:

```powershell
python .\For-AI/engineering/validation\scripts\run_one_block_actual_condition_validation.py `
  --run-setup-manifest local_data\dashboard_projects\0_study_project_registry\profile_pfeiffer_2018_lateral_perihead_left_to_right\6_experiment_run_setup\experiment_run_setup_manifest.json `
  --device 31 `
  --audio-gain 0.0005 `
  --tactile-gain 0.02 `
  --capture-channels 3 `
  --capture-latency-s 0.010 `
  --capture-blocksize 256
```

2. Compare physical loopback, digital output evidence, and LSL/event records:

```powershell
python .\For-AI/engineering/validation\scripts\compare_recording_layers.py `
  --session-dir artifacts\validation_runs\one_block_actual_condition_current\sessions\P001_YYYYMMDD_HHMMSS `
  --output-dir artifacts\validation_runs\recording_layer_alignment_current
```

3. If an external LSL probe or LabRecorder-derived CSV is available, add:

```powershell
  --rich-lsl-csv artifacts\validation_runs\lsl_probe_rich\lsl_marker_probe.csv `
  --numeric-lsl-csv artifacts\validation_runs\lsl_probe_numeric\lsl_marker_probe.csv
```

## Acceptance Criteria

- Internal event/LSL records have no missing, duplicate, or extra event IDs.
- External LSL/XDF captures match internal markers when supplied.
- The local audio evidence WAV has the expected channels, duration, zero dropped
  buffers, no clipping, and visible tactile-channel click markers.
- Physical loopback aligns with the digital evidence WAV and reports physical
  minus digital latency as mean +/- SD, median, p95, min, and max.
- Physical left/right skew is <= 1 ms.
- Physical tactile-minus-audio skew is <= 2 ms.
- Callback-derived LSL timestamps match the audio-sample timeline with p95
  error <= 1 ms.
- Response-marker pulses are recovered from physical channel 3 with >= 95%
  detection and p95 residual <= 2 ms after fitting physical offset.

## Interpretation

The digital evidence WAV is the runner's local copy of what it attempted to
send to the audio device. It is not proof of physical arrival. The physical
loopback is the electrical reference that validates arrival and channel
synchronization. LSL arrival timing is monitoring metadata; explicit
callback-derived LSL timestamps are the event timing source. Woojer mechanical
vibration onset remains unmeasured unless an external vibration sensor is added.

## Accepted Current Run

Accepted artifact set:

- Actual-condition session:
  `artifacts/validation_runs/recording_layer_actual_condition_20260613_anchor/sessions/P001_20260613_174019/`
- Alignment report:
  `artifacts/validation_runs/recording_layer_alignment_20260613_anchor/recording_layer_alignment_report.json`

Summary:

- Physical-minus-digital latency: 33.462 +/- 0.013 ms, median 33.469 ms,
  p95 33.469 ms, range 33.447-33.469 ms.
- Interchannel skew: right-minus-left -0.023 ms; tactile-minus-audio 0.011 ms.
- Digital audio evidence WAV: 3 channels, zero dropped buffers, no clipping.
- Internal event/LSL mirror: 146 events and 146 marker rows, no missing,
  extra, or duplicate marker event IDs.
- Sample-anchored internal LSL timestamp error: p95 below 0.000001 ms.
- Physical response-marker recovery: 20/20 markers detected, 0.000 ms residual
  jitter after fitting the common recording offset.
