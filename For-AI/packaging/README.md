# Windows desktop packaging

This folder owns the build plan and evidence for a self-contained Windows
installer. Product source, icons, scientific resources, component manifests,
and licenses stay in their existing product roots. Generated installers and
staging trees stay under ignored `dist/`. Nothing under `For-AI/` is installed.

## Target product

- Install **Experiment Planner** (the current Designer code) and **Experiment
  Runner** as separate launchable Tauri/Rust applications from one Full
  installer. Each application bundles its own local HTML/CSS/JavaScript GUI.
  Ordinary authoring, execution, and result review work without GitHub Pages
  or a Pages-hosted client connecting to a PC backend.
- The WebView displays state and requests typed, narrowly authorized commands.
  Rust owns privileged file operations, profile validation, generation and
  experiment execution, audio/response timing, and durable results. Retain the
  existing `.pps-profile`/prepared-experiment handoff and scientific contracts.
- The Full installer provides both named entrypoints/shortcuts and exactly one
  compatible Shared resource set. If separate app installers remain available,
  they must check the Shared version and inventory hash before reuse.
- Pages remains a separate public information/browser surface. Optional phone
  controls are a separately scoped feature; they do not supply the installed
  GUI or change native experiment authority.

## Existing package versus target

The current [V1 inventory](../download_package_inventory.md) and
[`Build_PPS_Distribution.ps1`](../engineering/build/windows/Build_PPS_Distribution.ps1)
build Python/PyWebView Designer, Python/PySide Runner, ZIP payloads, and Go
downloaders. A local Full candidate has only a clean-folder launch smoke. It
does not establish a Tauri Full installer or native V2 acquisition readiness.

Runner has a candidate Tauri shell at `apps/runner/src-tauri/`; its production
configuration points at local `apps/runner/compiled/` bytes. Designer still
needs its Tauri/Rust shell and native boundary before a two-app Tauri installer
can be built. Follow the [Windows installer plan](windows-installer.md) for
that migration and installed-path gates. Reuse the existing build/release
tools where their component ownership and inventory checks still apply.
The Runner-only Windows validation installer has a fresh-path silent CI install
inventory for its executable and canonical HTML/CSS bytes. The
[exact-source Windows audit](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37190366500)
also launched its bundled WebView, read the Rust idle snapshot, and exercised
the control, logging, and remote tabs. This validation artifact is not the
two-app Full composition or an installed participant run.

## Stage boundary

The [workflow](../WORKFLOW.md) keeps source, package, and release claims
separate. A source build or Pages preview is not installer evidence. Once the
Full installer passes a clean-path test, use that installer to reinstall both
apps on this PC and verify both launch and the profile handoff from their
installed paths. Preserve existing user and participant data during replacement.
Do not advertise V2 research acquisition until its installed workflow, device
calibration, and scientific checks pass.
