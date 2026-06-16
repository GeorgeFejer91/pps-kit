# Lerner et al. (2021)

- Record ID: `lerner_2021_3d_boundary`
- DOI: `10.3389/frvir.2021.644214`
- DOI URL: https://doi.org/10.3389/frvir.2021.644214
- Coverage category: `covered_blocked_toolkit_structure`
- Task family: VR 3D audio-tactile PPS boundary estimation
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.53` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 20/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 20/25 fields with candidate values

## Known Prior Gaps

- exact Unity/3D Tune-In stimulus engine behavior

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 34 | sound; far; distance; receding; spl; unity; audio stimuli; pink noise; cm/s; db; tone | OpenDataLoader page(s) 1, 2, 4, 6, 7, 8, 9, 10 |
| `timing_soa` | `completed` | 4 | duration; soa; delays | OpenDataLoader page(s) 8, 9, 10 |
| `trial_structure_intermixing` | `completed` | 30 | audio-tactile; order; condition; conditions; random; trial; trials; block | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 9 | for each; total; blocks | OpenDataLoader page(s) 8, 10, 11, 12, 13 |
| `tactile_response_apparatus` | `completed` | 26 | respond; reaction time; threshold; vibration; calibration; tactile stimulus; response | OpenDataLoader page(s) 1, 3, 6, 9, 10, 11, 12, 13 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; white noise; 35 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 8, 12 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: Unity; pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 8, 9 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: 130 cm; 22 cm | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 11, 12, 8 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 100 ms; 5.5 s | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 9, 8, 10 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 100 cm/s; 22 cm/s | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 8, 12, 9 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: left; right | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 10, 2, 8 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 22 dB | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 9, 8 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: Unity; virtual audio source | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 11, 7, 8 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: random combination of trials | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 8, 10, 11 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order; 2 blocks | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 8, 10, 11 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 0.5 s; 5.5 s | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 11, 8, 10 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 11, 9, 10 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 200 Hz; 50 Hz; 100 ms; 35 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 10, 9, 8 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 9, 8, 10 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 5.5 s; 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 8, 9, 10 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 10 trials; 24 trials; 144 trials | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 8, 9, 10 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 10 trials; 24 trials; 144 trials | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 9, 10, 11 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 10 trials; 24 trials; 144 trials | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 9, 10, 11 |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 2 blocks | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 10, 11, 8 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 24 trials; 144 trials; 10 trials | artifacts/paper_metadata_audit/extracted/opendataloader/lerner_2021_3d_boundary.json; OpenDataLoader page(s) 10, 9, 11 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
