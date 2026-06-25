# Noel et al. (2015a)

- Record ID: `noel_2015_bodily_self`
- DOI: `10.1016/j.cognition.2015.07.012`
- DOI URL: https://doi.org/10.1016/j.cognition.2015.07.012
- Coverage category: `covered_runnable_profile`
- Task family: chest tactile PPS with looming sound
- PDF status: `downloaded`
- Supplement status: `not_found`
- Supplement acquisition attempts: `2` (`checked_no_supplement_candidates`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.39` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 10/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 10/25 fields with candidate values
- PPS visualization mining: `source_mined`; 5/9 visualization-form candidates

## Known Prior Gaps

- None recorded in the prior coverage ledger.

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `checked_not_found` - Automated source routes found no supplement candidates; use publisher/source checks again before final missing-value decisions.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 9 | distance; spl; sound; loudspeaker; speaker; approaching; far; db; cm/s; dba; receding; near | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 8 | t2; soa; t1; t5; temporal delay; delays; duration | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `trial_structure_intermixing` | `completed` | 8 | condition; conditions; block; order; trial; trials; unimodal; intermingled | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 6 | for each; blocks; baseline; catch; repetitions; total; unimodal tactile | source page/section(s) 2, 3, 4, 5, 6, 7 |
| `tactile_response_apparatus` | `completed` | 7 | respond; tactile stimulus; vibro-tactile; vibration; response; button; reaction time | source page/section(s) 1, 2, 3, 4, 5, 6, 9 |
| `pps_visualization_reporting` | `completed` | 9 | rt; mep; fig.; boundary; map; model; figure; erp; plot; reaction time; facilitation | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## PPS Visualization Candidates

| Visualization type | Candidate status | Detected terms | Source pointer | Visual verification required | Plotted-parameter checklist | Manual review fields |
|---|---|---|---|---|---|---|
| `rt_by_soa_or_distance_curve` | `inferred_low_confidence` | reaction time; rt; facilitation; soa; distance; t1; t2; d1; plotted; plot; temporal delay | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 4, 3, 5 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `pps_boundary_or_size_index` | `inferred_low_confidence` | pps boundary; boundary; extension | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 6, 4, 5 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `condition_group_bar_box_summary` | `inferred_low_confidence` | sem; condition; pre; baseline | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 7 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `near_far_or_distance_bin_plot` | `inferred_low_confidence` | far; close; d1; d4; d5; d6 | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 6, 4, 5 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `apparatus_trajectory_schematic` | `inferred_low_confidence` | fig.; apparatus; setup; speaker; loudspeaker; approaching; participant; tactile; figure; looming; source | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 2, 3, 4 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 2, 4, 8 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: away from body; approaching trajectory | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 2, 3, 6 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; front; left; right | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 2, 4, 8 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); virtual audio source | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 2, 3, 1 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 3, 4, 5 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 4, 3, 6 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 3, 4, 5 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 5, 6, 3 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: T6 | artifacts/paper_metadata_audit/extracted/fallback/noel_2015_bodily_self/noel_2015_bodily_self.fallback.txt; source page/section(s) 1, 2, 3 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
