# PPS Download Distribution

The finished Windows distribution uses two download layers:

- `PPS-Toolkit-Downloader.exe` is the small GitHub-hosted bootstrapper. It must stay below 100 MiB, should stay below 50 MiB, and preferably stays below 25 MiB.
- `PPS-Toolkit-vX.Y.Z-offline-lab-windows-x64.zip` is the heavyweight Zenodo-hosted offline lab package. It contains the runner, dashboard files, redistributable assets, FABIAN SOFA resource, approved 3DTI files, docs, licenses, and Windows launchers.

## Build

Build the downloader only:

```powershell
windows\Build_PPS_Downloader.ps1
```

Build the release package and manifest:

```powershell
windows\Build_PPS_Distribution.ps1 -Version 0.1.0 -ZenodoPayloadUrl "https://zenodo.org/records/<record>/files/PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip?download=1" -ZenodoDoi "10.5281/zenodo.<record>"
```

The downloader build requires Go for Windows. The script embeds the PPS icon, writes both a versioned exe and `dist\PPS-Toolkit-Downloader.exe`, and fails if the exe is at or above 100 MiB.

## Manifest

The downloader reads `pps_download_manifest.v1.json`. Generate it with:

```powershell
python tools\make_download_manifest.py --payload dist\PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip --payload-url "https://zenodo.org/records/<record>/files/PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip?download=1" --zenodo-doi "10.5281/zenodo.<record>"
```

The manifest records the version, source tag, commit, Zenodo DOI, payload URL, size, SHA256, platform, and installed entrypoints. The downloader refuses to extract or launch the package until the payload hash matches the manifest.

## Release Order

1. Create the `release/vX.Y.Z` branch and tag `vX.Y.Z`.
2. Build the Focus Mode runner with `windows\Build_Experiment_Runner_Exe.ps1`.
3. Build the offline lab ZIP and manifest with `windows\Build_PPS_Distribution.ps1`.
4. Upload the heavyweight ZIP and manifest to Zenodo and record the version DOI.
5. Rebuild the manifest with the final Zenodo URL if needed.
6. Build the lightweight downloader with the final manifest URL embedded.
7. Attach the downloader and manifest to the GitHub release.
8. Verify downloader install on a clean Windows folder before announcing the release.

