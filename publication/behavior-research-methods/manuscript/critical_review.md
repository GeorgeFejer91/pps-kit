# Critical Review Audit

This note records the self-review pass requested for the Behavior Research
Methods manuscript draft. It is a working audit, not manuscript text.

## Iteration 1: Current Draft Read

### Main Critiques

- The first draft had the right thesis, but it relied too heavily on
  `evidence_matrix.csv` to carry the design-decision argument. A BRM reader
  should not have to open the CSV to understand why each GUI layer exists.
- The opening framed the problem well, but it did not explicitly enough state
  the paper's fit with BRM-style software/methods articles: usability,
  instrumentation, timing validation, reusable materials, and practical data
  analysis.
- Paragraphs were mostly coherent, but several sections compressed multiple
  ideas into one paragraph: field heterogeneity, toolkit provenance, and
  validation boundaries needed clearer separation.
- The manuscript was constructive about methodological problems, but it needed
  a stronger statement that heterogeneity is not a defect to erase. The field's
  diversity is the reason provenance has to be explicit.
- The tactile-threshold section had the correct caution around the anecdotal
  hit-rate observation, but the reader needed a clearer distinction between
  calibration, run-local safeguards, and scientific claims about habituation.
- The HRTF section needed a sharper caveat: near-field HRTFs and 3DTI-compatible
  rendering are important provenance layers, but generic/non-individualized
  rendering does not establish perceived distance or externalization.
- The validation section was useful but still sounded like a future plan. It
  should be tied more directly to the BRM expectation that a software paper
  documents what the tool does, how it can be reused, and where its evidence
  boundaries are.

### Resolution In This Revision

- Added a `Contribution and Journal Fit` section that explicitly positions the
  manuscript as a BRM-style methods/software contribution.
- Added reader-facing prose after the condensed evidence matrix, organized by
  GUI/running decision clusters rather than by isolated features.
- Expanded the rationale for Segment 0-6 decisions: profile provenance,
  auditory source modes, trajectory/HRTF metadata, within-trial sequencing,
  baseline/catch logic, repetition/randomization, participant package
  preparation, and native runner handoff.
- Added clearer language that tactile calibration and adaptive nudging are
  operational safeguards and evidence artifacts, not validated corrections.
- Added citations and bibliography entries for broader behavioral experiment
  software/timing validation context and near-field HRTF caution.

## Iteration 2: Residual Concerns After Revision

- The bibliography still includes several placeholder author lists using
  `and others`. This compiles, but final submission should replace placeholder
  metadata with complete BibTeX from publisher pages, Crossref, or the final
  citation manager export.
- The manuscript still does not include a real validation figure, screenshot, or
  table of artifact hashes. That is acceptable for this drafting pass, but final
  submission should add at least one reproducible run-through table.
- The draft still cannot claim quantitative tactile miss-rate decline. It
  correctly labels that point as anecdotal, but final submission should either
  attach traceable artifacts or remove the observation entirely.
- The manuscript is now more complete but still intentionally source-heavy. A
  later copyedit can shorten repeated caveats once the validation evidence is
  fixed.
