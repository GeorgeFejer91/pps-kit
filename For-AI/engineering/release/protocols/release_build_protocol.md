# Release Build Protocol

This protocol builds the existing V1 component artifacts on a Windows build PC.
It does not qualify the in-progress Python-free Tauri Designer/native Runner.
Keep their source, installed-package and physical evidence separate; do not
substitute a V1 PyInstaller build for the new Rust release acceptance gates.

## Prerequisites

Use an explicitly selected build environment. Python is a V1 build dependency;
the new generation release may use it only for development verification.
Record exact Python, Go, Rust, Node and Windows SDK versions with the artifact.
The downloader icon tool is pinned to `github.com/akavel/rsrc@v0.10.2`.
Go 1.27.3 has been checked locally; this does not assert an installed release.

Verify the selected tools before building:

```powershell
py -3.12 --version
go version
```

If the current shell cannot resolve `go` immediately after install, start a fresh terminal or rely on `For-AI\engineering\build\windows\Build_PPS_Downloader.ps1`, which also checks `C:\Program Files\Go\bin\go.exe`.

## Build Order

```powershell
powershell -ExecutionPolicy Bypass -File For-AI\engineering\build\windows\Setup_Windows_App.ps1
powershell -ExecutionPolicy Bypass -File For-AI\engineering\build\windows\Build_PPS_Distribution.ps1 -Version 0.1.0 -PayloadBaseUrl "http://127.0.0.1:8788"
```

The example is a local smoke build. For release, supply the allocated payload
folder URL (for example a real Zenodo record's `/files` folder), plus its DOI
using `-ZenodoDoi`. Do not pass one ZIP URL or append a query to the base.
Missing/placeholder URLs and the retired `-ZenodoPayloadUrl` are rejected.

The builder runs the release audit, builds Designer and Runner unless skipped,
and stages the manifest-defined components. It validates each package inventory
and creates three sets of payload/download manifests and downloaders:

| Component | Payload stem | Download manifest | Downloader |
| --- | --- | --- | --- |
| Designer | `PPS-Designer-vVERSION-windows-x64.zip` | `pps_designer_download_manifest.v1.json` | `PPS-Designer-Downloader.exe` |
| Runner | `PPS-Experiment-Runner-vVERSION-windows-x64.zip` | `pps_runner_download_manifest.v1.json` | `PPS-Experiment-Runner-Downloader.exe` |
| Full | `PPS-Toolkit-vVERSION-windows-x64.zip` | `pps_toolkit_download_manifest.v1.json` | `PPS-Toolkit-Downloader.exe` |

Installed entrypoints are `apps/PPSDesigner/PPSDesigner.exe` and
`apps/PPSExperimentRunner/PPSExperimentRunner.exe`, with compatible resources
under `shared/`. Internal `For-AI/` content is excluded.

Generated artifacts stay under ignored `dist/` until uploaded to GitHub Releases or Zenodo.

## Release Upload

1. Verify every exact-revision package locally with the fresh-PC protocol.
2. Upload the three verified payloads under the approved release authorization.
3. Generate matching manifests with the final payload URLs/DOI and exact hashes.
4. Build each downloader with the final `-ManifestBaseUrl` folder and attach
   matching downloaders/manifests to the approved GitHub release.
5. Test public routes and fresh-machine installation before promoting direct
   download buttons. Localhost success and a new folder on a development PC do
   not establish a clean Windows installation without a checkout or Python.
