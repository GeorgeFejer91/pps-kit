# How ageing shapes body and space representations (2021)

- Record ID: `ageing_2021`
- DOI: `10.1016/j.cortex.2020.11.021`
- DOI URL: https://doi.org/10.1016/j.cortex.2020.11.021
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: audio-tactile PPS task in ageing context
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.5` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 18/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 18/25 fields with candidate values

## Known Prior Gaps

- exact task parameters need extraction; age group context is non-blocking

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 39 | far; near; unity; sound; loudspeaker; speaker; approaching; dba; db; auditory stimuli; distance | OpenDataLoader page(s) 2, 3, 4, 5, 6, 7, 10, 11 |
| `timing_soa` | `completed` | 12 | duration; temporal delay; delays; sound onset | OpenDataLoader page(s) 4, 6, 7, 10, 11, 12, 16, 20 |
| `trial_structure_intermixing` | `completed` | 29 | audio-tactile; random; randomized; order; trial; condition; block; trials; unimodal; randomly; conditions; sequence | OpenDataLoader page(s) 1, 3, 4, 5, 6, 7, 10, 11 |
| `baseline_catch_counts` | `completed` | 19 | total; repetitions; for each; blocks; baseline; catch; absence of auditory; unimodal tactile | OpenDataLoader page(s) 3, 4, 5, 6, 7, 9, 10, 11 |
| `tactile_response_apparatus` | `completed` | 18 | respond; threshold; reaction time; vibration; tactile stimulus; response | OpenDataLoader page(s) 1, 2, 3, 5, 6, 7, 10, 11 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: 150 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 6, 5, 11 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: Unity | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 5, 6 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; 0 cm; 100 cm; 18.22 cm; 12.85 cm; 20 cm; 10 cm; 80 cm | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 5, 11, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 3 sec; 1.5 sec; 2.7 sec; 2 sec; 1 sec | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 6, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; IN sound; rear; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 4, 5, 11 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); Unity; virtual audio source | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 5, 6 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 6, 7, 12 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 5, 4, 6 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order; 2 blocks | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 5, 6, 4 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 100 msec | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 4, 5 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 6, 4 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 60 mA; 150 Hz; 100 msec | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 6, 5, 10 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline; tactile-only/no-sound baseline | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 6, 7, 12 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 6, 4 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 5, 6, 4 |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 6, 5, 4 |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 2 blocks | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 5, 3, 4 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ageing_2021.json; OpenDataLoader page(s) 4, 5, 6 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
