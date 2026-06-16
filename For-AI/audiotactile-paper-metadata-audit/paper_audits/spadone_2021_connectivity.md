# Spadone et al. (2021)

- Record ID: `spadone_2021_connectivity`
- DOI: `10.1038/s41598-021-00048-5`
- DOI URL: https://doi.org/10.1038/s41598-021-00048-5
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: fMRI audio-tactile task with looming/flat and near/far conditions
- PDF status: `downloaded`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `22` (`not_file_html`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.49` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 17/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 17/25 fields with candidate values
- PPS visualization mining: `source_mined`; 8/9 visualization-form candidates

## Known Prior Gaps

- extract near/far, flat/dynamic, and fMRI block timing separately from scanner context

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 13 | sound; approaching; near; far; receding; distance; spl; pink noise; auditory stimuli; loudspeaker; speaker; db | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 8 | t2; t3; temporal delay; delays; t5; sound onset; t1; t4; duration; soa | source page/section(s) 1, 2, 3, 7, 9, 10, 11, 12 |
| `trial_structure_intermixing` | `completed` | 13 | trial; audio-tactile; order; trials; condition; conditions; block; random; randomly; intermingled; sequence | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 9 | for each; blocks; total; catch; false alarm | source page/section(s) 1, 2, 3, 4, 6, 7, 9, 10 |
| `tactile_response_apparatus` | `completed` | 12 | respond; response; tactile stimulus; threshold; electrodes; button | source page/section(s) 2, 3, 4, 6, 7, 8, 9, 10 |
| `pps_visualization_reporting` | `completed` | 14 | rt; map; fig.; boundary; model; figure; sigmoid; threshold; plot; graph; erp; curve | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## PPS Visualization Candidates

| Visualization type | Candidate status | Detected terms | Source pointer | Visual verification required | Plotted-parameter checklist | Manual review fields |
|---|---|---|---|---|---|---|
| `rt_by_soa_or_distance_curve` | `inferred_low_confidence` | rt; temporal delay; distance; t1; t2; t3; t4; t5; curve | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 10, 3 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `sigmoid_psychometric_fit` | `inferred_low_confidence` | sigmoid; fit; fitted; slope | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `pps_boundary_or_size_index` | `inferred_low_confidence` | pps boundary; boundary; threshold; extension; extent; index | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 7, 8 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `condition_group_bar_box_summary` | `inferred_low_confidence` | bar plot; condition; pre; post; comparison | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 5 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `near_far_or_distance_bin_plot` | `inferred_low_confidence` | near; far; close; d6 | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 7, 8, 9 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `apparatus_trajectory_schematic` | `inferred_low_confidence` | fig.; setup; experimental setup; looming; participant; tactile; source; speaker; loudspeaker; approaching; receding | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 10, 9, 2 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `neural_trace_topography_or_brain_map` | `inferred_low_confidence` | erp; eeg; meg; tms; fmri; bold; brain; cortex; electrode | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 13, 2, 9 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `model_parameter_or_fit_table` | `inferred_low_confidence` | model; parameter; coefficient; table; bic | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 11, 2, 12 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 7, 10 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 10, 8 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 10, 2, 3 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: towards body; approaching trajectory; 100 cm; 97.7 cm; 95.3 cm; 88.6 cm; 70.5 cm; 41.7 cm; 98 cm | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 7, 10 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 3100 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms; 411 ms; 2241 ms; 1550 ms; 30 ms; 3.7 ms; 1.55 s | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 10, 11 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; front; left; right | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 2, 9, 7 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB; 62.5 dB | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 7, 10 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); headphones | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 10, 2 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 10, 11, 7 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled; random combination of trials | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 10, 4 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 10, 4 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 3100 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms; 411 ms; 2241 ms; 1550 ms; 30 ms; 3.7 ms | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 10, 7 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 7, 9, 10 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore auditory stimulus; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 10, 11 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: 411 ms; 2241 ms; 1550 ms; 30 ms; 3.7 ms | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 10, 3, 8 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 3100 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms; 411 ms; 2241 ms; 1550 ms; 30 ms; 3.7 ms | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 10, 3 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: post-sound tactile baseline; 3100 ms; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms; 411 ms; 2241 ms; 1550 ms; 30 ms; 3.7 ms | artifacts/paper_metadata_audit/extracted/fallback/spadone_2021_connectivity/spadone_2021_connectivity.fallback.txt; source page/section(s) 9, 7, 10 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
