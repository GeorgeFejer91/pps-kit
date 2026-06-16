# Tonelli et al. (2019)

- Record ID: `tonelli_2019_echolocation`
- DOI: `10.1007/s00221-019-05469-3`
- DOI URL: https://doi.org/10.1007/s00221-019-05469-3
- Coverage category: `covered_blocked_toolkit_structure`
- Task family: seven-speaker audio-tactile PPS task
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.56` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 22/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 22/25 fields with candidate values

## Known Prior Gaps

- apparatus-specific seven-speaker switching/timing details

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 34 | sound; auditory stimuli; distance; tone; approaching; far; loudspeaker; speaker; cm/s; db; headphone; dba | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 9 | temporal delay; delays; inter-trial; jitter; duration; t1 | OpenDataLoader page(s) 3, 4, 5, 6, 8 |
| `trial_structure_intermixing` | `completed` | 19 | audio-tactile; trial; trials; random; randomized; block; unimodal; randomly; condition; order; sequence | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 10 | total; catch; absence of auditory; unimodal tactile; not to respond; for each; blocks; baseline | OpenDataLoader page(s) 2, 3, 4, 5 |
| `tactile_response_apparatus` | `completed` | 15 | reaction time; tactile stimulus; respond; vibro-tactile; vibration; response; threshold; microphone | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: white noise | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 2, 3, 1 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: towards body; 17 cm; 119 cm; 102 cm; 34 cm | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 2, 3, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 75 ms; 900 ms; 497.57 ms; 116.25 ms; 3 s; 20 ms | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 4, 6, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 34 cm/s | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 2, 4, 3 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: front; left | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 4, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); headphones | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; unimodal tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 2, 4, 3 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized; pseudo-randomized | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 2, 4 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order; pseudo-randomized | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 4, 2 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: ITI not fixed; jittered interval; 75 ms; 900 ms; 3 s; 20 ms | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 4, 2 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: speeded response | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 1, 3 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: withhold response on catch trials; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 3, 4 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 500 ms; 20 ms | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 3, 2 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 500 ms | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 3, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline; tactile-only/no-sound baseline | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 3, 4, 5 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 3 s; 20 ms | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 4, 2, 3 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials; withhold response on catch trials; 140 trials; 12 trials; 40 trials | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 3, 4 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 140 trials; 12 trials; 49 trials | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 4, 5 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 140 trials; 12 trials; 40 trials | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 3, 4 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 140 trials; 12 trials; 40 trials | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 3, 4 |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 2 blocks | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 4 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 140 trials; 12 trials; 40 trials; 10 trials; 30 trials | artifacts/paper_metadata_audit/extracted/opendataloader/tonelli_2019_echolocation.json; OpenDataLoader page(s) 4 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
