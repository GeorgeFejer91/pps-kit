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

## Existing Designer payload adapter

`design::plan_ingredient_generation(payload, opt_in)` consumes the complete
`collectPayload()` object plus `bake_recipe`, including pending
`trajectory_controls`. `GenerationOptIn` requires the exact source algorithm,
`accept_non_legacy_source_algorithm: true`, and the native seed for generated
noise. Legacy NumPy IDs fail. The returned plan contains the request, renderer
policy, opaque HRTF/import references, and canonical source/snapshot metadata.
It never opens a path. The host resolves imports only from native picker or
verified **dry-source** receipts, never from arbitrary saved `source_input_path`
or a prebaked spatial output. Import SHA/channel/length policies are required.

Unchanged rounded controls preserve saved polar arcs and unwrapped angles.
Deliberate endpoint edits follow the existing Cartesian control semantics;
explicit polar edits require complete polar design fields. Pending holds and
movement update both DSP and canonical metadata. Estimated SPL maps to digital
targets but remains unmeasured; measured claims fail pending verified receipts.
The native policy defaults to propagation delay on, near-field/far filtering off,
with explicit attenuation derived from the level policy. The optional recipe
`spatialization` object can explicitly set those three Boolean effect switches;
near-field and far filtering still fail as unsupported.

After generation, `write_ingredient_wav` emits stereo and rejects any tactile
cue. `design::generated_ingredient_entry(plan, relative_path, wav_bytes,
stimulus, renderer_report, cancelled)` checks staged PCM against the DSP result
and renderer policy, hashes the actual WAV, and returns a Serialize-only receipt.
`design::apply_generated_ingredient(plan, entry)` returns canonical `design` and
`asset` values plus `invalidate_segments: [2,3,4,5,6]` and
`invalidate_run_package: true`. It inserts/replaces the correct collection,
propagates existing source-label references, and marks the design customized
and unqualified. The host owns accepted-plan locks, revision/cancellation fences,
atomic publication, and downstream file/state invalidation. A plan digest binds
the full payload **and** explicit algorithm/seed opt-in.

`tests/fixtures/ingredient_payload.json` freezes the existing payload shape;
it is a contract fixture, not a real study qualification. The explicit native
adapter test rendered its polar burst path through the actual C++ executable,
verified stereo bytes/metadata, and measured the calibrated window within
±0.02 dB in 15 s (2026-10-27).

## Frozen source-block assembly

`assembly::VerifiedAssemblyAsset::from_wav_bytes(reference, bytes, sha256, role,
cancelled)` decodes bounded PCM16/24/32 or float32 WAV. Roles are
`BinauralIngredient`, `Instruction`, `TactileCue`, and `StationaryBaseline`.
The native-only receipt binds actual samples and hash. It opens no path;
the host resolves only native-authorized assets and budgets all acquisition.
Rates must match. Mono instructions duplicate into L/R; tactile must be the
verified existing mono cue. There is no source substitution or hidden resampling.

`plan_assembly_preview(design, preview, variants, assets, tactile, cancelled)`
consumes all existing Segment 5 `blocks[].preview_rows` and the existing
`stripPreviewVariants` choices as `{row_label, sequence_variant_key, choices}`.
It checks design seed/block count, row counts/order, unique source/variant
bindings, chosen factors, bounded sample counts and complete cue fit. It returns
`AssemblyPreview` with corrected actual durations/onsets, `accepted: false`,
and hashes for local review. No second randomization happens. The exact existing
instruction offset gain (default -6 dB) applies once. Tactile-only baseline mutes
the looming segment while retaining instructions; stationary-burst baseline
requires a source's explicit `native_stationary_baseline_asset` reference with
the same rate and duration. A moving waveform is never reused as a stationary
comparator. The complete actual 204-row browser fixture correctly reports the
missing stationary comparator; its four selected audio assets and 100 ms cue
are 44.1 kHz. That is a capability check, not successful full-study assembly.

`accept_assembly_preview(preview, expected_design_hash, expected_preview_hash,
revision)` creates a native-only accepted plan. `prepare_accepted_session(plan,
assets, tactile, private_output_dir, participant_id, session_id, cancelled)`
then writes actual 3-channel trial/block WAVs, exact source CSV rows, sample-indexed
prepared CSVs, and a `pps-run-session.v1` participant-block package. The directory
must be new; it remains private until the host revalidates it with the existing
package verifier and atomically publishes its manifest reference after the
revision/cancellation fence. Do not rename an already verified candidate because
V1 source paths bind that directory. Failed partial candidates remain private
for host cleanup. WAV/CSV/JSON files are flushed before the manifest is returned.

This checkpoint assembles reviewed **source blocks once**. Pre/post phases,
counterbalanced participant order and instruction-slot execution require the
existing participant planner contract and are explicitly gated; they are not
flattened into one invented part. Tests verify two real source blocks through
the production package verifier and event scheduler, exact audio/tactile samples,
preserved row order, missing/stale inputs, and cancellation during WAV writing
without a session manifest. Output remains physically unqualified.

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
additional trajectory/burst policies; ILD near-field correction; complete
participant/phase profile assembly and instruction slots; physical calibration.
This subset is not full catalogue replication.
