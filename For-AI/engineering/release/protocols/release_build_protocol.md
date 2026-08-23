# Release Build Protocol

This protocol builds the release artifacts from a Windows build PC.

## Prerequisites

Install build tools when a fresh PC lacks them:

```powershell
winget install --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements
winget install --id GoLang.Go --source winget --accept-package-agreements --accept-source-agreements
```

Verify:

```powershell
py -3.12 --version
go version
```

If the current shell cannot resolve `go` immediately after install, start a fresh terminal or rely on `For-AI\engineering\build\windows\Build_PPS_Downloader.ps1`, which also checks `C:\Program Files\Go\bin\go.exe`.

## Build Order

```powershell
powershell -ExecutionPolicy Bypass -File For-AI\engineering\build\windows\Setup_Windows_App.ps1
powershell -ExecutionPolicy Bypass -File For-AI\engineering\build\windows\Build_Experiment_Runner_Exe.ps1
powershell -ExecutionPolicy Bypass -File For-AI\engineering\build\windows\Build_Dashboard_Launcher_Exe.ps1
powershell -ExecutionPolicy Bypass -File For-AI\engineering\build\windows\Build_PPS_Distribution.ps1 -Version 0.1.0 -ZenodoPayloadUrl "https://zenodo.org/records/<record>/files/PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip?download=1" -ZenodoDoi "10.5281/zenodo.<record>"
```

`Build_PPS_Distribution.ps1` runs the release audit, builds both packaged exe entrypoints unless explicitly skipped, stages the repo-shaped install payload, validates `pps_package_inventory.v1.json`, zips the payload, generates `pps_download_manifest.v1.json`, and builds `PPS-Toolkit-Downloader.exe`.

Generated artifacts stay under ignored `dist/` until uploaded to GitHub Releases or Zenodo.

## Release Upload

1. Upload `PPS-Toolkit-vX.Y.Z-offline-lab-windows-x64.zip` to Zenodo.
2. Regenerate `dist/pps_download_manifest.v1.json` with the final Zenodo URL and DOI.
3. Rebuild `dist/PPS-Toolkit-Downloader.exe` with the final GitHub manifest URL embedded.
4. Attach `PPS-Toolkit-Downloader.exe` and `pps_download_manifest.v1.json` to the GitHub Release.
5. Verify the public downloader from a clean install folder before changing the public download button to a direct asset link.
