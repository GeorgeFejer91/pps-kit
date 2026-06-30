# Submission Readiness Audit

Audit date: 2026-06-30.

This audit maps the current Behavior Research Methods manuscript source against
the requested PPS Toolkit methods/software paper goals. It is a source-level
readiness ledger, not manuscript text, not a participant-results report, and not
evidence that a particular laboratory hardware route has been validated.

The manuscript presents PPS Toolkit as a full suite for designing new
audio-tactile PPS experiments, recreating or scaffolding published paradigms as
auditable profiles, running accepted designs through a native acquisition
pipeline, validating output evidence, and reviewing exploratory post-run
analysis. The current source is strong enough to support that framing as a draft
methods/software paper. It is not yet a final submission package.

## Status Key

- `source-ready`: represented in committed source artifacts and checked by
  source/build inspection.
- `partially supported`: represented in the draft, but still needs final
  release metadata, validation artifacts, copy editing, or human confirmation.
- `not claimed`: intentionally excluded from the current paper framing.
- `blocked until artifact`: cannot be completed without an external release,
  hardware validation run, traceable participant/run artifact, or human-supplied
  submission information.

## Requirement Matrix

| Requirement | Current evidence | Status | Remaining work |
| --- | --- | --- | --- |
| Springer/BRM manuscript workspace | `publication/behavior-research-methods/README.md` records the Springer Nature template source, Overleaf pointer, download date, ZIP hash, extracted template path, and `sn-apa` guidance. | source-ready | Recheck current Springer/BRM instructions immediately before submission. |
| BRM methods/software article framing | `main.tex` includes a methods/software title, abstract, `Contribution and Journal Fit`, `PPS Toolkit Overview`, `Design, Run, and Recreation Pathway`, technical method, validation/use-case, discussion, declarations, and open-practices sections. | partially supported | Replace placeholder author email/affiliation/funding/conflict fields and perform final human copy edit. |
| Tutorial-style reader orientation | `main.tex` now includes a reader-guide table mapping practical reader questions to manuscript sections and source artifacts. | source-ready | Keep the table aligned with source files if manuscript artifacts are renamed or moved. |
| Full suite framing rather than design-only framing | `main.tex` names PPS Toolkit as a suite in the title, abstract, contribution section, practical entry-point table, Segment 6 runner handoff, archive-layer table, and conclusion. | source-ready | Keep this framing in future edits; do not collapse the article back to a dashboard-only methods note. |
| Design, run, and published-profile recreation entry points | The pathway section separates new-study design, published-profile recreation, and native acquisition; the archive table separates design, profile-recreation, validation, and participant archives. The validation section now adds an operator procedure/evidence handoff table. | source-ready | Add final external archive/DOI links once the release and any validation archive are published. |
| Consensus-backed literature grounding | `references.bib`, `evidence_matrix.csv`, and `critical_review.md` record literature-backed rows for PPS, baselines, tactile calibration, HRTF/spatial rendering, software methods, randomization, and analysis decisions. | source-ready | If new claims are added, add new source-pointer rows rather than making uncited prose claims. |
| Formal meta-analysis request | The manuscript explicitly frames the literature work as an evidence matrix and source-pointer scaffold, not a PRISMA systematic review or effect-size meta-analysis. | not claimed | To make a formal meta-analysis claim, add inclusion/exclusion rules, screening logs, extracted effect sizes, risk-of-bias fields, and reproducible synthesis code. |
| Every visible Segment 0-6 GUI decision represented | `evidence_matrix.csv` contains 44 literature-bearing decision rows; `gui_control_coverage.csv` contains 64 visible-control audit rows mapping controls either to evidence rows or to operational/non-method categories. | source-ready | Re-run the control audit after any dashboard UI change. GUI usability validation remains separate from manuscript source coverage. |
| Smooth looming versus salient burst-train source decisions | Segment 1 prose and evidence rows distinguish `Burst train` from `Smooth linear`, with rationale for burst/noise salience, continuous looming, ecological/affective sounds, and profile-specific source substitutions. | source-ready | Preserve source hashes and source-profile metadata in final archived examples. |
| Trajectory and spatial frame decisions | The draft covers start/end distance, azimuth, elevation, front/rear/left/right variants, looming/receding direction, body-centered interpretation, and action/body remapping caveats. | source-ready | Published-profile recreations should continue to mark missing geometry as approximated rather than verified. |
| HRTF/SOFA/FABIAN/3DTI rendering | `main.tex` includes a spatial-audio technical section covering SOFA/HRTF resources, FABIAN/TU Berlin default public reference, 3D Tune-In-compatible rendering, near-field caveats, and provenance metadata. | source-ready | Do not claim perceived distance, externalization, or individualized HRTF validity without additional perceptual validation. |
| Trial sequence design decisions | Segment 2 prose and evidence rows cover instruction snippets, source alternatives, jitter, row/family order, and within-trial sequence materialization. | source-ready | Attach exact final source manifests and sequence manifests in the release archive. |
| Baseline/control logic | The evidence matrix and prose cover no-baseline, tactile-only, stationary/fixed-distance auditory baseline, auditory-only catch, direction-coupled baseline, min/max controls, and expectancy/correction caveats. | source-ready | Confirm final study examples name their baseline correction method, baseline sample size, and whether baseline trials enter the same response rule. |
| Tactile calibration and tactile misses | `main.tex` and the matrix treat threshold calibration, adaptation, misses, and response probability as first-class methods decisions. The reported 70% long-session hit-rate observation is kept as anecdotal design motivation only. | partially supported | Publish quantitative hit-rate decline only if traceable run artifacts and analysis code are supplied. |
| Adaptive tactile threshold rule | The technical method narrowly describes the implemented run-local safeguard: after every two tactile misses, including top-up misses, Output 3/4 is raised by 0.01 percentage points up to 0.5%, with `tactile_threshold_adapted` events and adaptive-threshold artifacts. | source-ready | Future empirical work should test whether the rule improves completeness without condition-dependent bias. |
| Randomization, repetition pools, blocks, and participant schedules | The draft covers deterministic repetition pools, row/family order preservation, block acceptance, participant-by-part schedules, and artifact-producing gates. | source-ready | Record final seed/permutation manifests for any example study archive. |
| Running/acquisition suite layer | Segment 6 and the technical method describe `PPSExperimentRunner.exe`, multichannel output, response logging, LSL markers, optional LabRecorder capture, local audio evidence, loopback evidence, tactile calibration, and top-up. | partially supported | Add publication-hardware validation artifacts before making claims about a specific lab route. |
| Validation evidence tiers | The manuscript distinguishes software schedule evidence, digital audio evidence, electrical loopback evidence, and tactile perceptual evidence. `validation_evidence.csv` summarizes current source-pointer evidence. | partially supported | Attach final hardware/electrical-loopback and perceptual/calibration artifacts for any timing or tactile claims beyond software materialization. |
| Published-profile recreation / replication scaffold | The manuscript and validation table describe Profile 12-style materialization through Segment 6 and caveat that this is not exact reuse of private original stimuli or every apparatus property. `profile_family_examples.csv` and the manuscript profile-family table map canonical dynamic, baseline/expectancy, directional, mobile/DynaSpace, affective/ecological, and action/immersive method families to toolkit representations and caveats. | partially supported | For each final profile, verify source-paper pointers, represented fields, missing fields, and substitution notes before calling it recreation-ready. |
| Analysis choices | `main.tex` covers raw RT curves, tactile-only baseline correction, sigmoid/log-decay/linear fits, AICc triage, low-N warnings, response-quality visibility, and exploratory rather than confirmatory interpretation. | source-ready | Confirmatory claims require preregistered analysis and adequate participant/sample evidence outside this draft. |
| Declarations and open practices | The draft includes Code Availability, Data Availability, Materials Availability, Ethics/consent, Competing Interests, Funding, and Open Practices sections. | blocked until artifact | Fill real author metadata, ethics statement, funding, competing interests, repository release tag, commit, DOI, and archived materials links. |
| Copyright and private-data boundary | README files and the open-practices statement exclude copyrighted PDFs, private participant outputs, local SOFA files, proprietary sounds, and unlicensed generated assets. | source-ready | Run a final release audit before submission and before any archived supplement is minted. |
| Compile integrity | The latest compile check on 2026-06-30 produced a clean Springer `sn-apa` draft after a final cross-reference rerun; generated build artifacts were removed. | partially supported | Recompile after every source change and keep generated `.aux`, `.bbl`, `.blg`, `.log`, `.out`, and `.pdf` files out of Git unless an explicit release snapshot is requested. |
| Final submission readiness | The draft is a serious BRM methods/software source package for a full design-run-recreate-run-analysis suite with explicit profile-family and operator-procedure scaffolds. | partially supported | Not final until release metadata, author/declaration fields, final validation archives, and copy editing are complete. |

## Current Bottom Line

The source now supports the intended article thesis: PPS Toolkit is a reusable
suite for designing, running, validating, and recreating audio-tactile PPS
experiments while preserving the methodological variation of the field. The
remaining blockers are not broad conceptual manuscript gaps; they are final
submission artifacts, profile-specific verification, and evidence boundaries:
release DOI/commit, author and declaration metadata, publication-hardware
validation, and traceable data if any participant hit-rate or tactile-adaptation
effect is quantified.
