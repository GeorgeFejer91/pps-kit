---
name: html-dashboard-orchestrator
description: Change PPS Designer HTML controls and their local backend contracts, with scoped segment guidance, local preview verification, and canonical frontend/Pages parity at source promotion.
---

# PPS HTML dashboard orchestrator

Use for the PPS Designer's HTML/JavaScript interface and local software actions.
The browser collects decisions; the local backend validates/materializes them;
manifests record provenance. Native timing and acquisition remain native.

## Route before editing

Read [the UI domain](../../domains/design-ui.md) and the current development
stage. Use Ponytail for implementation and `uncodixfy-pretext` for touched
HTML text/layout. Resolve them through [SKILLS.md](../../SKILLS.md); report a
missing skill and use existing checks rather than inventing its rules.

- Layout-only: read [interface principles](../../interface_design_principles.md)
  and the affected screen's behavior; leave scientific defaults unchanged.
- Segment/control change: read matching headings in
  [GUI behavior](../../dashboard_gui_behavior.md) and
  [segment contracts](../../segment_registry_contract.md), then trace the
  control through state, API, persistence, and owning tests.
- New saved field, generation action, or runtime handoff: also read the affected
  [runtime contract](../../domains/experiment-runtime.md).
- Old decision not covered there: search the named feature in
  [preserved contract notes](../../archive/html-dashboard-orchestrator.md).
  Resolve historical contradictions against current contracts and source.

## Implement one coherent change

Canonical source is `apps/designer/frontend/`; the local service facade is
`packages/pps-runtime/src/peripersonal_space_toolkit/dashboard_app.py`.
Reuse existing controls and backend seams. Preserve Segment 0-6 ownership,
explicit creation/continuation, confirmed/read-only stages, downstream stale
checks, scientific defaults, and the finished-profile-to-Runner handoff.

For a changed control, cover visible state, event/payload, Rust or Python
validation as applicable, persistence, and manifest/QC consequences. Keep
imports and generated/participant files local and ignored; hide privileged
paths from ordinary editable UI. Measure bounded text with the existing
Pretext contract, then inspect actual rendered geometry.

## Complete the requested stage

Follow [WORKFLOW.md](../../WORKFLOW.md). Build/test the canonical frontend and
exercise actual controls locally. Layout changes require inspected screenshots
and supported viewport/zoom/content checks in addition to backend tests.

For completed changes to the Pages UI, use the
[standing deployment workflow](../../WORKFLOW.md#ui-exploration-and-promotion).
Compile the canonical frontend, assemble Pages from those bytes, promote the
scoped change to `main`, and check the deployed UI before handoff. Use
`website/` for the Pages wrappers. Packaging is a separate deliverable.

Use [the checklist](references/orchestrator-checklist.md) for the affected
contract/interaction/visual gate. Update only owning guidance/current work.
