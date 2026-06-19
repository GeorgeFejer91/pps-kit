# Protocol 02: Audio Route Loopback Latency

## Purpose

Measure electrical output-to-input latency and jitter on the synchronized
3-channel route. This reuses `pps-latency-validate`; it does not measure Woojer
mechanical vibration onset.

## Required Cable State

Use the calibration loopback state:

- Komplete output volume down before patching.
- Input gain low.
- Phantom power off.
- Inputs in line mode, not Hi-Z.
- Headphones and Woojer disconnected or muted.
- Hardware playback amplitude starts at `0.05` and must not exceed `0.10`
  in these internal scripts.
- Clipping is a stop condition: lower gain or repatch before rerunning.
- Physical output 1 to input 1.
- Physical output 2 to input 2.
- Physical output 3 to input 3.
- Optional participant-run proxy: if Focus Mode `Wired loopback: mirror tactile
  to Output 4` is enabled, patch physical output 4 to input 4. This records a
  duplicate tactile-drive proxy while output 3 still drives the Woojer; it does
  not measure the exact Woojer input node or mechanical vibration onset.

Physical jack labels are 1-based. Software selectors are 0-based.

## Procedure

From the repository root:

```powershell
.\validation_protocols\scripts\run_loopback_calibration.ps1 -EstablishBaseline -Repeats 5
```

For follow-up stability runs against the existing baseline:

```powershell
.\validation_protocols\scripts\run_loopback_calibration.ps1 -Repeats 5
```

To validate a session folder that already has block loopback recordings:

```powershell
.\validation_protocols\scripts\run_loopback_calibration.ps1 -SessionDir local_data\sessions\P001_YYYYMMDD_HHMMSS
```

## Acceptance Criteria

- ASIO route is selected for official claims.
- Three full-duplex channels are available.
- No callback status flags.
- Detection rate is at least 95 percent on every channel.
- No clipping and no low-signal failure.
- Left/right median skew is <= 1 ms.
- Tactile/audio median skew is <= 2 ms.
- p95 residual jitter is <= 2 ms.
- Max residual jitter is <= 5 ms.
- Drift is <= 0.5 ms/min.
- Baseline median roundtrip shift is <= 3 ms when a baseline exists.
- Baseline inter-channel skew shift is <= 1 ms when a baseline exists.

## Not Measured

This protocol does not measure tactile transducer mechanics, skin contact,
perceived vibration onset, or Bluetooth behavior.
