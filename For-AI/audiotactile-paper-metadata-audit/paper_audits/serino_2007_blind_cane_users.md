# Serino et al. (2007)

- Record ID: `serino_2007_blind_cane_users`
- DOI: `10.1111/j.1467-9280.2007.01952.x`
- DOI URL: https://doi.org/10.1111/j.1467-9280.2007.01952.x
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: static near/far weak-target Go/NoGo tactile detection
- PDF status: `downloaded`
- Supplement status: `paywalled`
- Supplement acquisition attempts: `1` (`supplement_routes_access_limited`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.43` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 13/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 13/25 fields with candidate values

## Known Prior Gaps

- full calibration and response-capture implementation details need extraction

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 40 | far; auditory stimuli; near; db; sound; distance; loudspeaker; speaker; approaching; tone | source page/section(s) 1, 2, 3, 4, 5, 6 |
| `timing_soa` | `completed_no_hits` | 0 |  |  |
| `trial_structure_intermixing` | `completed` | 21 | audio-tactile; condition; conditions; trial; trials; order; block; blocked | source page/section(s) 1, 2, 3, 4, 5, 6 |
| `baseline_catch_counts` | `completed` | 3 | catch; total; for each | source page/section(s) 2, 3, 4 |
| `tactile_response_apparatus` | `completed` | 18 | respond; electrical; reaction time; electrodes; response; voice; stimulator | source page/section(s) 1, 2, 3, 4, 5 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: white noise | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 3, 4, 1 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: away from body; 125 cm; 30 cm | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 2, 1 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 5 ms; 697 ms; 648 ms; 653 ms | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 3, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: front; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 3, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 3, 1, 2 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 3, 1, 2 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 2, 4 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore sound; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 2, 3 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 2, 3 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 150 trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 2, 1 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 150 trials; 30 trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 2, 3, 4 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 150 trials; 30 trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 2, 3, 4 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 150 trials; 30 trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2007_blind_cane_users.json; source page/section(s) 3, 2 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
