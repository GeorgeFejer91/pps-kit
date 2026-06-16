# Multisensory integration in PPS indexes consciousness states (2026)

- Record ID: `cell_reports_medicine_2026_consciousness`
- DOI: `10.1016/j.xcrm.2026.102705`
- DOI URL: https://doi.org/10.1016/j.xcrm.2026.102705
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: audio-tactile PPS task in sleep/disorders-of-consciousness setting
- PDF status: `downloaded`
- Supplement status: `not_found`
- Supplement acquisition attempts: `2` (`checked_no_supplement_candidates`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.35` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 7/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 7/25 fields with candidate values

## Known Prior Gaps

- extract near/far audiotactile stimulus distances, tactile settings, timing, trial counts, response/trigger settings, and apparatus details independently of sleep or clinical endpoint

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `checked_not_found` - Automated source routes found no supplement candidates; use publisher/source checks again before final missing-value decisions.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 7 | near; distance; far; receding; auditory stimuli; dba; db | source page/section(s) 1, 2, 3, 5, 7, 11 |
| `timing_soa` | `completed_no_hits` | 0 |  |  |
| `trial_structure_intermixing` | `completed` | 8 | order; random; trial; trials; condition; conditions | source page/section(s) 1, 2, 3, 5, 7, 10 |
| `baseline_catch_counts` | `completed` | 4 | for each; baseline; total | source page/section(s) 3, 5, 7, 9 |
| `tactile_response_apparatus` | `completed` | 17 | electrical; respond; response; electrodes; threshold | source page/section(s) 1, 2, 3, 5, 7, 9, 10, 11 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: 20-30 Hz; 37 Hz; 26 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/cell_reports_medicine_2026_consciousness.json; source page/section(s) 11, 3, 5 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: receding trajectory | artifacts/paper_metadata_audit/extracted/opendataloader/cell_reports_medicine_2026_consciousness.json; source page/section(s) 3, 5 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: receding; front; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/cell_reports_medicine_2026_consciousness.json; source page/section(s) 5, 7 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/cell_reports_medicine_2026_consciousness.json; source page/section(s) 5, 7, 3 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 20 s | artifacts/paper_metadata_audit/extracted/opendataloader/cell_reports_medicine_2026_consciousness.json; source page/section(s) 5, 7 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/cell_reports_medicine_2026_consciousness.json; source page/section(s) 5, 3 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation | artifacts/paper_metadata_audit/extracted/opendataloader/cell_reports_medicine_2026_consciousness.json; source page/section(s) 1, 2 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
