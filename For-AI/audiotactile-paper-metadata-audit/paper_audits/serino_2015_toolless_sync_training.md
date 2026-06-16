# Serino/Canzoneri 2015 toolless sync training

- Record ID: `serino_2015_toolless_sync_training`
- DOI: `10.3389/fnbeh.2015.00004`
- DOI URL: https://doi.org/10.3389/fnbeh.2015.00004
- Coverage category: `covered_blocked_missing_publication_parameters`
- Task family: bimodal IN/OUT target trials plus auditory-only catch trials
- PDF status: `downloaded`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `6` (`not_file_html`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.43` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 13/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 13/25 fields with candidate values

## Known Prior Gaps

- electrocutaneous tactile calibration
- voice-key response capture

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 14 | sound; far; distance; db; near; dba; spl; pink noise; auditory stimuli; loudspeaker; speaker; receding | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 7 | t3; tafter; soa; duration; delays; t1; t2; t4; t5 | source page/section(s) 1, 2, 5, 6, 9, 11, 13 |
| `trial_structure_intermixing` | `completed` | 13 | trial; audio-tactile; order; condition; random; randomized; sequence; conditions; unimodal; randomly; intermingled; trials | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 3 | for each; catch; baseline | source page/section(s) 6, 8, 9 |
| `tactile_response_apparatus` | `completed` | 14 | electrical; respond; response; tactile stimulus; reaction time; stimulator; electrodes; vibro-tactile; voice | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 9, 8, 11 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 8, 5, 2 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions; IN and OUT sounds | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 9, 8, 10 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; receding trajectory | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 8, 9, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; IN sound; OUT sound; front; right | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 10, 9, 8 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 8, 9, 1 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 8, 9, 4 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 2, 9, 5 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 9, 2, 5 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: voice-key response capture | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 6, 2, 9 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 9, 8, 2 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 300,800,1500,2200,2700ms | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 9, 2, 5 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: Tafter | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_toolless_sync_training/serino_2015_toolless_sync_training.fallback.txt; source page/section(s) 2, 6, 11 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
