# Matsuda et al. (2021)

- Record ID: `matsuda_2021_four_directions`
- DOI: `10.1038/s41598-021-90784-5`
- DOI URL: https://doi.org/10.1038/s41598-021-90784-5
- Coverage category: `covered_runnable_profile`
- Task family: front, rear, left, and right approaching/receding audio-tactile PPS task
- PDF status: `downloaded`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `5` (`http_429`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.56` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 22/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 22/25 fields with candidate values

## Known Prior Gaps

- None recorded in the prior coverage ledger.

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 21 | sound; approaching; receding; near; far; auditory stimuli; audio stimuli; unity; pink noise; loudspeaker; speaker; distance | source page/section(s) 1, 2, 4, 5, 6, 7 |
| `timing_soa` | `completed` | 11 | t2; temporal delay; delays; sound onset; sound offset; t1; t3; t4; t5; tbefore; tafter | source page/section(s) 2, 4, 5, 7 |
| `trial_structure_intermixing` | `completed` | 14 | audio-tactile; trial; condition; conditions; order; trials; unimodal; sequence; block; random; randomized | source page/section(s) 1, 2, 4, 5, 7 |
| `baseline_catch_counts` | `completed` | 6 | catch; false alarm; total; for each; repetitions; blocks; not to respond | source page/section(s) 2, 4, 5, 7 |
| `tactile_response_apparatus` | `completed` | 12 | tactile stimulus; respond; response; vibration; actuator; arduino | source page/section(s) 1, 2, 4, 6, 7 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; 44.1 kHz | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 4, 5 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: four body-relative directions; approaching and receding motions | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2, 1 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: away from body; approaching trajectory; receding trajectory; 10 cm; 110 cm | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 1 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; duration relative to sound offset; 3,000 ms; 3000 ms; 2700 ms; 700 ms | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: linear uniform motion; 33.3 cm/s | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; front; rear; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2, 1 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 55-70 dBA | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); Arduino | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 24 ms; 2700 ms; 700 ms | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; tactile actuator; 24 ms; 2700 ms; 700 ms | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 2700 ms; 700 ms; T1, T2, T3, T4, T5, and Tafter) | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: pre-sound tactile baseline; post-sound tactile baseline; 2700 ms; 700 ms; Tbefore; Tafter | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: no-tactile catch trials; withhold response on catch trials; 100 trials; 40 trials; 60 trials; 200 trials; 800 trials | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 100 trials; 40 trials; 60 trials; 200 trials; 800 trials | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 4, 5, 7 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 100 trials; 40 trials; 60 trials; 200 trials; 800 trials | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 100 trials; 40 trials; 60 trials; 200 trials; 800 trials | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 2, 7 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 100 trials; 40 trials; 60 trials; 200 trials; 800 trials | artifacts/paper_metadata_audit/extracted/opendataloader/matsuda_2021_four_directions.json; source page/section(s) 7, 2 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
