# For-AI Project Memory

This is the required starting point for AI agents working on PPS Kit. `For-AI/`
is public, tracked development memory and orchestration; it is never part of an
end-user package.

## Repository Boundary

Use one classification rule:

- Outside `For-AI/`: source, resources, specifications, documentation, and
  declarative manifests that form or define a shipped application or public
  website.
- Inside `For-AI/`: build execution, testing, validation, diagnostics,
  research, publication work, code generation, audits, migration records, and
  unapproved experiments.

The public products are two independently shippable applications:

- Designer: `apps/designer/`
- Experiment Runner: `apps/runner/`

V1 still ships those two validated products. The candidate V2 Runner source is
also under `apps/runner/`, with shared Rust crates under `packages/`. An
optional experimental Meta Quest application context lives separately at
`apps/quest-runner/`; it is not the primary PPS Kit Runner target. Neither
preview is present
in V1 component manifests or allowed to weaken the validated Python/PySide
Runner and Windows acquisition evidence.

They share the Python runtime in `packages/pps-runtime/`, approved resources in
`packages/pps-resources/`, and versioned component manifests in
`distributions/manifests/`. The Full download composes Designer, Runner, and
exactly one compatible Shared component. V1 has no central hub.

`peripersonal_space_toolkit` remains the Python import name. `repo_root()` is a
one-release compatibility alias; new code should use `product_root()`,
`resource_root()`, `designer_frontend_root()`, and `writable_root()` from
`runtime_paths.py`. Frozen applications continue to honor `PPS_TOOLKIT_ROOT`.

## Read Next

- [project_context.md](project_context.md): scientific scope, product behavior,
  and current boundaries.
- [evolving_goals.md](evolving_goals.md): dated decisions and ongoing work.
- [module_map.md](module_map.md): code and resource ownership.
- [download_package_inventory.md](download_package_inventory.md): component and
  installer contract.
- [segment_registry_contract.md](segment_registry_contract.md): preserved
  Segment 0-6 manifests and handoff contracts.
- [dashboard_gui_behavior.md](dashboard_gui_behavior.md): Designer UI behavior.
- [agent_update_protocol.md](agent_update_protocol.md): memory update rules.
- [engineering/migration/repository-layout.v1.json](engineering/migration/repository-layout.v1.json):
  machine-readable migration ledger.
- [engineering/migration/root-allowlist.v1.json](engineering/migration/root-allowlist.v1.json):
  allowed repository-root entries.

## Internal Layout

```text
For-AI/
  engineering/
    automation/     CI and Pages implementation called by thin GitHub wrappers
    build/          executable build and environment setup
    release/        component assembly, inventories, protocols, and audits
    tooling/        generators and maintenance utilities
    tests/          pytest and downloader tests
    validation/     software, UI, audio, and hardware validation
    diagnostics/    approved diagnostic tools and reference captures
    migration/      compatibility ledgers and housekeeping records
  research/
    literature/     paper audits, citation sources, and screening ledgers
    calibration/    exploratory loudness/calibration work
    publication/    manuscript and legacy methods material
    hardware/       research-only device investigations
  experiments/
    android-companion/  unapproved Android companion and PC-side experiments
```

The generated, approved publication-network projection may ship with the
Designer; its broad source/audit graph remains under `For-AI/research/`.
Android source, Android administration CLIs, phone bridges, tests, and visible
controls under `For-AI/experiments/android-companion/` are development-only and
excluded from V1 manifests. The separate `apps/quest-runner/` candidate is an
optional application-context proof, not a primary PPS Kit product; its
Gradle/device suites are not V1 release gates. The default pytest scope remains
`For-AI/engineering/tests/`.

## Product and Publication Contracts

- The Designer compiled frontend is the single offline/online UI artifact.
  Local packaging consumes `apps/designer/frontend/compiled/`; Pages assembly
  copies those same bytes into ignored staging alongside approved catalogues.
- The Runner companion is built once under `apps/runner/compiled/`. Pages
  publishes its companion HTML and allowlisted browser assets byte-for-byte at
  `/experiment-runner/`; never publish the Tauri desktop entry or capabilities.
- `website/CNAME` is the tracked Pages source. The assembled Pages root must
  contain `CNAME` with `ppskit.qzz.io`.
- Preserve `/`, `/documentation`, `/download`, `/experiment-runner/`,
  `https://georgefejer91.github.io/pps-kit/`, and the existing fallback routes.
- Any Designer HTML change must rebuild the compiled frontend, assemble Pages,
  and verify both local and hosted-facing copies in the same change.
- Preserve `.pps-profile`, prepared-experiment, Segment 0-6, and existing
  scientific schemas. Preserve `pps-designer`, generation/rendering CLIs, the
  Runner executable, and `pps-dashboard` as a one-release Designer alias.

## Agent Requirements

1. Read this file before planning or editing.
2. Keep product files out of `For-AI/` and development execution out of product
   manifests.
3. Update project memory when goals, GUI behavior, schemas, runner behavior,
   publication boundaries, tests, or repository structure change.
4. Never add secrets, participant data, generated runtime outputs, or private
   absolute paths.
5. Run the relevant structural, package-inventory, release/privacy, frontend,
   and runtime tests.
6. Commit and push every completed repository change. Stage only the intended
   change set; report the exact blocker if pushing is not possible.
