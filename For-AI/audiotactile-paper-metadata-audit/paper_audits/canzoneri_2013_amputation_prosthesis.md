# Canzoneri et al. (2013b)

- Record ID: `canzoneri_2013_amputation_prosthesis`
- DOI: `10.1038/srep02844`
- DOI URL: https://doi.org/10.1038/srep02844
- Coverage category: `covered_blocked_missing_publication_parameters`
- Task family: Canzoneri-style dynamic PPS task
- PDF status: `downloaded`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `11` (`not_file_html`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.54` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 21/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 21/25 fields with candidate values

## Known Prior Gaps

- exact trial count and tactile calibration table

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 20 | distance; sound; approaching; receding; far; auditory stimuli; loudspeaker; speaker; near; pink noise; db | source page/section(s) 1, 2, 3, 4, 6, 7 |
| `timing_soa` | `completed` | 9 | t1; temporal delay; delays; t5; t2; t3; t4; soa | source page/section(s) 1, 2, 4, 5, 6, 7 |
| `trial_structure_intermixing` | `completed` | 24 | audio-tactile; order; unimodal; condition; conditions; trial; block; blocked; trials; random; randomly; intermingled | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `baseline_catch_counts` | `completed` | 7 | for each; false alarm; blocks; total; catch | source page/section(s) 2, 4, 7 |
| `tactile_response_apparatus` | `completed` | 10 | respond; tactile stimulus; threshold; response; electrical; stimulator; electrodes; voice | source page/section(s) 1, 2, 4, 5, 6, 7 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 4 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 4, 6, 7 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: IN and OUT sounds | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 2 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: near loudspeaker; far loudspeaker; towards body; approaching trajectory; receding trajectory; 100 cm | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 4, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 440 ms; 430 ms; 414 ms; 402 ms; 404 ms | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 3, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; IN sound; OUT sound | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 4 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 4 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 2 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 2 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 402 ms; 404 ms | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 4 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: vocal response; voice-key response capture | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 4, 6 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore sound; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator; 3000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 2 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: T1 IN and T5 OUT (farthest distance from the body), T2 IN and T4 OUT (far distance), T3 IN and T3 OUT (intermediate distance), T4 IN and T2 OUT (close distance), and T5 IN and T1 O | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 2, 6 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 4, 2 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 76 trials; 36 trials | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 2 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 36 trials; 76 trials | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7 |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 2 blocks | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7, 4 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 36 trials; 76 trials | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2013_amputation_prosthesis.json; source page/section(s) 7 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
