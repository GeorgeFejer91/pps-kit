# PPS Kit ownership map

Locate the owning code, then inspect actual callers/contracts. Python module
names below are relative to `packages/pps-runtime/src/peripersonal_space_toolkit/`.

| Area | Source authority | Guidance |
|---|---|---|
| Designer UI/viewer | `apps/designer/frontend/`, `frontend/viewer/`; one `frontend/compiled/` artifact | [Design/UI](domains/design-ui.md) |
| Designer local service | `dashboard_app.py`, `dashboard_backend/`, `designer_app.py`, `designer_shell.py`, `designer_segments/` | [Design/UI](domains/design-ui.md), [runtime](domains/experiment-runtime.md) |
| Design/profile handoff | `design.py`, `templates.py`, `profile_bundle.py`, `profile_recreation.py`, `profile_preparation.py` | [Runtime](domains/experiment-runtime.md) |
| Generation/scheduling | `stimulus_generation.py`, `render_backend.py`, `spatial.py`, `loudness.py`, `audio_routing.py`, `timing_schedule.py`, `trial_filmstrip.py`, `participant_orders.py` | [Runtime](domains/experiment-runtime.md) |
| V1 native Runner | `apps/runner/launchers/`, `apps/runner/packaging/`, `focus_app.py`, `focus_launch.py`, `session_runner.py` | [Runtime](domains/experiment-runtime.md) |
| Responses/calibration/evidence/review | `response_policy.py`, `tactile_calibration/`, `timing_events.py`, `session_events.py`, `output_evidence.py`, `labrecorder_capture.py`, `decoder.py`, `analysis.py`, `analysis_review.py` | [Runtime](domains/experiment-runtime.md), [science](domains/scientific-evidence.md) |
| Candidate V2 desktop authority | `apps/runner/src-tauri/src/`, especially `execution_owner.rs`, `runtime.rs`, `remote.rs` | [Runtime](domains/experiment-runtime.md) |
| Candidate Rust contracts/execution | `packages/pps-contracts/`, `pps-brsp/`, `pps-runner-core/`, `pps-session-package/`, `pps-runner-execution/`, `pps-runner-audio/`, `pps-runner-audio-cpal/` | [Runtime](domains/experiment-runtime.md) |
| Candidate Runner UI/companion | `apps/runner/frontend/`; one `apps/runner/compiled/` artifact | [Design/UI](domains/design-ui.md), [runtime](domains/experiment-runtime.md) |
| Approved profiles/resources | `packages/pps-resources/`; logical paths remain `assets/`, `study_templates/`, `configs/` | [Science](domains/scientific-evidence.md) |
| Paper audits/source ledgers | `For-AI/research/literature/`; read-only package access in `paper_audit.py` | [Science](domains/scientific-evidence.md) |
| Research/publication/calibration | `For-AI/research/{publication,calibration,hardware}/` | [Science](domains/scientific-evidence.md) |
| Component/install definitions | `distributions/manifests/`, `distributions/downloader/`, `distributions/windows-support/` | [Release](domains/release-operations.md) |
| Pages | `website/`; assembly in `For-AI/engineering/automation/build_pages.mjs` | [Release](domains/release-operations.md) |
| Build/check/evidence execution | `For-AI/engineering/{automation,build,release,tests,validation,tooling,diagnostics}/` | [Release](domains/release-operations.md) |

Preserve public facades, manifest identity, and deterministic bytes during
extraction. Keep one experiment authority; UI, IPC, CLI, and remote adapters
call it. Software evidence is separate from hardware/behavioral qualification.

Optional Android work lives under `For-AI/experiments/android-companion/`;
the Quest candidate lives under `apps/quest-runner/`. Neither is a default
PPS development or V1 packaging gate.

[The former detailed map](archive/module_map.md) retains native authority,
queue, media, transport, and evidence notes at the sync checkpoint. Consult
only affected sections and verify them against current code.
