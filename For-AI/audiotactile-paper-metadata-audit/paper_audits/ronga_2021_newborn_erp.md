# Spatial tuning of multisensory responses in newborns (2021)

- Record ID: `ronga_2021_newborn_erp`
- DOI: `10.1073/pnas.2024548118`
- DOI URL: https://doi.org/10.1073/pnas.2024548118
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: near/far auditory plus electrical tactile stimulation with ERP endpoint
- PDF status: `downloaded`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `2` (`supplement_routes_access_limited`)
- Supplement extracted text files: `2`
- Extraction status: `parsed`
- Metadata confidence: `0.52` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 19/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 19/25 fields with candidate values

## Known Prior Gaps

- extract near/far auditory apparatus, electrical tactile parameters, timing offset, and ERP trigger needs

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `available_for_review` - Downloaded or locally provided supplement files are available for methods/table review.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 12 | far; auditory stimuli; distance; tone; near; sound; loudspeaker; speaker; db; spl | source page/section(s) 1, 2, 3, supplement |
| `timing_soa` | `completed` | 1 | inter-trial; duration | source page/section(s) supplement |
| `trial_structure_intermixing` | `completed` | 8 | unimodal; condition; conditions; trial; trials; audio-tactile; random; randomized; randomly; intermixed; block; sequence | source page/section(s) 1, 2, 3, supplement |
| `baseline_catch_counts` | `completed` | 1 | baseline; total; for each; blocks | source page/section(s) supplement |
| `tactile_response_apparatus` | `completed` | 15 | response; electrical; respond; voice; electrodes; arduino; reaction time; threshold; calibration | source page/section(s) 1, 2, 3, supplement |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: 784 Hz; 50 Hz; 1024 Hz; 1-30 Hz | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: 5 cm; 140 cm; 1 cm | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; source page/section(s) 1, supplement, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 338 ms; 400 ms; 50 ms; 5 ms; 2 s; 40 ms; 80 ms; 0.5 s; 1 s; 1.5 s; 0 s | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; source page/section(s) 1, 2, supplement |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: left; right | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; source page/section(s) 2, 1, supplement |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 64 dB | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1, 3 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); Arduino | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; baseline trials | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1, 2 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 338 ms; 400 ms; 50 ms; 5 ms; 2 s; 40 ms; 80 ms; 0.5 s; 1 s; 1.5 s; 0 s | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; source page/section(s) 1, supplement |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: tactile target trials | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; 338 ms; 400 ms; 11 mA; 4 mA; 25 mA; 1.03 mA; 784 Hz; 50 ms; 50 Hz; 5 ms; 40 ms; 80 ms; 1024 Hz; 1-30 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; source page/section(s) 1, supplement, 2 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 338 ms; 400 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; source page/section(s) 1 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 338 ms; 400 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; source page/section(s) 1 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 5 trials; 30 trials; 12 trials; 36 trials | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 5 trials; 30 trials; 12 trials; 36 trials | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 5 trials; 30 trials; 12 trials; 36 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ronga_2021_newborn_erp.json; source page/section(s) 1, supplement |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 6 blocks; 3 blocks | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 5 trials; 30 trials; 12 trials; 36 trials | artifacts/paper_metadata_audit/extracted/supplements/ronga_2021_newborn_erp/pnas.2024548118.sapp.txt; source page/section(s) supplement, 1 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
