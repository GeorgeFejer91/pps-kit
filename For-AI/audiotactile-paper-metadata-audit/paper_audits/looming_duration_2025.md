# Impact of looming sound duration on PPS measurement (2025)

- Record ID: `looming_duration_2025`
- DOI: `10.61782/fa.2025.0866`
- DOI URL: https://doi.org/10.61782/fa.2025.0866
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: looming-cue tactile-response PPS task varying auditory duration
- PDF status: `downloaded`
- Supplement status: `not_found`
- Supplement acquisition attempts: `2` (`checked_no_supplement_candidates`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.49` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 17/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 17/25 fields with candidate values

## Known Prior Gaps

- live PDF check reports 2 s/3 s right-lateral looming pink-noise tasks, seven SOAs per duration, 16 repetitions per delay/condition, 21 auditory-only catch trials, 80 Hz 200 ms sawtooth tactile stimulation, response button, starting distances, and speed; exact original MATLAB HRTF implementation and tactile-waveform profile are not current first-class toolkit inputs

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `checked_not_found` - Automated source routes found no supplement candidates; use publisher/source checks again before final missing-value decisions.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 26 | sound; approaching; far; near; speaker; headphone; spl; distance; pink noise; hrtf; receding; auditory stimuli | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `timing_soa` | `completed` | 17 | duration; temporal delay; delays; t1; t2; t3; t4; t5 | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `trial_structure_intermixing` | `completed` | 23 | audio-tactile; condition; conditions; trial; trials; block; unimodal; order | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `baseline_catch_counts` | `completed` | 15 | baseline; catch; total; repetitions; for each | source page/section(s) 2, 3, 4, 5, 6 |
| `tactile_response_apparatus` | `completed` | 16 | reaction time; respond; tactile stimulus; response; calibration; button; actuator | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; 80 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3, 2 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: towards body; away from body; approaching trajectory; 153.6 cm; 12 cm; 100 cm; 0 cm; 189 cm | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 1, 6 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 1000 ms; 1750 ms; 2625 ms; 200 ms; 3 s; 2 s | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3, 1 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 22 cm/s; 210 cm/s | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3, 6 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; front; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 2, 1 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: speaker(s); headphones; HRTF; virtual audio source | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 2, 6, 1 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3, 2 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 1000 ms; 1750 ms; 2625 ms; 3 s; 2 s | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3, 1 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: tactile actuator; 80 Hz; 200 ms; 1750 ms; 2625 ms; 1000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3, 1 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 1000 ms; 1750 ms; 2625 ms; T1, T2, T3, T4, T5, T6) | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3, 4, 5 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 1000 ms; 1750 ms; 2625 ms; 200 ms; 3 s; 2 s | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3, 1 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 224 trials; 245 trials | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3, 1 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 224 trials; 245 trials | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 224 trials; 245 trials | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 224 trials; 245 trials | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 224 trials; 245 trials | artifacts/paper_metadata_audit/extracted/opendataloader/looming_duration_2025.json; source page/section(s) 3 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
