# PPS Toolkit Architecture

This map records the intended ownership boundaries for the current Python-first PPS Toolkit. It is a maintenance aid for researchers and agents; it does not rename public CLIs or change the Segment 0-6 dashboard contract.

## Core Subsystems

| Subsystem | Owns | Current main locations |
|---|---|---|
| Dashboard backend | FastAPI app, local companion actions, project registry, local filesystem policy, runner handoff | `src/peripersonal_space_toolkit/dashboard_app.py`, `src/peripersonal_space_toolkit/dashboard_backend/` |
| Dashboard frontend | Browser decisions, static/hosted orchestration, previews, local companion calls | `src/peripersonal_space_toolkit/dashboard/`, root `index.html` |
| Segment manifests | Segment 0-6 artifact state, stale-upstream checks, deterministic manifest hashes | currently in `dashboard_app.py`, target split into manifest/segment modules |
| Stimulus and render | Looming/tactile generation, trajectory sampling, SOFA/FABIAN and native 3DTI handoff | `design.py`, `stimulus_generation.py`, `render_backend.py`, `timing_schedule.py` |
| Runtime and events | Session package materialization, participant playback, event logs, LSL/XDF mirrors, output evidence | `session_runner.py`, `focus_app.py`, `timing_events.py`, `session_events.py`, `output_evidence.py` |
| Validation evidence | Software, UI, hardware, LSL/XDF, loopback, and publication-readiness protocols | `validation_protocols/`, `tests/` |
| Preloads and profile recreation | Published-study templates, preload catalogs, Segment 0-4 gates, Protocol 12 | `study_templates/`, `assets/preloads/`, `profile_recreation.py` |
| Literature and paper audit | Paper/supplement metadata extraction, source-pointer ledgers, implementation blockers, profile-candidate evidence | `peripersonal_space_toolkit.paper_audit`, `tools/paper_metadata_parser/`, `For-AI/audiotactile-paper-metadata-audit/` |

## Authority Rules

- Browser JavaScript is a request and display layer. It must not become the authority for timing, generated files, participant runtime state, or manifest validity.
- Segment manifests are the authority for generated workflow state. Filenames remain inspection aids, not source-of-truth parsers.
- Native Focus Mode and `SessionRunnerController` own participant runtime timing, event emission, response pairing, and local session outputs.
- Literature/paper audit state is a core upstream evidence pipeline. It should feed profile recreation, missing-parameter decisions, and future toolkit feature gaps while keeping raw PDFs and extracted full text out of Git.
- Validation protocols are evidence layers. They should say exactly what they prove: software contract, UI clickability, physical loopback timing, XDF preservation, or profile recreation.

## Split Strategy

Prefer behavior-preserving extraction over rewrites:

1. Keep existing public entrypoints as facades.
2. Move one authority at a time into a focused module.
3. Add tests at the new seam before moving more code.
4. Preserve deterministic manifest bytes unless a schema change is intentional and documented.
5. Do not move timing-sensitive behavior into the dashboard or hosted page.

The first stable extraction is the paper-audit package API plus dashboard backend security helpers. Larger splits of `dashboard_app.py`, `focus_app.py`, `session_runner.py`, and `dashboard/app.js` should follow this same pattern.
