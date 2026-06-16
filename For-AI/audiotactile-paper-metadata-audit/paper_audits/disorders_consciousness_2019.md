# PPS encoding in disorders of consciousness (2019)

- Record ID: `disorders_consciousness_2019`
- DOI: `10.1016/j.nicl.2019.101940`
- DOI URL: https://doi.org/10.1016/j.nicl.2019.101940
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: audio-tactile PPS task with neuroclinical endpoint
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.49` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 17/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 17/25 fields with candidate values

## Known Prior Gaps

- extract 5 cm/75 cm auditory-tactile timing, tactile apparatus, response/EEG triggers, and task execution separately from clinical endpoint

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 23 | near; distance; auditory stimuli; far; sound; loudspeaker; speaker; approaching; db; spl | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 15 | duration; inter-trial; t1; t2; delays | OpenDataLoader page(s) 3, 4, 5, 6, 7, 8, 9, 10 |
| `trial_structure_intermixing` | `completed` | 32 | audio-tactile; order; trial; trials; block; random; randomized; condition; conditions; randomly; sequence | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 11 | total; blocks; for each; baseline | OpenDataLoader page(s) 2, 3, 4, 5, 6 |
| `tactile_response_apparatus` | `completed` | 30 | electrodes; response; respond; electrical; threshold; reaction time | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: white noise; 35 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 3, 2, 8 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; 75 cm; 5 cm | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 8, 1, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 50 ms; 474 ms; 69 ms; 155 ms; 126 ms; 51 ms; 30 ms; 54 ms; 7 ms; 71 ms; 61 ms; 1.5-2 s | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 3, 7, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 4, 3, 7 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 65.2 dB; 64.1 dB | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 3, 4 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 3, 1, 2 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 3, 4, 5 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 3, 4, 1 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 238 ms; 332-384 ms | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 5, 1, 2 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; 50 ms; 35 Hz; 5 mA; 11 mA; 512 Hz; 50 Hz; 0.1 Hz; 40 Hz; 100 Hz; 100 ms; 500 ms; 474 ms; 69 ms; 155 ms; 126 ms | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 3, 4, 7 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 238 ms; 332-384 ms; 191238 ms | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 5, 6 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 250 trials | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 1, 2, 3 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 250 trials | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 2, 3, 4 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 250 trials | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 2, 3, 4 |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 1-5 sessions; 96 blocks; 3.2 blocks; 1-7 blocks | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 2, 3, 4 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 250 trials | artifacts/paper_metadata_audit/extracted/opendataloader/disorders_consciousness_2019.json; OpenDataLoader page(s) 2, 3, 4 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
