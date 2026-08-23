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
- `claim_boundary_audit.csv`: claim-to-evidence ledger that separates safe
  manuscript phrasing from overclaims and lists the artifact needed before each
  stronger claim could be made.
- `brm_comparator_articles.csv`: source-pointer table of same-journal BRM
  software, toolbox, tutorial, sharing, and timing-validation papers used as
  article-style comparators.
- `brm_recommended_article_models.csv`: article-level recommendation ledger
  mapping the closest same-journal BRM comparators to their PPS Toolkit style
  transfer, limits, and Consensus source pointers.
- `profile_family_examples.csv`: source-pointer map from common published PPS
  method families to toolkit profile/scaffold representations and caveats.
- `profile_recreation_audit.csv`: per-profile claim ledger for current preload
  profiles, separating published run-ready profiles, partial materializable
  scaffolds, unpublished local examples, missing-parameter blockers, and
  toolkit structural gaps.
- `figure_source_plan.csv`: planned figure/source-artifact map for the final
  submission, including the generated PNG path and evidence boundary for each
  figure.
- `figures/generate_figures.py`: deterministic Pillow generator for
  source-owned schematic manuscript figures.
- `figures/figure*.png`: redistributable schematic figures generated from the
  tracked script. They summarize toolkit workflow, evidence ledgers, stimulus
  alternatives, evidence tiers, tactile safeguards, and exploratory analysis
  surfaces without using private participant data or copyrighted source-paper
  figures.
- `procedural_gap_register.csv`: procedural gap register listing the screening,
  timing, tactile-delivery, spatial-perception, rights, and analysis-governance
  evidence that should be closed or caveated before final submission.
- `pre_run_qualification_checklist.csv`: pre-run qualification checklist that
  turns the procedural gaps into participant/session readiness records for
  listening eligibility, spatial perception, route timing, tactile readiness,
  task/response governance, and profile rights/provenance.
- `output_schema_dictionary.csv`: source-level dictionary for the runner's
  public `1.Data_min` exports, richer `2.Data_max` reconstruction layer,
  event/marker/timing evidence, tactile calibration/top-up/adaptive-threshold
  artifacts, exploratory analysis outputs, and private metadata sidecars.
- `validation_evidence.csv`: committed source-pointer summary of validation
  evidence used in the draft; generated raw reports remain under ignored
  validation folders.
- `submission_readiness_audit.md`: source-level checklist mapping the requested
  BRM methods/software-paper goals to the current draft, including explicit
  source-ready, partial, not-claimed, and blocked-until-artifact statuses.
- `critical_review.md`: self-review audit recording critique points and
  revision decisions for the manuscript draft.
- `render_pdf.ps1`: durable Windows build script for this PC. It sets the
  Springer template paths, runs the manual `pdflatex`/`bibtex`/rerun sequence,
  validates the log, and leaves `main.pdf` for local review.
- `render_pdf.cmd`: double-clickable wrapper around `render_pdf.ps1`.
- `../../../For-AI/research/publication/Render_BRM_Manuscript_PDF.ps1` and
  `../../../For-AI/research/publication/Render_BRM_Manuscript_PDF.cmd`: permanent repo-root PC
  entry points that delegate to `render_pdf.ps1` without requiring the user to
  `cd` into this manuscript folder.
- `.gitignore`: ignores local LaTeX render outputs, including `main.pdf`, so
  repeated PC renders do not pollute the tracked manuscript source set.
- `latexmkrc`: local build configuration that points LaTeX/BibTeX at the
  preserved Springer Nature template under
  `../springer-nature-latex-template/sn-article-template/`.

## Build

From this folder:

```powershell
.\render_pdf.ps1
```

From the repository root, use the permanent PC path:

```powershell
.\For-AI\research\publication\Render_BRM_Manuscript_PDF.ps1
```

The script sets the Springer template path, runs `pdflatex`/`bibtex`/reruns on
Windows, repeats extra `pdflatex` passes when LaTeX says labels or citations
changed, verifies that no unresolved references remain, and removes auxiliary
build files by default while leaving `main.pdf` for local review. Use
`.\render_pdf.cmd` from this folder or
`.\For-AI\research\publication\Render_BRM_Manuscript_PDF.cmd` from the repository root for a stable
double-clickable PC entry point, `-OpenPdf` to open the rendered PDF, or
`-KeepAux` when debugging LaTeX. Use `-MaxPdflatexReruns <n>` only when a large
table/refactor needs more than the default five final passes.

`latexmk -pdf main.tex` remains supported when MiKTeX has a Perl engine
installed; on this PC, `render_pdf.ps1` is the durable build path because
MiKTeX's `latexmk.exe` currently cannot find Perl.

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
- `claim_boundary_audit.csv` is a self-review and submission-safety ledger. It
  does not add new empirical evidence; it records which claims are source-ready,
  partially supported, blocked, or unsafe until additional artifacts exist.
- `brm_comparator_articles.csv` is a style and journal-fit audit, not a claim
  that PPS Toolkit has the same maturity, user base, or validation scope as the
  comparator tools.
- `brm_recommended_article_models.csv` preserves article-level reading/style
  recommendations for drafting. It is not a systematic corpus, and source
  pointer rows added in future passes should be converted to verified
  bibliography entries before their papers are cited directly in manuscript
  prose.
- `profile_family_examples.csv` is a profile-family map, not a claim that every
  listed paradigm has been exactly replicated with original apparatus and
  stimuli.
- `profile_recreation_audit.csv` is a current-source claim ledger. It records
  what each preload profile may safely claim, but it is not a rights clearance,
  apparatus reconstruction, perceptual validation, or proof of original-study
  effects.
- `figure_source_plan.csv` records the planned figure set and the current
  generated PNG path for each source-owned schematic. The schematic figures
  support workflow and evidence-boundary explanation only; they are not
  screenshots of validated runtime behavior, hardware timing evidence, tactile
  mechanical evidence, or participant-effect evidence.
- `procedural_gap_register.csv` is a reviewer-facing readiness scaffold, not a
  claim that those procedural validations have already been completed.
- `pre_run_qualification_checklist.csv` is a reporting checklist for labs and
  release examples. It does not certify that listening, spatial, timing,
  tactile, rights, or analysis qualification artifacts have already been
  supplied.
- `output_schema_dictionary.csv` documents current output artifacts for
  publication planning. It is not a guarantee that every artifact is public:
  release status still depends on deidentification, rights, path/privacy review,
  and the evidence tier each artifact supports.
- `submission_readiness_audit.md` is a maintenance/readiness ledger, not
  manuscript prose. It should remain honest about the distinction between a
  source-ready draft and a final submission package.
- The tactile hit-rate decline noted during pilot use is treated only as
  anecdotal design motivation until traceable runner artifacts are attached.
- No copyrighted paper PDFs, participant outputs, local SOFA files, or private
  generated stimuli belong in this folder.
