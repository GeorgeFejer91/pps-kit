# Agent Update Protocol

`For-AI/` is tracked project memory. It is not a private scratchpad.

## Required Session Loop

Every AI agent working in this repository must:

1. Read `AGENTS.md`.
2. Read `For-AI/README.md`.
3. Consult `project_context.md` and `evolving_goals.md` before planning or editing.
4. If the work changes the HTML/dashboard web GUI, read `For-AI/skills/html-dashboard-orchestrator/SKILL.md` before editing.
5. Do the requested work.
6. If the work changes the HTML/dashboard web GUI, update the matching online website/static GitHub Pages version in the same change set before finalizing.
7. Before finalizing, decide whether the work was substantive.
8. If substantive, update the relevant `For-AI/` file.
9. For any GUI or runner workflow claim, run or add an end-user mouse-click validation before finalizing. The accepted proof must emulate a user clicking visible controls through the workflow, not only call backend APIs or direct helper functions.
10. In the final response, state whether `For-AI/` was updated.

## What Counts As Substantive

Update `For-AI/` after changes to:

- project aims or scope
- GUI behavior or user workflows
- data schemas, saved settings, templates, or config contracts
- experiment runner behavior
- stimulus generation, decoding, analysis, or event capture
- privacy/publication boundaries
- tests, release checks, or repository structure
- literature-derived goals or supported paradigms

## Web GUI Website Sync

Every change to the new HTML/dashboard web GUI must be reflected on the online website version before the work is considered complete. Future agents should not stop after updating only the local dashboard files. They must also update the hosted/static GitHub Pages-facing files or deployment artifact used by the public website, then verify that the website version still uses relative dashboard/viewer assets and talks to the local companion backend rather than trying to run timing-sensitive experiments in browser JavaScript.

## Local Browser Orchestration Boundary

The HTML dashboard, whether launched locally or served from GitHub Pages, is only an orchestration surface. It must not upload stimulus files, participant data, generated WAVs, or experiment artifacts to an online service. Browser actions that select files, import audio, render stimuli, prepare sessions, stress audio, or launch Focus Mode must be executed by the local companion/backend on the research PC, with files stored in ignored local folders such as `local_data/` or `artifacts/`.

## Required UI Click Validation

Final validation for GUI/runner behavior must include user-style mouse-click emulation across the relevant visible controls. A workflow is not considered UI-ready merely because unit tests pass, manifests exist, or backend APIs can be called directly. The validation artifact should prove that the intended operator can complete the path by clicking buttons, selectors, and continuation controls in the UI. For Study 5 and finished-profile claims, this means validating the Segment 6 handoff and the standalone Experiment Runner profile-selection path with mouse-click behavior through Focus Mode completion. Hardware/audio-latency evidence can be separate, but UI usability proof by mouse-click emulation is mandatory.

Prefer background/offscreen mouse-event validation for automated GUI checks unless the user explicitly asks for a visible OS-cursor test. Visible Win32/OS-click validations can steal focus and interrupt the research PC; treat them as opt-in diagnostic tests. Background validation is acceptable when it sends real Qt/browser mouse events to the same controls and writes an artifact proving selector/button clicks, Focus Mode start/continuation clicks, session completion, and event counts.

## Preload Catalog Storage Rule

Preload profile storage should mirror the dashboard workflow instead of becoming a flat asset bucket. Every preload profile should have a folder under `assets/preloads/<template_id>/` with segment folders matching the HTML GUI stages: `01_profile/`, `02_looming_stimuli/`, `03_baseline_strategy/`, `04_trial_designer/`, and `05_run_setup/`. Put prebaked auditory-only profile WAVs and source/trajectory metadata in `02_looming_stimuli/`, profile/citation metadata in `01_profile/`, baseline/catch defaults in `03_baseline_strategy/`, trial-row/SOA/snippet metadata in `04_trial_designer/`, and participant/randomization defaults in `05_run_setup/`. Rebuild this cabinet and the inventory with `tools/build_preload_catalog.py` whenever preload templates, source labels, trajectory metadata, or bundled WAVs change.

## What To Update

- Update `evolving_goals.md` for new decisions, changed priorities, or backlog changes.
- Update `project_context.md` when the current architecture, scope, or product boundaries change.
- Update this protocol if the maintenance rules themselves change.
- Update `README.md` only when human-facing setup or repo navigation changes.

## What Not To Store

Do not store:

- participant data
- raw recordings
- generated artifacts
- secrets or credentials
- private local paths
- unsupported claims about published studies
- long chat transcripts

Keep entries concise and operational. The goal is to preserve current intent so future agents do not rediscover the same decisions from scratch.
