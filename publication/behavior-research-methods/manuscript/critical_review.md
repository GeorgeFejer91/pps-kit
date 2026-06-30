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

## Iteration 13: GUI Control Coverage Pass

### Main Critiques

- The manuscript now presented PPS Toolkit as a full design-run-recreation
  suite, but it still relied on the phrase `visible toolkit control` too
  broadly. A reviewer could reasonably ask whether every dashboard button was
  being treated as a literature-backed methods decision.
- The evidence matrix covered the scientific and runner decisions, but there
  was no explicit source artifact showing how ordinary UI controls such as
  tabs, camera presets, modal close buttons, folder openers, and refresh
  actions were classified.
- Without that distinction, the suite framing risked becoming less parsimonious:
  operational controls help researchers inspect, materialize, or launch the
  experiment, but only some controls alter PPS design, provenance, acquisition
  boundary, or runner handoff.

### Resolution In This Revision

- Added `gui_control_coverage.csv`, a 64-row dashboard coverage ledger. It maps
  visible Segment 0-6 and shell controls either to existing evidence-matrix rows
  or to explicit non-method categories such as navigation, documentation,
  folder inspection, artifact review, or modal workflow mechanics.
- Revised the design-decision matrix introduction so it describes
  `evidence_matrix.csv` as a literature-bearing control scaffold, and names
  `gui_control_coverage.csv` as the control-level audit behind the
  every-visible-control claim.
- Updated the manuscript README to document the new coverage file and its
  boundary: it is an interface coverage ledger, not another literature matrix.
- Removed a stale page-count-specific compile statement from the validation
  evidence table so the manuscript does not drift when small text changes alter
  pagination.

### Residual Concerns

- The coverage ledger proves source-level interface coverage, not usability.
  A separate click-through validation remains necessary for GUI behavior
  changes; this revision did not change the dashboard itself.
- Final submission still needs release metadata, author/affiliation/funding
  fields, and publication-hardware validation evidence before strong timing
  claims can be made.

## Iteration 14: Parsimony And Archive-layer Pass

### Main Critiques

- A paragraph-length audit found that the main remaining long prose paragraph
  was the archive-layer paragraph in the `Design, Run, and Recreation Pathway`
  section. It compressed design archives, profile-recreation archives,
  validation archives, participant archives, computational reproducibility, and
  the conditional suite claim into one paragraph.
- That compression weakened the BRM-style tutorial value. A reader should be
  able to see what each suite entry point produces and what claim each archive
  layer can support without unpacking a dense prose block.
- The technical-method response-classification paragraph also carried two
  ideas in one paragraph: the actual click-classification rule and the reason
  response probability matters for interpreting PPS RT curves.
- A fresh Consensus search on behavioral software tools returned the familiar
  BRM/software pattern: graphical tools should lower implementation barriers
  while keeping task logic, timing, runnable assets, and reproducibility
  visible. This supported a parsimony edit rather than a new citation-heavy
  detour.

### Resolution In This Revision

- Replaced the dense archive-layer paragraph with a short lead-in plus a new
  table, `Recommended archive layers for PPS Toolkit studies`, separating
  design, profile-recreation, validation, and participant archives.
- Shortened the suite boundary paragraph so it states one central claim:
  public and executable assets still require local validation when hardware,
  tactile actuators, HRTFs, stimuli, or populations change.
- Split the response-classification paragraph into one paragraph that states
  the current 100-1300 ms tactile-onset response rule and one paragraph that
  explains why response-probability visibility matters for PPS interpretation.
- Re-ran the paragraph-length audit. The remaining 120+ word entries are tables,
  the abstract, and two introduction-style overview paragraphs rather than
  hidden multi-idea method blocks.

### Residual Concerns

- The new archive-layer table improves manuscript readability, but final
  submission still needs actual release DOIs, exact repository commit, and a
  publication-hardware validation archive before the table can point to final
  external artifacts.
- The response-window default is clearer, but confirmatory studies still need a
  preregistered or study-specific justification for the exact response window.

## Iteration 15: Submission-readiness Audit Pass

### Main Critiques

- The manuscript had become much clearer as a full design-run-recreation suite,
  but there was no single source-level artifact mapping the original request to
  the current draft state.
- Without that ledger, a compiling manuscript could be mistaken for a
  submission-ready package even though several final artifacts are still
  missing: release DOI, exact paper commit, author/declaration metadata, and
  publication-hardware validation.
- The suite framing also needs a durable guardrail. Future edits should not
  shrink the article back to a dashboard-only paper or let profile recreation
  imply exact replication of private stimuli and apparatus details.

### Resolution In This Revision

- Added `submission_readiness_audit.md`, a requirement-by-requirement readiness
  ledger with `source-ready`, `partially supported`, `not claimed`, and
  `blocked until artifact` statuses.
- The audit explicitly states that PPS Toolkit is being presented as a suite for
  designing, recreating/scaffolding, running, validating, and reviewing
  audio-tactile PPS experiments.
- The audit also states that the current source is not final-submission ready
  until release metadata, human declarations, and final validation artifacts are
  supplied.
- Updated the manuscript README and workspace README so future agents know the
  audit is a maintenance/readiness artifact rather than manuscript prose.

### Residual Concerns

- The readiness audit improves project governance, not scientific evidence.
  Hardware timing, tactile perception, and any quantified participant hit-rate
  claims still require traceable external artifacts before the final paper can
  make those claims.

## Iteration 16: Tutorial Reader-guide Pass

### Main Critiques

- The manuscript was correctly framed as a full suite, but the tutorial value
  was partly implicit. A BRM reader could see the evidence matrix, reporting
  checklist, pathway, and validation section, but there was no compact guide
  explaining which artifact answers which practical question.
- The article should help three kinds of reader: a lab designing a new task, a
  lab recreating a published paradigm, and a reviewer checking whether the
  claims are supported by the right evidence tier.
- Another Consensus software-methods search again favored a practical article
  pattern: usable tools should explain task logic, runnable materials,
  reproducibility boundaries, and validation examples rather than functioning
  only as software advertisements.

### Resolution In This Revision

- Added a short `Tutorial Use of the Manuscript and Source Package` subsection
  after `Contribution and Journal Fit`.
- Added Table `Reader guide for using the manuscript and source package`,
  mapping five reader questions to the relevant manuscript sections and source
  artifacts: design variation, new-task construction, published-profile
  recreation, run evidence, and reporting/sharing.
- Updated `submission_readiness_audit.md` so tutorial-style reader orientation
  is now an explicit source-ready requirement.

### Residual Concerns

- The reader-guide table improves navigability, but it still depends on the
  final release archive and validation artifacts being supplied before
  submission.

## Iteration 17: Procedural-method Gap Pass

### Main Critiques

- The manuscript presented PPS Toolkit as a full design-run-recreation suite,
  but the published-profile recreation claim was still too compressed. It named
  example profiles without mapping the main methodological families to the
  procedural controls and caveats that make each family runnable or only
  scaffolded.
- The validation section described four use cases, but it did not yet provide a
  compact participant-session procedure. A reviewer could infer setup,
  calibration, execution, top-up, and post-run review from separate sections,
  but the paper needed a single operator handoff table.
- The largest procedural risk was wording: profile recreation must not sound
  like exact replication of original apparatus, copyrighted sounds, perceived
  spatial position, or participant-level effects.

### Resolution In This Revision

- Added `profile_family_examples.csv`, mapping six published-method families to
  toolkit representations, represented decisions, caveats, citation keys, and
  profile/template identifiers.
- Added a manuscript profile-family table covering canonical dynamic looming,
  baseline/expectancy correction, directional/body-frame variants,
  mobile/DynaSpace burst trains, affective/ecological sounds, and
  action/full-body/immersive variants.
- Added an `Operator Procedure and Evidence Handoff` subsection with a table
  spanning pre-run setup, output/calibration, execution, post-run review, and
  sharing. Each stage names the written evidence and the boundary of the claim.
- Updated the readiness audit and manuscript README so the new profile-family
  map is tracked as source evidence rather than manuscript-only prose.

### Residual Concerns

- The new procedural tables make the methods package more reviewable, but final
  submission still needs profile-by-profile source checks, release archive
  links, and hardware/perceptual validation artifacts before exact replication
  or timing/tactile claims are made.

## Iteration 18: Same-journal Comparator Pass

### Main Critiques

- The paper cited several behavioral software articles, but the BRM-style model
  was still implicit. A reviewer should be able to see why the draft reads as a
  methods/software article rather than as a PPS empirical-results article.
- The same-journal comparator set includes broad experiment builders,
  specialized toolboxes, hosting/sharing workflows, timing comparisons, and
  simulation/validation papers. Those genres imply different writing duties:
  explain the user workflow, show a runnable example, name validation evidence,
  and avoid overclaiming platform equivalence.
- Without a source-pointer comparator table, future revisions could add or
  remove journal-fit claims without knowing which BRM examples motivated them.

### Resolution In This Revision

- Added `brm_comparator_articles.csv`, a source-pointer table mapping BRM
  comparator clusters to style lessons for PPS Toolkit.
- Added a compact same-journal comparator table in `Contribution and Journal
  Fit`. The table ties general experiment builders, hosting/sharing workflows,
  specialized domain toolboxes, and timing/validation exemplars to the
  corresponding PPS Toolkit manuscript choices.
- Added missing bibliography entries for lab.js, OpenSesame, PsyToolkit, Open
  Lab, vexptoolbox, OpenMaze, and the browser psychophysics timing comparison.

### Residual Concerns

- The comparator pass strengthens journal fit, but the draft still needs final
  copy editing to keep the added table from making the introduction feel too
  front-loaded once figures and release links are added.

## Iteration 19: Figure and Source-material Plan Pass

### Main Critiques

- The manuscript now has strong textual and tabular scaffolds, but a BRM
  software/toolkit submission will likely need figures that show the workflow,
  controls, evidence tiers, and analysis surfaces.
- The previous draft mentioned figures only as a limitation, which left a gap:
  it did not say which figures should be generated, what artifacts should
  support them, or what each figure is allowed to prove.
- Without a source-material plan, future figure creation could accidentally use
  copyrighted paper figures, private participant records, local SOFA files, or
  screenshots whose source state cannot be reconstructed.

### Resolution In This Revision

- Added `figure_source_plan.csv`, mapping six recommended figures to manuscript
  roles, source artifacts, supported claims, and boundaries.
- Added a `Figure and Source-material Plan` subsection in the validation/use
  cases section. The table covers workflow, design matrix, auditory/stimulus
  choices, evidence tiers, tactile/operator safeguards, and exploratory
  post-run analysis.
- Updated the readiness audit and manuscript README so final figures remain
  tied to redistributable toolkit artifacts rather than copyrighted or private
  materials.

### Residual Concerns

- The plan does not generate final artwork. Before submission, the actual
  figures still need to be rendered from release-state screenshots, manifests,
  schemas, validation reports, and deidentified sample outputs, then visually
  checked for readability in the Springer layout.

## Iteration 20: Procedural Gap Register Pass

### Main Critiques

- The draft named evidence boundaries throughout the manuscript, but a reviewer
  still had to assemble the remaining procedural gaps from several places:
  listening/headphone checks, route timing, tactile mechanical delivery, spatial
  perception, rights/provenance, and analysis governance.
- Same-journal timing, psychoacoustic, tactile, and platform-validation papers
  make a repeated stylistic move: they separate tool capability from local
  route validation. The draft needed that separation in one concise table.
- Without a gap register, future revisions could close one validation layer
  while accidentally implying that all layers were closed.

### Resolution In This Revision

- Added `procedural_gap_register.csv`, a source-pointer register of five
  procedural gaps: auditory eligibility/listening checks, route-specific timing,
  tactile mechanical and perceptual delivery, spatial-audio perception/HRTF
  assumptions, and recreation/analysis governance.
- Added a `Procedural Gap Register` subsection to the validation/use-case
  section. The table names current toolkit coverage, publication-ready evidence,
  and the boundary for each procedural gap.
- Added missing BRM comparator citations for auditory synchronization,
  high-resolution timing, touchscreen/keyboard timing, web psychoacoustics,
  headphone screening, and browser/mobile tactile delivery.

### Residual Concerns

- The register is not a validation artifact. It makes the remaining procedural
  work easier to close, but final submission still needs actual screening
  scripts, hardware route diagrams, loopback reports, tactile actuator evidence,
  profile rights/source checks, and preregistered analysis choices where claims
  require them.

## Iteration 21: Paragraph Parsimony Pass

### Main Critiques

- The manuscript was well scaffolded, but several prose paragraphs still
  carried multiple jobs at once: field heterogeneity plus inferential problem,
  suite components plus contribution, GUI gates plus validation principle, or
  tactile calibration plus adaptation caveat.
- Long table rows are expected in the Springer source, but long prose
  paragraphs can make a BRM methods paper feel like a ledger rather than a
  tutorial. The user's explicit standard was one main idea per paragraph.
- The densest prose was mostly in the introduction, overview, evidence-matrix
  explanation, Segment 0/1/3 rationale, spatial-rendering caveat, evidence-tier
  description, and discussion.

### Resolution In This Revision

- Split the longest prose paragraphs into smaller units with a clearer
  sequence: field use, methodological problem, toolkit response, and evidence
  boundary.
- Preserved the same claims and citations while reducing the number of
  paragraphs that mix tool description with interpretive caveat.
- Re-ran a paragraph-density check after editing. The remaining longest entries
  are table rows; ordinary prose now sits near or below roughly 100 words per
  paragraph.

### Residual Concerns

- The abstract is still necessarily dense because it summarizes the whole
  article in the journal style. Final submission should still receive a human
  copy edit after release links, author metadata, and validation artifacts are
  finalized.

## Iteration 22: Same-journal Sensory-suite Comparator Pass

### Main Critiques

- The comparator table already anchored the draft in BRM experiment-builder and
  timing-validation conventions, but it underweighted the papers most similar
  to PPS Toolkit's claim to be a full sensory suite.
- For reviewers, the closest stylistic neighbors are not only Gorilla,
  PsychoPy2, or OpenSesame. They also include BRM papers where calibration
  screens, device-specific limits, synchronous I/O, modality-specific timing,
  response capture, and analysis handoff are part of the method.
- Without those comparators, the manuscript could sound like it was presenting a
  GUI for designing PPS experiments, rather than a design-run-validation-analysis
  workflow whose evidence layers have to travel together.

### Resolution In This Revision

- Added a `Multimodal sensory and calibration suites` row to
  `brm_comparator_articles.csv` and to the manuscript's BRM comparator table.
- Added same-journal comparator citations for browser tactile delivery,
  PsySuite, the cognitive-hearing OpenSesame extension, Titta, and Mousetrap.
- The row now states that PPS Toolkit should be read as a route-aware suite:
  dashboard controls, runner route, validation artifacts, calibration evidence,
  and analysis outputs must be reported together.

### Residual Concerns

- This improves the article-style model, but it does not close the underlying
  validation gaps. Final submission still needs route-specific hardware timing,
  tactile delivery/perceptual artifacts, and final release metadata before
  strong route or tactile claims can be made.

## Iteration 23: Dashboard Control Recheck Pass

### Main Critiques

- The manuscript claims that visible Segment 0-6 GUI decisions are represented
  in the evidence/control ledgers. That claim can drift if the dashboard changes
  while the paper is being drafted.
- The current worktree had uncommitted dashboard edits. Even if those edits were
  not part of the manuscript change set, the source-level coverage claim needed
  a fresh check against the current dashboard labels.
- The audit needed to distinguish scientific design controls from operational
  status indicators, especially because readiness badges are visible to users.

### Resolution In This Revision

- Added `dashboard_control_recheck_20260630.md`, a source-level recheck of the
  current local dashboard source against `gui_control_coverage.csv`.
- The recheck found no new literature-bearing PPS design control. The visible
  dirty-dashboard label/status change is a not-ready readiness-badge glyph and
  styling change, already covered by the left-rail readiness-badge row.
- Updated `gui_control_coverage.csv`, the manuscript README, and
  `submission_readiness_audit.md` so this point-in-time recheck is discoverable.

### Residual Concerns

- This is not screenshot-based visual validation and not user-click workflow
  validation. If dashboard controls change before submission, rerun the source
  audit and, for GUI/readiness claims, use the project-required visual and
  click-validation workflows.

## Iteration 24: Claim Boundary Audit Pass

### Main Critiques

- The manuscript has become increasingly careful, but its boundaries are spread
  across prose, tables, CSV files, and readiness notes. A reviewer or future
  editor could still accidentally strengthen a sentence beyond the evidence.
- The riskiest terms are "suite", "recreation", "validation", "HRTF", "tactile
  calibration", "adaptive threshold", and "analysis". Each is acceptable when
  tied to the proper evidence layer, and risky when promoted to a participant,
  hardware, or exact-replication claim.
- The user's requested self-review loop needs a compact artifact that states
  not only what the paper says, but what it must not say until additional
  release, hardware, profile-source, or participant artifacts exist.

### Resolution In This Revision

- Added `claim_boundary_audit.csv`, a claim-to-evidence ledger covering BRM
  article type, literature-review scope, GUI decision coverage, full-suite
  framing, profile recreation, Study 5-style example, source/loudness/spatial
  decisions, tactile calibration, adaptive threshold, randomization, native
  acquisition, exploratory analysis, figures/materials, and declarations.
- Each row records the evidence needed for a strong claim, current source
  evidence, status, safe submission phrasing, unsafe phrasing, and the next
  artifact required before stronger wording would be defensible.
- Updated the manuscript README and readiness audit so future edits treat the
  claim ledger as part of the manuscript safety scaffolding.

### Residual Concerns

- The ledger prevents overclaiming only if it is kept current. Any new empirical
  result, profile-recreation claim, hardware timing claim, or final figure must
  update the claim boundary audit and the readiness audit before submission.

## Iteration 25: Same-Journal Article Recommendation Pass

### Main Critiques

- The manuscript had a cluster-level BRM comparator table, but the user's
  practical question was article-level: which papers from the same journal are
  most similar, and what exactly should this paper borrow from them?
- Without an article-level ledger, future edits could cite large software
  papers generically while missing the more useful style lessons: calibration
  boundary language, device-specific validation, analysis handoff, and
  orchestration boundaries.

### Resolution In This Revision

- Added `brm_recommended_article_models.csv`, an article-level recommendation
  ledger for same-journal BRM comparators. It records the closest suite,
  experiment-builder, multimodal/tactile, calibration, device-evaluation,
  analysis-handoff, embodied-threat, and interoperability models.
- Updated the journal-fit prose to point readers and future drafters to this
  article-level ledger alongside the existing comparator-cluster audit.
- Updated the manuscript README and readiness audit so the recommendation
  ledger is treated as a style/drafting aid rather than a systematic corpus or
  evidence that PPS Toolkit has the same validation scope as the comparator
  tools.

### Residual Concerns

- Several recommended papers are currently source-pointer recommendations only.
  Convert them to verified BibTeX entries before citing them directly in
  manuscript prose.

## Iteration 26: Permanent Windows PDF Render Path

### Main Critiques

- The manuscript depends on the Springer Nature template and multiple
  bibliography/rerun passes. Relying only on `latexmk` is brittle on this PC
  because MiKTeX reports that it cannot find the Perl script engine.
- The README described `latexmk`, but the working local route was an informal
  manual `pdflatex`/`bibtex` sequence. That is too easy to forget and too easy
  to perform inconsistently during repeated manuscript revisions.

### Resolution In This Revision

- Added `render_pdf.ps1` as the durable Windows build path. It sets
  `TEXINPUTS` and `BSTINPUTS` to the local Springer template folders, runs
  `pdflatex`, `bibtex`, and two final `pdflatex` passes by default, checks the
  log for unresolved citations/references, and removes auxiliary build files
  unless `-KeepAux` is supplied.
- Added `render_pdf.cmd` as a stable PC/double-click wrapper for the PowerShell
  script.
- Added a manuscript-local `.gitignore` for LaTeX render outputs, including
  `main.pdf`, so local PDF review does not create accidental staged artifacts.
- Updated the manuscript README and readiness audit so future builds use the
  permanent script instead of rediscovering the manual fallback.

### Residual Concerns

- The generated `main.pdf` remains a local review artifact and should not be
  committed unless an explicit release snapshot is requested.

## Iteration 27: Verified Article-Model Bibliography Pass

### Main Critiques

- The same-journal article recommendation ledger had useful style guidance, but
  several rows were still source-pointer-only. That made the recommendations
  less useful for manuscript prose and increased the risk that future edits
  would cite article models without verified bibliography metadata.
- The BRM comparator table also underused the article-level models for adaptive
  calibration, low-cost device evaluation, analysis handoff, domain-specific
  threat tooling, and cross-platform interoperability.

### Resolution In This Revision

- Added verified BibTeX entries for adaptive Titta calibration, Tobii EyeX
  evaluation, PyTrack, VRthreat, and Psynteract using Consensus/Crossref
  matches and stable DOI metadata.
- Converted the corresponding `brm_recommended_article_models.csv` rows from
  `Consensus source pointer` to manuscript citation keys.
- Expanded the manuscript comparator table so the article models now support
  route suitability, adaptive calibration boundaries, analysis handoff, and
  external-tool/interoperability language directly in the draft.

### Residual Concerns

- These article models guide BRM style and reporting boundaries. They do not
  prove that PPS Toolkit has the same validation maturity, hardware coverage,
  user base, or empirical evidence as the comparator systems.

## Iteration 28: Output Schema and Data Dictionary Pass

### Main Critiques

- The manuscript described the runner as producing a minimal public data layer
  and a richer reconstruction layer, but it did not yet provide a source-level
  dictionary that named the files, fields, release status, and evidence role.
- This was a procedural-method gap for a BRM software paper. Reviewers need to
  know not only that artifacts exist, but which artifacts can be shared, which
  artifacts are private, and which artifacts support timing, tactile,
  reconstruction, or exploratory-analysis claims.

### Resolution In This Revision

- Added `output_schema_dictionary.csv`, an implementation-derived dictionary
  covering public `1.Data_min` CSVs, the `2.Data_max` reconstruction mirror,
  participant-trial fields, session manifests, prepared block evidence,
  verbose event logs, LSL/XDF/trigger artifacts, tactile calibration, top-up,
  adaptive-threshold artifacts, exploratory analysis outputs, and private
  demographics sidecars.
- Added a compact output schema/archive-boundary table to `main.tex` so the
  manuscript itself distinguishes public response summaries, rich
  reconstruction, prepared playback evidence, event/marker evidence, tactile
  safeguards, and exploratory review outputs.
- Updated the README, readiness audit, and claim-boundary audit so future
  revisions keep the output dictionary aligned with runner schema changes.

### Residual Concerns

- The dictionary is a source-level planning artifact. Before submission, it
  must be rechecked against the exact release runner and any archived example
  run; public release still requires deidentification, local-path review,
  rights review, and validation hashes.

## Iteration 29: Profile Recreation Claim-State Pass

### Main Critiques

- The manuscript now presents PPS Toolkit as a suite for designing, running,
  and recreating or scaffolding published PPS paradigms. That framing is
  accurate only if readers can see which specific profiles are run-ready and
  which remain blocked by missing parameters, rights, apparatus geometry, or
  unsupported toolkit structures.
- The existing profile-family table was useful, but family-level language can
  accidentally make a blocked profile sound as mature as a verified,
  materializable profile.

### Resolution In This Revision

- Added `profile_recreation_audit.csv`, a per-profile claim ledger covering all
  current preload profiles. It distinguishes unpublished local examples,
  published verified run-ready profiles, the partial-but-materializable
  Serino peri-trunk scaffold, missing-parameter scaffolds, and structural-gap
  scaffolds.
- Added a compact manuscript table summarizing these profile claim states and
  pointing readers to the CSV for the full per-profile ledger.
- Updated the README, readiness audit, and claim-boundary audit so exact
  recreation language remains conditional on final profile-specific source
  review, rights clearance, apparatus notes, and release-state materialization
  evidence.

### Residual Concerns

- The new ledger is derived from the current preload manifests and status JSON.
  It should be regenerated or manually rechecked after any profile, template,
  source-asset, or dashboard materialization change.
- A run-ready profile is still not an original-apparatus replication. Exact
  recreation requires original methods/assets or a validated and explicitly
  reported approximation.
