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
