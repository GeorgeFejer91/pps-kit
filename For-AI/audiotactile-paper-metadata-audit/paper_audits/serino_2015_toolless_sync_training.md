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
- Extraction status: `parsed`
- Metadata confidence: `0.45` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 14/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 14/25 fields with candidate values

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
| `stimulus_reconstruction` | `completed` | 55 | far; distance; sound; near; auditory stimuli; dba; db; spl; pink noise; loudspeaker; speaker; receding | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 8 | temporal delay; duration; soa; delays; sound onset; t1; t2; t3; t4; t5 | source page/section(s) 2, 5, 8, 9, 11 |
| `trial_structure_intermixing` | `completed` | 60 | audio-tactile; order; sequence; condition; random; randomized; conditions; unimodal; intermingled; randomly; trial; trials | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 8 | for each; unimodal tactile; catch; baseline | source page/section(s) 5, 6, 7, 8, 9, 10 |
| `tactile_response_apparatus` | `completed` | 39 | respond; response; reaction time; tactile stimulus; stimulator; electrical; electrodes; voice; vibro-tactile | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 8, 9, 6 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 8, 6, 9 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions; IN and OUT sounds | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 9, 10, 8 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: near loudspeaker; approaching trajectory; receding trajectory | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 8, 9, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 8, 9, 5 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; IN sound; OUT sound; right | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 8, 10 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 8, 9, 1 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; unimodal tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 6, 8 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 2, 9, 1 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 9, 2, 8 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 8, 4, 9 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 8, 5, 6 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: T1 IN and T5 OUT (farthest distance from the body) and at T2 IN and T4 OUT (far distance), T3 IN and T3 OUT (intermediate distance), T4 IN and T2 OUT (close distance), T5 IN and T1 | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 9, 1 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_toolless_sync_training.json; source page/section(s) 6, 1, 2 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
