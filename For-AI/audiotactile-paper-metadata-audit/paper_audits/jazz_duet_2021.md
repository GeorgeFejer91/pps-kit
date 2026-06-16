# Jazz duet PPS (2021)

- Record ID: `jazz_duet_2021`
- DOI: `10.1007/s00426-020-01365-6`
- DOI URL: https://doi.org/10.1007/s00426-020-01365-6
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: audio-tactile PPS task after musical interaction context
- PDF status: `paywalled`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `8` (`downloaded`)
- Supplement extracted text files: `1`
- Extraction status: `pending_pdf`
- Metadata confidence: `0.16` (`partial_extraction`)
- Confidence basis: Supplement or other extracted source text yielded candidate values for 1/25 fields, but the main publication PDF is still missing or unavailable.
- Automated evidence mining: `source_mined`; 1/25 fields with candidate values
- PPS visualization mining: `no_visualization_terms_found`; 0/9 visualization-form candidates

## Known Prior Gaps

- extract the audiotactile PPS task parameters separately from the musical-interaction manipulation; music/social context is non-blocking unless it changes the task audio assets

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `available_for_review` - Downloaded or locally provided supplement files are available for methods/table review.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 1 | near; far | source page/section(s) supplement |
| `timing_soa` | `completed_no_hits` | 0 |  |  |
| `trial_structure_intermixing` | `completed` | 1 | unimodal; condition | source page/section(s) supplement |
| `baseline_catch_counts` | `completed` | 1 | baseline; for each | source page/section(s) supplement |
| `tactile_response_apparatus` | `completed_no_hits` | 0 |  |  |
| `pps_visualization_reporting` | `completed` | 1 | figure; rt; facilitation | source page/section(s) supplement |

## PPS Visualization Candidates

- `no_visualization_terms_found`: Treat visualization candidates as a triage map. Confirm actual figure forms by inspecting rendered figures/captions and record only short pointers, not figure screenshots or long source text.

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: baseline trials | artifacts/paper_metadata_audit/extracted/supplements/jazz_duet_2021/426_2020_1365_MOESM1_ESM.txt; source page/section(s) supplement |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `source_unavailable` |  |  |
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
