# Download and Component Inventory

This file records the V1 Windows distribution boundary future agents must
preserve.

## Published Downloads

One parameterized source tree under `distributions/downloader/` builds three
GitHub-hosted bootstrapper artifacts:

- `PPS-Designer-Downloader.exe`
- `PPS-Experiment-Runner-Downloader.exe`
- `PPS-Toolkit-Downloader.exe`

Each must remain below GitHub's 100 MiB asset limit and should remain below 25
MiB. Heavy, pinned payload ZIPs may be hosted on Zenodo. A bootstrapper must
download, hash-verify, inventory-verify, install, and launch its declared
product; a link-only executable is not a valid release.

## Authoritative Component Manifests

The tracked schema is `pps-component-manifest.v1`:

- `distributions/manifests/shared.v1.json`
- `distributions/manifests/designer.v1.json`
- `distributions/manifests/runner.v1.json`
- `distributions/manifests/full.v1.json`

Each component records ID, version, platform, source-to-install mappings,
dependencies, entrypoints, licenses, and explicit exclusions.

- **Shared** owns approved templates, resources, public docs, required
  runtime/renderer dependencies, and licenses.
- **Designer** owns `PPSDesigner.exe`, the one compiled Designer frontend, and
  Designer-specific installed support. It depends on Shared.
- **Runner** owns `PPSExperimentRunner.exe`, Qt runtime/support, Runner assets,
  installed-PC support, and normal post-run analysis/review. It depends on
  Shared and must include `qwindows.dll`.
- **Full** is exact composition: Designer + Runner + one Shared. It does not
  introduce a hub and creates separate Designer and Runner shortcuts.

Every distributable file has exactly one owning leaf component. Composition may
reference dependencies but must not duplicate their files.

## Compatibility and Install Root

Standalone products may share one chosen install root. The downloader records a
component marker and the Shared version/inventory hash. A second installer must
reject an incompatible Shared component rather than silently mixing releases.

Each download manifest pins its own payload URL, filename, size, SHA256,
component ID/version, component-manifest hash, package-inventory hash,
entrypoints, and dependency declarations. The Full manifest pins the exact
Designer, Runner, and Shared composition.

## Required Product Contents

Designer inventory includes:

- `dist/PPSDesigner/PPSDesigner.exe` and required onedir support
- `apps/designer/frontend/compiled/` as the offline UI
- Designer launch/support material declared by its manifest
- compatible Shared component

Runner inventory includes:

- `dist/PPSExperimentRunner/PPSExperimentRunner.exe`
- `dist/PPSExperimentRunner/_internal/PySide6/plugins/platforms/qwindows.dll`
- audio/ASIO preflight and the frozen-entrypoint `SD_ENABLE_ASIO=1` guard
- prepared-experiment playback, runtime assets, output review/analysis needed
  for ordinary Runner use
- compatible Shared component

Shared inventory includes:

- `packages/pps-resources/assets/`
- `packages/pps-resources/study_templates/`
- `packages/pps-resources/configs/`
- `packages/pps-resources/data/sample/`
- reviewed `third_party/` dependencies and licenses
- public docs, `LICENSE`, `THIRD_PARTY_LICENSES.md`, and `CITATION.cff`

Logical installed paths remain `assets/...`, `study_templates/...`, and related
scientific/profile paths even though the repository sources live under
`packages/pps-resources/`.

## Explicit Exclusions

No component, package inventory, payload, or download manifest may include:

- `For-AI/`
- Android companion source, APKs, Android administration CLIs, phone bridges,
  or visible phone controls
- participant/demographic data or name-bearing exports
- generated sessions, renders, recordings, validation runs, or local caches
- `local_data/`, `artifacts/`, build work directories, or downloaded models
- private absolute paths, credentials, or secrets
- unreviewed third-party assets, unapproved research ledgers, or private paper
  artifacts

The Android companion remains under `For-AI/experiments/android-companion/` and
is development-only for V1.

## Build and Acceptance Order

1. Run structural classification, ownership, release, privacy, and path audits.
2. Build `PPSDesigner.exe` and `PPSExperimentRunner.exe`; verify the Runner's Qt
   plugin and ASIO preflight.
3. Assemble Shared, Designer, Runner, and Full payloads from the component
   manifests and write independent `pps_package_inventory.v1.json` files.
4. Generate component-specific `pps_download_manifest.v1.json` files with final
   URLs and hashes.
5. Build all three downloader executables from the parameterized Go source.
6. On clean Windows folders verify Designer-only, Runner-only, and Full. Full
   must install two shortcuts and one compatible Shared component.
7. Verify the public `/download` route references only assets that exist on the
   release; use the Releases page until direct assets exist.

Build execution lives under `For-AI/engineering/build/`; release assembly and
audits live under `For-AI/engineering/release/`. Generated release outputs stay
under ignored `dist/` and are never committed.

## External Driver Policy

The Native Instruments Komplete Audio ASIO driver is proprietary. PPS may open
the official provider page and display install/reconnect guidance but must not
mirror or bundle the installer without documented redistribution permission.
Installer success does not replace Runner audio preflight. The validated route
uses one native multichannel ASIO stream: auditory outputs 1/2, tactile and
response marker output 3, with output 4 available as a tactile mirror when the
driver requires an even stream width.
