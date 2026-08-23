# Protocol 01: GUI To Stimulus Trace

## Purpose

Verify that researcher-facing GUI choices are preserved through saved design
state, segment manifests, 3DTI-compatible render configuration, generated WAV
metadata, block CSVs, and prepared session manifests.

This is a traceability test, not a timing measurement.

## Setup

- Use a deterministic test design or Study 5 preload.
- Use a non-participant test ID such as `VALIDATION_P001`.
- Keep generated outputs under `local_data/validation_runs/` or the normal
  ignored dashboard/session folders.

## Procedure

1. Open the local HTML dashboard.
2. Select the study profile or create the custom validation project.
3. Record the GUI values under test in a validation run manifest:
   - study/profile id
   - trajectory start/end position and duration
   - source labels and source type
   - SOA list
   - tactile duration/source
   - baseline and catch settings
   - repetition counts
   - participant count and one-part/two-part setup
4. Run the visible segment actions in order:
   - Segment 0: apply profile/create project
   - Segment 1: bake ingredient
   - Segment 2: bake trial sequences
   - Segment 3: bake baseline/tactile trials
   - Segment 4: bake trial pool CSV
   - Segment 5: regenerate/accept blocks
   - Segment 6: prepare experiment and open runner
5. Inspect the active project folder and prepared session folder.
6. Compare the recorded GUI settings against:
   - `0_profile/study_manifest.json`
   - Segment 1 ingredient manifest
   - Segment 2 trial-sequence manifest
   - Segment 3 tactile/baseline manifest
   - Segment 4 trial-pool CSV/manifest
   - Segment 5 final block CSVs/manifest
   - Segment 6 run-setup CSV/manifest
   - prepared `session_manifest.json`
   - prepared block CSV sample columns

## Acceptance Criteria

- GUI-selected values match the generated manifests and CSVs exactly.
- Segment manifests reference current upstream hashes, not stale assets.
- Prepared block CSVs include sample columns for trial start, looming onset,
  tactile onset, response-window onset, and trial end where applicable.
- Prepared block WAV channel roles remain left audio, right audio, tactile.
- Any mismatch is classified as either a GUI state bug, manifest propagation
  bug, render/preparation bug, or intentional known limitation.

## Result Notes

Write findings into `templates/acceptance_report.example.md` or a copied report
under `artifacts/validation_runs/<run_id>/`.
