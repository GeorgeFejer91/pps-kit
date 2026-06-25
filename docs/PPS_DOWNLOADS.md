# PPS Download Distribution

The finished Windows distribution uses two download layers:

- `PPS-Toolkit-Downloader.exe` is the small GitHub-hosted bootstrapper. It must stay below 100 MiB, should stay below 50 MiB, and preferably stays below 25 MiB.
- `PPS-Toolkit-vX.Y.Z-offline-lab-windows-x64.zip` is the heavyweight Zenodo-hosted offline lab package. It contains the runner, packaged dashboard launcher, dashboard files, redistributable assets, FABIAN SOFA resource, approved 3DTI files, docs, licenses, and Windows launchers.

The repo contains the installer package source under `windows/downloader/`
and the tracked package definition at
`windows/installer_package_inventory.v1.json`. Generated release outputs stay
under ignored `dist/`: the downloader exe, offline ZIP,
`pps_download_manifest.v1.json`, and the generated
`pps_package_inventory.v1.json` embedded inside the offline ZIP. Installer
build protocols and missing-link ledgers live in `installer_protocols/`.

## Build

Build the downloader only:

```powershell
windows\Build_PPS_Downloader.ps1
```

Build the packaged dashboard launcher:

```powershell
windows\Build_Dashboard_Launcher_Exe.ps1
```

Build the release package and manifest:

```powershell
windows\Build_PPS_Distribution.ps1 -Version 0.1.0 -ZenodoPayloadUrl "https://zenodo.org/records/<record>/files/PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip?download=1" -ZenodoDoi "10.5281/zenodo.<record>"
```

The downloader build requires Go for Windows. The script embeds the PPS icon, writes both a versioned exe and `dist\PPS-Toolkit-Downloader.exe`, and fails if the exe is at or above 100 MiB.

The distribution build validates the staged offline package with the repo venv
Python:

```powershell
.\.venv\Scripts\python.exe tools\package_inventory.py --stage-root dist\<stage-folder> --output dist\<stage-folder>\pps_package_inventory.v1.json --strict
```

This fails the package before zipping if a required item is missing, including
the packaged runner exe, packaged dashboard launcher exe, dashboard assets,
preload catalogs, Study 5 audio/tactile assets, FABIAN SOFA resource, docs,
licenses, `installer_protocols/`, and installer source/build scripts. It also checks the packaged Qt platform plugin
`dist/PPSExperimentRunner/_internal/PySide6/plugins/platforms/qwindows.dll`,
because the Experiment Runner cannot start on Windows without it.

`windows\Build_Experiment_Runner_Exe.ps1` runs `tools\check_qt_runtime.py`
before and after PyInstaller. The preflight verifies that PySide6 imports
cleanly and that the packaged runner contains the Windows Qt platform plugin.
`windows\Build_Dashboard_Launcher_Exe.ps1` builds
`dist\PPSDashboardLauncher\PPSDashboardLauncher.exe`, which starts the local
dashboard companion and opens the browser UI without requiring Python on the
installed PC.

## Manifest

The downloader reads `pps_download_manifest.v1.json`. Generate it with:

```powershell
python tools\make_download_manifest.py --payload dist\PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip --payload-url "https://zenodo.org/records/<record>/files/PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip?download=1" --zenodo-doi "10.5281/zenodo.<record>"
```

The manifest records the version, source tag, commit, Zenodo DOI, payload URL,
size, SHA256, platform, installed entrypoints, and the package inventory hash.
The dashboard entrypoint is `dist/PPSDashboardLauncher/PPSDashboardLauncher.exe`.
The downloader refuses to extract or launch the package until the payload hash
matches the manifest, and it rejects manifests whose package inventory reports
missing required items.

## Release Order

1. Create the `release/vX.Y.Z` branch and tag `vX.Y.Z`.
2. Build the Focus Mode runner with `windows\Build_Experiment_Runner_Exe.ps1`.
3. Build the dashboard launcher with `windows\Build_Dashboard_Launcher_Exe.ps1`.
4. Build the offline lab ZIP and manifest with `windows\Build_PPS_Distribution.ps1`.
5. Upload the heavyweight ZIP to Zenodo and record the version DOI.
6. Rebuild the manifest with the final Zenodo URL if needed.
7. Build the lightweight downloader with the final manifest URL embedded.
8. Attach the downloader and manifest to the GitHub release.
9. Verify downloader install on a clean Windows folder before announcing the release.

Keep `installer_protocols/missing_links.md` current until the GitHub release
assets and Zenodo payload URL exist.

