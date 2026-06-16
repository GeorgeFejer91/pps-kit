# Lamia, Shabani, & Candidi (2026)

- Record ID: `lamia_2026_arm_movement`
- DOI: `10.1038/s41598-026-36796-5`
- DOI URL: https://doi.org/10.1038/s41598-026-36796-5
- Coverage category: `covered_runnable_profile`
- Task family: looming/receding audio-tactile task with arm-movement context
- PDF status: `downloaded`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `0` (`existing_files`)
- Supplement extracted text files: `1`
- Extraction status: `parsed`
- Metadata confidence: `0.49` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 17/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 17/25 fields with candidate values

## Known Prior Gaps

- None recorded in the prior coverage ledger.

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `available_for_review` - Downloaded or locally provided supplement files are available for methods/table review.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 49 | sound; auditory stimuli; near; far; dba; db; approaching; receding; distance; pink noise; speaker; spl | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 21 | t1; silence; duration; temporal delay; delays; sound onset; t2; t3; t4; t5 | source page/section(s) 3, 4, 5, 6, 7, 8, 9, 10 |
| `trial_structure_intermixing` | `completed` | 40 | audio-tactile; sequence; condition; conditions; trial; order; trials; block; random; randomized; intermixed; randomly | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 14 | for each; baseline; catch; blocks; total | source page/section(s) 4, 5, 6, 7, 11, supplement |
| `tactile_response_apparatus` | `completed` | 22 | threshold; calibration; response; respond; tactile stimulus; stimulator; electrical; electrodes; reaction time; button | source page/section(s) 2, 3, 4, 5, 6, 7, 9, 10 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; 44.1 kHz; 20 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 3, 4, 1 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 3, 4 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: towards body; away from body; receding trajectory; 100 cm; 10 cm; 30 cm | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 3, 10, supplement |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 800 ms; 1300 ms; 2000 ms; 2700 ms; 3200 ms; 300 ms; 10 ms; 19.9 ms; 3 s; 4 s | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 4, 10 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 10 cm/s; 7,5 cm/s | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 4, 3 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: receding; front; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 4, 3 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB; 55 dB | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 3, 4, 2 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 3, 4 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 4 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 5, 4 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: silence interval; 3000 ms; 4000 ms; 800 ms; 1300 ms; 2000 ms; 2700 ms; 3200 ms; 300 ms | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 3, 4 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 4, 3 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator; 3000 ms; 4000 ms; 5-10 mA | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 3, 4 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 800 ms; 1300 ms; 2000 ms; 2700 ms; 3200 ms; 300 ms; T1 at 800 ms, T2 at 1300 ms, T3 at 2000 ms, T4 at 2700 ms, and T5 at 3200 ms (see Fig | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 4, supplement, 8 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: silence baseline window | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 3, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 4000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 3, supplement, 4 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 15 trials; 166 trials; 10 trials; 110 trials; 50 trials; 200 trials; 440 trials; 640 trials | artifacts/paper_metadata_audit/extracted/opendataloader/lamia_2026_arm_movement.json; source page/section(s) 4, 5 |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
