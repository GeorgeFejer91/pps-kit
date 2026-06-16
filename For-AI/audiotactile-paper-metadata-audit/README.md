# Audiotactile Paper Metadata Audit

This folder is dedicated to metadata extraction from published audio-tactile PPS papers. It is intentionally independent from GUI/profile recreation: the goal is to inspect papers and supplements and record whether Segment 1-4 metadata can be extracted.

## Local Artifact Folders

- `artifacts/paper_metadata_audit/publication_pdfs/`: place publication PDFs here as `<record_id>.pdf`.
- `artifacts/paper_metadata_audit/supplements/<record_id>/`: place supplementary PDFs, DOCX, XLSX, ODS, ZIPs, scripts, or appendices here.
- `artifacts/paper_metadata_audit/extracted/`: parser output from OpenDataLoader PDF and fallback extractors.

The `artifacts/` tree is ignored by Git. Do not commit PDFs, supplements, extracted full text, page images, or long copied passages.

## Current Inventory

- Literature records: 74
- PDF status counts: `{"downloaded": 28, "needs_user_download": 10, "not_applicable": 5, "open_access_unavailable": 13, "paywalled": 18}`
- Supplement status counts: `{"downloaded": 10, "needs_user_download": 16, "not_applicable": 5, "not_checked": 6, "not_found": 18, "paywalled": 19}`
- Extraction status counts: `{"parsed": 28, "parsed_with_warnings": 5, "pending_pdf": 41}`
- Metadata confidence counts: `{"not_applicable": 5, "partial_extraction": 30, "pending_source": 10, "source_unavailable": 29}`
- Automated evidence status counts: `{"no_extracted_source": 39, "not_applicable": 5, "source_mined": 30}`
- Automated evidence mined field total: 518
- Supplement extracted records/files: 10 records / 13 files
- Semantic review strategy count: 5
- Semantic review pass status counts: `{"completed": 146, "completed_no_hits": 4, "not_applicable": 25, "source_unavailable": 195}`
- Missing download/check requests: 82

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
5. Fill `metadata_audit.jsonl` or the per-paper summaries with extracted Segment 1-4 values using short evidence pointers only.

Automated evidence-mined values are `inferred_low_confidence` candidates. Treat them as a triage map for critical review, not as final paper metadata.

Before marking any value `not_reported_after_review`, inspect the main PDF, methods/tables, supplements, and at least one fallback/source route.
