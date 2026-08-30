# PPS Kit

PPS Kit is a public monorepo for designing and running audio-tactile
peripersonal-space experiments. It publishes two related but independently
installable Windows applications:

- **PPS Designer** creates stimulus designs, profiles, rendered assets, and
  prepared experiments.
- **PPS Experiment Runner** opens prepared experiments, performs participant
  runs, records evidence, and provides normal post-run review.

Both products use the same scientific schemas, Python runtime, approved
resources, and immutable study templates. They can be downloaded separately or
together; V1 does not add a central hub.

## Repository Map

```text
apps/
  designer/        compiled web UI, launchers, and product specifications
  runner/          validated runner plus Tauri/browser preview
  quest-runner/    optional experimental Meta Quest/Spatial SDK context
packages/
  pps-runtime/     peripersonal_space_toolkit Python package
  pps-resources/   approved assets, templates, configs, and sample data
  pps-contracts/   shared Rust action, scope, wire, and state contracts
  pps-brsp/        transport-neutral authenticated remote protocol
  pps-runner-core/ pure Rust target-authoritative runner reducer
distributions/
  manifests/       shared, designer, runner, and full component manifests
  downloader/      one parameterized Windows downloader codebase
  windows-support/ scripts that execute on an installed PC
website/           GitHub Pages product inputs and route wrappers
docs/              end-user and public developer documentation
third_party/       reviewed, pinned runtime/build dependencies and licenses
For-AI/            development orchestration, tests, research, and experiments
```

The classification boundary is strict: shipped application inputs stay outside
`For-AI/`; build execution, testing, validation, diagnostics, research,
publication work, generators, audits, and unapproved experiments stay inside
`For-AI/`. `For-AI/` is public project memory, not a secrecy mechanism, and is
excluded from every end-user package.

## Windows Development Quick Start

From the repository root:

```powershell
.\For-AI\engineering\build\windows\Setup_Windows_App.ps1
```

Launch the Designer:

```bat
apps\designer\launchers\Launch_HTML_Dashboard.bat
```

Build and launch the Experiment Runner:

```powershell
.\For-AI\engineering\build\windows\Build_Experiment_Runner_Exe.ps1
```

```bat
apps\runner\launchers\Launch_Experiment_Runner.bat
```

The packaged executable is
`dist\PPSExperimentRunner\PPSExperimentRunner.exe`. The Runner remains an
independent entrypoint and can open a prepared experiment without the Designer
being installed.

Useful device launchers:

```bat
apps\runner\launchers\List_Audio_Devices.bat
apps\runner\launchers\Stress_Audio_Device.bat
```

The approved FABIAN HRIR source resource is stored at:

```text
packages/pps-resources/assets/0. Head-Related Impulse Response (HRIR) model/
  FABIAN_HRIR_measured_HATO_0.sofa
```

## Python Interfaces

The import and command surface is preserved:

```powershell
pps-generate --dry-run
pps-generate --participants 50
pps-designer
pps-dashboard
pps-design
pps-render-design --design packages/pps-resources/study_templates/pfeiffer_2018_lateral_perihead_left_to_right.json --output-dir artifacts/rendered_pfeiffer --seed 2018
pps-decode --input-dir local_data/loopback_recordings
pps-analyze --sample
pps-audio-stress --device-query Komplete
pps-latency-validate specs
```

`pps-designer` is the primary native Designer shell. `pps-dashboard` remains a
documented one-release compatibility alias. The Python package continues to be
imported as `peripersonal_space_toolkit` even though its source now lives under
`packages/pps-runtime/src/`.

Runtime path discovery is centralized. Source checkouts and frozen products use
separate product, resource, frontend, and writable roots; frozen applications
continue to honor `PPS_TOOLKIT_ROOT`.

## Designer and Website

`apps/designer/frontend/compiled/` is the one compiled Designer artifact. The
local Designer package consumes it directly. GitHub Pages assembly copies the
same bytes—plus approved public catalogues and `website/CNAME`—into ignored
staging; there is no second hand-edited dashboard implementation.

Public routes:

- [PPS Kit](https://ppskit.qzz.io/)
- [Documentation](https://ppskit.qzz.io/documentation/)
- [Downloads](https://ppskit.qzz.io/download/)
- [GitHub Pages fallback](https://georgefejer91.github.io/pps-kit/)

See [GitHub Pages and hosted Designer](docs/GITHUB_PAGES_DASHBOARD.md) and the
[paradigm library](docs/PARADIGM_LIBRARY.md).

## Downloads and Component Manifests

PPS Kit defines four `pps-component-manifest.v1` inventories:

- `shared`: approved templates, resources, public documentation, required
  runtime dependencies, and licenses.
- `designer`: `PPSDesigner.exe`, the compiled Designer frontend, and Shared.
- `runner`: `PPSExperimentRunner.exe`, Qt runtime/support, normal post-run
  review, and Shared.
- `full`: exact composition of Designer, Runner, and one Shared component.

The parameterized downloader source builds three bootstrapper names:

- `PPS-Designer-Downloader.exe`
- `PPS-Experiment-Runner-Downloader.exe`
- `PPS-Toolkit-Downloader.exe`

Each bootstrapper pins its own payload and component inventory hash. Separate
installs may share one installation root only when their Shared versions and
hashes are compatible. Full creates separate Designer and Runner shortcuts.

Build commands:

```powershell
.\For-AI\engineering\build\windows\Build_PPS_Designer.ps1
.\For-AI\engineering\build\windows\Build_Experiment_Runner_Exe.ps1
.\For-AI\engineering\build\windows\Build_PPS_Downloader.ps1
.\For-AI\engineering\build\windows\Build_PPS_Distribution.ps1 -Version 0.1.0 -ZenodoPayloadUrl "https://zenodo.org/records/<record>/files/<payload>.zip?download=1" -ZenodoDoi "10.5281/zenodo.<record>"
```

See [PPS downloads](docs/PPS_DOWNLOADS.md) and
[component manifests](distributions/manifests/README.md).

## Preserved Scientific Contracts

The migration preserves `.pps-profile`, prepared-experiment packages, Segment
0-6 manifests, profile/template formats, Runner output schemas, and the
Designer generation/rendering interfaces. Logical paths such as `assets/...`
and `study_templates/...` remain valid inside installed products and serialized
profiles even though their source-of-truth folders are under
`packages/pps-resources/` in the repository.

Participant data, generated sessions/renders, downloaded models, and private
reference material are ignored and are rejected by release audits. Only
deidentified sample data under `packages/pps-resources/data/sample/` may ship.

## Development and Experimental Work

Tests, release audits, build execution, and validation protocols live under
`For-AI/engineering/`. Literature screening, full evidence ledgers, manuscript
sources, calibration work, and hardware investigations live under
`For-AI/research/`.

The Android companion is an unapproved experiment under
`For-AI/experiments/android-companion/`. Android launchers, administration
CLIs, assets, and visible controls are excluded from V1 products and component
manifests. Runner safety behavior required for ordinary desktop execution
remains product code.

The next-generation Runner preview is intentionally separate from that legacy
phone experiment. `apps/runner/` now also contains a Tauri v2 desktop shell and
no-install browser companion backed by shared Rust contracts. The separate
`apps/quest-runner/` tree is an optional experimental Meta Spatial SDK
application context using the same reducer through JNI; it is not the primary
PPS Kit Runner target. These previews do not replace the validated V1
Python/PySide Runner or its release manifests. See
[Cross-platform Runner and browser remote preview](docs/CROSS_PLATFORM_RUNNER_AND_REMOTE.md).

## Documentation

- [Windows installation and operation](docs/WINDOWS_APP.md)
- [PPS Designer](docs/PPS_DESIGNER.md)
- [Cross-platform Runner and browser remote preview](docs/CROSS_PLATFORM_RUNNER_AND_REMOTE.md)
- [Study replication workflow](docs/replication_workflow.md)
- [Privacy boundary](docs/privacy_boundary.md)
- [Windows PC requirements](docs/WINDOWS_PC_SOFTWARE_REQUIREMENTS.md)
- [Internal project memory](For-AI/README.md)

## License and Attribution

See [LICENSE](LICENSE), [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md), and
[CITATION.cff](CITATION.cff).
