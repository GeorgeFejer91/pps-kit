# Lerner et al. (2021)

- Record ID: `lerner_2021_3d_boundary`
- DOI: `10.3389/frvir.2021.644214`
- DOI URL: https://doi.org/10.3389/frvir.2021.644214
- Coverage category: `covered_runnable_profile`
- Task family: VR 3D audio-tactile PPS boundary estimation
- PDF status: `downloaded`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `15` (`not_file_html`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.43` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 13/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 13/25 fields with candidate values
- PPS visualization mining: `source_mined`; 5/9 visualization-form candidates

## Known Provenance Caveats

- exact Unity/3D Tune-In stimulus engine behavior and per-subject head/arm scaling are not reproduced exactly

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 14 | sound; far; db; distance; dba; receding; spl; unity; audio stimuli; cm/s; tone; pink noise | source page/section(s) 1, 2, 4, 6, 7, 8, 9, 10 |
| `timing_soa` | `completed` | 9 | t3; duration; soa; delays; t4; t1 | source page/section(s) 3, 4, 5, 6, 8, 9, 10, 15 |
| `trial_structure_intermixing` | `completed` | 16 | audio-tactile; order; condition; conditions; random; trial; trials; block | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 5 | for each; total; blocks | source page/section(s) 8, 10, 11, 12, 13 |
| `tactile_response_apparatus` | `completed` | 9 | respond; reaction time; threshold; vibration; calibration; tactile stimulus; response | source page/section(s) 1, 6, 9, 10, 11, 12, 13, 14 |
| `pps_visualization_reporting` | `completed` | 16 | rt; boundary; figure; graph; sigmoid; map; model; reaction time; threshold; erp; mep | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## PPS Visualization Candidates

| Visualization type | Candidate status | Detected terms | Source pointer | Visual verification required | Plotted-parameter checklist | Manual review fields |
|---|---|---|---|---|---|---|
| `rt_by_soa_or_distance_curve` | `inferred_low_confidence` | reaction time; rt; distance; t3; soa; d1; d2 | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 6, 9, 11 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `pps_boundary_or_size_index` | `inferred_low_confidence` | boundary; border; threshold | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 12 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `near_far_or_distance_bin_plot` | `inferred_low_confidence` | far; close; d1 | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 12 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `apparatus_trajectory_schematic` | `inferred_low_confidence` | figure; apparatus; setup; trajectory; tactile; source; receding; looming; participant | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 2, 6, 7 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `neural_trace_topography_or_brain_map` | `inferred_low_confidence` | erp; mep; amplitude; tms; brain; cortex | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 9, 15 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; white noise | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 12, 8, 13 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: Unity; pink-noise samples | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 8, 13, 12 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 12, 14, 8 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: IN sound; front; left; right | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 10, 13, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: Unity; virtual audio source | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 7, 8, 9 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 9, 10, 11 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 2, 7, 8 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 11, 9, 10 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 10, 9, 11 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 24 trials; 144 trials | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 9, 10, 11 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 24 trials; 144 trials | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 9, 10, 11 |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 2 blocks | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 10, 11, 2 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 24 trials; 144 trials | artifacts/paper_metadata_audit/extracted/fallback/lerner_2021_3d_boundary/lerner_2021_3d_boundary.fallback.txt; source page/section(s) 10, 9, 11 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
