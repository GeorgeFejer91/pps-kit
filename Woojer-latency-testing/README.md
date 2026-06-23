# Woojer Audio Loopback Latency Testing

This folder is an isolated lab workflow for measuring Woojer audio pass-through
latency. It is not part of the toolkit runtime, dashboard workflow, or
participant runner. Generated run outputs stay local under `runs/` and are
ignored by Git.

## Measurement Scope

This protocol measures the audio signal that exits the Woojer after the
Komplete Audio 6 MK2 sends a pulse into the Woojer. It does not measure Woojer
mechanical vibration onset, participant perception, comfort, or behavioral PPS
validity.

## Wiring States

Use one wiring state at a time.

### Direct Baseline

1. Turn Komplete output volume down.
2. Turn the selected Komplete input gain low.
3. Keep phantom power off.
4. Patch Komplete Output 3 to Komplete Input 3.
5. Run a low-amplitude baseline test.

### Woojer Loop

1. Turn Komplete output volume down.
2. Route Komplete Output 3 to the Woojer analog input.
3. Route the Woojer audio output back to Komplete Input 3.
4. Keep the Woojer on the wired audio path, not Bluetooth.
5. Run a low-amplitude Woojer-loop test and compare it against the direct
   baseline run.

Physical jack numbers are 1-based. The script options are also 1-based for
researcher-facing channel names.

## Commands

Run the direct Komplete baseline:

```powershell
python .\Woojer-latency-testing\scripts\run_woojer_audio_loopback_stress.py --mode direct-baseline
```

Run the Woojer loop and subtract the direct baseline median:

```powershell
python .\Woojer-latency-testing\scripts\run_woojer_audio_loopback_stress.py --mode woojer-loop --baseline-run .\Woojer-latency-testing\runs\direct-baseline_YYYYMMDD_HHMMSS
```

Append the result to the tracked LaTeX log:

```powershell
python .\Woojer-latency-testing\scripts\run_woojer_audio_loopback_stress.py --mode woojer-loop --baseline-run .\Woojer-latency-testing\runs\direct-baseline_YYYYMMDD_HHMMSS --append-tex-log
```

Useful options:

```text
--drive-output-channel 3
--return-input-channel 3
--pulse-count 120
--pulse-interval-ms 500
--repeats 3
--max-added-latency-ms 25
```

By default, the workflow is measure-first: it checks signal reliability and
jitter but does not fail on absolute Woojer-added latency unless
`--max-added-latency-ms` is provided.

## Outputs

Each run writes a timestamped folder under `Woojer-latency-testing/runs/`:

- `stimulus.wav`: generated pulse train.
- `capture.wav`: captured Komplete input signal.
- `planned_pulses.csv`: expected pulse sample indices.
- `woojer_audio_loopback_events.csv`: per-pulse detections.
- `woojer_audio_loopback_report.json`: machine-readable report.
- `woojer_audio_loopback_report.md`: human-readable report.

## Interpretation

Use `direct-baseline` to estimate the Komplete output-input roundtrip for the
selected cable path. Use `woojer-loop` to estimate the combined Komplete plus
Woojer audio pass-through path. When a baseline report is supplied, the script
reports Woojer-added latency as:

```text
woojer_loop_latency - direct_baseline_latency
```

If the return signal is low, clipped, unstable, or missing pulses, fix wiring,
levels, or device selection before interpreting latency numbers.
