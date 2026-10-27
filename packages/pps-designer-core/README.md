# Native generation kernel

First Rust generation slice for the Windows Designer. No Python runtime,
playback/device access, process spawning, or publication authority. Outputs are
staged and unqualified. This does not establish study-source conformance,
measured SPL, or participant-run readiness.

## Scientific contract

Requests must name `pps-native-generation.v1` and
`rand-0.8.8-std-rng-box-muller.v1`. The latter explicitly selects a new source
algorithm: locked rand 0.8.8 StdRng, Box–Muller pairs, dry peak normalization,
f32 PCM. Seeds are **not NumPy-compatible**. No legacy profile is implicitly
migrated. Unknown fields, algorithms, and modes fail. Frozen seed samples detect
drift with tolerance; cross-platform bit identity is not claimed.

Sources: continuous white/pink/blue/violet/brown noise or colored Gaussian bursts with
duration-derived count, symmetric fitting, and raised-cosine edges. Burst seeds
are `seed + 37 * burst_index` (wrapping u64). Timing rounds ties to even. Fixed
and linear/polar paths include holds; PPS coordinates are X right, Y front, Z up.
Polar radius and unwrapped azimuth interpolate directly at constant elevation,
matching the reference arc (170→-170 goes through the front). They are not
converted to Cartesian chords. Burst edges use the reference endpoint-exclusive
cosine, with an explicit envelope algorithm in QC and all samples fixture-tested.
Paths inside the listener head fail.

Tactile cues preserve the reference 20 ms frequency switch, half-Hann envelope,
explicit peak, and channel 2. Overlap above full scale, silent subsample cues,
or cues extending outside the stimulus fail instead of being silently rescaled.

Level modes are distinct:

- `preserve` applies only explicit gain, with no spatial-output normalization.
- `linear_db_ramp` holds endpoints, ramps linearly in dB, and scales to target RMS
  in the final active window. Distance attenuation is forbidden. A peak-ceiling
  conflict fails instead of flattening the ramp or lowering its target.

QC always reports `physical_spl_qualified: false`. A caller may derive digital
targets from an independently audited calibration policy; this crate does not
convert an estimate into measured SPL.

The explicit `noise` request combines a color with a `continuous` or
`gaussian_burst_train` profile. Pink/blue/violet use the reference frequency-power
shaping with locked RustFFT 6.4.1; brown uses a cumulative sum. Shared-input NumPy
fixtures test the transformation, without claiming NumPy seed parity. Each
spectral transform is limited to 1,048,576 frames; cancellation is checked before
and after the bounded transform. Default RustFFT CPU dispatch remains enabled.

`imported_wav` requires `wav-pcm-dry.v1`, seed zero, SHA-256, explicit `mono` or
`stereo_mean`, and `exact` or `trim_or_zero_pad`. Call `prepare_imported_wav` with
native-authorized bounded bytes. Hash/headers are checked before PCM allocation.
PCM16/24/32 and float32 WAVs are supported at an exact matching rate. Amplitude
is preserved, and every decoded sample is validated even if a tail is trimmed.
`generation_capabilities()` exposes these limits to the host/UI.

## Integration

1. `prepare(request, cancelled)` validates input and generates dry/tactile PCM.
2. `write_spatializer_input(prepared, writer, options, cancelled)` writes float32
   little-endian `dry.f32`. Serialize its returned config beside it.
3. The native job owner invokes the rebuilt 3DTI executable with `--config`,
   `--output-dir`, `--manifest`, `--qc`, in a unique staging directory. Bound
   logs/deadline and kill/reap the child on cancellation or timeout.
4. `read_stereo_wav` checks exact rate, frames, format, finite samples and layout.
5. `compose_spatial_output` applies levels and interleaves L/R/tactile.
   `write_stimulus_wav` writes the final three-channel float WAV.
6. Retain request, source QC, level QC, native report and actual file hashes.
   Recheck job/revision/cancellation before atomic publication. A cancelled
   write may leave a partial staging file; the kernel never publishes it.

HRTF paths require native authorization. HRTF and source rates must match;
there is no implicit resampling. Attenuation and propagation are explicit.
Far-distance filtering is disabled. Near-field correction fails pending verified
ILD asset support. HRTF ear geometry can still change level with distance when
the gain controller is off.

Limits: 8–192 kHz; 60 s / 11,520,000 frames; 256 tactile cues. Allocation is
fallible, and bounded loops check cancellation. At the maximum, one job needs
hundreds of MiB across PCM buffers plus the separate HRTF process. The caller
must serialize generation against its resource budget.

## Verification

`cargo test -p pps-designer-core` tests actual PCM, channels, silence, timing,
gain, and RMS. `tests/fixtures/reference_oracle.py` is a development-only capture
of existing Python tactile samples, burst timing and loudness-window targets
at reference commit `ae8a4aa43e6046aa5e12e632496410a5dd41b2ca`. It is never a shipped
fallback. A deliberate 20→19 ms tactile-switch mutation failed the fixture test;
restoring it passed.

```powershell
$env:PPS_TEST_RENDERER = (Resolve-Path 'artifacts/3dti-v2-bin/Release/pps-3dti-renderer.exe').Path
cargo test -p pps-designer-core --test native_spatializer -- --ignored --nocapture
```

The explicit native test measures input/output PCM hashes, no hidden
normalization, attenuation at identical geometry, moving left/right cues,
propagation delay, rate rejection, tactile preservation, and actual/target RMS
within ±0.02 dB. A too-loud burst ramp deliberately fails the ceiling and a
lower explicit target succeeds. The 2026-10-27 MSVC/FABIAN run, including polar
versus Cartesian waveform differences, passed in 67 s.
Evidence remains in ignored `artifacts/`. No audio device is opened or qualified.

Unavailable: legacy NumPy generation; resampled or compressed imported sources;
additional trajectory/burst policies; ILD near-field correction; full profile
assembly; physical calibration. This subset is not full catalogue replication.
