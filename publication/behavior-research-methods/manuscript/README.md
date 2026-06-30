# PPS Toolkit BRM Manuscript Draft

This folder contains the draft Springer Nature/Behavior Research Methods
manuscript for PPS Toolkit.

## Files

- `main.tex`: single-file Springer Nature `sn-apa` manuscript draft with the
  design-decision matrix and reporting checklist.
- `references.bib`: bibliography assembled from Consensus searches, existing
  repo paper-audit notes, and Springer/software policy pointers.
- `evidence_matrix.csv`: source-pointer design-decision matrix mapping visible
  PPS Toolkit GUI/runner controls to literature variation and caveats.
- `gui_control_coverage.csv`: dashboard control-level coverage audit that maps
  visible Segment 0-6 controls either to evidence-matrix rows or to explicit
  non-method roles such as navigation, folder inspection, documentation, or
  modal workflow mechanics.
- `dashboard_control_recheck_20260630.md`: source-level recheck against the
  current local dashboard source confirming that the observed not-ready badge
  glyph/layout change is operational UI and does not introduce a new
  literature-bearing PPS design decision.
- `brm_comparator_articles.csv`: source-pointer table of same-journal BRM
  software, toolbox, tutorial, sharing, and timing-validation papers used as
  article-style comparators.
- `profile_family_examples.csv`: source-pointer map from common published PPS
  method families to toolkit profile/scaffold representations and caveats.
- `figure_source_plan.csv`: planned figure/source-artifact map for the final
  submission, including the evidence boundary for each figure.
- `procedural_gap_register.csv`: procedural gap register listing the screening,
  timing, tactile-delivery, spatial-perception, rights, and analysis-governance
  evidence that should be closed or caveated before final submission.
- `validation_evidence.csv`: committed source-pointer summary of validation
  evidence used in the draft; generated raw reports remain under ignored
  validation folders.
- `submission_readiness_audit.md`: source-level checklist mapping the requested
  BRM methods/software-paper goals to the current draft, including explicit
  source-ready, partial, not-claimed, and blocked-until-artifact statuses.
- `critical_review.md`: self-review audit recording critique points and
  revision decisions for the manuscript draft.
- `latexmkrc`: local build configuration that points LaTeX/BibTeX at the
  preserved Springer Nature template under
  `../springer-nature-latex-template/sn-article-template/`.

## Build

From this folder:

```powershell
latexmk -pdf main.tex
```

Do not commit generated LaTeX build artifacts or compiled PDFs unless a release
workflow explicitly asks for an archived submission snapshot.

## Draft Boundaries

- The draft is a methods/software manuscript, not a formal meta-analysis.
- The evidence matrix is a structured literature audit scaffold, not a PRISMA
  extraction log.
- `gui_control_coverage.csv` is an interface coverage ledger, not a second
  literature matrix. It exists to show which visible controls are scientific
  design decisions and which are ordinary suite/navigation mechanics.
- `dashboard_control_recheck_20260630.md` is a point-in-time source audit of
  the local dashboard worktree. It is not GUI usability validation and should be
  rerun if dashboard controls change before submission.
- `brm_comparator_articles.csv` is a style and journal-fit audit, not a claim
  that PPS Toolkit has the same maturity, user base, or validation scope as the
  comparator tools.
- `profile_family_examples.csv` is a profile-family map, not a claim that every
  listed paradigm has been exactly replicated with original apparatus and
  stimuli.
- `figure_source_plan.csv` is a publication-preparation scaffold, not generated
  figure evidence. Final figures must be generated from redistributable toolkit
  artifacts and should cite or archive the exact source files used.
- `procedural_gap_register.csv` is a reviewer-facing readiness scaffold, not a
  claim that those procedural validations have already been completed.
- `submission_readiness_audit.md` is a maintenance/readiness ledger, not
  manuscript prose. It should remain honest about the distinction between a
  source-ready draft and a final submission package.
- The tactile hit-rate decline noted during pilot use is treated only as
  anecdotal design motivation until traceable runner artifacts are attached.
- No copyrighted paper PDFs, participant outputs, local SOFA files, or private
  generated stimuli belong in this folder.
