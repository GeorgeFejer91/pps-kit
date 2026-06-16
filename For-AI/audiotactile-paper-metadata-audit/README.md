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

## Information Extraction Strategy

Use at least five semantic passes before finalizing a paper: stimulus reconstruction, visual/spatial geometry, trial sequence/intermixing, tactile timing/baseline, and counts/catch trials. The visual/spatial pass must explicitly answer three orientation questions: which direction the participant faced, where each speaker or virtual source sat in room coordinates, and which body-relative direction the authors intended. This prevents a lateral left-of-head array, a frontal speaker pair, and a participant-rotated four-direction block from being collapsed into the same "looming" label.

When methods text is thin, search figures, captions, timing diagrams, table footnotes, percentage formulas, supplement files, publisher HTML, and cited prior-protocol papers. Record whether each value is text-reported, caption-reported, derived from reported numbers, visually approximated, or inherited only as protocol lineage. Do not upgrade a visually approximated value to `reported` unless the caption or methods prose supplies the number or coordinate frame.

Use a hidden-parameter retrieval ladder before marking a field missing:

1. Main text methods/procedure/apparatus/results tables, including abbreviations such as D1-Dn, T1-Tn, AT, A-only, T-only, near/far, IN/OUT, and pre/post.
2. Figures and captions, especially apparatus photos, timing diagrams, distance-axis labels, block-design panels, and row-percentage formulas.
3. Supplement files, data dictionaries, trial tables, scripts, appendix methods, publisher "source data", and article-export ZIPs.
4. Publisher HTML and reference/citation context, including phrases such as adapted from, following, based on, well-established, as previously described, protocol, frontal, front, sagittal, lateral, and near space.
5. Cited prior-protocol papers when the current paper delegates low-level stimulus, trajectory, timing, or repetition details to earlier work.

For visual approximation, render pages at readable resolution and keep values conservative. Use scaled figure labels or axis ticks when available; otherwise record only qualitative geometry such as "speaker appears lateral to the left hand" or "participant-facing direction unclear". If a diagram supplies direction but not exact distance/speed/timing, the direction can be `derived` while the missing numeric field remains `not_reported_after_review` only after the supplement and protocol-lineage checks are complete.

Use this decision ladder for every figure-derived spatial value:

1. Record the page, figure, caption, and panel that produced the clue.
2. Identify the participant's posture, head/trunk facing direction, gaze/fixation instruction, blindfold/eyes-closed state, and any block-wise participant rotation.
3. Identify the room/apparatus frame: speaker/source positions, near/far labels, height, azimuth/elevation, source movement, and whether the speaker array, participant, or digital renderer changes across conditions.
4. Translate the page/apparatus frame into the participant/body frame: front, rear, left, right, ipsilateral, contralateral, approaching, receding, proximal, or distal relative to the tactile anchor.
5. Extract numbers only from printed labels, axes, tables, captions, or a scaled diagram. If the drawing is unscaled, keep the value qualitative and mark it `inferred_low_confidence`.
6. Cross-check figure-derived geometry against supplement files and protocol-lineage citations when the methods text is incomplete or inconsistent.

## Tracked Generated Ledgers

- `pdf_retrieval_inventory.csv`: canonical running list of which main publication PDFs are already retrieved, which are missing, DOI/DOI URL for missing records, and the local target filename.
- `protocol_lineage_candidates.csv`: cited prior-protocol papers that may contain missing stimulus, trajectory, timing, or count details for another audited paper.
- `doi_inventory.csv`: DOI/DOI URL inventory plus current PDF and supplement status for every literature record.
- `missing_pdf_request_list.csv`: actionable download queue for missing main PDFs and supplement/methods files.
- `running_checklist.csv`: compact all-record metadata audit progress checklist.

## Current Inventory

- Literature records: 74
- PDF status counts: `{"downloaded": 36, "needs_user_download": 8, "not_applicable": 5, "open_access_unavailable": 12, "paywalled": 13}`
- Main PDFs retrieved/missing/not applicable: 36 / 33 / 5
- Supplement status counts: `{"downloaded": 12, "needs_user_download": 16, "not_applicable": 5, "not_checked": 6, "not_found": 17, "paywalled": 18}`
- Extraction status counts: `{"parsed": 36, "parsed_with_warnings": 5, "pending_pdf": 33}`
- Metadata confidence counts: `{"not_applicable": 5, "partial_extraction": 38, "pending_source": 8, "source_unavailable": 23}`
- Automated evidence status counts: `{"no_extracted_source": 31, "not_applicable": 5, "source_mined": 38}`
- Automated evidence mined field total: 652
- Supplement extracted records/files: 12 records / 16 files
- Semantic review strategy count: 5
- Semantic review pass status counts: `{"completed": 185, "completed_no_hits": 5, "not_applicable": 25, "source_unavailable": 155}`
- Missing download/check requests: 73

## Environment Readiness

- Java available: `True`
- `opendataloader_pdf` installed: `True`
- OpenDataLoader ready: `True`
- Fallback extractors: `{"pdfinfo_available": true, "pdfplumber_installed": true, "pdftoppm_available": true, "pypdf_installed": true}`

## How To Use

1. Download each available publication PDF into `artifacts/paper_metadata_audit/publication_pdfs/<record_id>.pdf`.
2. Download supplements into `artifacts/paper_metadata_audit/supplements/<record_id>/`.
3. Run `python -m tools.paper_metadata_parser --refresh` from the repo root.
4. Review `pdf_retrieval_inventory.csv` first for the running list of retrieved/missing PDFs and missing-paper DOI URLs.
5. Review `protocol_lineage_candidates.csv` when a paper cites an adapted or established prior protocol.
6. Review `running_checklist.csv`, `missing_pdf_request_list.csv`, and `paper_audits/<record_id>.md`.
7. Promote critically checked Segment 1-4 values into `manual_reviews/<record_id>.json` and update `manual_review_index.csv`.

Automated evidence-mined values are `inferred_low_confidence` candidates. Treat them as a triage map for critical review, not as final paper metadata.

Before marking any value `not_reported_after_review`, inspect the main PDF, methods/tables, supplements, at least one fallback/source route, and any cited prior protocol paper that the article says it adapted, followed, or used as an established paradigm.

Before marking trajectory/direction values as reported, inspect the rendered figure/caption evidence and verify the participant-facing direction relative to speakers, the body-relative direction being tested, and whether the trajectory is physical, digitally rendered, or inferred from gain/cross-fade timing.

Every manual review should preserve the orientation decision in short form, even when no final profile is created. A useful note format is: `participant faces <direction/unclear>; speakers/sources at <room/apparatus positions>; authors test <body-relative label>; tactile anchor <body site>; movement implemented by <physical source/digital renderer/speaker switching/gain envelope>; evidence <text/caption/figure/supplement/lineage>`.
