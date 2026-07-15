# Galli et al. (2015)

- Record ID: `galli_2015_wheelchair`
- DOI: `10.3389/fpsyg.2015.00639`
- DOI URL: https://doi.org/10.3389/fpsyg.2015.00639
- Coverage category: `covered_runnable_profile`
- Task family: front/back trunk tactile PPS with dynamic auditory field
- PDF status: `downloaded`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `7` (`http_404`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.43` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 13/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 13/25 fields with candidate values
- PPS visualization mining: `source_mined`; 7/9 visualization-form candidates

## Known Prior Gaps

- No remaining publication-parameter gap recorded in the current coverage ledger.

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `reviewed_for_profile_recreation` - Frontiers HTML/source review confirmed the array geometry, Gaussian amplitude field, 75 cm/s front/back loom, tactile timing anchors, baseline/catch roles, 500 ms ITI, and 216-trial PPS-assessment formula.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 11 | far; db; sound; approaching; distance; dba; auditory stimuli; loudspeaker; speaker; near; cm/s; spl | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 9 | t2; delays; t3; temporal delay; sound onset; t1; tbefore; inter-trial; duration | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `trial_structure_intermixing` | `completed` | 10 | condition; random; randomly; order; trial; trials; unimodal; conditions; intermingled; block; sequence | source page/section(s) 2, 3, 4, 5, 6, 7, 8, 9 |
| `baseline_catch_counts` | `completed` | 4 | baseline; catch; unimodal tactile; total; repetitions; for each | source page/section(s) 3, 4, 5, 7 |
| `tactile_response_apparatus` | `completed` | 9 | tactile stimulus; respond; response; reaction time; vibration; button; threshold | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 9 |
| `pps_visualization_reporting` | `completed` | 11 | rt; reaction time; boundary; map; model; figure; threshold; graph; erp; plot; eeg | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## PPS Visualization Candidates

| Visualization type | Candidate status | Detected terms | Source pointer | Visual verification required | Plotted-parameter checklist | Manual review fields |
|---|---|---|---|---|---|---|
| `rt_by_soa_or_distance_curve` | `inferred_low_confidence` | reaction time; rt; temporal delay; distance; t1; t2; t3; d1; d2 | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 5, 3, 6 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `pps_boundary_or_size_index` | `inferred_low_confidence` | threshold; extension; extent | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 4 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `condition_group_bar_box_summary` | `inferred_low_confidence` | mean; sem; condition; group; pre; post; baseline; comparison | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 5, 7, 8 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `spatial_map_heatmap_or_body_boundary` | `inferred_low_confidence` | map; near space; body-centered | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 9 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `near_far_or_distance_bin_plot` | `inferred_low_confidence` | distant; d1; d2; d3; d4; d5; d6; close; near; far | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 6, 5, 3 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `apparatus_trajectory_schematic` | `inferred_low_confidence` | figure; schematic; setup; speaker; loudspeaker; approaching; looming; participant; tactile; source | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 3, 2, 4 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `neural_trace_topography_or_brain_map` | `inferred_low_confidence` | erp; tms; brain; cortex | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 11 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: away from body; approaching trajectory; 27.5 cm | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 3, 2, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 500 ms; 3.66 s | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 3, 4, 6 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; IN sound; front; left; right | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 3, 4, 6 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 3, 4, 5 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 500 ms; 3.66 s | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 4, 3, 6 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 2, 5, 3 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 4, 3, 5 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 3, 1, 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 3, 4, 5 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 500 ms; 3.66 s; Tbefore | artifacts/paper_metadata_audit/extracted/fallback/galli_2015_wheelchair/galli_2015_wheelchair.fallback.txt; source page/section(s) 4, 3, 6 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
