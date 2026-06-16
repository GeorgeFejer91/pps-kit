# Pregnancy PPS study (2019)

- Record ID: `pregnancy_2019`
- DOI: `10.1038/s41598-019-45224-w`
- DOI URL: https://doi.org/10.1038/s41598-019-45224-w
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: audio-tactile PPS measurement in pregnancy context
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.54` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 21/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 21/25 fields with candidate values

## Known Prior Gaps

- extract exact audio-tactile PPS timing, distances, trial counts, and response settings; pregnancy context is non-blocking

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 21 | near; far; auditory stimuli; sound; distance; approaching; pink noise; loudspeaker; speaker; db; spl | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6 |
| `timing_soa` | `completed` | 6 | delays; sound onset; silence; temporal delay; duration | OpenDataLoader page(s) 2, 5, 6 |
| `trial_structure_intermixing` | `completed` | 19 | audio-tactile; condition; order; trial; trials; random; sequence; conditions; unimodal | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6 |
| `baseline_catch_counts` | `completed` | 7 | total; for each; unimodal tactile; catch | OpenDataLoader page(s) 2, 3, 6 |
| `tactile_response_apparatus` | `completed` | 8 | respond; reaction time; tactile stimulus; response; arduino | OpenDataLoader page(s) 1, 2, 4, 5, 6 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; 44.1 kHz | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 1 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: samples of pink noise; pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 3 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: near loudspeaker; far loudspeaker; towards body; away from body; approaching trajectory | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 6, 1 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 3000 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2500 ms | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; left | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 6, 5 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 6 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); Arduino | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 6 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 6 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 6, 3 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: silence interval; 3000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 6 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: speeded response | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 6, 2, 5 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore sound; catch/no-target trials | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 6, 5 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2500 ms | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 2, 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 300 ms; 800 ms; 1500 ms; 2200 ms; 2500 ms | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 6, 2 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline; silence baseline window | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 6, 5 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: post-sound tactile baseline; 300 ms; 800 ms; 1500 ms; 2200 ms; 2500 ms | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 5, 6, 2 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 65 trials | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 6, 5 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 65 trials | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 6, 2 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 65 trials | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 6, 5 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 65 trials | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 6, 5 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 65 trials | artifacts/paper_metadata_audit/extracted/opendataloader/pregnancy_2019.json; OpenDataLoader page(s) 6, 2, 5 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
