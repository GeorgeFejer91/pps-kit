# Lost in time and space? (2024)

- Record ID: `depersonalisation_2024`
- DOI: `10.1177/17470218241261645`
- DOI URL: https://doi.org/10.1177/17470218241261645
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: audio-tactile PPS and time-perception task
- PDF status: `downloaded`
- Supplement status: `paywalled`
- Supplement acquisition attempts: `1` (`supplement_routes_access_limited`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.53` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 20/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 20/25 fields with candidate values

## Known Prior Gaps

- determine PPS-task parameters separately from time-perception measures

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 16 | far; near; sound; approaching; spl; distance; pink noise; auditory stimuli; loudspeaker; speaker; db; receding | source page/section(s) 2, 3, 4, 5, 6, 7, 9, 10 |
| `timing_soa` | `completed` | 4 | duration; temporal delay; delays; silence | source page/section(s) 2, 3, 4, 5 |
| `trial_structure_intermixing` | `completed` | 24 | audio-tactile; condition; order; conditions; trial; trials; unimodal; random; randomly | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 7 | total; catch; baseline; unimodal tactile; for each | source page/section(s) 3, 5, 6, 8 |
| `tactile_response_apparatus` | `completed` | 20 | response; respond; reaction time; threshold; tactile stimulus; stimulator; electrical; electrodes; vibration; voice | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 4, 5 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 4, 6, 5 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 4, 5, 6 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: near loudspeaker; far loudspeaker; towards body; approaching trajectory; receding trajectory | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 300 ms; 800 ms | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 4, 5 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; front; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 4, 5 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 4, 5 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 6 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 3, 4 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: silence interval; 300 ms; 800 ms | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 4, 5 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore auditory stimulus; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 4, 6 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; vibrotactile stimulation; tactile stimulator; 300 ms; 800 ms | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 4, 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 300 ms; 800 ms | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline; silence baseline window | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 300 ms; 800 ms | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 4 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 3, 4 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 24 trials; 72 trials; 12 trials | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 6, 4 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 24 trials; 72 trials; 12 trials | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 6, 4 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 24 trials; 72 trials; 12 trials | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 6, 3 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 24 trials; 72 trials; 12 trials | artifacts/paper_metadata_audit/extracted/opendataloader/depersonalisation_2024.json; source page/section(s) 5, 6, 3 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
