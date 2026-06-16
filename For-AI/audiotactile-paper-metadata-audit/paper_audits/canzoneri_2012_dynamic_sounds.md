# Canzoneri et al. (2012)

- Record ID: `canzoneri_2012_dynamic_sounds`
- DOI: `10.1371/journal.pone.0044306`
- DOI URL: https://doi.org/10.1371/journal.pone.0044306
- Coverage category: `covered_blocked_toolkit_structure`
- Task family: canonical dynamic looming/receding sound with tactile detection
- PDF status: `downloaded`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `5` (`not_file_html`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.47` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 16/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 16/25 fields with candidate values

## Known Prior Gaps

- exact original SoundForge gain/envelope files
- voice-key response capture
- electrical tactile threshold calibration

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 32 | approaching; near; sound; receding; distance; far; db; auditory stimuli; pink noise; loudspeaker; speaker; spl | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `timing_soa` | `completed` | 9 | delays; temporal delay; silence; duration; t1; t2; t3; t4; t5; sound onset | source page/section(s) 1, 2, 3, 5 |
| `trial_structure_intermixing` | `completed` | 18 | audio-tactile; condition; order; conditions; trial; trials; intermingled; unimodal | source page/section(s) 1, 2, 3, 5, 6, 7 |
| `baseline_catch_counts` | `completed` | 4 | catch; for each; total; false alarm | source page/section(s) 2, 3, 5 |
| `tactile_response_apparatus` | `completed` | 15 | tactile stimulus; respond; response; reaction time; stimulator; electrical; electrodes; threshold | source page/section(s) 1, 2, 3, 5, 6, 7 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; 44.1 kHz | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 5, 6 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: SoundForge; Sonic Foundry; samples of pink noise; pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 5, 3 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: IN and OUT sounds | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 5, 6 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: near loudspeaker; far loudspeaker; towards body; away from body; approaching trajectory; receding trajectory; 100 cm | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 6 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 3000 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 100 msec | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 5, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; IN sound; OUT sound; right | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 7, 3 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB; 55 dB | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 3, 1 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 1, 3 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 3 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: silence interval; 3000 ms; 19.60 ms; 22.54 ms; 20.59 ms; 20.70 ms; 0.03 ms; 2.15 ms | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 5 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 3, 2 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 1, 3 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 478 ms; T1 corresponds to 300 ms, T2 to 800 ms, T3 to 1500 ms, T4 to 2200 ms and T5 to 2700 ms | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 5, 3 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: silence baseline window | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 1, 3 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 100 msec | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 2, 1, 3 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/canzoneri_2012_dynamic_sounds.json; source page/section(s) 3, 1 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
