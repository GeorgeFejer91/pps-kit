# Holmes et al. (2020), four experiments

- Record ID: `holmes_2020_four_experiments`
- DOI: `10.1007/s00221-020-05771-5`
- DOI URL: https://doi.org/10.1007/s00221-020-05771-5
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: static near/far sounds paired with weak vibrotactile targets and Go/NoGo response logic
- PDF status: `downloaded`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `0` (`existing_files`)
- Supplement extracted text files: `4`
- Extraction status: `parsed`
- Metadata confidence: `0.5` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 18/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 18/25 fields with candidate values

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
| `stimulus_reconstruction` | `completed` | 63 | sound; near; far; distance; auditory stimuli; tone; speaker; db; dba; spl; receding; pink noise | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 5 | inter-trial; duration; sound onset; t1; t2; soa; t5 | source page/section(s) 4, 9, 10, supplement |
| `trial_structure_intermixing` | `completed` | 44 | trial; trials; condition; conditions; intermixed; block; random; order; audio-tactile | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 19 | catch; total; blocks; baseline; false alarm; for each | source page/section(s) 2, 3, 4, 5, 6, 8, 9, 10 |
| `tactile_response_apparatus` | `completed` | 51 | response; reaction time; respond; vibration; threshold; microphone; button; tactile stimulus; stimulator; electrical | source page/section(s) 1, 2, 3, 4, 6, 7, 8, 9 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; white noise; pure tone | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 10, supplement |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: four body-relative directions | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 8, 2 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: away from body | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 8, supplement, 1 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 2.9 ms; 5 ms; 4 s; 1-4 s; 16 ms; 125 ms | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 10, 9, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: front; rear; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 8, 6 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 80 dB | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 4, 2, 3 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: speaker(s); headphones; HRTF | artifacts/paper_metadata_audit/extracted/supplements/holmes_2020_four_experiments/holmes_2020_MOESM3.txt; source page/section(s) supplement, 10 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 6, supplement |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 8, 4, 6 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 150 ms; 36 ms; 125 ms; 1 s; 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 2, 4 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: microphone response capture; button response; speeded response | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 2, 1, 3 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 9, 2 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; vibrotactile stimulation; 16 ms | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 9, supplement, 3 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 2.9 ms; 5 ms | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 10, supplement |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: post-sound tactile baseline; 4 s; 1-4 s; 16 ms; 125 ms | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 9, 2, 6 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: no-tactile catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 2, supplement, 4 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 160 trials; 40 trials | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 4, 6 |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 44 trials; 40 trials; 160 trials | artifacts/paper_metadata_audit/extracted/opendataloader/holmes_2020_four_experiments.json; source page/section(s) 3, 8, 6 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
