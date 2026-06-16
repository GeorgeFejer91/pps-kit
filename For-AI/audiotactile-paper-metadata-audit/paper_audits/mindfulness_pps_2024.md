# Mindfulness and PPS boundaries (2024)

- Record ID: `mindfulness_pps_2024`
- DOI: `10.3390/bs14040306`
- DOI URL: https://doi.org/10.3390/bs14040306
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: audio-tactile PPS boundary task around focused-attention meditation context
- PDF status: `downloaded`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `4` (`http_403`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.56` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 22/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 22/25 fields with candidate values

## Known Prior Gaps

- extract exact audio-tactile PPS task timing, distances, trial counts, and response settings; meditation context is non-blocking unless it changes trial execution

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 17 | near; far; distance; dba; db; sound; pink noise; auditory stimuli; loudspeaker; speaker; approaching; spl | source page/section(s) 2, 3, 4, 5, 6, 7, 8, 9 |
| `timing_soa` | `completed` | 8 | duration; temporal delay; delays; t1; t2; t3; t4; t5; silence | source page/section(s) 5, 6, 7, 8, 10 |
| `trial_structure_intermixing` | `completed` | 9 | condition; conditions; order; unimodal; trial; trials; random; randomly; intermingled | source page/section(s) 1, 2, 3, 4, 5, 6, 8 |
| `baseline_catch_counts` | `completed` | 11 | total; for each; catch; no tactile | source page/section(s) 2, 5, 6, 7, 8 |
| `tactile_response_apparatus` | `completed` | 19 | respond; tactile stimulus; reaction time; stimulator; electrical; voice; threshold; calibration; response; button | source page/section(s) 1, 3, 5, 6, 7, 8, 9 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; 44.1 kHz | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 4, 5 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 4, 5 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: near loudspeaker; far loudspeaker; approaching trajectory; 100 cm; 5 cm | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 4, 5, 6 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 1000 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; IN sound; front; left | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 4, 5 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 4, 5 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 4, 5 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 6, 4 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 4 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 4 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: pre/post trial silence; silence interval; 3000 ms; 1000 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 6, 4 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 3, 7 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 6, 4 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator; 3000 ms; 5 mA; 60-90 mA; 1000 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 1000 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: silence baseline window | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 1000 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; T0; T6 | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 4 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials; 10 trials; 62 trials; 42 trials | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 6, 4 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 10 trials; 62 trials; 42 trials | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 6 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 10 trials; 62 trials; 42 trials | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 6, 4 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 10 trials; 62 trials; 42 trials | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 6, 4 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 10 trials; 62 trials; 42 trials | artifacts/paper_metadata_audit/extracted/opendataloader/mindfulness_pps_2024.json; source page/section(s) 5, 3, 6 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
