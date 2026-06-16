# Spatial tuning of multisensory responses in newborns (2021)

- Record ID: `ronga_2021_newborn_erp`
- DOI: `10.1073/pnas.2024548118`
- DOI URL: https://doi.org/10.1073/pnas.2024548118
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: near/far auditory plus electrical tactile stimulation with ERP endpoint
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.35` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 7/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 7/25 fields with candidate values

## Known Prior Gaps

- extract near/far auditory apparatus, electrical tactile parameters, timing offset, and ERP trigger needs

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 11 | far; auditory stimuli; distance; tone; near | OpenDataLoader page(s) 1, 2, 3 |
| `timing_soa` | `completed_no_hits` | 0 |  |  |
| `trial_structure_intermixing` | `completed` | 7 | unimodal; condition; conditions | OpenDataLoader page(s) 1, 2, 3 |
| `baseline_catch_counts` | `completed_no_hits` | 0 |  |  |
| `tactile_response_apparatus` | `completed` | 14 | response; electrical; respond; voice | OpenDataLoader page(s) 1, 2, 3 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: 5 cm; 140 cm | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; OpenDataLoader page(s) 1, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 338 ms; 400 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; OpenDataLoader page(s) 1, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: left; right | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; OpenDataLoader page(s) 2, 1 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 338 ms; 400 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; OpenDataLoader page(s) 1, 2 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; 338 ms; 400 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; OpenDataLoader page(s) 1, 2, 3 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 338 ms; 400 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; OpenDataLoader page(s) 1 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 338 ms; 400 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; OpenDataLoader page(s) 1 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
