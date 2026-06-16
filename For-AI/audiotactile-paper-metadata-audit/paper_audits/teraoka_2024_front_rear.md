# Teraoka et al. (2024)

- Record ID: `teraoka_2024_front_rear`
- DOI: `10.1007/s00221-024-06782-2`
- DOI URL: https://doi.org/10.1007/s00221-024-06782-2
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: front/rear approaching auditory probe with vibrotactile detection and baseline
- PDF status: `paywalled`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `13` (`downloaded`)
- Supplement extracted text files: `1`
- Extraction status: `pending_pdf`
- Metadata confidence: `0.25` (`partial_extraction`)
- Confidence basis: Supplement or other extracted source text yielded candidate values for 8/25 fields, but the main publication PDF is still missing or unavailable.
- Automated evidence mining: `source_mined`; 8/25 fields with candidate values

## Known Prior Gaps

- extract auditory-probe trajectory, baseline structure, and apparatus geometry

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `available_for_review` - Downloaded or locally provided supplement files are available for methods/table review.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 1 | sound; auditory stimuli; approaching; near; far; distance | source page/section(s) supplement |
| `timing_soa` | `completed` | 1 | t2 | source page/section(s) supplement |
| `trial_structure_intermixing` | `completed` | 1 | trial; trials; audio-tactile; condition; conditions | source page/section(s) supplement |
| `baseline_catch_counts` | `completed` | 1 | baseline; for each | source page/section(s) supplement |
| `tactile_response_apparatus` | `completed` | 1 | tactile stimulus; respond; reaction time | source page/section(s) supplement |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory | artifacts/paper_metadata_audit/extracted/supplements/teraoka_2024_front_rear/221_2024_6782_MOESM1_ESM.txt; source page/section(s) supplement |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; IN sound; front; rear | artifacts/paper_metadata_audit/extracted/supplements/teraoka_2024_front_rear/221_2024_6782_MOESM1_ESM.txt; source page/section(s) supplement |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; baseline trials | artifacts/paper_metadata_audit/extracted/supplements/teraoka_2024_front_rear/221_2024_6782_MOESM1_ESM.txt; source page/section(s) supplement |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 6 trials | artifacts/paper_metadata_audit/extracted/supplements/teraoka_2024_front_rear/221_2024_6782_MOESM1_ESM.txt; source page/section(s) supplement |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 6 trials | artifacts/paper_metadata_audit/extracted/supplements/teraoka_2024_front_rear/221_2024_6782_MOESM1_ESM.txt; source page/section(s) supplement |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 6 trials | artifacts/paper_metadata_audit/extracted/supplements/teraoka_2024_front_rear/221_2024_6782_MOESM1_ESM.txt; source page/section(s) supplement |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 6 trials | artifacts/paper_metadata_audit/extracted/supplements/teraoka_2024_front_rear/221_2024_6782_MOESM1_ESM.txt; source page/section(s) supplement |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 6 trials | artifacts/paper_metadata_audit/extracted/supplements/teraoka_2024_front_rear/221_2024_6782_MOESM1_ESM.txt; source page/section(s) supplement |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
