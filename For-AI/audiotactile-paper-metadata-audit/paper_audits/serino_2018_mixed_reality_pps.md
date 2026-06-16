# Serino et al. (2018 mixed reality)

- Record ID: `serino_2018_mixed_reality_pps`
- DOI: `10.3389/fict.2017.00031`
- DOI URL: https://doi.org/10.3389/fict.2017.00031
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: mixed-reality PPS task using visual or audiovisual looming stimuli paired with tactile detection
- PDF status: `downloaded`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `3` (`not_file_html`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.54` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 21/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 21/25 fields with candidate values

## Known Prior Gaps

- extract whether audio-only trials are available separately from audiovisual trials, the acoustic stimulus/rendering details, tactile timing, response settings, MR apparatus synchronization, and trial counts before deciding whether an audio-tactile-only scaffold is honest

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 12 | auditory stimuli; near; far; distance; sound; approaching; spl; loudspeaker; speaker; headphone; cm/s; dba | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 5 | t4; temporal delay; delays; t1 | source page/section(s) 4, 5, 6, 7, 8 |
| `trial_structure_intermixing` | `completed` | 11 | condition; conditions; order; trial; trials; unimodal; random; randomly; intermingled; block | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 4 | baseline; catch; unimodal tactile; no tactile; total; for each; blocks | source page/section(s) 5, 6, 7, 8 |
| `tactile_response_apparatus` | `completed` | 12 | respond; tactile stimulus; response; reaction time; microphone; stimulator; button; vibration; threshold | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: white noise; 75 Hz; 56 Hz | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 4, 6, 3 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: away from body; approaching trajectory; 6.3 cm; 50 cm; 105 cm; 200 cm; 123 cm | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 4, 5, 9 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 2,600 ms; 400 ms; 500 ms; 1,200 ms; 300 ms; 5,000 ms; 10 ms | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 6, 4, 9 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 75 cm/s | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 5, 6, 4 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; front; right | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 6, 4, 5 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); headphones; HRTF; virtual audio source | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 4, 5, 10 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 6, 5, 8 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 6, 4, 5 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 6, 4, 5 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 10 ms; 2,600 ms; 400 ms; 500 ms; 1,200 ms; 300 ms; 5,000 ms | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 4, 5, 6 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: microphone response capture | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 3, 7, 8 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 5, 6, 8 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; tactile stimulator; 2,600 ms; 400 ms; 500 ms; 1,200 ms; 300 ms; 5,000 ms | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 6, 3, 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 2,600 ms; 400 ms; 500 ms; 1,200 ms; 300 ms; 5,000 ms | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 5, 6, 7 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 5, 6, 8 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 10 ms; 2,600 ms; 400 ms; 500 ms; 1,200 ms; 300 ms; 5,000 ms | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 4, 5, 6 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: no-tactile catch trials; 300 trials; 36 trials; 75 trials; 540 trials; 12 trials; 135 trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 6, 5, 4 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 300 trials; 36 trials; 75 trials; 540 trials; 12 trials; 135 trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 6, 8, 7 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 300 trials; 36 trials; 75 trials; 540 trials; 12 trials; 135 trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 5, 6, 8 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 300 trials; 36 trials; 75 trials; 540 trials; 12 trials; 135 trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 5, 6, 8 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 300 trials; 36 trials; 75 trials; 540 trials; 12 trials; 135 trials | artifacts/paper_metadata_audit/extracted/fallback/serino_2018_mixed_reality_pps/serino_2018_mixed_reality_pps.fallback.txt; source page/section(s) 6, 5, 8 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
