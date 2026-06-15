# Download Package Inventory

This file records what future agents must preserve when packaging PPS Toolkit as an easy-to-download Windows software package.

## Release Shape

The user-facing download must be a single lightweight downloader executable, not
a source ZIP and not a heavyweight bundled installer.

- Public download-page artifact: `PPS-Toolkit-Downloader.exe`.
- Hard size limit: below 100 MiB so GitHub Releases can host it directly.
- Preferred size target: below 25 MiB.
- The downloader is a bootstrapper/orchestrator. It must actually download the
  toolkit payloads and dependencies; a link-only or no-op exe is a broken
  release.
- The downloader should ask for, or at minimum clearly offer, the installation
  location. The installed toolkit should become a repo-shaped program directory
  at the user's chosen path, not only a hidden cache under `%LOCALAPPDATA%`.
- The installed directory should preserve enough repository structure that a
  researcher/developer can inspect docs, launchers, source package files,
  assets, configs, and release manifests from the installed location.
- The installed directory must expose normal user entrypoints, including an exe
  that launches the offline/local HTML GUI and `PPSExperimentRunner.exe` for the
  native experiment runner.

The repo should contain downloader source and packaging manifests, not generated
release binaries.

- Tracked installer source: `windows/downloader/`
- Tracked installer package definition: `windows/installer_package_inventory.v1.json`
- Package inventory generator and validator: `tools/package_inventory.py`
- Lightweight GitHub release output: `dist/PPS-Toolkit-Downloader.exe`
- Download verification manifest: `dist/pps_download_manifest.v1.json`
- Installed package inventory written into the target folder: `pps_package_inventory.v1.json`

`dist/` stays ignored. Generated downloader binaries, packaged runner builds,
runtime bundles, dependency bundles, and any assembled repository payloads are
attached to GitHub Releases or fetched from declared upstream URLs; they are not
committed to the source repo.

Do not point the public download page directly at
`https://github.com/GeorgeFejer91/pps-kit/releases/latest/download/PPS-Toolkit-Downloader.exe`
until a public GitHub Release actually contains that asset and the matching
`pps_download_manifest.v1.json`. Before that release exists, link the installer
card to `https://github.com/GeorgeFejer91/pps-kit/releases` so the website does
not expose a dead direct-download button.

## Downloader Payload Contract

The downloader must orchestrate downloads declared in
`pps_download_manifest.v1.json`. That manifest should pin every payload by URL,
filename, size, SHA256, version, and role. The primary payloads should come from
GitHub Releases whenever possible so the public download path stays GitHub-based.
If an external upstream URL is unavoidable, the manifest must include the URL,
hash, license/provenance note, and whether the payload is required or optional.

The downloader must materialize a complete program repository into the chosen
install folder. At minimum the installed folder must include:

- `dist/PPSExperimentRunner/PPSExperimentRunner.exe` and its PyInstaller onedir resources.
- The packaged Qt Windows platform plugin at `dist/PPSExperimentRunner/_internal/PySide6/plugins/platforms/qwindows.dll`; without it the runner shows "no Qt platform plugin could be initialized" and cannot start.
- An exe entrypoint for the offline/local HTML GUI. It should start the local companion and open the dashboard without requiring users to run Python commands or batch files.
- Dashboard launchers kept for inspectability and fallback: `windows/Launch_HTML_Dashboard.bat`, `windows/Start_Website_Companion.bat`, and `windows/Launch_Experiment_Runner.bat`.
- Installer/build support needed to audit or rebuild the package: `windows/downloader/`, `windows/Build_PPS_Downloader.ps1`, `windows/Build_PPS_Distribution.ps1`, `windows/Setup_Windows_App.ps1`, and `windows/Create_Desktop_Shortcut.ps1`.
- Local dashboard and hosted-dashboard assets: `src/peripersonal_space_toolkit/dashboard/`, root `index.html`, `.nojekyll`, and `src/peripersonal_space_toolkit/viewer/`.
- App identity assets under `src/peripersonal_space_toolkit/assets/`.
- Preload catalogs and readiness ledgers under `assets/preloads/`, including `preload_inventory.json` and `profile_recreation_status.json`.
- Study 5 and shared audio assets: `assets/breathing/` and `assets/tactile/default_tactile_cue.wav`.
- The redistributable FABIAN/TU SOFA file and manifest under `assets/0. Head-Related Impulse Response (HRIR) model/`.
- `study_templates/`, `configs/`, and `data/sample/`.
- User docs, release docs, licenses, citation metadata, and third-party attribution: `docs/`, `README.md`, `LICENSE`, `THIRD_PARTY_LICENSES.md`, and `CITATION.cff`.
- Release helper tools needed to audit, manifest, and rebuild the package.
- A local runtime/dependency environment or runtime bootstrap metadata sufficient for the GUI exe and runner exe to work after installation.

The old heavy offline ZIP/Zenodo plan is not the current primary release target.
An offline ZIP may remain an internal fallback, but the public `/download` path
should lead to the single sub-100 MiB downloader exe once that asset exists.

Optional but preferred when available:

- Approved native 3DTI renderer binaries under `third_party/3dti_renderer/bin/`.
- Pinned 3DTI source/attribution material under `third_party/3dti_AudioToolkit/`.

## Build And Verification Order

1. Install dependencies into `.venv` with the Windows setup path or `python -m pip install -e ".[tts,gui,web,lsl,xdf,validation,dev,package]"`. The GUI extra is pinned to PySide6 6.7.x because newer PySide6 releases have broken Qt imports in the current Anaconda-based lab venv.
2. Run tests and release audit before packaging.
3. Build the packaged runner with `windows/Build_Experiment_Runner_Exe.ps1`. This must run `tools/check_qt_runtime.py` before and after PyInstaller so broken PySide6 imports or missing `qwindows.dll` fail the build.
4. Build or stage the offline/local HTML GUI exe entrypoint that starts the companion and opens the dashboard.
5. Stage the repo-shaped program directory and all dependency/runtime payloads that the downloader will install.
6. Let `tools/package_inventory.py --strict` validate the staged repository-shaped package and write `pps_package_inventory.v1.json`.
7. Generate `pps_download_manifest.v1.json` with every GitHub-hosted payload URL, external dependency URL if unavoidable, SHA256, size, version, and role.
8. Build `PPS-Toolkit-Downloader.exe` with the final manifest URL embedded; fail the build if it is 100 MiB or larger.
9. Attach the downloader, manifest, and any GitHub-hosted dependency/runtime/repo payloads to the GitHub Release.
10. Test from the public download page on a clean Windows folder. The proof must show the single downloader exe downloading content, installing into a user-chosen location, creating/opening the offline HTML GUI exe, and launching `PPSExperimentRunner.exe`.

## Do Not Package

Do not include raw participant data, name-bearing exports, generated participant/session outputs, local validation artifacts, downloaded model caches, private local paths, credentials, or unreviewed third-party audio/assets. Local runtime folders such as `local_data/`, `artifacts/`, and `models/` remain ignored.
