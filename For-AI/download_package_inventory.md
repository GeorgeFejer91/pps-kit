# Download Package Inventory

This file records what future agents must preserve when packaging PPS Toolkit as an easy-to-download Windows software package.

## Release Shape

The repo should contain the installer package source, not heavyweight release binaries.

- Tracked installer source: `windows/downloader/`
- Tracked installer package definition: `windows/installer_package_inventory.v1.json`
- Package inventory generator and validator: `tools/package_inventory.py`
- Lightweight GitHub release output: `dist/PPS-Toolkit-Downloader.exe`
- Heavyweight offline lab package: `dist/PPS-Toolkit-vX.Y.Z-offline-lab-windows-x64.zip`
- Download verification manifest: `dist/pps_download_manifest.v1.json`
- Generated package inventory inside the ZIP: `pps_package_inventory.v1.json`

`dist/` stays ignored. Release binaries are attached to GitHub/Zenodo releases, not committed to the source repo.

Do not point the public download page directly at
`https://github.com/GeorgeFejer91/pps-kit/releases/latest/download/PPS-Toolkit-Downloader.exe`
until a public GitHub Release actually contains that asset and the matching
`pps_download_manifest.v1.json`. Before that release exists, link the installer
card to `https://github.com/GeorgeFejer91/pps-kit/releases` so the website does
not expose a dead direct-download button.

## Required Offline Package Contents

The offline ZIP must include:

- `dist/PPSExperimentRunner/PPSExperimentRunner.exe` and its PyInstaller onedir resources.
- The packaged Qt Windows platform plugin at `dist/PPSExperimentRunner/_internal/PySide6/plugins/platforms/qwindows.dll`; without it the runner shows "no Qt platform plugin could be initialized" and cannot start.
- Dashboard launchers: `windows/Launch_HTML_Dashboard.bat`, `windows/Start_Website_Companion.bat`, and `windows/Launch_Experiment_Runner.bat`.
- Installer/build support: `windows/downloader/`, `windows/Build_PPS_Downloader.ps1`, `windows/Build_PPS_Distribution.ps1`, `windows/Setup_Windows_App.ps1`, and `windows/Create_Desktop_Shortcut.ps1`.
- Local dashboard and hosted-dashboard assets: `src/peripersonal_space_toolkit/dashboard/`, root `index.html`, `.nojekyll`, and `src/peripersonal_space_toolkit/viewer/`.
- App identity assets under `src/peripersonal_space_toolkit/assets/`.
- Preload catalogs and readiness ledgers under `assets/preloads/`, including `preload_inventory.json` and `profile_recreation_status.json`.
- Study 5 and shared audio assets: `assets/breathing/` and `assets/tactile/default_tactile_cue.wav`.
- The redistributable FABIAN/TU SOFA file and manifest under `assets/0. Head-Related Impulse Response (HRIR) model/`.
- `study_templates/`, `configs/`, and `data/sample/`.
- User docs, release docs, licenses, citation metadata, and third-party attribution: `docs/`, `README.md`, `LICENSE`, `THIRD_PARTY_LICENSES.md`, and `CITATION.cff`.
- Release helper tools needed to audit, manifest, and rebuild the package.

Optional but preferred when available:

- Approved native 3DTI renderer binaries under `third_party/3dti_renderer/bin/`.
- Pinned 3DTI source/attribution material under `third_party/3dti_AudioToolkit/`.

## Build And Verification Order

1. Install dependencies into `.venv` with the Windows setup path or `python -m pip install -e ".[tts,gui,web,lsl,xdf,validation,dev,package]"`. The GUI extra is pinned to PySide6 6.7.x because newer PySide6 releases have broken Qt imports in the current Anaconda-based lab venv.
2. Run tests and release audit before packaging.
3. Build the packaged runner with `windows/Build_Experiment_Runner_Exe.ps1`. This must run `tools/check_qt_runtime.py` before and after PyInstaller so broken PySide6 imports or missing `qwindows.dll` fail the build.
4. Build the offline package with `windows/Build_PPS_Distribution.ps1`.
5. Let `tools/package_inventory.py --strict` validate the staged package and write `pps_package_inventory.v1.json`.
6. Generate `pps_download_manifest.v1.json` with the offline ZIP hash and package inventory hash.
7. Upload the heavy ZIP to Zenodo and the small downloader plus manifest to GitHub Releases.
8. Test the downloader install on a clean Windows folder before announcing the release.

## Do Not Package

Do not include raw participant data, name-bearing exports, generated participant/session outputs, local validation artifacts, downloaded model caches, private local paths, credentials, or unreviewed third-party audio/assets. Local runtime folders such as `local_data/`, `artifacts/`, and `models/` remain ignored.
