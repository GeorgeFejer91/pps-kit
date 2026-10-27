# PPS 3DTI wrapper

The Windows wrapper retains 3DTI AudioToolkit commit
`6bfee08705675308a8c348b4c3a4d582586d2f99`. The Rust Designer uses
`pps-3dti-spatialize.v2`, consuming prepared PCM with no Python generation.
Rebuilding source does not update installed packages or the historical tracked
executable in `bin/`.

```powershell
pps-3dti-renderer.exe --config staging/config.json --output-dir staging `
  --manifest staging/spatialized.json --qc staging/spatialized.csv
```

## Prepared PCM contract

`packages/pps-designer-core::write_spatializer_input` writes the required config
and `dry.f32`. The config declares rate/frames, algorithm/SHA-256, fixed or linear
motion, explicit spatialization controls, and a native-authorized HRTF asset.
Unknown fields fail. The wrapper verifies byte count, SHA-256 and finite input,
then renders those samples rather than regenerating noise.

Output is exactly stereo L/R float32 with the requested frame count. It has no
normalization, limiter, level ramp or tactile mixing; Rust owns those later
operations. The toolkit HQ anechoic path uses interpolation, customized ITD and
512-frame blocks. Linear motion is sampled at each block center. Convolution
and propagation tails are explicitly truncated at the requested frame count.
Coordinates map `3DTI(x,y,z) = PPS(y,-x,z)` for PPS X right, Y front, Z up.

Attenuation and propagation are explicit switches. Toolkit attenuation uses a
**1.95 m** reference and approximately -6.0206 dB per distance doubling, with
smoothing. HRTF ear projection may still change level/spectrum when gain
attenuation is disabled. Far-distance filtering is disabled. Near-field ILD
correction fails pending a verified ILD asset; an unloaded filter is not
presented as conformance.

Invalid values, source paths inside the listener head, HRTF rate mismatch,
unsupported normalization or layout fail. No implicit resampling occurs.
Limits: 1 MiB config, 8–192 kHz, 60 s / 11,520,000 frames, 512 MiB HRTF. SHA-256
uses Windows BCrypt. The job owner controls deadline, cancellation and staging.

The v2 report records actual source/stereo PCM and HRTF hashes, toolkit commit,
rate/layout, all controls, block/tail policies, digital peak, and
`physical_spl_qualified: false`.

## Build and verify

CMake, a C++17 compiler and Windows SDK are required. The toolkit, JSON header,
and bundled SOFA reader/dependencies are vendored. Keep build outputs away from
tracked historical binaries:

```powershell
cmake -S third_party/3dti_renderer -B artifacts/3dti-v2-build `
  -DPPS_RENDERER_OUTPUT_DIR="$PWD/artifacts/3dti-v2-bin"
cmake --build artifacts/3dti-v2-build --config Release --parallel 4
$env:PPS_TEST_RENDERER = (Resolve-Path 'artifacts/3dti-v2-bin/Release/pps-3dti-renderer.exe').Path
cargo test -p pps-designer-core --test native_spatializer -- --ignored --nocapture
```

The 2026-10-27 MSVC/FABIAN offline test passes source amplitude, attenuation,
motion, propagation, channel, hash and ±0.02 dB level assertions. It opens no
audio device. Packaging, physical qualification and full catalogue support
remain separate. See the kernel README for reference fixtures and limits.

## Historical v1 adapter

`pps-3dti-render-config.v1` remains a legacy Python adapter for compatibility.
It generates C++ noise, uses nearest sampled motion and implicit distance
effects, peak normalizes, mixes tactile itself and emits placeholder WAV hashes.
It is not the new Rust generation path, does not establish NumPy seed or
burst/level conformance, and must not be selected by the native Designer worker.
The rebuilt v2 executable and dependencies need integration/release checks
before being packaged.
