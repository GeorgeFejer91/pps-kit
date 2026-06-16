# Noel et al. (2018)

- Record ID: `noel_2018_neural_adaptation`
- DOI: `10.1152/jn.00652.2017`
- DOI URL: https://doi.org/10.1152/jn.00652.2017
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: psychophysical-computational PPS resizing task
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.52` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 19/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 19/25 fields with candidate values

## Known Prior Gaps

- extract velocity levels, peri-face/peri-trunk mapping, timing, tactile settings, response settings, and whether the psychophysical task reuses an existing dynamic PPS scaffold

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 136 | sound; auditory stimuli; approaching; near; far; dba; db; loudspeaker; speaker; cm/s; distance; audio stimuli | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 8, 9 |
| `timing_soa` | `completed` | 13 | sound onset; t1; t2; t3; t4; t5; duration | OpenDataLoader page(s) 3, 6, 7, 8, 10, 11, 18, 22 |
| `trial_structure_intermixing` | `completed` | 66 | order; trial; trials; audio-tactile; unimodal; random; condition; randomized; sequence; randomly; conditions | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 14 | repetitions; for each; baseline; catch; unimodal tactile; total | OpenDataLoader page(s) 1, 3, 11, 13, 18, 24 |
| `tactile_response_apparatus` | `completed` | 64 | electrical; respond; response; reaction time; vibration; button; tactile stimulus; threshold | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; 25 cm; 50 cm; 75 cm; 100 cm; 125 cm; 150 cm; 175 cm; 20 cm; 40 cm; 10 cm; 400 cm | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3, 5 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 1 s; 2 s; 3 s; 4 s; 5 s; 6 s; 7 s; 0.33 s; 0.66 s; 1.00 s; 1.33 s; 1.66 s; 2.00 s; 2.33 s; 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3, 10, 11 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 25 cm/s; 75 cm/s | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3, 6 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: IN sound; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 16, 13, 18 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 50 dB | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3, 10 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3, 11 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 1 s; 2 s; 3 s; 4 s; 5 s; 6 s; 7 s; 0.33 s; 0.66 s; 1.00 s; 1.33 s; 1.66 s; 2.00 s; 2.33 s | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: 100 ms; 200 ms; 18.4 ms; 10.9 ms | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 10, 11, 13 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 100 ms; 200 ms; T1 1 s, T2 2 s, T3 3 s, T4 4 s, T5 5 s, T6 6 s, T7 7 s | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3, 10, 11 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3, 11, 13 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 1 s; 2 s; 3 s; 4 s; 5 s; 6 s; 7 s; 0.33 s; 0.66 s; 1.00 s; 1.33 s; 1.66 s; 2.00 s; 2.33 s; 50 ms; 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 320 trials | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 5 trials; 320 trials | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3, 11 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 320 trials | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 320 trials | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2018_neural_adaptation.json; OpenDataLoader page(s) 3 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
