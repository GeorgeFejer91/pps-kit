# Audiotactile Paper Metadata Audit

This folder is dedicated to metadata extraction from published audio-tactile PPS papers. It is intentionally independent from GUI/profile recreation: the goal is to inspect papers and supplements and record whether Segment 1-4 metadata can be extracted.

## Local Artifact Folders

- `artifacts/paper_metadata_audit/publication_pdfs/`: place publication PDFs here as `<record_id>.pdf`.
- `artifacts/paper_metadata_audit/supplements/<record_id>/`: place supplementary PDFs, DOCX, XLSX, ODS, ZIPs, scripts, or appendices here.
- `artifacts/paper_metadata_audit/extracted/`: parser output from OpenDataLoader PDF and fallback extractors.
- `artifacts/paper_metadata_audit/resume_bundles/`: ignored local ZIP backups for private transfer/resume only.

The `artifacts/` tree is ignored by Git. Do not commit PDFs, supplements, extracted full text, page images, or long copied passages.
Use `python -m tools.paper_metadata_parser.bundle --repo-root .` to refresh `local_artifact_inventory.json` and create/update the ignored local resume ZIP. The inventory is GitHub-safe because it stores only relative paths, sizes, hashes, and restore notes.

## Tracked Manual Reviews

- `manual_reviews/<record_id>.json`: durable critical reviews with normalized Segment 1-4 values, field statuses, confidence scores, and short source pointers.
- `manual_review_index.csv`: compact progress index for hand-reviewed records.

Manual reviews are the layer where auto-mined candidates become checked metadata. Keep them short and source-pointer-only; do not paste full methods text or copyrighted passages.

## Protocol Lineage Rule

Some papers omit low-level stimulus, trajectory, timing, or count details because they say the task was adapted from, based on, or used as an established paradigm from earlier work. In those cases, inspect the cited prior-protocol paper before marking the field `not_reported_after_review`, and record the linked source in `protocol_lineage_candidates.csv`.

## Visual Geometry Rule

Many PPS papers tuck essential parameters into apparatus figures, captions, timing schematics, or row-percentage formulas rather than methods prose. Render and inspect those pages when reviewing a paper. For every trajectory or direction field, separate the physical speaker layout from the body-relative frame: record which way the participant faced, whether the participant rotated between blocks, whether the speakers moved, and which body part anchored the tactile stimulus. If a value is estimated from a figure rather than text/caption, mark it `derived` or `inferred_low_confidence` and explain the visual approximation basis.

Every manual review must include an orientation ledger before Segment 1 trajectory fields are finalized:

- Participant frame: seated/supine/standing posture, gaze or body-facing direction when reported, whether eyes were closed/blindfolded, and whether the participant rotated between blocks.
- Room/apparatus frame: physical speaker/source positions in room or page coordinates, speaker height, near/far distances, azimuth/elevation, and whether the speaker array or participant moved.
- Body-relative mapping: how the authors label the same source as front, rear, left, right, ipsilateral, contralateral, proximal, distal, approaching, or receding relative to the stimulated body part.
- Tactile anchor: body site and side being stimulated, because hand-, trunk-, face-, neck-, and back-centered setups can invert the practical meaning of "near", "front", or "left".
- Evidence class: text-reported, caption-reported, table-reported, supplement-reported, protocol-lineage-reported, visually derived from a scaled figure, or inferred with low confidence.

Never assume that figure-left/figure-right equals participant-left/participant-right. If the paper shows a person icon, first identify which way the person is facing relative to the speakers, then map the speaker direction into the participant/body frame. If that mapping is not explicit, keep the ambiguity in the review rather than collapsing it into a generic "looming" or "frontal" label.

Treat orientation as a relation, not a label. First record the participant face/head/trunk vector, then record the speaker/source vector in the apparatus or room frame, then translate only the supported part into body-relative terms such as front, rear, left, right, approaching, receding, ipsilateral, contralateral, proximal, or distal. When a top-view schematic, side-view drawing, photograph, or screenshot lacks a visible face/gaze/body-front cue, write `participant-facing direction unclear` and keep the trajectory qualitative until text, caption, supplement, or protocol-lineage evidence resolves it.

For visual approximation, reviewers must preserve the intermediate reasoning rather than only the final label. Use this worksheet in the manual note or `evidence_note`: `raw visual clue <page/figure/panel>; participant-facing vector <reported/derived/unclear>; speaker/source vector <room/apparatus direction>; face-to-source relation <front/rear/left/right/near/far/unclear>; tactile anchor <body site/side>; body-relative translation <supported label or unclear>; approximation grade <reported/derived/inferred_low_confidence>`. This is especially important when the speaker is shown left/right on the page but the participant may be facing another direction.

## PPS Visualization Reporting Rule

Every reviewed paper must also record how PPS itself is visualized or summarized in the Results, figures, tables, and supplements. This is separate from apparatus geometry. Extract short pointers for every visualization form present: RT/facilitation by SOA or distance curves, sigmoid/logistic/psychometric fits, PPS boundary or size indices, condition/group bar/box summaries, near/far or distance-bin plots, spatial maps/heatmaps/body-boundary drawings, apparatus/trajectory schematics, neural traces/topographies/brain maps, and model-parameter or fit tables.

For each confirmed visualization, preserve the figure/table/panel pointer, visual form, x-axis and y-axis encodings, PPS metric, model function if any, boundary/index definition, condition facets, and uncertainty display such as SEM, SD, confidence interval, shaded range, or no uncertainty shown. Each confirmed visualization also needs a plotted-parameter visual verification note: render or inspect the source page and check that SOA/distance/bin values, axis units, y-axis metric, fitted parameters, PPS boundary/index values, and uncertainty encodings match the caption, methods, results text, or tables. The generated `pps_visualization_inventory.csv` is a triage ledger only; final review still requires figure/caption inspection and must not commit figure screenshots or long source text.

## Information Extraction Strategy

Use at least six semantic passes before finalizing a paper: stimulus reconstruction, visual/spatial geometry, trial sequence/intermixing, tactile timing/baseline, counts/catch trials, and PPS visualization reporting. The visual/spatial pass must explicitly answer three orientation questions: which direction the participant faced, where each speaker or virtual source sat in room coordinates, and which body-relative direction the authors intended. This prevents a lateral left-of-head array, a frontal speaker pair, and a participant-rotated four-direction block from being collapsed into the same "looming" label.

Write the visual/spatial pass as a short coordinate audit, not just a keyword hit. Minimum acceptable form: `viewpoint <top/side/front/photo/unclear>; participant faces <direction/unclear>; sources at <room/apparatus coordinates>; tactile anchor <body part/side>; body-relative mapping <front/rear/left/right/near/far/etc.>; movement implementation <physical/digital/gain/switching/unclear>; evidence <text/caption/figure/supplement/lineage>`.

When a visual clue is used, always record the face/source relation before assigning the final body-relative label. For example, `speaker at page-left` is only a raw clue; `speaker left of participant` requires evidence about the participant's facing direction; `frontal sagittal near/far line` requires evidence that the participant faced along that line. If the face/source relation is unresolved, keep `body-relative mapping unclear` even if the apparatus direction itself is visible.

When methods text is thin, search figures, captions, timing diagrams, table footnotes, percentage formulas, supplement files, publisher HTML, and cited prior-protocol papers. Record whether each value is text-reported, caption-reported, derived from reported numbers, visually approximated, or inherited only as protocol lineage. Do not upgrade a visually approximated value to `reported` unless the caption or methods prose supplies the number or coordinate frame.

Treat each paper like a parameter-recovery problem, not a text-mining problem. Search for the function a value plays in recreation even when the exact Segment field name is absent:

- Segment 1 values may be hidden in apparatus photographs, sound-generation software notes, figure legends, SPL/equalization clauses, source-code bundles, or distance-at-touch tables.
- Segment 2 values may be hidden in randomization constraints, block diagrams, "no more than N consecutive" rules, ITI/ISI clauses, and task instructions rather than stimulus paragraphs.
- Segment 3 values may be hidden in timing diagrams, trigger descriptions, D/T labels, analysis-baseline definitions, and control-condition prose.
- Segment 4 values may be hidden in design formulas, row percentages, block x condition multiplications, supplement trial tables, and exclusions/results denominators.

For every visually inferred spatial value, the audit note must state the viewpoint before the interpretation: top view, side view, front view, photograph, screenshot, or unclear. Then record the participant-facing direction relative to the source, not just a page direction. A valid visual note distinguishes `page-left speaker near hand` from `participant-left speaker near hand`; the latter is allowed only when the participant's body/facing direction is reported or unambiguous from caption/context.

Use a hidden-parameter retrieval ladder before marking a field missing:

1. Main text methods/procedure/apparatus/results tables, including abbreviations such as D1-Dn, T1-Tn, AT, A-only, T-only, near/far, IN/OUT, and pre/post.
2. Figures and captions, especially apparatus photos, timing diagrams, distance-axis labels, block-design panels, and row-percentage formulas.
3. Supplement files, data dictionaries, trial tables, scripts, appendix methods, publisher "source data", and article-export ZIPs.
4. Publisher HTML and reference/citation context, including phrases such as adapted from, following, based on, well-established, as previously described, protocol, frontal, front, sagittal, lateral, and near space.
5. Cited prior-protocol papers when the current paper delegates low-level stimulus, trajectory, timing, or repetition details to earlier work.
6. A consistency pass comparing extracted values against the task's arithmetic: path length divided by duration, SOA-to-distance mapping, repetitions x rows x blocks, baseline/catch percentages, and whether a reported speed belongs to the auditory object, a hand/body movement, or another manipulation.

For visual approximation, render pages at readable resolution and keep values conservative. Use scaled figure labels or axis ticks when available; otherwise record only qualitative geometry such as "speaker appears lateral to the left hand" or "participant-facing direction unclear". If a diagram supplies direction but not exact distance/speed/timing, the direction can be `derived` while the missing numeric field remains `not_reported_after_review` only after the supplement and protocol-lineage checks are complete.

Use this decision ladder for every figure-derived spatial value:

1. Record the page, figure, caption, and panel that produced the clue.
2. Identify the participant's posture, head/trunk facing direction, gaze/fixation instruction, blindfold/eyes-closed state, and any block-wise participant rotation.
3. Identify the room/apparatus frame: speaker/source positions, near/far labels, height, azimuth/elevation, source movement, and whether the speaker array, participant, or digital renderer changes across conditions.
4. Translate the page/apparatus frame into the participant/body frame: front, rear, left, right, ipsilateral, contralateral, approaching, receding, proximal, or distal relative to the tactile anchor.
5. Extract numbers only from printed labels, axes, tables, captions, or a scaled diagram. If the drawing is unscaled, keep the value qualitative and mark it `inferred_low_confidence`.
6. Cross-check figure-derived geometry against supplement files and protocol-lineage citations when the methods text is incomplete or inconsistent.
7. Preserve ambiguity explicitly when orientation remains unresolved: record `body-relative mapping unclear` rather than replacing it with a generic trajectory label.
8. Revisit any `frontal`, `lateral`, `ipsilateral`, or `contralateral` term in local context; it may describe anatomy, electrodes, analysis regions, or response mapping rather than auditory-source direction.

Common orientation traps to guard against:

- A participant may rotate across direction blocks while the room speakers stay fixed; in that case, the same physical speaker can become front, rear, left, or right in the body frame.
- A figure may draw the apparatus from the experimenter's viewpoint, not the participant's viewpoint.
- "Frontal" may refer to an anatomical/EEG region rather than an auditory source direction; check the local sentence context before using it as trajectory evidence.
- A reported movement speed may describe the participant's hand/arm/body, not the auditory stimulus; only assign it to `stimulus_speed` when the source trajectory or sound timing supports that mapping.
- Virtual or headphone-rendered sources need renderer-frame coordinates and HRTF/gain provenance; a speaker-style diagram alone is not enough to infer physical speaker placement.

The detailed tucked-away parameter triage matrix lives in `parameter_checklist.md`. Use it when a field is missing from obvious Methods prose: search by the role a value plays in recreation, not only by the Segment field name. For example, a sound speed may be recoverable from a distance-at-touch table plus a duration label, count totals may be hidden in a design formula, and participant-facing direction may appear only in a schematic/caption. Preserve those clues as `derived` or `inferred_low_confidence` with short evidence notes unless the text, table, caption, supplement, or cited protocol reports the value directly.

## Tracked Generated Ledgers

- `pdf_retrieval_inventory.csv`: canonical running list of which main publication PDFs are already retrieved, which are missing, DOI/DOI URL for missing records, and the local target filename.
- `protocol_lineage_candidates.csv`: cited prior-protocol papers that may contain missing stimulus, trajectory, timing, or count details for another audited paper.
- `doi_inventory.csv`: DOI/DOI URL inventory plus current PDF and supplement status for every literature record.
- `pps_visualization_inventory.csv`: one row per automated candidate for how each study visualizes PPS effects, models, boundaries, spatial maps, condition summaries, or neural traces.
- `missing_pdf_request_list.csv`: actionable download queue for missing main PDFs and supplement/methods files.
- `running_checklist.csv`: compact all-record metadata audit progress checklist.

## Current Inventory

- Literature records: 75
- PDF status counts: `{"downloaded": 26, "needs_user_download": 12, "not_applicable": 5, "open_access_unavailable": 13, "paywalled": 18}`
- Main PDFs retrieved/missing/not applicable: 26 / 43 / 5
- Supplement status counts: `{"downloaded": 10, "needs_user_download": 17, "not_applicable": 5, "not_checked": 6, "not_found": 21, "paywalled": 15}`
- Extraction status counts: `{"parsed_with_warnings": 31, "pending_pdf": 43}`
- Metadata confidence counts: `{"not_applicable": 5, "partial_extraction": 28, "pending_source": 12, "source_unavailable": 29}`
- Automated evidence status counts: `{"no_extracted_source": 41, "not_applicable": 5, "source_mined": 28}`
- Automated evidence mined field total: 477
- Supplement extracted records/files: 10 records / 13 files
- Semantic review strategy count: 6
- Semantic review pass status counts: `{"completed": 164, "completed_no_hits": 4, "not_applicable": 30, "source_unavailable": 246}`
- PPS visualization taxonomy count: 9
- PPS visualization candidate records/forms: 27 records / 173 candidates
- PPS visualization status counts: `{"no_extracted_source": 41, "no_visualization_terms_found": 1, "not_applicable": 5, "source_mined": 27}`
- PPS visualization type counts: `{"apparatus_trajectory_schematic": 27, "condition_group_bar_box_summary": 21, "model_parameter_or_fit_table": 13, "near_far_or_distance_bin_plot": 25, "neural_trace_topography_or_brain_map": 16, "pps_boundary_or_size_index": 20, "rt_by_soa_or_distance_curve": 26, "sigmoid_psychometric_fit": 14, "spatial_map_heatmap_or_body_boundary": 11}`
- Missing download/check requests: 81

## Environment Readiness

- Java available: `False`
- `opendataloader_pdf` installed: `False`
- OpenDataLoader ready: `False`
- Fallback extractors: `{"pdfinfo_available": false, "pdfplumber_installed": true, "pdftoppm_available": false, "pypdf_installed": true}`

## How To Use

1. Download each available publication PDF into `artifacts/paper_metadata_audit/publication_pdfs/<record_id>.pdf`.
2. Download supplements into `artifacts/paper_metadata_audit/supplements/<record_id>/`.
3. Run `python -m tools.paper_metadata_parser --refresh` from the repo root.
4. Review `pdf_retrieval_inventory.csv` first for the running list of retrieved/missing PDFs and missing-paper DOI URLs.
5. Review `protocol_lineage_candidates.csv` when a paper cites an adapted or established prior protocol.
6. Review `pps_visualization_inventory.csv` to see every mined candidate for how PPS is plotted, modelled, mapped, or summarized across studies.
7. Review `running_checklist.csv`, `missing_pdf_request_list.csv`, and `paper_audits/<record_id>.md`.
8. Promote critically checked Segment 1-4 values and confirmed PPS visualization notes into `manual_reviews/<record_id>.json` and update `manual_review_index.csv`.

Automated evidence-mined values are `inferred_low_confidence` candidates. Treat them as a triage map for critical review, not as final paper metadata.

Before marking any value `not_reported_after_review`, inspect the main PDF, methods/tables, supplements, at least one fallback/source route, and any cited prior protocol paper that the article says it adapted, followed, or used as an established paradigm.

Before marking trajectory/direction values as reported, inspect the rendered figure/caption evidence and verify the participant-facing direction relative to speakers, the body-relative direction being tested, and whether the trajectory is physical, digitally rendered, or inferred from gain/cross-fade timing.

Before accepting a visualization style as confirmed, inspect the actual figure/caption/table and record what is plotted, what axes and model functions are used, whether a PPS boundary or index is derived, how uncertainty is displayed, and whether the plotted parameter values were visually checked against reported text/tables.

Every manual review should preserve the orientation decision in short form, even when no final profile is created. A useful note format is: `participant faces <direction/unclear>; speakers/sources at <room/apparatus positions>; authors test <body-relative label>; tactile anchor <body site>; movement implemented by <physical source/digital renderer/speaker switching/gain envelope>; evidence <text/caption/figure/supplement/lineage>`.
