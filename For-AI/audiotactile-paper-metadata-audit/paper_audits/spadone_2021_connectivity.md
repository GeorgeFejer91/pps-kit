# Spadone et al. (2021)

- Record ID: `spadone_2021_connectivity`
- DOI: `10.1038/s41598-021-00048-5`
- DOI URL: https://doi.org/10.1038/s41598-021-00048-5
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: fMRI audio-tactile task with looming/flat and near/far conditions
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.47` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 16/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 16/25 fields with candidate values

## Known Prior Gaps

- extract near/far, flat/dynamic, and fMRI block timing separately from scanner context

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 41 | sound; approaching; near; far; receding; spl; distance; pink noise; auditory stimuli; loudspeaker; speaker; db | OpenDataLoader page(s) 1, 2, 3, 4, 6, 7, 8, 9 |
| `timing_soa` | `completed` | 9 | t2; t3; t5; temporal delay; delays; sound onset; t1; t4; duration | OpenDataLoader page(s) 1, 2, 7, 9, 10, 11 |
| `trial_structure_intermixing` | `completed` | 37 | trial; audio-tactile; order; trials; condition; conditions; block; random; randomly; sequence; intermingled | OpenDataLoader page(s) 1, 2, 3, 4, 6, 7, 8, 9 |
| `baseline_catch_counts` | `completed` | 16 | for each; blocks; total; catch; false alarm | OpenDataLoader page(s) 1, 2, 3, 4, 6, 7, 9, 10 |
| `tactile_response_apparatus` | `completed` | 19 | respond; response; threshold; electrodes; tactile stimulus; button | OpenDataLoader page(s) 2, 3, 4, 7, 8, 9, 10, 11 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 10 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 10, 8 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; 100 cm; 97.7 cm; 95.3 cm; 88.6 cm; 70.5 cm; 41.7 cm; 98 cm | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 7, 10 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 3100 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms; 411 ms; 2241 ms | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 10 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; front; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 7, 8, 9 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB; 62.5 dB | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 7, 10 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 10 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 11, 9, 10 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled; random combination of trials | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 10 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 10 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 3100 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms; 1550 ms; 30 ms | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 10 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 11, 2 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore auditory stimulus; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 10, 9, 11 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: 3100 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 10, 8 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 3100 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 10 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: post-sound tactile baseline; 3100 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms; 411 ms; 2241 ms; 1550 ms; 30 ms | artifacts/paper_metadata_audit/extracted/opendataloader/spadone_2021_connectivity.json; OpenDataLoader page(s) 9, 10 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
