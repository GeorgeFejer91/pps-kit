# PPS Kit Architecture

PPS Kit is a public monorepo with two independently shippable applications and
one compatible Shared component. This map does not rename public CLIs or change
Segment 0-6/scientific schemas.

## Classification Rule

- Outside `For-AI/`: anything that forms or declaratively defines a shipped
  application, Shared resource set, public documentation, or public website.
- Inside `For-AI/`: execution and evidence used to research, build, test,
  validate, publish, generate, diagnose, audit, or experiment on the products.

GitHub-required workflow wrappers are the sole location exception; substantive
workflow logic remains in `For-AI/engineering/automation/`.

## Product Ownership

| Component | Owns | Source roots |
|---|---|---|
| Designer | design/profile/prepared-experiment UI and launch | `apps/designer/`, Designer runtime modules |
| Runner | prepared-experiment execution, participant timing, event/evidence capture, normal post-run review | `apps/runner/`, Runner runtime modules |
| Shared | immutable templates, approved resources, public docs, licenses, reviewed dependencies | `packages/pps-resources/`, `docs/`, `third_party/` |
| Full | exact composition of Designer + Runner + one Shared | `distributions/manifests/full.v1.json` |

The Python implementation remains under `packages/pps-runtime/src/` and keeps
the `peripersonal_space_toolkit` import surface. Executable packaging selects
the modules needed by each leaf application; component manifests own installed
files exactly once.

## Stable Interfaces

- `.pps-profile` and prepared-experiment packages are the stable Designer to
  Runner handoff.
- Segment 0-6 manifests, hashes, and stale-upstream rules remain authoritative.
- Browser JavaScript is a request/display surface, not the timing, generated
  file, participant runtime, or manifest authority.
- Focus Mode and `SessionRunnerController` own participant timing, response
  pairing, event emission, and local outputs.
- Logical product paths (`assets/...`, `study_templates/...`) remain stable in
  schemas and installed layouts.
- `runtime_paths.py` separates product, resources, compiled frontend, and
  writable outputs. `repo_root()` is a temporary compatibility alias.

## Frontend and Pages

`apps/designer/frontend/compiled/` is the only compiled Designer UI. PyInstaller
consumes it directly. Pages assembly copies the same bytes into ignored staging
with approved catalogues and `website/CNAME`. `website/` contains route wrappers
and Pages inputs, not a second dashboard source.

## Internal Boundaries

| Internal area | Owns |
|---|---|
| `engineering/build/` | executable build/setup |
| `engineering/release/` | component assembly, inventories, protocols, audits |
| `engineering/tests/` | automated tests, including structural/ownership tests |
| `engineering/validation/` | software/UI/audio/hardware evidence |
| `engineering/tooling/` | generators and maintenance utilities |
| `engineering/diagnostics/` | diagnostic tools and approved captures |
| `research/` | literature, calibration, publication, research hardware |
| `experiments/android-companion/` | unapproved phone execution/control work |

Internal material never enters a component manifest. Android-specific source,
CLIs, assets, launchers, and visible controls are excluded from V1. Only normal
desktop Runner safety behavior remains in product code.

## Dependency and Split Strategy

1. Keep stable public interfaces as facades while extracting authorities.
2. Move one authority at a time and test its seam.
3. Avoid Designer GUI dependencies in Runner runtime and Runner GUI dependencies
   in Designer packaging.
4. Preserve deterministic manifest bytes unless a documented schema change is
   intentional.
5. Reject incompatible Shared versions/hashes at install time.
6. Never move timing-sensitive behavior into the hosted page.
