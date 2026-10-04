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

The [V1 inventory](../download_package_inventory.md) and
[`Build_PPS_Distribution.ps1`](../engineering/build/windows/Build_PPS_Distribution.ps1)
build Python/PyWebView Designer, Python/PySide Runner, ZIP payloads, and Go
downloaders. They remain the compatibility path.

Runner and Planner have candidate Tauri shells at `apps/runner/src-tauri/` and
`apps/designer/src-tauri/`. The Full NSIS configuration composes their bundled
WebViews with one Shared resource tree. Exact source
`76b5f525826c357e30ed5b075920dbd87b31688e` passed the
[two-app installed CI audit](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37227818117):
21 inventory items matched source, both installed apps launched, Planner
generated 3DTI audio and exported a two-block JSON profile, and Runner prepared
both blocks into a verified package with PCM and a partial event journal.
Fresh install, reinstall, uninstall, and incompatible-Shared rejection passed.
The [single Full validation installer](https://github.com/GeorgeFejer91/pps-kit/actions/runs/37227818117/artifacts/11313192953)
has SHA-256
`17ffb768eb8728ea12c908513cc4a7c1d1e350d9737c173b91e4f81a15c0f807`
and is retained through 2026-10-11. It is unsigned and marked validation-only;
the CI host enumerated no output devices. Physical output, finalized participant
recording, local-PC reinstall, Runner's stable identifier, ASIO SDK licensing,
and release qualification remain open. Follow the
[Windows installer plan](windows-installer.md) for those gates.

## Stage boundary

The [workflow](../WORKFLOW.md) keeps source, package, and release claims
separate. A source build or Pages preview is not installer evidence. Once the
Full installer passes a clean-path test, use that installer to reinstall both
apps on this PC and verify both launch and the profile handoff from their
installed paths. Preserve existing user and participant data during replacement.
Do not advertise V2 research acquisition until its installed workflow, device
calibration, and scientific checks pass.
