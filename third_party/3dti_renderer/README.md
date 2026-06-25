# PPS 3DTI Renderer Wrapper

The Python/Qt app calls a narrow native executable at:

`third_party/3dti_renderer/bin/pps-3dti-renderer.exe`

The wrapper is the boundary between the experiment-specific PPS designer and
the pinned 3DTI AudioToolkit source snapshot in `third_party/3dti_AudioToolkit`.
It should keep 3DTI as the renderer of record while exposing only this command
line contract to Python:

```powershell
pps-3dti-renderer.exe `
  --config render_config.3dti.json `
  --output-dir rendered `
  --manifest render_manifest.json `
  --qc render_qc.csv
```

Expected native-wrapper behavior:

- read `pps-3dti-render-config.v1`
- synthesize the deterministic generated noise streams
- render one stationary listener and one moving source through 3DTI
- write binaural WAV files named from `outputs.expected_wav_pattern`
- write `render_manifest.json` with exact renderer, resource, WAV, and level hashes
- write `render_qc.csv` with duration, sample rate, peak, clipping, and cue summaries

Current Python behavior:

- `pps-render-design --engine native-3dti` requires this executable and reports
  `backend_missing` when it is absent.
- `pps-render-design --engine auto` uses this executable when available.
- If the executable is absent, `auto` renders with the bundled Python
  SOFA/FABIAN reference engine from the same config and labels outputs
  `rendered_reference`.

The Python reference renderer exists so the GUI can already produce auditable
stimulus WAVs. The native wrapper is still the planned 3DTI renderer-of-record
for final 3DTI-backed publication builds.

## Native Wrapper Source

This folder now contains the small native wrapper project:

- `CMakeLists.txt`
- `src/pps_3dti_renderer.cpp`

The wrapper consumes the exact `render_config.3dti.json` emitted by
`pps-render-design`, maps PPS app coordinates into the default 3DTI coordinate
system, calls 3DTI's anechoic high-quality binaural path, and writes a
three-channel WAV:

- channel 0: binaural left
- channel 1: binaural right
- channel 2: vibrotactile cue

Coordinate mapping:

```text
PPS app: X right, Y front, Z up
3DTI default: X forward, -Y right, Z up
adapter: 3DTI(x, y, z) = (app_y, -app_x, app_z)
```

Build dependencies that are not vendored here:

- CMake and a C++17 compiler
- `nlohmann_json`
- optional: the SOFA C++ reader API that provides `SOFA.h` and
  `SOFAExceptions.h`, needed only when the wrapper reads `.sofa` files directly

The wrapper can load either:

- `source.sofa_file`, using 3DTI's `HRTFFactory` plus the external SOFA C++
  reader; or
- `source.hrtf_3dti_file`, using 3DTI's native `.3dti-hrtf` cereal loader.

The current Python config emits `source.sofa_file` because the bundled FABIAN
asset is a SOFA file. A future release can add a preconverted `.3dti-hrtf` cache
beside the SOFA file and avoid the SOFA C++ reader at native-render runtime.

Example CMake configure:

```powershell
cmake -S third_party\3dti_renderer -B third_party\3dti_renderer\build `
  -DSOFA_INCLUDE_DIR=C:\path\to\sofa\include `
  -DSOFA_LIBRARY=C:\path\to\sofa\lib\sofa.lib `
  -DCMAKE_TOOLCHAIN_FILE=C:\path\to\vcpkg\scripts\buildsystems\vcpkg.cmake
cmake --build third_party\3dti_renderer\build --config Release
```

To build a wrapper that only accepts preconverted `.3dti-hrtf` files:

```powershell
cmake -S third_party\3dti_renderer -B third_party\3dti_renderer\build `
  -DPPS_ENABLE_SOFA_READER=OFF
cmake --build third_party\3dti_renderer\build --config Release
```

The current development machine used for this repository did not have CMake, a
C++ compiler, or the SOFA C++ reader on PATH, so the source is present but the
native executable is not yet bundled.
