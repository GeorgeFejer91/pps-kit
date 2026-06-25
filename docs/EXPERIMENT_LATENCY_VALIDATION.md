# Experiment Latency Validation

This protocol validates the electrical timing of the PPS rendered-stimulus
route. It checks whether the signal sent by the experiment software to the
Komplete Audio 6 MK2 outputs arrives back at the Komplete inputs with stable
timing across:

- output 1: binaural left
- output 2: binaural right
- output 3: tactile drive

It does not measure the mechanical onset latency of the Woojer Strap 4
transducer. That would require an external vibration sensor, accelerometer, or
contact microphone attached to the strap.

## Hardware Assumptions

The lab route is:

- Native Instruments Komplete Audio 6 MK2 using `Komplete Audio ASIO Driver`
- three-channel ASIO playback at 44.1 kHz
- requested latency `0.010`
- blocksize `256`
- Woojer Strap 4 for the tactile target during participant runs

The Komplete Audio 6 MK2 is documented as a 24-bit / 192 kHz interface with
4 analog inputs and 4 analog outputs plus digital I/O. The Woojer Strap 4
manual lists analog aux input and 1-250 Hz haptic frequency response. Vendor
source links are written into each validation `device_specs.json` report.

## Cable Plan

Use two distinct cable states. Do not mix them.

### Calibration Loopback State

Use this state before participant testing.

1. Turn Komplete output volume down.
2. Turn input gain low.
3. Turn phantom power off.
4. Set inputs 1/2 to line input mode, not instrument/Hi-Z.
5. Disconnect or mute headphones and Woojer.
6. Patch physical output 1 to physical input 1 with a 1/4-inch TRS line cable.
7. Patch physical output 2 to physical input 2 with a 1/4-inch TRS line cable.
8. Patch physical output 3 to physical input 3 with a 1/4-inch TRS line cable.
9. Optional: patch output 4 to input 4 only for padded or future 4-channel tests.

Physical labels are 1-based. Software selectors are 0-based:

| Physical jack | Software selector | Role |
| --- | ---: | --- |
| Output 1 | output 0 | left audio |
| Output 2 | output 1 | right audio |
| Output 3 | output 2 | tactile drive |
| Input 1 | input 0 | left loopback |
| Input 2 | input 1 | right loopback |
| Input 3 | input 2 | tactile loopback |

### Experiment State

Use this state for participant runs after calibration passes.

1. Remove the direct output-to-input loopback patches.
2. Route output 1/2 to headphones or a headphone amplifier.
3. Route output 3 to the Woojer Strap 4 analog aux input.
4. Use the wired analog Woojer path for timing-sensitive tactile work.
5. Do not use Bluetooth for tactile timing validation.

If continuous participant-run loopback is needed later, add proper line-level
splitters or a distribution amplifier. Do not create ad hoc Y-cable loading as
the default validation path.

## Commands

Write the device specs, wiring plan, and local route snapshot:

```powershell
pps-latency-validate specs
```

Run active electrical calibration:

```powershell
pps-latency-validate calibrate --establish-baseline
```

After a baseline exists, run the same command without establishing a new
baseline:

```powershell
pps-latency-validate calibrate
```

Validate available loopback recordings from an existing session:

```powershell
pps-latency-validate validate-session --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS
```

## Output Files

Calibration writes a timestamped folder under:

```text
artifacts\latency_validation\
```

Important files:

- `device_specs.json`: vendor/spec snapshot and scope limitations
- `wiring_plan.json`: cable state checklist and channel map
- `route_snapshot.json`: local route, sample rate, latency, blocksize, selectors
- `calibration_stimulus.wav`: generated 3-channel pulse train
- `planned_pulses.csv`: expected pulse samples and times
- `loopback_capture.wav`: captured physical loopback recording
- `latency_events.csv`: detected pulse timing per channel
- `latency_summary.csv`: per-channel detection, latency, jitter, drift
- `latency_validation_report.json`: full pass/fail report

Baselines are written under:

```text
local_data\latency_baselines\
```

That folder is local-only and should not be published.

## Pass/Fail Rules

The default calibration fails if any of these checks fail:

- selected route is not a usable 3-channel full-duplex route
- callback reports status flags
- fewer than 95% of planned pulses are detected on any channel
- any channel is clipped
- any channel is below the minimum usable signal level
- left/right median skew is greater than 1 ms
- tactile/audio median skew is greater than 2 ms
- p95 residual jitter is greater than 2 ms on any channel
- max residual jitter is greater than 5 ms on any channel
- drift is greater than 0.5 ms/min on any channel
- when a baseline exists, median roundtrip shift is greater than 3 ms
- when a baseline exists, inter-channel skew shift is greater than 1 ms

## Interpreting Failures

Low signal usually means the input gain is too low, the wrong input was patched,
or the interface is not receiving the expected physical output.

Clipping means output level or input gain is too high. Lower the output first,
then reduce input gain.

Large inter-channel skew means the route is not behaving like one synchronized
multichannel path. Confirm `Komplete Audio ASIO Driver` is selected and do not
split rendered stimuli over separate Windows stereo endpoints.

Callback status flags usually indicate the buffer settings are too aggressive
or another audio client is interfering. Close other audio applications and rerun
with the default `0.010` latency and `256` blocksize before changing protocol
settings.

Session validation aligns block recordings by the first detected tactile event
and checks intra-block residual timing. It is useful as a QC layer for existing
session recordings, but absolute electrical latency should be established with
`pps-latency-validate calibrate`.

## Callback-Derived LSL Timing Checklist

Use this checklist after a participant session has been prepared from Segment 5
and Segment 6 and before relying on LSL markers for EEG alignment.

1. Prepare one participant session through the dashboard/runner so the session
   folder contains participant block CSVs with `Trial_Start_Sample`,
   `Looming_Onset_Sample`, `Tactile_Onset_Sample`,
   `Response_Window_Onset_Sample`, and `Trial_End_Sample`.
2. In Focus Mode, complete participant metadata and press `Submit setup` before
   starting the run. That setup submission creates the session-lifetime LSL
   outlets and keeps `Start Run` locked until the runner can prepare them.
   If using the runner-owned LabRecorder path, enable `Record full-session
   LabRecorder XDF` before setup/start; the runner will confirm both LSL
   streams by session `source_id`, start LabRecorder through RCS, wait until
   LabRecorder reports data collection started for both streams, and hold
   playback until that gate passes. The native XDF is written directly to the
   participant session folder as `<session_id>_external_labrecorder.xdf`. If
   using a separate lab EEG recorder, start it after setup submission but
   before block playback and confirm both LSL
   streams are visible:
   - `PPSMarkersV2` for rich reconstructable string markers.
   - `PPSTriggerCodes` for numeric trigger codes.
3. Play a short block or use a prepared dry-run participant. Do not use
   trial-by-trial WAV playback; the validated runner path is one continuous
   WAV per block.
4. After playback, inspect the participant session folder and verify:
   - `events.csv` contains callback-derived trial/stimulus rows with
     `timestamp_quality = dac_time_sample_exact` whenever PortAudio DAC timing
     was available.
   - `lsl_markers.csv` mirrors each LSL marker attempt with `event_code`,
     `trigger_key`, `lsl_timestamp`, `sample_index`, and `trial_uid`.
   - `lsl_markers.xdf` stores the same internal rich/numeric marker records in
     XDF form so local reconstruction does not depend on an external recorder.
   - `trigger_dictionary.json` maps every numeric EEG trigger code back to a
     deterministic `trigger_key`.
   - Optional `*_audio_evidence.wav` files contain the runner's mixed output
     buffers, including tactile-channel response marker clicks, but are not a
     physical loopback measurement.
   - `timing_qc.csv` contains response marker versus mouse-click deltas for
     participant clicks.
5. If `timestamp_quality` falls back to `callback_stream_time_estimated` or
   `callback_perf_fallback`, keep the run for software debugging but treat it as
   weaker timing evidence than a `dac_time_sample_exact` run.
6. If hardware loopback is connected, compare the physical tactile/audio
   onsets in the loopback recording against `Tactile_Onset_Sample` and
   `response_marker_start` from the logs. Large systematic offsets should be
   documented as route latency; large jitter should be fixed before collecting
   participant data.
