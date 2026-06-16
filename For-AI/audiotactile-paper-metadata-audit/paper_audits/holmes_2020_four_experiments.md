# Holmes et al. (2020), four experiments

- Record ID: `holmes_2020_four_experiments`
- DOI: `10.1007/s00221-020-05771-5`
- DOI URL: https://doi.org/10.1007/s00221-020-05771-5
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: static near/far sounds paired with weak vibrotactile targets and Go/NoGo response logic
- PDF status: `downloaded`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `9` (`downloaded`)
- Supplement extracted text files: `4`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.52` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 19/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 19/25 fields with candidate values

## Known Prior Gaps

- task is publicly documented but needs translation into a static near/far toolkit profile

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `available_for_review` - Downloaded or locally provided supplement files are available for methods/table review.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 19 | sound; near; far; distance; tone; auditory stimuli; speaker; db; dba; spl; receding; pink noise | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 5 | inter-trial; duration; sound onset; t1; t2; soa; t5 | source page/section(s) 4, 9, 10, supplement |
| `trial_structure_intermixing` | `completed` | 19 | trial; trials; condition; conditions; intermixed; random; block; order; audio-tactile | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 12 | catch; total; blocks; baseline; false alarm; for each; no tactile | source page/section(s) 2, 3, 4, 5, 6, 8, 9, 10 |
| `tactile_response_apparatus` | `completed` | 17 | response; reaction time; vibration; respond; threshold; tactile stimulus; stimulator; microphone; button; electrical | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; white noise; pure tone | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 2, supplement |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: four body-relative directions | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 3, 8, 14 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: away from body; 5 cm; 105 cm; 1 cm; 125 cm; 20 cm; 70 cm; 2.5 cm; 30 cm | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 3, 2, 8 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 5 ms; 2.9 ms; 33 ms; 4 s; 1-4 s; 16 ms; 42 ms; 81 ms; 9.5 ms; 25.7 ms; 15.2 ms; 0.082 ms; 71.7 ms | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 10, 9, 11 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; front; rear; left; right | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 3, 8, 14 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 80 dB | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 4, 3, 7 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: speaker(s); headphones; HRTF | artifacts/paper_metadata_audit/extracted/supplements/holmes_2020_four_experiments/221_2020_5771_MOESM3_ESM.txt; source page/section(s) supplement, 10 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/supplements/holmes_2020_four_experiments/221_2020_5771_MOESM3_ESM.txt; source page/section(s) supplement, 2, 3 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 4, 8, 13 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 1 s; 100 ms; 340 ms; 253 ms; 324 ms; 194 ms; 201 ms; 123 ms; 195 ms; 183 ms; 85 ms; 38.7 ms; 28 ms; 2 s; 150 ms; 50 ms | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 6, 2, 3 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; vibrotactile stimulation; tactile stimulator; 125 ms; 5 ms; 250 ms; 500 ms; 2.9 ms; 31.2 ms; 22.8 ms; 438 ms | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 3, supplement, 8 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 5 ms; 2.9 ms | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 10, supplement |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: post-sound tactile baseline; 33 ms; 4 s; 1-4 s; 16 ms; 9.5 ms; 15.2 ms; 50 ms; 150 ms; 36 ms; 125 ms; 5.5 ms; 13.5 ms; 19 ms; 1 ms | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 9, 1, 2 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: no-tactile catch trials; 160 trials; 40 trials | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 2, 6, supplement |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 40 trials; 160 trials | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 2, 4, 6 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 40 trials | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 4, supplement |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 160 trials; 40 trials | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 6, 4, supplement |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 40 trials; 8 trials | artifacts/paper_metadata_audit/extracted/fallback/holmes_2020_four_experiments/holmes_2020_four_experiments.fallback.txt; source page/section(s) 3, 8, 12 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
