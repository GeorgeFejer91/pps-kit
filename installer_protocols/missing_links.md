# Installer Missing Links

Last checked: 2026-06-25.

The source repo can build and locally smoke-test the installer pipeline, but the public installer path is not complete until these release links exist.

## Public Release Assets

- GitHub currently has no public release assets for this repo. The public releases page reports that there are no releases.
- Missing GitHub Release asset: `PPS-Toolkit-Downloader.exe`.
- Missing GitHub Release asset: `pps_download_manifest.v1.json`.
- Missing final direct URL: `https://github.com/GeorgeFejer91/pps-kit/releases/latest/download/PPS-Toolkit-Downloader.exe`.
- Missing final direct URL: `https://github.com/GeorgeFejer91/pps-kit/releases/latest/download/pps_download_manifest.v1.json`.

## Zenodo Payload

- Missing final Zenodo record URL for `PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip`.
- Missing final Zenodo DOI for the versioned payload.
- Until the final Zenodo URL exists, generated manifests may use a localhost or placeholder payload URL only for smoke testing.

## Verification Links

- Missing public downloader proof from a clean Windows folder.
- Missing public download-page proof that the downloaded `PPS-Toolkit-Downloader.exe` fetches the GitHub manifest, downloads the Zenodo ZIP, verifies SHA256, extracts the package, creates shortcuts, opens `PPSDashboardLauncher.exe`, and launches `PPSExperimentRunner.exe`.
- Missing optional Android emulator proof for the hosted download page/local dashboard shell. The 2026-06-25 fresh-PC run installed SDK tools and AVD images under ignored `local_data/`, but emulator boot was blocked because the Android Emulator Hypervisor Driver was not installed and the current shell was not elevated. See `android_emulator_verification_protocol.md`.

The hosted download page should continue linking to the GitHub Releases page, not a direct installer URL, until the GitHub release contains both the downloader and matching manifest.
