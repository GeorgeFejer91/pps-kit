# Windows desktop packaging

This folder owns the build plan and evidence for a self-contained Windows
installer. Product source, icons, scientific resources, component manifests,
and licenses stay in their existing product roots. Generated installers and
staging trees stay under ignored `dist/`. Nothing under `For-AI/` is installed.

## Target product

- Install Designer and Runner as separate launchable Tauri/Rust applications.
  Each application bundles its own local HTML/CSS/JavaScript GUI. Ordinary
  authoring, execution, and result review work without GitHub Pages or a
  Pages-hosted client connecting to a PC backend.
- The WebView displays state and requests typed, narrowly authorized commands.
  Rust owns privileged file operations, profile validation, generation and
  experiment execution, audio/response timing, and durable results. Retain the
  existing `.pps-profile`/prepared-experiment handoff and scientific contracts.
- The Full installer provides both entrypoints/shortcuts and exactly one
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

## Stage boundary

The [workflow](../WORKFLOW.md) keeps source, package, and release claims
separate. A source build or Pages preview is not installer evidence. Do not
replace the V1 compatibility package or advertise V2 research acquisition
until its installed workflow, device calibration, and scientific checks pass.
