# Serino et al. (2015), Exp. 2

- Record ID: `serino_2015_front_back_trunk_exp2`
- DOI: `10.1038/srep18603`
- DOI URL: https://doi.org/10.1038/srep18603
- Coverage category: `covered_blocked_toolkit_structure`
- Task family: front/back trunk tactile PPS with physical speaker array
- PDF status: `downloaded`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `9` (`downloaded`)
- Supplement extracted text files: `1`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.56` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 22/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 22/25 fields with candidate values

## Known Prior Gaps

- 13-distance internal schedule

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `available_for_review` - Downloaded or locally provided supplement files are available for methods/table review.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 15 | auditory stimuli; approaching; receding; near; far; distance; sound; loudspeaker; speaker; cm/s; spl; db | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 6 | temporal delay; delays; sound onset; t2; t1; duration; inter-trial; t4 | source page/section(s) 2, 9, 11, 12, 13, supplement |
| `trial_structure_intermixing` | `completed` | 13 | trial; trials; audio-tactile; unimodal; condition; order; conditions; block; random; randomly | source page/section(s) 2, 3, 4, 5, 6, 7, 8, 9 |
| `baseline_catch_counts` | `completed` | 12 | baseline; catch; unimodal tactile; no tactile; for each; blocks; total; absence of auditory; repetitions | source page/section(s) 2, 3, 4, 5, 6, 7, 8, 9 |
| `tactile_response_apparatus` | `completed` | 13 | electrical; respond; response; reaction time; tactile stimulus; vibration; button | source page/section(s) 1, 2, 3, 4, 5, 7, 8, 10 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; 44.1 kHz | artifacts/paper_metadata_audit/extracted/supplements/serino_2015_front_back_trunk_exp2/41598_2015_BFsrep18603_MOESM1_ESM.txt; source page/section(s) supplement, 2, 5 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: SoundForge; Sonic Foundry; samples of pink noise; pink-noise samples | artifacts/paper_metadata_audit/extracted/supplements/serino_2015_front_back_trunk_exp2/41598_2015_BFsrep18603_MOESM1_ESM.txt; source page/section(s) supplement, 1, 12 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 3, 10, 11 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: near loudspeaker; far loudspeaker; towards body; away from body; approaching trajectory; receding trajectory; 5 cm; 100 cm; 50 cm; 80 cm; 63 cm; 25 cm; 93 cm; 43 cm; 45 cm; 59 cm | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 3, 6, 10 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 100 ms; 50 ms | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 12, 11, supplement |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 22 cm/s; 75 cm/s; 35 cm/s; 25 cm/s; 100 cm/s | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 3, 11, 12 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; IN sound; front; left; right | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 7, 11, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB; 55 dB | artifacts/paper_metadata_audit/extracted/supplements/serino_2015_front_back_trunk_exp2/41598_2015_BFsrep18603_MOESM1_ESM.txt; source page/section(s) supplement, 3, 6 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 7, 3, supplement |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 12, 2, 7 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 5, 13, 2 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 700 ms | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 13, 1, 2 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 12, 1, 5 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 12, 2, 6 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 60 Hz; 125 Hz; 100 ms | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 12, 2, 3 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 100 ms; 50 ms | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 12, supplement, 11 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline; tactile-only/no-sound baseline | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 12, 2, 6 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 1 S | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 1, 2, 3 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: no-tactile catch trials; 240 trials; 372 trials; 208 trials; 480 trials; 432 trials; 320 trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 12, 2, 13 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 240 trials; 372 trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 12, 2, 7 |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 240 trials; 372 trials; 208 trials; 480 trials; 432 trials; 320 trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 2, 12, 13 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 240 trials; 372 trials; 208 trials; 480 trials; 432 trials; 320 trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2015_front_back_trunk_exp2/serino_2015_front_back_trunk_exp2.fallback.txt; source page/section(s) 12, 13, 2 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
