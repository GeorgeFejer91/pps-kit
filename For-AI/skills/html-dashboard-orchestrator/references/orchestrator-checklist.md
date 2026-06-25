# HTML Orchestrator Checklist

Use this checklist before finalizing an HTML dashboard change.

## Contract

- Does the browser control map to an existing backend action?
- If not, did you add the smallest backend endpoint or schema field that represents the researcher decision?
- Are saved defaults backward-compatible with existing designs/templates?
- Are render/session manifests or QC rows updated when behavior changes?

## Local-Only Boundary

- Does any file import/store/process action happen through the local companion backend?
- Are ignored local folders used for generated or imported artifacts?
- Does the hosted page avoid direct uploads and direct experiment execution?
- Does the UI communicate that imported files are local without turning the page into a tutorial?

## Interaction

- Are related controls live-synchronized where the user expects immediate feedback?
- Are direct-manipulation controls mirrored in numeric fields or saved schema?
- Do remove/add actions update status badges and validation gates?
- Does custom mode still force the sequential minimum runnable profile?

## Workflow Segmentation

- Does each one-page website section represent one natural decision stage?
- Are panels localized to the functional segment that owns them?
- Are unrelated controls kept out of earlier segments even when there is visual space?
- Are previews and backend feedback colocated with the decision they support?
- Do left-rail navigation, status gates, and continue actions follow the same segment order?

## Frontend Quality

- Are controls dense, calm, and domain-specific?
- Are labels short and unambiguous?
- Are dimensions stable across desktop and narrow viewports?
- Are panel splitters/edge handles preserved rather than replaced by left-rail size sliders?

## Validation

- Run targeted API/schema tests.
- Run relevant render/session tests when backend behavior changes.
- Browser-smoke the local dashboard.
- Verify the GitHub Pages/static version after push when dashboard files changed.
- State any test that could not be run.
