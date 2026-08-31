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
`For-AI/engineering/build/windows/Build_3DTI_Renderer.ps1`.

## Three.js

- Project: Three.js
- Repository: https://github.com/mrdoob/three.js
- Vendored files: `apps/designer/frontend/viewer/vendor/three/`
- License: MIT

Three.js is used only for the embedded trajectory preview. Its license text is
included with the vendored files.

## Gradle Wrapper

- Project: Gradle
- Repository: https://github.com/gradle/gradle
- Vendored files:
  `For-AI/experiments/android-companion/runner-companion/gradle/wrapper/gradle-wrapper.jar`
  and `apps/quest-runner/gradle/wrapper/gradle-wrapper.jar`
- License: Apache License 2.0

The Android runner companion source uses the Gradle wrapper to reproduce the
requested Gradle version. Android app dependencies such as AndroidX Compose,
CameraX, ML Kit barcode scanning, OkHttp, Kotlin coroutines, and JUnit are
resolved from Maven repositories during build and are not vendored in this
source tree.

## Browser Remote Sync Protocol

- Project: Browser Remote Sync Protocol
- Repository: https://github.com/GeorgeFejer91/browser-remote-sync-protocol
- Pinned commit: `62ff66c6df724847c1e54161feabb470b67b1192`
- License: MIT
- Consumer: `apps/runner/package.json`; bundled into the deterministic browser
  companion build where imported

BRSP supplies the browser-side typed protocol and data-transport helpers. PPS
Kit's Rust authority and wire profile live in `packages/pps-brsp/` and
`packages/pps-contracts/`.

### VDO.Ninja SDK 1.5.5

- Project: VDO.Ninja SDK / NinjaSDK
- Repository: https://github.com/steveseguin/ninjasdk
- Version: `1.5.5`
- License: Mozilla Public License 2.0
- Local reviewed copy:
  `apps/runner/frontend/public/vendor/vdoninja/1.5.5/`
- Production runtime file: `vdoninja-sdk.min.js`, SHA-256
  `390ea6c8b1a4e57bf7fa18ff2b394f25cc79e637130f97e4a29ca958a90fac77`
- Corresponding readable source: `vdoninja-sdk.js`, SHA-256
  `8097d5420d7ed2426623d7ff08f6abd45f03f89e6540a6cc4b86bcdc057d841e`
- MPL text: `LICENSE-MPL-2.0.txt`, SHA-256
  `3f3d9e0024b1921b067d6f7f88deb4a60cbe7a78e76c64e3f1d7fc3b779b9d04`

The four files in that directory, including `NOTICE.md`, are copied without
modification from the SDK snapshot carried by the pinned BRSP dependency. The
same exact bytes are included in the bundled Runner frontend and the public
Pages companion; no runtime CDN is used. VDO.Ninja supplies data-only WebRTC
signaling and ICE support for this optional adapter. It does not receive PPS
participant records or become the experiment authority.

## Browser companion JavaScript dependencies

- `@noble/hashes` 1.7.1 — MIT — HMAC/SHA-256 in browser contexts where
  `crypto.subtle` is unavailable, including typical cleartext lab-LAN pages.
- `qrcode` 1.5.4 — MIT — local QR rendering for fragment-based invitations.
- Vite 6.4.3 — MIT — build-time frontend bundler; it is not a production
  runtime dependency.
- Tauri JavaScript API/CLI 2.x — Apache-2.0 OR MIT — desktop bridge and build
  tooling.

Exact resolved JavaScript packages and integrity hashes are recorded in
`apps/runner/package-lock.json`. No companion runtime dependency is loaded from
a CDN.

## Hound

- Project: Hound WAV encoding and decoding library
- Repository: https://github.com/ruuda/hound
- Version: `3.5.1` (exactly pinned in the Rust workspace)
- License: Apache License 2.0
- Consumer: `packages/pps-runner-audio/`

Hound parses the narrowly accepted PCM16 prepared-WAV format in the native
Runner audio-preparation seam. It is resolved through `Cargo.lock`; its source
is not vendored in this repository.

## Tauri and Meta Spatial SDK build dependencies

The candidate desktop application resolves Tauri v2 and its Rust dependencies
through `Cargo.lock`; their individual licenses are recorded in upstream crate
metadata. The candidate Quest application resolves Meta Spatial SDK 0.13.2,
AndroidX Compose, Kotlin, OkHttp, and related Android dependencies from Maven
repositories. Those binaries are not vendored source and remain subject to
their respective vendor and open-source terms. Direct versions are pinned in
`apps/quest-runner/gradle/libs.versions.toml`, but the preview does not yet
commit Gradle dependency locks or verification metadata for every transitive
artifact. Generate and review the complete resolved dependency, checksum, and
license inventory before any public APK release.

## Springer Nature LaTeX Author Template

- Project: Springer Nature LaTeX author template
- Source page: https://www.springernature.com/gp/authors/campaigns/latex-author-support
- Overleaf entry:
  https://www.overleaf.com/latex/templates/springer-nature-latex-template/myxmhdsbzkyd
- Downloaded package:
  `For-AI/research/publication/behavior-research-methods/springer-nature-latex-template-dec-2024.zip`
- Extracted files:
  `For-AI/research/publication/behavior-research-methods/springer-nature-latex-template/`
- Download date: 2026-06-30
- ZIP SHA-256:
  `812E76DCAA9C28DC1BFF1FB6065D51729B67D4EA140552A05088317414A3ECAE`

These are third-party author-support materials for preparing Springer Nature
journal submissions, added for the Behavior Research Methods manuscript
workspace. The template files retain their upstream notices; for example,
`sn-jnl.cls` declares LaTeX Project Public License terms for the generated class
source. The template package is not part of the PPS Toolkit MIT license grant.

## Redistributable HRTF Candidates

The GUI study profiles preload trajectory, timing, and noise parameters. HRTF
resources are standardized renderer assets under the hood, not arbitrary
experimenter-selected SOFA files. Current and future candidate assets and their
source/license notes are tracked in `assets/REDISTRIBUTABLE_HRTF_ASSETS.md`.

Only include HRTF files in a public release bundle when that release also
includes attribution, license metadata, and file hashes for the exact bundled
files.
