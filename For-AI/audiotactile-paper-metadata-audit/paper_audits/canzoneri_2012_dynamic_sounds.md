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
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.56` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 22/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 22/25 fields with candidate values

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
| `stimulus_reconstruction` | `completed` | 8 | sound; approaching; receding; near; far; distance; db; pink noise; auditory stimuli; loudspeaker; speaker; spl | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 6 | delays; t1; silence; temporal delay; sound onset; t2; t3; t4; t5; duration | source page/section(s) 1, 2, 3, 4, 5, 8 |
| `trial_structure_intermixing` | `completed` | 8 | audio-tactile; condition; order; trial; trials; conditions; intermingled; unimodal; random; randomly; block | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 3 | catch; for each; without any sound; false alarm; total; blocks | source page/section(s) 2, 3, 5 |
| `tactile_response_apparatus` | `completed` | 8 | tactile stimulus; respond; stimulator; electrical; electrodes; response; threshold; voice; reaction time | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; 44.1 kHz | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 2, 5, 3 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: SoundForge; samples of pink noise; pink-noise samples | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 2, 3, 5 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions; IN and OUT sounds | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 1, 4 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: near loudspeaker; far loudspeaker; towards body; approaching trajectory; receding trajectory | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 2, 1, 5 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 76 s; 20.70 ms; 2.15 ms | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 5 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; IN sound; OUT sound; rear; right | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 5 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 2, 1, 3 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 2, 3, 6 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled; random combination of trials | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 1, 2 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 1, 2 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: silence interval; 76 s | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 1 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: voice-key response capture | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 5, 3, 2 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore auditory stimulus; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 5 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator; 20.70 ms; 2.15 ms | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 2, 3, 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 20.70 ms; 2.15 ms; T1, T2, T3, T4, T5, T6) | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 5, 1 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: tactile-only/no-sound baseline; silence baseline window | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 1 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 76 s; T0; T6 | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 1 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 112 trials; 80 trials | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 1 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 112 trials; 80 trials | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 5 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 112 trials; 80 trials | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 1 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 112 trials; 80 trials | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 1 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 112 trials; 80 trials | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2012_dynamic_sounds/canzoneri_2012_dynamic_sounds.fallback.txt; source page/section(s) 3, 2, 1 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
