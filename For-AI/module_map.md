# PPS Kit Module and Ownership Map

Read this after `For-AI/README.md` and before structural edits.

## Product Applications

### Designer

- Canonical frontend source and compiled offline/online artifact:
  `apps/designer/frontend/` and `apps/designer/frontend/compiled/`.
- Trajectory viewer: `apps/designer/frontend/viewer/`; the frontend build copies
  it into `compiled/viewer/`.
- Native/source launchers: `apps/designer/launchers/`.
- Windows/Linux product definitions: `apps/designer/packaging/`.
- Python service/controller facade:
  `packages/pps-runtime/src/peripersonal_space_toolkit/dashboard_app.py`.
- Native system-WebView shell and `pps-designer`:
  `designer_shell.py`; `pps-dashboard` remains its one-release compatibility
  alias.
- Segment 0-6 public contracts and lineage:
  `peripersonal_space_toolkit/designer_segments/`.

### Experiment Runner

- Native/source launchers: `apps/runner/launchers/`.
- Windows product definition: `apps/runner/packaging/PPSExperimentRunner.spec`.
- Focus Mode product implementation: `focus_app.py`.
- Prepared-experiment/session materialization and runtime:
  `session_runner.py`, `profile_preparation.py`, and `focus_launch.py`.
- Output/event/analysis support needed for normal Runner operation:
  `session_events.py`, `session_analysis.py`, `analysis_review.py`,
  `output_evidence.py`, `timing_events.py`, `topup.py`, and related runtime
  modules.
- The packaged executable is the only participant-facing Runner entrypoint.
  Legacy direct Python/Tk runner execution remains retired.

Android/phone execution is not a V1 Runner module. Its Python/Kotlin source,
bridges, tests, protocols, and CLIs live under
`For-AI/experiments/android-companion/`. `companion_v1_disabled.py` provides
only safe disabled defaults required by the desktop product while experimental
controls remain absent.

## Shared Runtime and Resources

- Python import source:
  `packages/pps-runtime/src/peripersonal_space_toolkit/`.
- Stable import name: `peripersonal_space_toolkit`.
- Runtime path ownership: `runtime_paths.py` exposes `product_root()`,
  `resource_root()`, `designer_frontend_root()`, and `writable_root()`.
  `repo_root()` is a one-release compatibility alias; frozen applications honor
  `PPS_TOOLKIT_ROOT`.
- Approved application/resources source: `packages/pps-resources/assets/`.
- Immutable built-in profiles: `packages/pps-resources/study_templates/`.
- Product examples: `packages/pps-resources/configs/`.
- Deidentified public sample data: `packages/pps-resources/data/sample/`.
- Logical serialized/installed paths remain `assets/...`,
  `study_templates/...`, `configs/...`, and `data/sample/...`.
- Pinned product dependencies/licenses: `third_party/`.

Key scientific modules:

- design model, validation, profile serialization: `design.py`, `templates.py`,
  `profile_bundle.py`, `profile_recreation.py`
- stimulus generation/spatial rendering: `render_backend.py`, `spatial.py`,
  `loudness.py`, `audio_routing.py`
- trial/block scheduling: `trial_filmstrip.py`, `participant_orders.py`,
  `designer_segments/`
- decoding/analysis: `decoder.py`, `analysis.py`, `analysis_review.py`
- calibration and acquisition evidence: `tactile_calibration/`,
  `latency_validation.py`, `output_evidence.py`, `labrecorder_capture.py`

## Distribution

- Component schema/manifests: `distributions/manifests/`.
- Parameterized Go downloader source: `distributions/downloader/`.
- Scripts executed on an installed PC: `distributions/windows-support/`.
- Designer leaf component owns Designer-only files and depends on Shared.
- Runner leaf component owns Runner-only files and depends on Shared.
- Shared owns approved common files exactly once.
- Full composes Designer + Runner + one Shared and creates two shortcuts; no
  central hub is introduced.

Release assembly code and tests are internal:
`For-AI/engineering/release/` and `For-AI/engineering/tests/`.

## Website

- Tracked Pages inputs: `website/`.
- Canonical domain source: `website/CNAME`.
- Pages assembly: `For-AI/engineering/automation/build_pages.mjs`.
- GitHub-required thin wrapper: `.github/workflows/pages.yml`.
- Assembly copies the exact Designer `compiled/` bytes and approved public
  catalogues into ignored `dist/pages/`, including root `CNAME`.
- Preserve `/`, `/documentation`, `/download`, `ppskit.qzz.io`, and the
  `georgefejer91.github.io/pps-kit/` fallback.

## Internal Engineering

- CI/Pages implementation: `For-AI/engineering/automation/`.
- Executable build/setup: `For-AI/engineering/build/`.
- Release assembly, inventories, protocols, audits:
  `For-AI/engineering/release/`.
- Generators/maintenance tools: `For-AI/engineering/tooling/`.
- Test suite: `For-AI/engineering/tests/`.
- Software/UI/audio/hardware validation:
  `For-AI/engineering/validation/`.
- Diagnostics/reference captures: `For-AI/engineering/diagnostics/`.
- Migration ledgers/allowlists: `For-AI/engineering/migration/`.

GitHub workflows must remain minimal wrappers because GitHub requires their
location. Their substantive logic belongs under `For-AI/engineering/automation/`.

## Internal Research

- Literature audits, source networks, screening, evidence ledgers:
  `For-AI/research/literature/`.
- Broad citation-network source and builder:
  `For-AI/research/literature/publication-network/` and
  `For-AI/research/literature/tools/build_publication_network_asset.mjs`.
- Approved public projection copied into the Designer:
  `apps/designer/frontend/publication_network.v3.json`.
- Calibration exploration: `For-AI/research/calibration/`.
- BRM/manuscript work: `For-AI/research/publication/`.
- Woojer and other research-only hardware work: `For-AI/research/hardware/`.

Research screening and full evidence ledgers are not product preload assets.
Only the reduced approved catalogue, inventory, and recreation-status projection
remain under `packages/pps-resources/assets/preloads/`.

## Tests and Structural Enforcement

- `test_repository_structure.py`: root allowlist, tracked-path classification,
  component ownership, exclusion rules, and no `For-AI/` distribution entries.
- `test_package_inventory.py`: independent Shared/Designer/Runner/Full
  inventories and exact composition.
- `test_release_audit.py`: public/private boundary and stale product paths.
- Designer frontend tests plus Vite build validate the canonical compiled UI.
- Runner smoke/response-marker/Protocol 12 tests validate prepared packages and
  Segment 0-6 handoff without claiming participant or hardware evidence.
