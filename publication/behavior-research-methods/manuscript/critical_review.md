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

## Iteration 6: Near-field Rendering Caveat Pass

### Main Critiques

- The manuscript correctly said that HRTF/SOFA/3DTI metadata are provenance
  rather than proof of perceived distance, but the caveat was still too general
  for a PPS methods paper. Readers could infer that a near-field renderer solves
  the perceptual-distance problem as long as the renderer is open source.
- The evidence matrix's spatial-rendering row cited renderer and dataset
  sources, but it did not yet cite near-field perceptual studies showing why
  rendered nearby sources need separate validation.
- The validation table still reported the older 20-page compile result even
  though the near-field reference pass now compiles to a 22-page PDF.

### Resolution In This Revision

- Added near-field rendering/perception citations for real-versus-virtual
  nearby sources, distance-variation filtering, and nearby-source filter models
  (`Parseihian2014`, `Kan2009`, `Spagnol2017`).
- Revised the design-decision and technical-method HRTF paragraphs so the
  reader sees exactly why PPS Toolkit records renderer metadata without
  claiming individualized localization, externalization, front/back accuracy, or
  absolute perceived distance.
- Updated the evidence matrix's spatial-rendering row to include the new
  validation citations and a stronger caveat.
- Updated the validation table's compile summary from 20 to 22 pages so it
  matches the current successful Springer build.

### Residual Concerns

- This pass improves the argument but does not add new physical validation.
  Before submission, any claim about timing performance on a specific lab setup
  still needs publication-hardware evidence and artifact hashes.
- The draft is now less likely to overclaim spatial audio, but a final paper
  that uses a specific SOFA/HRIR file should still name the exact file, version,
  license, renderer command/path, trajectory sample table, and any perceptual
  localization or externalization check that was actually run.

## Iteration 7: Loudness Contract and Gain-law Pass

### Main Critiques

- The manuscript acknowledged trajectory, HRTF, tactile threshold, and output
  levels, but it did not yet make the Segment 1 `Loudness Contract` a distinct
  GUI design decision.
- This was a substantive gap because auditory distance and looming perception
  can be driven by level, gain envelopes, source spectrum, reverberation, and
  normalization choices. A PPS methods paper should not imply that a reported
  start/end distance is enough if the level law is hidden.
- The current toolkit default uses an estimated Komplete Audio 6 MK2 / HD 560S
  playback-chain policy. The paper needed clearer language that this is a
  convenience profile, not publication-grade participant-ear SPL.

### Resolution In This Revision

- Added a loudness/gain-law row to the condensed manuscript table and the full
  `evidence_matrix.csv`.
- Added auditory-distance and level-normalization citations
  (`Zahorik2002`, `Kolarik2015`, `Arend2021Level`) and connected them to the
  existing near-field citation `Spagnol2017`.
- Revised the abstract, introduction, Segment 1 overview, design-decision prose,
  reporting checklist, and technical method to name loudness policy as
  first-class provenance.
- Added a new `Auditory Level and Loudness Policy` technical-method subsection
  that separates estimated hardware SPL, measured acoustic calibration, digital
  output evidence, and physical participant-ear SPL.

### Residual Concerns

- The manuscript now reports the intended loudness contract, but final
  participant-level SPL claims still require direct acoustic measurement on the
  publication hardware route.
- The current paper should avoid saying the default estimated Komplete/HD 560S
  profile is calibrated. It is a reporting scaffold until a measured
  `loudness_profile.json` or equivalent artifact exists.

## Iteration 8: BRM Open-Practices and Dashboard-Boundary Pass

### Main Critiques

- The draft had Code/Data/Materials declarations, but it did not yet include a
  distinct Open Practices Statement immediately before the references, which is
  expected in the current Behavior Research Methods submission workflow.
- The evidence matrix covered Segment 0 profiles and Segment 6 runner handoff,
  but it did not explicitly name the dashboard's View/Edit/read-only/hosted
  boundary as a GUI design decision.
- That omission matters because the public dashboard can inspect and download
  source-pointer artifacts, while local mutation and participant acquisition
  require the local companion and native runner. Without that distinction, a
  reader could mistake hosted preview parity for timing or tactile evidence.

### Resolution In This Revision

- Added a manuscript paragraph under `Profiles and Project Registry` explaining
  that bundled profiles open in view mode, editable copies are local projects,
  hosted/static pages are previews, and timing-sensitive acquisition belongs to
  the native runner.
- Added a condensed-table row and a full `evidence_matrix.csv` row for
  `Dashboard mode: view, edit, hosted preview, and local acquisition boundary`.
- Split the condensed design-decision matrix into design/stimulus and
  runner/analysis tables so the new row remains readable without an oversized
  LaTeX float.
- Added a `Dashboard state and execution boundary` row to the reporting
  checklist so future PPS Toolkit studies report whether a claim comes from
  preview, editable design artifacts, or native acquisition.
- Added an `Open Practices Statement` before the bibliography. It states that
  the current draft reports software rather than new participant data, lists the
  source artifacts intended for release, and says future participant or
  hardware-validation claims need archived redistributable artifacts, hashes,
  analysis scripts, and deidentified data.

### Residual Concerns

- The Open Practices Statement still needs final release metadata: repository
  URL, release tag, archived DOI, exact commit, and any final validation archive
  DOI.
- The dashboard-boundary language is now clearer, but it does not replace
  publication-hardware timing, acoustic, tactile, or participant validation.

## Iteration 9: Response-Window and Classification Pass

### Main Critiques

- The manuscript named response rules in the abstract and reporting checklist,
  and the evidence matrix contained an `Instant analysis: response layer` row,
  but the runner's response-classification policy was not yet described as a
  first-class methods decision.
- That omission mattered because PPS RT evidence depends on how participant
  clicks are assigned to tactile onsets, how anticipations and late clicks are
  handled, how catch false alarms are separated from correct no-responses, and
  how missed trials become eligible for top-up. Without those rules, another
  lab could reproduce the stimuli while silently changing the behavioral
  estimand.
- A fresh Consensus search for audio-tactile PPS response-window/catch/false
  alarm terms returned the same core methodological anchors already in the
  draft: Canzoneri-style tactile RT plus catch logic, Holmes et al.'s response
  probability critique, and Roussel et al.'s smartphone RT-validation boundary.

### Resolution In This Revision

- Added a runner-table row for `Response rule and classification`.
- Added a full `evidence_matrix.csv` row for `Focus Mode: response window and
  classification`, bringing the matrix to 43 source-pointer rows.
- Added a technical-method paragraph stating the current Focus Mode rule:
  participant clicks are credited only from 100 to 1300 ms after tactile onset;
  earlier and later clicks remain logged but are not valid tactile responses;
  the next trial start does not shorten an open tactile-response deadline; catch
  trials separate false alarms from correct no-responses; and top-up preserves
  selected click identifiers.
- Added a reporting-checklist row requiring future papers to report response
  device, tactile-onset anchor, valid RT window, anticipation/late-click rule,
  catch false-alarm policy, miss/top-up policy, and selected click IDs.
- Recompiled the Springer `sn-apa` manuscript to a 25-page PDF. The final log
  scan found no unresolved citations/references, rerun warnings, float-too-large
  warnings, or overfull boxes; generated LaTeX artifacts and the PDF were
  removed afterward.

### Residual Concerns

- The 100-1300 ms window is a toolkit default and should be justified or
  preregistered for confirmatory participant studies.
- Response classification improves auditability, but it does not validate
  tactile perception, hardware timing, or the presence of a PPS effect.

## Iteration 10: Design-Run-Recreation Suite Pass

### Main Critiques

- The manuscript was strong on design rationale and reporting checklists, but
  the reader-facing suite path was still distributed across the overview,
  reporting checklist, validation use cases, and declarations.
- That made the draft slightly less BRM-like than it should be. A software or
  methods article should tell a reader how to design new experiments, recreate
  published paradigms, run accepted designs, validate outputs, and archive the
  tool's outputs, not only why the tool was designed that way.
- User feedback clarified that the manuscript should present PPS Toolkit as a
  full suite for designing, running, and replicating or recreating other
  experiments, not merely as a reusable design artifact.
- A fresh Consensus search on BRM software tools and reproducibility reinforced
  this standard: reusable behavioral tools should reduce programming barriers
  while preserving timing/task logic and making public assets executable rather
  than merely available.

### Resolution In This Revision

- Revised the abstract, introduction, contribution framing, pathway section, and
  conclusion so they describe PPS Toolkit as a design-run-recreation suite.
- Replaced the narrower `Reader Reuse Pathway` with `Design, Run, and
  Recreation Pathway`. The section now gives three entry points: new-design,
  published-profile recreation, and native acquisition.
- Expanded the archive-layer language to distinguish design archives,
  profile-recreation archives, validation archives, and deidentified participant
  archives. It states that new hardware routes, tactile actuators, HRTFs,
  original-stimulus substitutions, and participant populations still require
  local validation.
- Recompiled the Springer `sn-apa` manuscript to a 25-page PDF. The final log
  scan found no unresolved citations/references, rerun warnings, float-too-large
  warnings, or overfull boxes; generated LaTeX artifacts and the PDF were
  removed afterward.

### Residual Concerns

- The manuscript still needs final release metadata and at least one
  publication-hardware validation archive before submission.
- The design-run-recreation pathway is a manuscript-level guide; the final
  public repository should also expose the same path in human-facing
  documentation.

## Iteration 11: GUI Gate And Artifact Boundary Pass

### Main Critiques

- A fresh GUI-label audit found that the manuscript described segment hashes and
  artifact layers, but the evidence matrix did not name the visible
  `Apply Profile/Create Project Folder`, `Bake`, `Accept Blocks`, `Prepare
  Output Folder`, and `Save Design and Start Experiment Runner` controls as
  their own methodological boundary.
- That omission mattered because the user's core framing is a full suite for
  designing, running, and recreating experiments. The bake/apply/prepare gates
  are what turn an inspectable design into executable source WAVs, sequence
  manifests, baseline/catch assets, repetition pools, accepted block schedules,
  participant-order plans, and runner packages.
- A Consensus search for BRM-style behavioral software reproducibility and
  experiment builders reinforced the point: reusable tools should lower
  programming barriers while preserving timing/task logic, self-documenting
  task definitions, operational research assets, and pre-data validation.

### Resolution In This Revision

- Added a full `evidence_matrix.csv` row for `Dashboard workflow: apply, bake,
  accept, and prepare gates`, bringing the matrix to 44 source-pointer rows.
- Added a condensed matrix row for `Artifact materialization gates`.
- Added a PPS Toolkit overview paragraph explaining that `Apply`, `Bake`,
  `Accept`, `Prepare`, and `Start Experiment Runner` actions are methods gates:
  they materialize durable artifacts and mark downstream products stale after
  upstream changes.
- Added a reporting-checklist row requiring manuscripts or shared profiles to
  report applied profile/project id, Segment 1-6 bake/prepare actions, consumed
  upstream hashes, written manifests, accepted block state, stale warnings, and
  runner handoff package id.
- Recompiled the Springer `sn-apa` manuscript to a 27-page PDF with no
  unresolved citations/references, rerun warnings, float-too-large warnings, or
  overfull boxes in the final log scan; generated LaTeX artifacts and the PDF
  were removed afterward.

### Residual Concerns

- Gate completion validates artifact consistency and provenance only. It does
  not validate hardware timing, tactile mechanical onset, acoustic output, or
  the theoretical adequacy of the selected PPS design.

## Iteration 12: BRM Title And Entry-point Parsimony Pass

### Main Critiques

- The manuscript had been reframed as a full design-run-recreation suite, but
  the title still called PPS Toolkit a `design and validation workflow`. That
  under-described the runner and published-profile recreation components.
- The `Design, Run, and Recreation Pathway` section had the right content but
  compressed three entry points, runner responsibilities, archive layers, and
  evidence limits into two long paragraphs. That was less parsimonious than a
  BRM methods/tutorial reader needs.
- A narrow Consensus search on behavioral software papers again emphasized the
  common BRM/software-article pattern: name the usable tool, describe practical
  entry points, keep task logic inspectable, and state validation boundaries.
  The official BRM scope pages also reinforced that the article should read as
  practical reusable methodology rather than a theory-only review.

### Resolution In This Revision

- Changed the title to `PPS Toolkit: A suite for designing, running, and
  recreating audio-tactile peripersonal-space experiments`.
- Replaced the dense entry-point paragraph with Table `Three practical entry
  points through PPS Toolkit`, separating new-study design, published-profile
  recreation, and native acquisition.
- Tightened the archive-layer paragraph so each sentence has one main job:
  design archive, profile-recreation archive, validation archive, participant
  archive, and conditional suite claim.
- Recompiled the Springer `sn-apa` manuscript to a 27-page PDF with no
  unresolved citations/references, rerun warnings, float-too-large warnings, or
  overfull boxes in the final log scan; generated LaTeX artifacts and the PDF
  were removed afterward.

### Residual Concerns

- The practical pathway is clearer, but the final submission still needs final
  release metadata and a publication-hardware validation archive before it can
  make strong claims about timing on a specific lab setup.
