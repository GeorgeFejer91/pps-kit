# Bernasconi/Noel et al. (2018)

- Record ID: `ieeg_trunk_2018`
- DOI: `10.1093/cercor/bhy156`
- DOI URL: https://doi.org/10.1093/cercor/bhy156
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: approaching auditory stimuli plus trunk tactile stimulation during iEEG
- PDF status: `downloaded`
- Supplement status: `paywalled`
- Supplement acquisition attempts: `2` (`supplement_routes_access_limited`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.47` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 16/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 16/25 fields with candidate values

## Known Prior Gaps

- extract exact approaching-sound trajectory, far/intermediate/close tactile timings, trunk tactile apparatus, and response/event settings; iEEG endpoint is non-blocking for audiotactile recreation

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 24 | sound; auditory stimuli; approaching; far; distance; near; speaker | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 2 | duration; jitter | source page/section(s) 3 |
| `trial_structure_intermixing` | `completed` | 25 | trial; trials; audio-tactile; condition; random; randomized; randomly; conditions; order; unimodal | source page/section(s) 3, 4, 5, 6, 7, 8, 9, 10 |
| `baseline_catch_counts` | `completed` | 14 | total; for each; baseline; false alarm; no tactile | source page/section(s) 3, 4, 5, 6 |
| `tactile_response_apparatus` | `completed` | 54 | respond; electrodes; response; electrical; vibration; arduino; microphone; tactile stimulus; threshold | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: white noise; 150 Hz; 10 kHz | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 1 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; 100 cm | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 8, 3, 1 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 50 ms; 100 ms; 3 s; 500 ms; 1500 ms; 0-200 ms; 1.9 s; 800 ms; 3000 ms; 300 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; IN sound; front | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 5, 3 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: speaker(s); Arduino | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 4 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 5, 4 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 10 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 10 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: jittered interval; 3 s; 500 ms; 1500 ms; 0-200 ms; 50 ms; 1.9 s; 800 ms; 3000 ms; 100 ms; 300 ms; 0-300 ms; 0 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 4, 5 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: microphone response capture | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 5 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 60 mA; 150 Hz; 50 ms; 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 10, 3, 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 50 ms; 100 ms; 500 ms; 1500 ms; 0-200 ms; 800 ms; 3000 ms; 300 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 50 ms; 100 ms; 3 s; 500 ms; 1500 ms; 0-200 ms; 1.9 s; 800 ms; 3000 ms; 300 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 4 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 85 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 4, 5 |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 85 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 5, 3, 4 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 85 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ieeg_trunk_2018.json; source page/section(s) 3, 4 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
