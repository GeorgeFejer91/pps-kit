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

## Current Inventory

- Literature records: 74
- PDF status counts: `{"downloaded": 36, "needs_user_download": 8, "not_applicable": 5, "open_access_unavailable": 12, "paywalled": 13}`
- Supplement status counts: `{"downloaded": 11, "needs_user_download": 16, "not_applicable": 5, "not_checked": 6, "not_found": 17, "paywalled": 19}`
- Extraction status counts: `{"parsed": 36, "parsed_with_warnings": 5, "pending_pdf": 33}`
- Metadata confidence counts: `{"not_applicable": 5, "partial_extraction": 38, "pending_source": 8, "source_unavailable": 23}`
- Automated evidence status counts: `{"no_extracted_source": 31, "not_applicable": 5, "source_mined": 38}`
- Automated evidence mined field total: 640
- Supplement extracted records/files: 11 records / 14 files
- Semantic review strategy count: 5
- Semantic review pass status counts: `{"completed": 183, "completed_no_hits": 7, "not_applicable": 25, "source_unavailable": 155}`
- Missing download/check requests: 74

## Environment Readiness

- Java available: `True`
- `opendataloader_pdf` installed: `True`
- OpenDataLoader ready: `True`
- Fallback extractors: `{"pdfinfo_available": true, "pdfplumber_installed": true, "pdftoppm_available": true, "pypdf_installed": true}`

## How To Use

1. Download each available publication PDF into `artifacts/paper_metadata_audit/publication_pdfs/<record_id>.pdf`.
2. Download supplements into `artifacts/paper_metadata_audit/supplements/<record_id>/`.
3. Run `python -m tools.paper_metadata_parser --refresh` from the repo root.
4. Review `running_checklist.csv`, `missing_pdf_request_list.csv`, and `paper_audits/<record_id>.md`.
5. Promote critically checked Segment 1-4 values into `manual_reviews/<record_id>.json` and update `manual_review_index.csv`.

Automated evidence-mined values are `inferred_low_confidence` candidates. Treat them as a triage map for critical review, not as final paper metadata.

Before marking any value `not_reported_after_review`, inspect the main PDF, methods/tables, supplements, and at least one fallback/source route.
