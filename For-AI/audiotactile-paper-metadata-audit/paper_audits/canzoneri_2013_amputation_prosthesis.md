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
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.43` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 13/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 13/25 fields with candidate values
- PPS visualization mining: `source_mined`; 6/9 visualization-form candidates

## Known Prior Gaps

- exact trial count and tactile calibration table

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 8 | far; distance; db; tone; sound; approaching; receding; loudspeaker; speaker; near; spl; dba | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 7 | soa; t1; t2; delays; t3; t4; t5; temporal delay; silence | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `trial_structure_intermixing` | `completed` | 7 | trial; audio-tactile; unimodal; condition; conditions; order; trials; block; blocked; random; randomly; intermingled | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `baseline_catch_counts` | `completed` | 4 | for each; blocks; total; catch | source page/section(s) 2, 4, 6, 7 |
| `tactile_response_apparatus` | `completed` | 7 | respond; tactile stimulus; threshold; response; electrical; stimulator; electrodes; voice | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `pps_visualization_reporting` | `completed` | 8 | rt; map; mep; figure; graph; threshold; erp; sigmoid; boundary; model | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## PPS Visualization Candidates

| Visualization type | Candidate status | Detected terms | Source pointer | Visual verification required | Plotted-parameter checklist | Manual review fields |
|---|---|---|---|---|---|---|
| `rt_by_soa_or_distance_curve` | `inferred_low_confidence` | rt; distance; t1; t2; t3; t4; t5; d1; d2; soa; temporal delay | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 2, 4, 6 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `pps_boundary_or_size_index` | `inferred_low_confidence` | threshold; extension; extent | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 2 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `condition_group_bar_box_summary` | `inferred_low_confidence` | mean; sem; condition; group; pre; post | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 4, 6, 5 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `near_far_or_distance_bin_plot` | `inferred_low_confidence` | near; far; close; d1; d2; d3; d4; d5; proximal; distal; d6 | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 4, 3, 7 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `apparatus_trajectory_schematic` | `inferred_low_confidence` | figure; approaching; receding; participant; tactile; source; speaker; loudspeaker | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 2, 4, 7 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `neural_trace_topography_or_brain_map` | `inferred_low_confidence` | erp; tms; fmri; bold; topographic; brain; cortex; electrode | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 7 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions; IN and OUT sounds | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 2, 7, 6 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: far loudspeaker; towards body; approaching trajectory; receding trajectory; 100 cm | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 4, 7, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 440 ms; 430 ms; 414 ms; 402 ms; 404 ms; 351 ms; 373 ms; 418 ms; 398 ms | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; IN sound; OUT sound; front; left; right | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 2, 6, 7 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 4, 7, 1 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 1, 4, 2 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order; 2 blocks | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 2, 4, 7 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: silence interval; 440 ms; 430 ms; 414 ms | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 7, 2, 3 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: voice-key response capture | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 7, 2, 3 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 7, 2, 4 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 2, 6, 7 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 440 ms; 430 ms; 414 ms; 402 ms; 404 ms; 351 ms; 373 ms; 418 ms; 398 ms | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 2 blocks | artifacts/paper_metadata_audit/extracted/fallback/canzoneri_2013_amputation_prosthesis/canzoneri_2013_amputation_prosthesis.fallback.txt; source page/section(s) 4, 2, 7 |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
