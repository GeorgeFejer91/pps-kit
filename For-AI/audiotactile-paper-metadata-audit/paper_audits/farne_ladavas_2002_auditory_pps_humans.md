# Farn\xc3\xa8 & L\xc3\xa0davas (2002)

- Record ID: `farne_ladavas_2002_auditory_pps_humans`
- DOI: `10.1162/089892902320474481`
- DOI URL: https://doi.org/10.1162/089892902320474481
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: front/back near/far auditory-tactile extinction task around the head in right-brain-damaged patients
- PDF status: `downloaded`
- Supplement status: `paywalled`
- Supplement acquisition attempts: `1` (`supplement_routes_access_limited`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.49` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 17/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 17/25 fields with candidate values

## Known Prior Gaps

- extract front/back and near/far auditory positions, pure-tone versus complex-sound settings, tactile site and response scoring, trial counts, and extinction-response procedure before templating

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 62 | tone; sound; near; far; db; auditory stimuli; distance; loudspeaker; speaker; approaching; spl | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 1 | duration | source page/section(s) 11 |
| `trial_structure_intermixing` | `completed` | 30 | trial; trials; unimodal; condition; conditions; order; sequence; random; randomly; block; randomized | source page/section(s) 3, 4, 5, 6, 7, 8, 9, 11 |
| `baseline_catch_counts` | `completed` | 15 | catch; unimodal tactile; false alarm; for each; baseline; blocks; no tactile | source page/section(s) 3, 4, 5, 8, 9, 11, 12 |
| `tactile_response_apparatus` | `completed` | 27 | tactile stimulus; respond; response; calibration | source page/section(s) 1, 2, 3, 5, 6, 7, 8, 9 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: white noise; pure tone; 200-3200 Hz; 1.5 kHz | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 2, 11 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: away from body; 50 cm; 20 cm; 70 cm | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11, 2, 8 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 1 sec | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11, 5 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: front; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11, 12, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11, 2, 5 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 12 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 12, 11 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11, 12 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 1 sec | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 12, 11 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11, 12, 3 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 1 sec | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 40 trials | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 12, 3 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 10 trials | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11 |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 40 trials; 10 trials | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 3, 12, 11 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 10 trials; 40 trials | artifacts/paper_metadata_audit/extracted/opendataloader/farne_ladavas_2002_auditory_pps_humans.json; source page/section(s) 11, 12 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
