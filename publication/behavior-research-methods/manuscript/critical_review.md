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

## Iteration 3: Parsimony, Reporting, And Remaining Evidence Gaps

### Main Critiques

- The revised text made the design logic clearer, but it still lacked a compact
  BRM-style reporting checklist that tells readers exactly what to report from
  the toolkit artifacts.
- The randomization discussion was too positive. It said block schedules are
  inspectable, but it did not warn that constrained randomization can solve one
  bias while introducing another sequential structure.
- The tactile adaptation language needed one more precision layer. The draft
  correctly avoided a quantitative hit-rate claim, but adaptation/recovery
  should be framed as stimulus-history-dependent tactile physiology and
  psychophysics, not as a simple one-way habituation story.
- The Ferri affective-sound citation metadata was still rough and should not
  remain as `Unknown Journal` in a paper-style bibliography.

### Resolution In This Revision

- Added a `Reporting Checklist` section with a compact table separating
  profile, source, rendering, sequence, baseline, randomization, runner,
  validation, and analysis reporting duties.
- Added constrained-randomization citations and language that randomized block
  schedules should be accepted as inspectable artifacts, not trusted because
  they are random.
- Added tactile adaptation/recovery support and clarified that the runner's
  adaptive threshold rule remains an operator safeguard.
- Corrected the Ferri affective-sound bibliography record and aligned the CSV
  evidence matrix with the new randomization and tactile citations.
- Reworded the validation section as four reproducible protocols rather than a
  loose future to-do list, while keeping clear that publication-hardware
  results still require attached artifacts.

### Residual Concerns

- The paper now has a stronger reporting apparatus, but final submission still
  needs at least one real, citable validation artifact table or figure generated
  from a redistributable run.
- Several bibliography records still use abbreviated author lists. That is
  acceptable for drafting but not for final journal submission.

## Iteration 4: Validation Evidence Snapshot

### Main Critiques

- The validation section was clearer after Iteration 3, but still did not give
  the reader a concrete current validation result. It specified what should be
  validated, while BRM readers will expect at least one reproducible tool-output
  snapshot.
- The manuscript must not compensate for this by overstating validation. A
  profile-materialization script is useful evidence for the design workflow, but
  it is not physical timing, tactile mechanics, or perceptual validation.

### Resolution In This Revision

- Ran Protocol 12 with:
  `python validation_protocols/scripts/run_profile_recreation_interface_matrix.py --output-dir artifacts/validation_runs/brm_profile_recreation_20260630`.
- Added `validation_evidence.csv` as a committed source-pointer summary rather
  than committing raw generated reports.
- Added a manuscript validation table reporting the fresh Protocol 12 result:
  30/30 required criteria passed, seven ready published profiles materialized
  through Segment 6, and two blocked samples were blocked as expected.
- Kept the validation boundary explicit: this is software/profile
  materialization evidence, not physical timing, Woojer mechanical onset,
  perceptual tactile validity, individualized spatial perception, or exact
  reuse of private original-author stimuli.

### Residual Concerns

- The validation section now has one concrete current evidence table. Final
  journal submission should still add at least one hardware/output validation
  table or figure if the paper is going to claim timing performance on a
  specific lab setup.

## Iteration 5: Bibliography Metadata Pass

### Main Critiques

- The paper was improving structurally, but the reference list still looked
  draft-like because many cited records used `and others`, incomplete
  volume/page fields, or source-pointer placeholders.
- Two profile-recreation references used `Source to be verified`, which is not
  acceptable in a journal manuscript even if the entries mainly support the
  evidence matrix.

### Resolution In This Revision

- Replaced placeholder author lists in the cited reference set with verified
  author lists where Crossref/title metadata matched clearly.
- Added DOI, volume, issue, page, or article-number metadata for the main PPS,
  tactile, software-methods, randomization, HRTF/rendering, and validation
  references where available.
- Corrected the Amiel front/rear Cortex record to its Crossref issue metadata
  (`year = 2026`, volume 194, pages 220--238) while retaining the existing
  citation key for source compatibility.
- Replaced the two `Source to be verified` records with publisher-style entries
  for the Canzoneri tool-use paper and the Serino body/full-body PPS paper.

### Residual Concerns

- Author email, affiliation, funding, competing-interest text, release DOI, and
  ethics wording still require human/project owner confirmation before
  submission.
- Some older or standards-style records still have sparse metadata, but no
  placeholder author or `Source to be verified` strings remain in the BibTeX.
