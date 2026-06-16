# Audiotactile Paper Metadata Audit

This folder is dedicated to metadata extraction from published audio-tactile PPS papers. It is intentionally independent from GUI/profile recreation: the goal is to inspect papers and supplements and record whether Segment 1-4 metadata can be extracted.

## Local Artifact Folders

- `artifacts/paper_metadata_audit/publication_pdfs/`: place publication PDFs here as `<record_id>.pdf`.
- `artifacts/paper_metadata_audit/supplements/<record_id>/`: place supplementary PDFs, DOCX, XLSX, ODS, ZIPs, scripts, or appendices here.
- `artifacts/paper_metadata_audit/extracted/`: parser output from OpenDataLoader PDF and fallback extractors.
- `artifacts/paper_metadata_audit/resume_bundles/`: ignored local ZIP backups for private transfer/resume only.

The `artifacts/` tree is ignored by Git. Do not commit PDFs, supplements, extracted full text, page images, or long copied passages.
Use `python -m tools.paper_metadata_parser.bundle --repo-root .` to refresh `local_artifact_inventory.json` and create/update the ignored local resume ZIP. The inventory is GitHub-safe because it stores only relative paths, sizes, hashes, and restore notes.

## Current Inventory

- Literature records: 74
- PDF status counts: `{"downloaded": 26, "needs_user_download": 12, "not_applicable": 5, "open_access_unavailable": 13, "paywalled": 18}`
- Supplement status counts: `{"downloaded": 10, "needs_user_download": 17, "not_applicable": 5, "not_checked": 6, "not_found": 21, "paywalled": 15}`
- Extraction status counts: `{"parsed_with_warnings": 31, "pending_pdf": 43}`
- Metadata confidence counts: `{"not_applicable": 5, "partial_extraction": 28, "pending_source": 12, "source_unavailable": 29}`
- Automated evidence status counts: `{"no_extracted_source": 41, "not_applicable": 5, "source_mined": 28}`
- Automated evidence mined field total: 477
- Supplement extracted records/files: 10 records / 13 files
- Semantic review strategy count: 5
- Semantic review pass status counts: `{"completed": 136, "completed_no_hits": 4, "not_applicable": 25, "source_unavailable": 205}`
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
4. Review `running_checklist.csv`, `missing_pdf_request_list.csv`, and `paper_audits/<record_id>.md`.
5. Fill `metadata_audit.jsonl` or the per-paper summaries with extracted Segment 1-4 values using short evidence pointers only.

Automated evidence-mined values are `inferred_low_confidence` candidates. Treat them as a triage map for critical review, not as final paper metadata.

Before marking any value `not_reported_after_review`, inspect the main PDF, methods/tables, supplements, and at least one fallback/source route.
