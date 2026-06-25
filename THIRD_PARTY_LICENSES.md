# Third-Party Licenses

## 3DTI AudioToolkit

- Project: 3DTI AudioToolkit
- Repository: https://github.com/3DTune-In/3dti_AudioToolkit
- Pinned commit: `6bfee08705675308a8c348b4c3a4d582586d2f99`
- License: GNU Lesser General Public License v3.0 only (`LGPL-3.0-only`)
- Local source snapshot: `third_party/3dti_AudioToolkit/`

The 3DTI AudioToolkit and Resource Management Package are copyright University
of Malaga and Imperial College London. The upstream license files are preserved
in `third_party/3dti_AudioToolkit/3DTI_AUDIOTOOLKIT_LICENSE` and
`third_party/3dti_AudioToolkit/LICENSE`.

Only source, documentation, and build-relevant files are vendored. Upstream
sample resources are intentionally excluded from this repository.

When distributing binaries that link against 3DTI, keep the LGPL obligations
intact: include license notices, provide the corresponding 3DTI source or exact
source offer, and allow users to replace or relink the LGPL component.

## nlohmann/json

- Project: JSON for Modern C++
- Repository: https://github.com/nlohmann/json
- Bundled version: v3.11.3
- License: MIT
- Bundled files: `third_party/nlohmann_json/single_include/nlohmann/json.hpp`
  and `third_party/nlohmann_json/LICENSE.MIT`
- Pin manifest: `third_party/nlohmann_json.PINNED.json`

This header-only parser is used by the native `pps-3dti-renderer` wrapper to
read the render config emitted by the Python GUI.

## cereal

- Project: cereal
- Repository: https://github.com/USCiLab/cereal
- Pinned commit: `51cbda5f30e56c801c07fe3d3aba5d7fb9e6cca4`
- License: BSD 3-Clause
- Bundled path:
  `third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/cereal/`

cereal is a 3DTI-pinned submodule used for reading/writing `.3dti-hrtf`
resource caches.

## Eigen

- Project: Eigen
- Repository: https://github.com/eigenteam/eigen-git-mirror
- Pinned commit: `a1b9c26c5e62cb8c17836e601edd64b92aa8e5ae`
- Primary license: MPL 2.0, with some files under BSD/LGPL as noted upstream
- Bundled path:
  `third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/eigen/`

Eigen is a 3DTI-pinned submodule used by 3DTI hearing-aid/hearing-loss support
code that is compiled into the native wrapper dependency graph.

## SOFA C++ API and Runtime Dependencies

- Project: SOFA API C++
- Repository: https://github.com/sofacoustics/API_Cpp
- Pinned commit: `2c5c3e269f66f5d6854bb9941937d43f8578fd04`
- License: BSD-style license in
  `third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/sofacoustics/libsofa/doc/LICENCE.txt`
- Bundled path:
  `third_party/3dti_AudioToolkit/3dti_ResourceManager/third_party_libraries/sofacoustics/`

The native `pps-3dti-renderer` builds this 3DTI-pinned SOFA API source so it
can load the bundled FABIAN `.sofa` file directly. The pinned SOFA API snapshot
also includes Windows x64 runtime binaries for NetCDF, HDF5, Curl, and Zlib;
these are copied beside the renderer executable by
`windows/Build_3DTI_Renderer.ps1`.

## Three.js

- Project: Three.js
- Repository: https://github.com/mrdoob/three.js
- Vendored files: `src/peripersonal_space_toolkit/viewer/vendor/three/`
- License: MIT

Three.js is used only for the embedded trajectory preview. Its license text is
included with the vendored files.

## Redistributable HRTF Candidates

The GUI study profiles preload trajectory, timing, and noise parameters. HRTF
resources are standardized renderer assets under the hood, not arbitrary
experimenter-selected SOFA files. Current and future candidate assets and their
source/license notes are tracked in `assets/REDISTRIBUTABLE_HRTF_ASSETS.md`.

Only include HRTF files in a public release bundle when that release also
includes attribution, license metadata, and file hashes for the exact bundled
files.
