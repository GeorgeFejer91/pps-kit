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

External PC dependencies that are not PPS payloads belong under the manifest's
`external_dependencies` list. The downloader may auto-download and locally cache
an external installer only when all of these are true: the provider/source URL is
declared, the filename/size/SHA256 are pinned, and the manifest records that
redistribution or automated caching is permitted. If the license does not grant
redistribution or mirroring rights, the downloader must not fetch from a PPS
mirror; it should open the official provider page in the user's default browser
and record `provider_action_required`.

Current ASIO policy:

- Native Instruments Komplete Audio ASIO Driver is proprietary. PPS may point to
  or open the official NI driver page, but must not bundle or mirror the driver
  installer unless written redistribution permission is recorded in the manifest.
- Treat the Komplete driver dependency as a state machine in installers and the
  runner: (1) registry absent means open the official NI driver page and show the
  install guide; (2) registry present but `sounddevice` route absent means ask the
  user to reconnect or power-cycle the Komplete Audio 6 MK2 and retry detection;
  (3) `Komplete Audio ASIO Driver` visible with at least three outputs means PPS
  automatically selects that native multichannel route.
- The required user-facing instructions are: disconnect the interface, download
  `Komplete Audio 6 MK2 Driver 5.22.0 - Windows 10` from the NI drivers page,
  extract the ZIP, run `setup.exe`, reconnect the interface, and click Retry
  Audio Detection or restart the runner. Package/downloader UI should reuse these
  same words rather than inventing a parallel flow.
- FlexASIO may be declared as an optional diagnostic fallback from Etienne
  Dechamps' GitHub release with pinned SHA256. It is not the validated
  publication timing route for synchronized left/right/tactile output.
- A green installer state does not by itself prove audio readiness. The
  experiment runner must still run sounddevice/ASIO preflight and tell the
  experimenter when the native Komplete 3+ channel ASIO route is missing.
- The packaged runner entry point must set `SD_ENABLE_ASIO=1` before importing
  `peripersonal_space_toolkit.focus_app` or any module that might import
  `sounddevice`. Without this import-order guard, python-sounddevice can lock
  the frozen app into a non-ASIO PortAudio backend even though source validation
  tools can see the Komplete ASIO route.
- `windows\Build_Experiment_Runner_Exe.ps1` may retry PyInstaller once with
  `PPS_EXPERIMENT_RUNNER_DISABLE_ICON=1` if the normal branded build fails while
  embedding the `.ico` resource, such as a Windows Defender
  `BeginUpdateResource` false-positive path. Treat this as a packaging
  continuity fallback only: the runner code path, Qt runtime checks, packaged
  `qwindows.dll`, and packaged-exe audio validation still have to pass.
- The Komplete ASIO route may need an even stream width. The runner should use
  a 4-channel ASIO stream when the native driver exposes 4+ outputs, while still
  routing auditory left/right to outputs 1/2, tactile stimuli and response
  marker click tone to output 3, and keeping output 4 silent.

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
- Tactile-channel response marker/click assets under `assets/click/`; the
  click-tone WAV is emitted into physical output 3 by the runner and must be
  included in the packaged exe resources and downloader payload.
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
3. Build the packaged runner with `windows/Build_Experiment_Runner_Exe.ps1`. This must run `tools/check_qt_runtime.py` before and after PyInstaller so broken PySide6 imports or missing `qwindows.dll` fail the build. After building, verify the packaged exe, not just source Python, can open `Komplete Audio ASIO Driver` through the real runner path because ASIO depends on the frozen entrypoint setting `SD_ENABLE_ASIO=1` before any sounddevice import.
4. Build or stage the offline/local HTML GUI exe entrypoint that starts the companion and opens the dashboard.
5. Stage the repo-shaped program directory and all dependency/runtime payloads that the downloader will install.
6. Let `tools/package_inventory.py --strict` validate the staged repository-shaped package and write `pps_package_inventory.v1.json`.
7. Generate `pps_download_manifest.v1.json` with every GitHub-hosted payload URL, external dependency URL if unavoidable, SHA256, size, version, and role.
8. Build `PPS-Toolkit-Downloader.exe` with the final manifest URL embedded; fail the build if it is 100 MiB or larger.
9. Attach the downloader, manifest, and any GitHub-hosted dependency/runtime/repo payloads to the GitHub Release.
10. Test from the public download page on a clean Windows folder. The proof must show the single downloader exe downloading content, installing into a user-chosen location, creating/opening the offline HTML GUI exe, and launching `PPSExperimentRunner.exe`.
11. On a clean Windows lab PC without Komplete ASIO, verify the downloader/setup
    opens the official NI driver page, reports provider action required, and the
    runner launcher shows an audio dependency message plus an `Audio Driver
    Instructions` action with official links and Retry Audio Detection. After
    installing the NI driver, rerun the PC audit and
    `pps-audio-stress --device-query Komplete --channels 3`.
12. On a Windows lab PC where the NI driver is installed but the interface is
    unplugged or not enumerated, verify setup/runner messaging switches to the
    reconnect/power-cycle/retry path and does not keep telling the user to
    download the driver. After the interface appears, the runner should proceed
    automatically from Retry Audio Detection without requiring manual device
    selection.

## Do Not Package

Do not include raw participant data, name-bearing exports, generated participant/session outputs, local validation artifacts, downloaded model caches, private local paths, credentials, or unreviewed third-party audio/assets. Local runtime folders such as `local_data/`, `artifacts/`, and `models/` remain ignored.
