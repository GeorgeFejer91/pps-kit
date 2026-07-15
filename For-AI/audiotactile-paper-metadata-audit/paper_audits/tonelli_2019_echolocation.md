# Tonelli et al. (2019)

- Record ID: `tonelli_2019_echolocation`
- DOI: `10.1007/s00221-019-05469-3`
- DOI URL: https://doi.org/10.1007/s00221-019-05469-3
- Coverage category: `covered_runnable_profile`
- Task family: seven-speaker audio-tactile PPS task
- PDF status: `downloaded`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `13` (`downloaded`)
- Supplement extracted text files: `1`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.56` (`partial_extraction`)
- Confidence basis: Manual review supplies enough Segment 1-4 parameters for a runnable virtual seven-distance lateral moving-source recreation; retained unresolved items are provenance caveats, not current runnable blockers.
- Automated evidence mining: `source_mined`; 22/25 fields with candidate values
- PPS visualization mining: `source_mined`; 6/9 visualization-form candidates

## Known Prior Gaps

- exact original white-noise asset
- exact loudspeaker switching/gain transfer law
- numeric response timeout
- unfixed experimenter-started ITI distribution

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `available_for_review` - Downloaded or locally provided supplement files are available for methods/table review.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 11 | tone; sound; auditory stimuli; approaching; far; distance; loudspeaker; speaker; cm/s; db; headphone; dba | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 4 | temporal delay; delays; inter-trial; jitter; duration | source page/section(s) 3, 4, 6, 8 |
| `trial_structure_intermixing` | `completed` | 8 | audio-tactile; trial; trials; block; unimodal; random; randomly; condition; order | source page/section(s) 1, 2, 3, 4, 5, 6, 8, supplement |
| `baseline_catch_counts` | `completed` | 7 | total; catch; unimodal tactile; for each; blocks; baseline | source page/section(s) 2, 3, 4, 5, 6, 7, supplement |
| `tactile_response_apparatus` | `completed` | 9 | reaction time; tactile stimulus; vibro-tactile; vibration; respond; response; threshold; microphone | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `pps_visualization_reporting` | `completed` | 11 | reaction time; rt; fig.; erp; threshold; boundary; plot; facilitation; map; model; figure | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## PPS Visualization Candidates

| Visualization type | Candidate status | Detected terms | Source pointer | Visual verification required | Plotted-parameter checklist | Manual review fields |
|---|---|---|---|---|---|---|
| `rt_by_soa_or_distance_curve` | `inferred_low_confidence` | rt; temporal delay; distance; facilitation; reaction time | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 3, 8, 1 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `pps_boundary_or_size_index` | `inferred_low_confidence` | pps boundary; boundary; threshold; extension | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 8, 4 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `condition_group_bar_box_summary` | `inferred_low_confidence` | bar plot; mean; condition; group; pre; post; baseline; comparison; standard error | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 5, 6, 7 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `spatial_map_heatmap_or_body_boundary` | `inferred_low_confidence` | map; peri-hand; body-centered; schema | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 10 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `apparatus_trajectory_schematic` | `inferred_low_confidence` | fig.; speaker; loudspeaker; looming; participant; tactile; source; approaching | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 2, 3, 4 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `neural_trace_topography_or_brain_map` | `inferred_low_confidence` | erp; tms; brain; cortex | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 8 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: white noise; 500 Hz tone; click; 500 Hz | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 2, 1, 4 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: towards body; approaching trajectory; 17 cm; 119 cm; 102 cm; 34 cm; 30 cm; 4.5 cm | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 20 s; 75 ms; 900 ms; 497.57 ms; 116.25 ms; 3 s; 20 ms | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 4, 6, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 34 cm/s | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; front; left; right | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 5, 7, 3 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); headphones | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; unimodal tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 2, 4, 3 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: pseudo-randomized | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order; pseudo-randomized | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 4, 2, 6 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: ITI not fixed; jittered interval; 20 s; 75 ms; 900 ms; 3 s; 20 ms | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 4, 2, 5 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: microphone response capture; speeded response | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 1, 3, 4 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 3, 4, 5 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 20 ms; 500 ms; 500 Hz; 75 ms; 900 ms | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 500 ms; 20 ms; 75 ms; 900 ms | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 3, 2, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 5, 3, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 3 s; 20 ms; 500 ms; 20 s; 75 ms; 900 ms | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials; 49 trials; 140 trials; 12 trials; 40 trials; 30 trials; 80 trials | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 3, 4, 2 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 49 trials; 140 trials; 12 trials; 40 trials; 30 trials; 80 trials | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 4, 5, 6 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 49 trials; 140 trials; 12 trials; 40 trials; 30 trials; 80 trials | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 5, 3, 4 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 49 trials; 140 trials; 12 trials; 40 trials; 30 trials; 80 trials | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 3, 4, 2 |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 2 blocks; 14 session | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 4, 2, 5 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 49 trials; 140 trials; 12 trials; 40 trials; 30 trials; 80 trials | artifacts/paper_metadata_audit/extracted/fallback/tonelli_2019_echolocation/tonelli_2019_echolocation.fallback.txt; source page/section(s) 4, 5, 7 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
