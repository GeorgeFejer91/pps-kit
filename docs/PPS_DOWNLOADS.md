# PPS Kit Downloads

PPS Kit offers a browser app and three Windows editions.

## Browser app (PWA)

Open [PPS Kit](https://ppskit.com/) and use your browser's Install app or Add to
Home Screen command when available. The Planner previews approved premade
stimuli. The Experiment Runner tab runs the built-in browser demo and can pair
with another compatible device; see [browser Runner instructions](CROSS_PLATFORM_RUNNER_AND_REMOTE.md#browser-companion).

## Windows installers

### Experiment Planner

`PPS-Designer-Downloader.exe` installs the stimulus/profile Designer, its
compiled offline interface, approved templates/resources, documentation, and
the compatible Shared component. It does not require the Experiment Runner to
launch.

### Experiment Runner

`PPS-Experiment-Runner-Downloader.exe` installs the participant Runner, Qt
runtime, runtime assets, normal post-run analysis/review, documentation, and the
compatible Shared component. It can open a prepared experiment without the
Designer being installed.

### Experiment Planner + Runner Suite

`PPS-Toolkit-Downloader.exe` installs Designer, Runner, and one Shared
component. It creates separate Designer and Runner shortcuts; V1 does not add a
central hub.

Until a GitHub Release contains the matching downloader and manifest assets,
use the [PPS Kit Releases page](https://github.com/GeorgeFejer91/pps-kit/releases)
rather than a guessed direct asset URL.

## Installation Integrity

Each downloader is built from the same parameterized source but pins a distinct
product/component ID, payload, component-manifest hash, and package-inventory
hash. The downloader verifies SHA256 and inventory metadata before extraction
or launch.

Designer and Runner may share one chosen installation root. If the existing
Shared component has a different version or inventory hash, installation stops
with an incompatibility message instead of mixing releases.

Heavy offline payload ZIPs may be hosted on Zenodo while the small downloader
executables and download manifests are attached to GitHub Releases.

## Installed Entrypoints

- Designer: `PPSDesigner.exe`
- Runner: `PPSExperimentRunner.exe`

The Runner package includes the Windows Qt platform plugin (`qwindows.dll`)
and performs its own audio/ASIO preflight. A successful installation alone does
not prove that the lab audio interface and native multichannel driver are
ready.

## Data and Privacy

End-user packages contain approved application source/resources,
documentation, licenses, and deidentified sample data. They exclude internal
`For-AI/` research/development material, participant data, generated sessions,
private paths, downloaded model caches, unreviewed assets, and the experimental
Android companion.

See [privacy boundary](privacy_boundary.md), [Windows operation](WINDOWS_APP.md),
and [Windows PC requirements](WINDOWS_PC_SOFTWARE_REQUIREMENTS.md).

## Release Engineering

For maintainers, component definitions live in
`distributions/manifests/*.v1.json`. Build execution and release audits live
under `For-AI/engineering/` and are not installed with the products.

```powershell
.\For-AI\engineering\build\windows\Build_PPS_Designer.ps1
.\For-AI\engineering\build\windows\Build_Experiment_Runner_Exe.ps1
.\For-AI\engineering\build\windows\Build_PPS_Downloader.ps1
.\For-AI\engineering\build\windows\Build_PPS_Distribution.ps1 -Version 0.1.0 -ZenodoPayloadUrl "https://zenodo.org/records/<record>/files/<payload>.zip?download=1" -ZenodoDoi "10.5281/zenodo.<record>"
```

Generated binaries, package inventories, manifests, and ZIPs remain under the
ignored `dist/` tree until attached to a reviewed release.

