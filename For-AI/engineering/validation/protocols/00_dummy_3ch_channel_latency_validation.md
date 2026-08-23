# Protocol 00: Dummy 3-Channel Channel And Latency Validation

## Purpose

Validate the basic measurement chain before using real experiment stimuli. This
protocol uses a generated 3-channel WAV with five coded rectangular pulses at
varied intervals. It is intentionally simple so channel routing, latency, and
data-collection failures are easy to see.

This protocol answers three questions:

1. Can one 3-channel WAV reliably split to the intended physical outputs?
2. Are audio channels 1/2 and tactile channel 3 synchronized closely enough?
3. Can our measurement/logging pipeline accurately measure that synchronization?

## Channel Mapping Under Test

The expected physical route is:

| WAV channel | Physical target | Validation meaning |
| ---: | --- | --- |
| 1 | left Sennheiser headphone path | left audio output |
| 2 | right Sennheiser headphone path | right audio output |
| 3 | Woojer/tactile output path | tactile drive output |

For the current electrical validation, patch outputs 1/2/3 back to inputs
1/2/3. The Woojer device is not physically in the current loop; future Woojer
mechanical validation should add an external vibration sensor, contact
microphone, or accelerometer and label the result as mechanical tactile onset.

## Stimulus

The default dummy stimulus is:

- sample rate: `44100`
- channels: `3`
- pulse count: `5`
- pre-roll: `1.0 s`
- pulse grid intervals: `300, 800, 1500, 2200 ms`
- post-roll: `1.0 s`
- hardware playback amplitude: `0.05`
- maximum hardware playback amplitude in these scripts: `0.10`

The three channels share nominal pulse onsets, but the pulse shapes are coded by
channel. This makes channel misrouting, downmixing, and channel-3 loss
detectable.

## Hardware Safety

- Start with interface output and input gains low.
- Do not treat equal knob positions as equal recorded signal levels. Different
  input paths can have different effective gain; acceptance is based on the
  recorded peak, SNR, shape correlation, and clipping flags.
- Do not run calibration tones through headphones or the Woojer while they are
  worn or attached; use electrical loopback for this first pass.
- Keep phantom power off on inputs used for direct loopback.
- Treat clipping as a failed safety and data-quality check. Stop and reduce
  gain rather than accepting the run.
- If one channel is too quiet while another is near clipping, fix routing,
  selector state, or input-gain balance instead of increasing the WAV amplitude.
- Avoid maximum input gain unless the recorded level is still low and the other
  channels are also safely below clipping. A max-gain capture that clips is a
  failed validation run, even if the route identity is otherwise correct.

## Procedure

Generate the dummy validation dataset without opening hardware:

```powershell
python .\For-AI/engineering/validation\scripts\make_dummy_pulse_stimulus.py
```

Run the primary direct loopback validation:

```powershell
python .\For-AI/engineering/validation\scripts\run_dummy_pulse_latency.py --device-query Komplete --record-asio-loopback
```

Optional run with LSL marker emission:

```powershell
python .\For-AI/engineering/validation\scripts\run_dummy_pulse_latency.py --device-query Komplete --record-asio-loopback --emit-lsl
```

Do not use WASAPI loopback for ASIO-route acceptance. On this setup, the Native
Instruments ASIO stream can bypass the Windows endpoint that WASAPI records, so
WASAPI loopback is inefficient and may return no data even when the physical
Komplete outputs are correct.

Compare recordings:

```powershell
python .\For-AI/engineering/validation\scripts\compare_dummy_pulse_recordings.py --run-dir artifacts\validation_runs\dummy_pulse_YYYYMMDD_HHMMSS
```

After a single-output route sweep, quantify level balance without playing more
audio:

```powershell
python .\For-AI/engineering/validation\scripts\analyze_dummy_signal_levels.py --run-dir artifacts\validation_runs\dummy_output_route_sweep_YYYYMMDD_HHMMSS
```

If a channel is visible but fails the acceptance gate, adjust analog input gain
or input mode and repeat the route sweep at the same digital amplitude. For ASIO
selector diagnostics, sweep more physical output selectors without raising the
signal:

```powershell
python .\For-AI/engineering/validation\scripts\run_dummy_output_route_sweep.py --device-query Komplete --input-channels 6 --output-channels 6 --sweep-output-count 6 --amplitude 0.05
```

## Acceptance Criteria

- One 3-channel WAV plays as three independent physical outputs.
- Channels 1/2/3 are not misrouted, mixed, downmixed, or dropped.
- Detection rate is at least 95 percent per channel.
- No channel clips or falls below the minimum usable signal.
- Captured channel levels are gain-balanced enough for detection; knob
  positions alone are not evidence of matched recording levels.
- Electrical left/right median skew is <= 1 ms.
- Electrical tactile-vs-audio median skew is <= 2 ms.
- Residual jitter remains within the existing loopback thresholds.
- LSL markers, when enabled, contain all expected pulse events with no duplicate
  pulse IDs.
- Measurement latency and jitter are reported separately from physical
  output-to-input latency.

## Deferred Mechanical Extension

Direct channel-3 electrical timing is not the same as Woojer mechanical onset.
The current protocol stops at electrical tactile-drive timing because the
Woojer is not physically in the loop. Do not claim mechanical tactile latency
unless the Woojer output is later measured with an external sensor.
