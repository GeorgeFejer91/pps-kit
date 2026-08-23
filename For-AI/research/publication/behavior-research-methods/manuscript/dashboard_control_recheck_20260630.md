# Dashboard Control Recheck

Audit date: 2026-06-30.

Purpose: recheck whether the current local HTML dashboard source introduces any
new visible Segment 0-6 design decisions that are not represented in
`gui_control_coverage.csv` and, where literature-bearing, in
`evidence_matrix.csv`.

## Sources Inspected

- `apps/designer/frontend/index.html`
- `apps/designer/frontend/app.js`
- `apps/designer/frontend/styles.css`
- `For-AI/research/publication/behavior-research-methods/manuscript/gui_control_coverage.csv`

The local dashboard files were already dirty before this publication audit. The
audit therefore treats the current worktree as the local source inspected on
2026-06-30, but it does not stage, edit, or validate those dashboard changes.
If the dashboard edits are later committed or replaced, this recheck should be
rerun against that committed source.

## Method

The audit extracted visible dashboard labels from `index.html`, including
button text, label text, `aria-label` values, and placeholder text. It also
inspected the current dashboard diff against `HEAD` for added or removed
controls, labels, and method-relevant terms.

The control ledger was then checked at source level for the relevant surfaces:
global shell controls, Segment 0 study/profile controls, Segment 1 trajectory
and source controls, Segment 2 sequence controls, Segment 3 baseline/tactile
controls, Segment 4 repetition-pool controls, Segment 5 block/randomization
controls, and Segment 6 participant/run handoff controls.

## Findings

- No new literature-bearing PPS design control was found in the current local
  dashboard diff.
- The visible dirty dashboard change affecting labels/status text is a not-ready
  readiness-badge glyph change from a plain ASCII `X` representation to a
  Unicode cross glyph representation (`U+2715`) plus associated styling.
- `gui_control_coverage.csv` already has the relevant non-method row:
  `Left-rail Segment 0-6 step links and readiness badges`.
- The readiness badge communicates workflow state and stale/readiness status. It
  does not add a PPS experimental factor, baseline rule, tactile rule, stimulus
  construction choice, randomization rule, participant schedule, or analysis
  decision.
- The current control ledger still covers the visible Segment 0-6 design
  decisions at source level. Literature-bearing controls remain mapped to
  evidence-matrix rows, while view-only controls, folder openers, status badges,
  camera controls, modals, and navigation are intentionally classified as
  operational UI.

## Remaining Caveat

This recheck is not a GUI usability validation and not a screenshot-based visual
review. It supports the manuscript's source-level coverage claim only: every
visible Segment 0-6 methods decision in the current local dashboard source is
represented by the control ledger, and the only detected dirty-dashboard label
change is operational/status UI. If dashboard controls are changed before
submission, rerun this audit and update the ledger before relying on the paper's
"every visible GUI decision" claim.
