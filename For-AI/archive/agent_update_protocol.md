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
10. For any visual, layout, sizing, placement, typography, or screen-adaptation decision, run a separate rendered UI or screenshot-based verification before finalizing. Treat visual proof as its own validation layer in addition to unit/backend tests and mouse-click workflow tests.
11. Commit the completed change set and push it to GitHub before finalizing. Keep the commit scoped to the intended work and do not stage unrelated pre-existing worktree changes. If authentication, network, branch protection, or conflicts block the push, report the exact blocker and leave the work ready to push.
12. In the final response, state whether `For-AI/` was updated and whether the change was pushed.

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

`apps/designer/frontend/compiled/` is the single offline/online Designer
artifact. Every HTML/dashboard change must rebuild that artifact, validate it in
the local package, assemble GitHub Pages from those exact compiled bytes, and
verify the hosted routes in the same change set. Do not maintain or edit a
second dashboard implementation under `website/`; that folder owns only public
route wrappers, Pages metadata, and other hosted product inputs. Hosted mode
must keep relative Designer/viewer assets. The Designer remains orchestration
only and must not run timing-sensitive experiments in browser JavaScript. The
separate canonical Runner companion may provide an explicitly exploratory,
locally armed Web Audio/vibration phone target, but that is not native or
publication-grade timing evidence.

## Public Domain And Pages URL Rule

The canonical public dashboard URL is `https://ppskit.qzz.io/`. The GitHub Pages fallback URL is `https://georgefejer91.github.io/pps-kit/`, and the repository/code URL is `https://github.com/GeorgeFejer91/pps-kit`.

Public route ownership is part of the product contract:

- Toolkit/app route: `https://ppskit.qzz.io/`
- Documentation route: `https://ppskit.qzz.io/documentation`
- Download route: `https://ppskit.qzz.io/download`
- Experiment Runner companion route: `https://ppskit.qzz.io/experiment-runner/`

Keep the matching GitHub Pages fallback routes available at `https://georgefejer91.github.io/pps-kit/`, `https://georgefejer91.github.io/pps-kit/documentation`, `https://georgefejer91.github.io/pps-kit/download`, and `https://georgefejer91.github.io/pps-kit/experiment-runner/`. The visible tab label may say `Downloads`, but the public route should remain singular `/download` unless the user explicitly changes this contract.

Do not reintroduce the old project Pages URL `https://georgefejer91.github.io/peripersonal-space-toolkit/` except as migration or historical context. The repository name controls the project Pages fallback path, so the GitHub repository should remain named `pps-kit` while this public URL contract is active.

`website/CNAME` is the tracked Pages source. Pages assembly must copy it to root
`CNAME` in the staged/deployed artifact. It contains only `ppskit.qzz.io`, with
no protocol, path, or second domain. The DNS provider points the subdomain to
`georgefejer91.github.io` without appending the repository name. If additional
domains are needed, use DNS/provider redirects rather than multiple CNAME
lines.

For hosted companion access, CORS origins are origins only: keep `https://ppskit.qzz.io` and `https://georgefejer91.github.io` allowed, but do not include paths such as `/pps-kit/`, `/documentation`, `/download`, or `/experiment-runner/` in an origin. GitHub Pages serves the Runner companion interface but no WebSocket relay; do not claim or configure hosted remote operation without an owned WSS or qualified WebRTC BRSP transport. When changing public URLs or tab routes, update repository references, release-manifest URLs, dashboard links, preloaded asset URLs, human docs, CORS tests, static deep-link handling, and this `For-AI/` rule together.

All external website links in the hosted/local HTML dashboard should open in a new browser tab with `rel="noopener noreferrer"`. Treat external HTTP(S) links as leaving the toolkit surface; internal route links, local companion calls, and repository-relative documentation links may remain in the same tab.

## Required GitHub Publishing

Every completed repository change must be committed and pushed to GitHub immediately after verification. Do not leave completed edits as local-only work. Stage only the intended change set; do not bundle unrelated dirty files or pre-existing user changes into the commit. If pushing is blocked by missing credentials, network failure, branch protection, or a non-fast-forward remote, report that blocker explicitly in the final response and describe the exact local commit or staged state that still needs to be pushed.

## Local Browser Orchestration Boundary

The HTML dashboard, whether launched locally or served from GitHub Pages, is only an orchestration surface. It must not upload stimulus files, participant data, generated WAVs, or experiment artifacts to an online service. Browser actions that select files, import audio, render stimuli, prepare sessions, stress audio, or launch Focus Mode must be executed by the local companion/backend on the research PC, with files stored in ignored local folders such as `local_data/` or `artifacts/`.

## Required UI Click Validation

Final validation for GUI/runner behavior must include user-style mouse-click emulation across the relevant visible controls. A workflow is not considered UI-ready merely because unit tests pass, manifests exist, or backend APIs can be called directly. The validation artifact should prove that the intended operator can complete the path by clicking buttons, selectors, and continuation controls in the UI. For Designer finished-profile claims, this means validating Segment 6 checklist/order preview/finalization/portable export. For Runner claims, independently validate finalized-profile discovery or import, participant session materialization, and the Focus Mode path. Hardware/audio-latency evidence can be separate, but UI usability proof by mouse-click emulation is mandatory.

Prefer background/offscreen mouse-event validation for automated GUI checks unless the user explicitly asks for a visible OS-cursor test. Visible Win32/OS-click validations can steal focus and interrupt the research PC; treat them as opt-in diagnostic tests. Background validation is acceptable when it sends real Qt/browser mouse events to the same controls and writes an artifact proving selector/button clicks, Focus Mode start/continuation clicks, session completion, and event counts.

## Required Visual Verification

Visual and layout decisions require a separate rendered UI or screenshot-based
verification. Unit tests, style diffs, geometry calculations, and backend
assertions are not enough to finalize changes that affect what an operator sees.
The verification should render the actual relevant UI state, save screenshots or
an equivalent visual artifact under an ignored validation folder, and explicitly
check for nonblank output, clipping, overlap, text visibility, panel placement,
and adaptive behavior across the target screen sizes when screen size matters.
For the HTML Experiment Designer, follow `interface_design_principles.md` and run
`python For-AI/engineering/validation/scripts/run_designer_visual_layout_audit.py`. Inspect
the screenshots/contact sheet, correct defects, rebuild, and rerun; collecting one
set of screenshots without a documented inspection-and-correction pass is not
visual approval.

## Android Emulator Validation Rule

Android emulator validation must treat the emulator as a fixed-size phone
screen. Do not resize, enlarge, repeatedly reposition, or otherwise manipulate
the emulator window to make the UI pass; smartphones have fixed viewports, and
flicker/reflow from window manipulation invalidates the usability signal. Run
ADB/uiautomator/button-press checks against the AVD's configured screen size,
capture screenshots at that size, and treat scrolling, clipping, cramped
controls, or hidden buttons as app/product findings to fix or document. Do not
run validation automation that moves or resizes Android emulator windows; manual
desktop arrangement by the human operator is outside the validation signal, and
the target remains the phone viewport, not a stretched desktop pane. Do not run
persistent desktop placement loops against Android emulator windows.
`For-AI/experiments/android-companion/tooling/Set_Companion_Emulation_Layout.ps1` intentionally leaves emulator
windows untouched and accepts old `-KeepForSeconds` arguments only as inert
compatibility input.

## Preload Catalog Storage Rule

Preload profile storage should mirror the dashboard workflow instead of becoming
a flat asset bucket. Repository source profiles live under
`packages/pps-resources/assets/preloads/<template_id>/`; installed and serialized
logical paths remain `assets/preloads/<template_id>/`. Keep the existing segment
folders `01_profile/` through `05_run_setup/`. Research screening, expected
outcome coverage, and full-pipeline evidence ledgers belong under
`For-AI/research/literature/preload-ledgers/`, not in the product preload
cabinet. Rebuild the approved catalogue with
`For-AI/engineering/tooling/build_preload_catalog.py` whenever templates,
source labels, trajectory metadata, or bundled WAVs change.

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
