# Noel et al. (2018)

- Record ID: `noel_2018_neural_adaptation`
- DOI: `10.1152/jn.00652.2017`
- DOI URL: https://doi.org/10.1152/jn.00652.2017
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: psychophysical-computational PPS resizing task
- PDF status: `downloaded`
- Supplement status: `paywalled`
- Supplement acquisition attempts: `1` (`supplement_routes_access_limited`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.54` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 21/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 21/25 fields with candidate values

## Known Prior Gaps

- extract velocity levels, peri-face/peri-trunk mapping, timing, tactile settings, response settings, and whether the psychophysical task reuses an existing dynamic PPS scaffold

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 27 | sound; auditory stimuli; approaching; near; far; spl; dba; db; loudspeaker; speaker; distance; cm/s | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 17 | soa; sound onset; t1; t2; t3; t4; t5; duration | source page/section(s) 1, 3, 5, 6, 7, 8, 9, 10 |
| `trial_structure_intermixing` | `completed` | 24 | order; trial; trials; audio-tactile; unimodal; condition; random; randomized; sequence; randomly; conditions | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 7 | repetitions; baseline; catch; total; for each; unimodal tactile | source page/section(s) 1, 3, 11, 12, 13, 18, 24 |
| `tactile_response_apparatus` | `completed` | 23 | electrical; respond; response; reaction time; vibration; button; tactile stimulus; threshold | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: four body-relative directions | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 2, 3, 8 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; 0 cm; 10 cm; 400 cm | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 6, 5 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 500 ms; 200 ms; 100 ms; 1 s; 2 s; 0.66 s; 1.00 s; 1.33 s; 1.66 s; 2.33 s; 15 s | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 22, 11, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 75 cm/s | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 6, 8 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; IN sound; front; rear; left; right | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 16, 3, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); virtual audio source | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 6, 1 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 12, 13 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 11, 15 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 4, 5 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 100 ms; 1 s; 2 s; 0.66 s; 1.00 s; 1.33 s; 1.66 s; 2.33 s; 15 s; 1 ms; 100-250 ms | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 5, 6 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 6, 18 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 12, 13 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: 1 ms; 100-250 ms; 100 ms | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 6, 5, 10 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 100 ms; 200 ms; 500 ms | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 11, 22 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 13, 3, 18 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 100 ms; 1 s; 2 s; 0.66 s; 1.00 s; 1.33 s; 1.66 s; 2.33 s; 15 s; T6 | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 4, 5 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 320 trials | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 12, 4 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 320 trials; 5 trials | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 11, 19 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 320 trials | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 13, 3, 6 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 320 trials | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 12, 6 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 320 trials | artifacts/paper_metadata_audit/extracted/fallback/noel_2018_neural_adaptation/noel_2018_neural_adaptation.fallback.txt; source page/section(s) 3, 6, 10 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
