# Finisguerra et al. (2015)

- Record ID: `finisguerra_2015_moving_sounds_motor`
- DOI: `10.1016/j.neuropsychologia.2014.09.043`
- DOI URL: https://doi.org/10.1016/j.neuropsychologia.2014.09.043
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: moving-sound hand-PPS task with rare tactile targets and motor-system/TMS endpoint
- PDF status: `downloaded`
- Supplement status: `not_found`
- Supplement acquisition attempts: `1` (`checked_no_supplement_candidates`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.49` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 17/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 17/25 fields with candidate values

## Known Prior Gaps

- extract moving-sound trajectory, tactile target schedule, vocal response capture, TMS/MEP trigger timing, baseline timing strategy, and trial counts before templating

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `checked_not_found` - Automated source routes found no supplement candidates; use publisher/source checks again before final missing-value decisions.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 34 | sound; approaching; receding; far; distance; audio stimuli; auditory stimuli; near; loudspeaker; speaker; db | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `timing_soa` | `completed` | 7 | duration; inter-trial; sound onset; temporal delay; delays | source page/section(s) 3, 4, 5, 6 |
| `trial_structure_intermixing` | `completed` | 17 | order; trial; trials; condition; conditions; block; sequence; random; randomly; intermingled | source page/section(s) 1, 2, 3, 4, 5, 6 |
| `baseline_catch_counts` | `completed` | 9 | baseline; blocks; for each; false alarm; total; repetitions; catch | source page/section(s) 2, 3, 4, 5, 6 |
| `tactile_response_apparatus` | `completed` | 20 | respond; electrical; response; threshold; tactile stimulus; electrodes; stimulator; reaction time | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions; IN and OUT sounds | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 2, 3, 4 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: towards body; away from body; approaching trajectory; receding trajectory; 15 cm; 90 cm; 60 cm; 105 cm | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 1, 2, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 50 ms; 300 ms | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 4, 5, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; IN sound; OUT sound; right | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 3, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 3, 2 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 3 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 2, 3, 4 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled; random combination of trials | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 4, 1, 2 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 4-5 s; 10 s; 12 s | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 2, 4 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 4, 3, 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 50 ms; 300 ms | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 5, 4, 6 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: post-sound tactile baseline; 50 ms; 300 ms | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 4, 5, 1 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 144 trials; 24 trials | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 4, 3 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 12 trials; 144 trials; 24 trials | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 2, 3, 4 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 12 trials; 144 trials; 24 trials | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 4, 2 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 144 trials; 24 trials; 12 trials | artifacts/paper_metadata_audit/extracted/opendataloader/finisguerra_2015_moving_sounds_motor.json; source page/section(s) 4, 2, 1 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
