# Installer Protocols

This folder is the clean release-orchestration lane for the PPS Toolkit Windows installer. It is intentionally separate from `For-AI/engineering/validation/`, which proves experiment timing and runner behavior, and from `For-AI/`, which is tracked project memory for future agents.

Use this folder for release build protocols, package-content rules, fresh-PC installer verification, and current missing-link ledgers. Do not store generated installers, ZIPs, participant data, validation artifacts, private paths, credentials, or local machine logs here.

Protocol files:

- `release_build_protocol.md` - build order for runner, dashboard launcher, payload, manifest, and downloader.
- `content_orchestration.md` - package-content boundaries and end-user payload rules.
- `fresh_pc_verification_protocol.md` - Windows downloader/install smoke.
- `android_emulator_verification_protocol.md` - optional Android emulator/mobile-page evidence lane and current acceleration blocker.
- `missing_links.md` - release URLs and external verification links that are still unavailable.

Current release shape:

- GitHub Release asset: `PPS-Toolkit-Downloader.exe`
- GitHub Release asset: `pps_download_manifest.v1.json`
- Zenodo payload: `PPS-Toolkit-vX.Y.Z-offline-lab-windows-x64.zip`
- Installed primary dashboard entrypoint: `dist/PPSDashboardLauncher/PPSDashboardLauncher.exe`
- Installed primary runner entrypoint: `dist/PPSExperimentRunner/PPSExperimentRunner.exe`

The dashboard launcher starts the local FastAPI companion and opens the local HTML GUI. The hosted GitHub Pages dashboard remains a static decision surface that talks to the local companion; it must not run timing-sensitive experiment code or upload local files.
