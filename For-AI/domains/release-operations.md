# Release operations

Own synchronization, checkpoints, test selection, Pages, component inventories,
installers, and release claims. Read [WORKFLOW.md](../WORKFLOW.md) for stages and
[agent_update_protocol.md](../agent_update_protocol.md) for memory/Git rules.

## Read for the task

- Repository moves: [architecture](../engineering/architecture/ARCHITECTURE.md),
  [migration ledger](../engineering/migration/repository-layout.v1.json),
  [root allowlist](../engineering/migration/root-allowlist.v1.json).
- Payload/installers: [inventory](../download_package_inventory.md),
  `distributions/manifests/`, and the matching release protocol.
- Pages: `For-AI/engineering/automation/build_pages.mjs` and
  `.github/workflows/pages.yml`. Matching product pushes to `main` deploy the
  public site; unsettled local previews use a review branch.
- Checks: [validation tiers](../engineering/validation/docs/VALIDATION.md).

Use **Ponytail** for tooling and **skill-creator** for skill maintenance.
Tauri guidance applies to Tauri checks/packages. Installed agent skills are
environment setup, not end-user runtime dependencies.

## Proportionate verification

- Memory-only: links, skill metadata, archive integrity, whitespace, and
  existing classification/release checks. No installer/hardware run.
- Python product: focused owning tests plus appropriate Quick/Standard tier
  via `For-AI/engineering/automation/check_all.ps1`.
- Designer UI: canonical build, actual interaction, inspected rendered audit,
  and Pages assembly/parity at promotion.
- Candidate Runner: owning Rust checks and applicable Core/Desktop/Browser
  mode of `For-AI/engineering/automation/check_runner_next.ps1`.
- Packaging: component inventories, rebuilt executable/installed-path checks;
  clean-install/full qualification for release claims.

Preserve exactly one Shared, V1 Qt/ASIO requirements, scientific handoffs,
public routes, and exclusion of `For-AI/` from every distribution.

Report each relevant gate as **VERIFIED**, **PARTIAL**, **BLOCKED**, or
**NOT RUN**, with the observed surface and missing evidence. A guidance review
does not qualify runtime code, installed packages, or scientific performance.

Pages assembly replaces only its owned dist/pages artifact directory after
checking every ancestor for symlinks/junctions. Custom outputs must be new;
existing contents are preserved. Canonical public inputs are compared byte for
byte during staging. The current task's compact evidence/remaining-gate record
is [implementation status](../engineering/validation/docs/implementation-status-2026-09-27.md).
