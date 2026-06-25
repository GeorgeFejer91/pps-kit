# How ageing shapes body and space representations (2021)

- Record ID: `ageing_2021`
- DOI: `10.1016/j.cortex.2020.11.021`
- DOI URL: https://doi.org/10.1016/j.cortex.2020.11.021
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: audio-tactile PPS task in ageing context
- PDF status: `downloaded`
- Supplement status: `not_found`
- Supplement acquisition attempts: `1` (`checked_no_supplement_candidates`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.52` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 19/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 19/25 fields with candidate values
- PPS visualization mining: `source_mined`; 6/9 visualization-form candidates

## Known Prior Gaps

- exact task parameters need extraction; age group context is non-blocking

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `checked_not_found` - Automated source routes found no supplement candidates; use publisher/source checks again before final missing-value decisions.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 20 | db; spl; far; tone; near; sound; loudspeaker; speaker; approaching; dba; unity; auditory stimuli | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 11 | t2; soa; duration; temporal delay; delays; sound onset | source page/section(s) 1, 3, 4, 6, 7, 10, 11, 12 |
| `trial_structure_intermixing` | `completed` | 14 | audio-tactile; random; randomized; trial; condition; block; order; trials; unimodal; randomly; conditions; sequence | source page/section(s) 1, 3, 4, 5, 6, 7, 10, 11 |
| `baseline_catch_counts` | `completed` | 10 | total; repetitions; blocks; for each; baseline; catch; unimodal tactile | source page/section(s) 3, 4, 5, 6, 7, 10, 12, 13 |
| `tactile_response_apparatus` | `completed` | 11 | respond; threshold; vibration; response; tactile stimulus; reaction time | source page/section(s) 1, 2, 5, 6, 7, 11, 12, 13 |
| `pps_visualization_reporting` | `completed` | 21 | rt; facilitation; erp; mep; threshold; model; graph; fig.; figure; map; reaction time; psychometric | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## PPS Visualization Candidates

| Visualization type | Candidate status | Detected terms | Source pointer | Visual verification required | Plotted-parameter checklist | Manual review fields |
|---|---|---|---|---|---|---|
| `rt_by_soa_or_distance_curve` | `inferred_low_confidence` | reaction time; rt; facilitation; temporal delay; distance; d1; d2 | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 16, 6, 12 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `condition_group_bar_box_summary` | `inferred_low_confidence` | mean; sem; group; pre; baseline; comparison; post | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 13, 3, 5 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `near_far_or_distance_bin_plot` | `inferred_low_confidence` | near; far; close; d1; d2; d3 | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 6, 11, 12 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `apparatus_trajectory_schematic` | `inferred_low_confidence` | figure; fig.; speaker; loudspeaker; approaching; looming; participant; tactile; source | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 5, 6 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `neural_trace_topography_or_brain_map` | `inferred_low_confidence` | fmri; topographic; brain; cortex; erp; mep; bold | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 21, 1, 9 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `model_parameter_or_fit_table` | `inferred_low_confidence` | model; parameter; slope; aic; bic | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 7 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: 150 Hz | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 6, 5, 11 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: Unity | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 5, 6, 19 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: four body-relative directions | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 4, 5, 6 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; 12.85 cm | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 5, 6, 11 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 3 sec; 100 msec | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 6, 4, 5 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; IN sound; front; rear; left; right | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 4, 11, 5 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); Unity; virtual audio source | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 5, 6, 4 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 6, 7, 12 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 4, 5, 6 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 4, 5, 6 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 100 msec; 3 sec | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 4, 5, 6 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 6, 4, 11 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 60 mA; 150 Hz; 100 msec | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 4, 5, 7 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 7, 10, 16 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 100 msec; 3 sec | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 4, 5, 6 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials; 32 trials | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 6, 4, 5 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 5, 6, 7 |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 6, 5, 4 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/fallback/ageing_2021/ageing_2021.fallback.txt; source page/section(s) 5, 6, 4 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
