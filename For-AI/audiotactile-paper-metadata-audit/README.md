# Audiotactile Paper Metadata Audit

This folder is dedicated to metadata extraction from published audio-tactile PPS papers. It is intentionally independent from GUI/profile recreation: the goal is to inspect papers and supplements and record whether Segment 1-4 metadata can be extracted.

## Local Artifact Folders

- `artifacts/paper_metadata_audit/publication_pdfs/`: place publication PDFs here as `<record_id>.pdf`.
- `artifacts/paper_metadata_audit/supplements/<record_id>/`: place supplementary PDFs, DOCX, XLSX, ODS, ZIPs, scripts, or appendices here.
- `artifacts/paper_metadata_audit/extracted/`: parser output from OpenDataLoader PDF and fallback extractors.

The `artifacts/` tree is ignored by Git. Do not commit PDFs, supplements, extracted full text, page images, or long copied passages.

## Current Inventory

- Literature records: 74
- PDF status counts: `{"needs_user_download": 69, "not_applicable": 5}`
- Supplement status counts: `{"not_applicable": 5, "not_checked": 69}`
- Extraction status counts: `{"parsed_with_warnings": 5, "pending_pdf": 69}`
- Missing download/check requests: 138

## Environment Readiness

- Java available: `False`
- `opendataloader_pdf` installed: `False`
- OpenDataLoader ready: `False`
- Fallback extractors: `{"pdfinfo_available": true, "pdfplumber_installed": false, "pdftoppm_available": true, "pypdf_installed": true}`

## How To Use

1. Download each available publication PDF into `artifacts/paper_metadata_audit/publication_pdfs/<record_id>.pdf`.
2. Download supplements into `artifacts/paper_metadata_audit/supplements/<record_id>/`.
3. Run `python -m tools.paper_metadata_parser --refresh` from the repo root.
4. Review `running_checklist.csv`, `missing_pdf_request_list.csv`, and `paper_audits/<record_id>.md`.
5. Fill `metadata_audit.jsonl` or the per-paper summaries with extracted Segment 1-4 values using short evidence pointers only.

Before marking any value `not_reported_after_review`, inspect the main PDF, methods/tables, supplements, and at least one fallback/source route.
