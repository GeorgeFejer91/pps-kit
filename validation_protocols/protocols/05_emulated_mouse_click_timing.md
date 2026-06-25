# Protocol 05: Emulated Mouse Click Timing

## Purpose

Verify that response logging and the low-gain tactile-channel response marker
stay linked and stable. This checks software response capture and marker-output
behavior, not human reaction time.

## Safety

The emulation script can generate real OS mouse clicks. Run it only with a test
participant/session and after confirming the pointer location is safe. The
script requires `--armed` before it clicks.

## Procedure

First run the internal software harness. This does not click the GUI; it checks
that the event logger, callback-derived response-marker timestamps, timing QC,
and optional LSL streams agree on the same click-to-marker timing:

```powershell
python .\validation_protocols\scripts\run_mouse_response_timing_stress.py --enable-lsl --count 50 --interval-s 0.02
python .\validation_protocols\scripts\lsl_marker_probe.py --stream-name PPSMarkersV2 --duration-s 15 --expected-count 104
python .\validation_protocols\scripts\lsl_marker_probe.py --stream-name PPSTriggerCodes --duration-s 15 --expected-count 104
python .\validation_protocols\scripts\compare_response_timing_strategies.py `
  --events-csv artifacts\validation_runs\mouse_response_timing_stress_YYYYMMDD_HHMMSS\events.csv `
  --timing-qc-csv artifacts\validation_runs\mouse_response_timing_stress_YYYYMMDD_HHMMSS\timing_qc.csv `
  --rich-lsl-probe-csv artifacts\validation_runs\lsl_probe_rich\lsl_marker_probe.csv `
  --output-dir artifacts\validation_runs\response_strategy_comparison
```

Then run the session-runner click-path stress. This still does not click the
desktop, but it exercises the real `SessionRunnerController.log_click()` path
during active playback with a deterministic fake audio engine:

```powershell
python .\validation_protocols\scripts\run_session_runner_click_path_stress.py --count 25 --interval-s 0.02
```

Then run the retired visible-runner OS-click stress only when historical Tk
regression coverage is needed. This opens the retired Tk runner surface, uses a
deterministic fake audio engine so no hardware audio is played, and sends armed
OS clicks to the visible click target:

```powershell
python .\validation_protocols\scripts\run_visible_runner_os_click_stress.py `
  --output-dir artifacts\validation_runs\visible_runner_os_click_stress_current `
  --count 10 --interval-s 0.05 --armed
```

For final physical backup validation, run the OS-click test against a
deterministic active runner session with direct loopback recording:

1. Prepare and start a deterministic test session.
2. While the block is playing, run:

```powershell
python .\validation_protocols\scripts\emulate_mouse_clicks.py --count 10 --interval-s 0.5 --start-delay-s 2 --armed
```

3. After the session finishes, summarize:

```powershell
python .\validation_protocols\scripts\summarize_validation_run.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS
```

4. If direct loopback recording is patched, also run session validation:

```powershell
pps-latency-validate validate-session --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS
python .\validation_protocols\scripts\compare_response_marker_loopback.py --session-dir local_data\sessions\P001_YYYYMMDD_HHMMSS --tactile-channel 3
```

## Acceptance Criteria

- Every emulated click during active playback creates a `mouse_click`.
- Every in-playback `mouse_click` has a linked `response_marker_start`.
- The session-runner click-path stress produces one linked
  `response_marker_start` for every controller-level click, with
  `dac_time_sample_exact` marker timestamps.
- The visible-runner OS-click stress produces one in-target `mouse_click` and
  one linked `response_marker_start` for every armed OS click while fake
  playback is active.
- `analysis/timing_qc.csv` reports stable marker-minus-mouse delays using the
  monotonic clock for delay calculation.
- Rich LSL and numeric trigger-code probes receive all expected response timing
  markers with no missing or duplicate event IDs.
- Strategy comparison reports local click-to-marker timing, rich LSL sample
  timestamp delay, and external LSL arrival delay separately.
- Direct loopback shows the response marker on the tactile channel when
  recording is available.
- `compare_response_marker_loopback.py` recovers every logged
  `response_marker_start` from the tactile-channel recording after fitting the
  physical recording offset, with p95 residual jitter at most 2 ms and maximum
  residual at most 5 ms.

## Not Measured

The internal harnesses do not estimate real participant motor latency,
button-box hardware latency, physical response-marker recovery, or Woojer
mechanical onset. The visible-runner harness is retained only as historical Tk
regression coverage; Focus Mode is the public participant runner UI.
