# Galli et al. (2015)

- Record ID: `galli_2015_wheelchair`
- DOI: `10.3389/fpsyg.2015.00639`
- DOI URL: https://doi.org/10.3389/fpsyg.2015.00639
- Coverage category: `covered_blocked_toolkit_structure`
- Task family: front/back trunk tactile PPS with dynamic auditory field
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.47` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 16/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 16/25 fields with candidate values

## Known Prior Gaps

- None recorded in the prior coverage ledger.

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 31 | far; approaching; sound; distance; loudspeaker; speaker; cm/s; dba; db; auditory stimuli; near; unity | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 6 | temporal delay; delays; sound onset; inter-trial; duration | OpenDataLoader page(s) 2, 3, 4, 5 |
| `trial_structure_intermixing` | `completed` | 28 | order; condition; random; randomly; trial; trials; unimodal; intermingled; block; conditions; sequence | OpenDataLoader page(s) 2, 3, 4, 5, 6, 8, 9, 10 |
| `baseline_catch_counts` | `completed` | 9 | baseline; catch; unimodal tactile; total; repetitions; for each | OpenDataLoader page(s) 3, 4, 5, 6, 7 |
| `tactile_response_apparatus` | `completed` | 19 | respond; tactile stimulus; response; reaction time; vibration; button; threshold | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 9 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: 150 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; 27.5 cm | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 380 ms; 760 ms; 1.140 ms; 1.520 ms; 1,900 ms; 2,280 ms; 500 ms; 3.66 s | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3, 4, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 75 cm/s | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3, 4 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: front; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3, 5, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3, 4, 5 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 4, 5, 2 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 500 ms; 3.66 s; 100 ms; 1000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 4, 3, 5 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 4, 3 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 100 ms; 60 mA; 150 Hz; 1000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3, 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 380 ms; 760 ms; 1.140 ms; 1.520 ms; 1,900 ms; 2,280 ms; 1000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3, 2, 5 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3, 5, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: post-sound tactile baseline; 380 ms; 760 ms; 1.140 ms; 1.520 ms; 1,900 ms; 2,280 ms; 100 ms; 500 ms; 3.66 s | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 3, 4 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/galli_2015_wheelchair.json; OpenDataLoader page(s) 4, 3 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
