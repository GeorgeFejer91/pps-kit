# PPS encoding in disorders of consciousness (2019)

- Record ID: `disorders_consciousness_2019`
- DOI: `10.1016/j.nicl.2019.101940`
- DOI URL: https://doi.org/10.1016/j.nicl.2019.101940
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: audio-tactile PPS task with neuroclinical endpoint
- PDF status: `downloaded`
- Supplement status: `not_found`
- Supplement acquisition attempts: `1` (`checked_no_supplement_candidates`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.42` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 12/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 12/25 fields with candidate values
- PPS visualization mining: `source_mined`; 5/9 visualization-form candidates

## Known Prior Gaps

- extract 5 cm/75 cm auditory-tactile timing, tactile apparatus, response/EEG trigger codes, baseline/ITI policy, and trial counts separately from clinical endpoint

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `checked_not_found` - Automated source routes found no supplement candidates; use publisher/source checks again before final missing-value decisions.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 14 | near; distance; db; tone; far; sound; loudspeaker; speaker; approaching; spl; dba | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 14 | t1; t2; t3; duration; t5; inter-trial; delays; t4 | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `trial_structure_intermixing` | `completed` | 14 | audio-tactile; order; trial; trials; block; condition; conditions; random; randomized; randomly; sequence | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 6 | total; blocks; baseline; for each | source page/section(s) 2, 3, 4, 5, 6, 7 |
| `tactile_response_apparatus` | `completed` | 12 | electrodes; respond; response; electrical; reaction time; threshold; calibration | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `pps_visualization_reporting` | `completed` | 14 | graph; rt; eeg; mep; map; erp; fig.; reaction time; threshold; topography; model; boundary | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## PPS Visualization Candidates

| Visualization type | Candidate status | Detected terms | Source pointer | Visual verification required | Plotted-parameter checklist | Manual review fields |
|---|---|---|---|---|---|---|
| `rt_by_soa_or_distance_curve` | `inferred_low_confidence` | reaction time; rt; distance; t1; t2; t3; d1; d2 | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 3, 6, 1 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `condition_group_bar_box_summary` | `inferred_low_confidence` | sem; condition; pre | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 12 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `near_far_or_distance_bin_plot` | `inferred_low_confidence` | near; far; close; d5; d6; d7; d1; d2; d3 | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 3, 7, 6 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `apparatus_trajectory_schematic` | `inferred_low_confidence` | fig.; apparatus; speaker; loudspeaker; approaching; participant; tactile; source | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 3, 13 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |
| `neural_trace_topography_or_brain_map` | `inferred_low_confidence` | erp; eeg; mep; topography; topographic; scalp; brain; electrode; amplitude; meg; cortex; tms | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 5, 13, 6 | `yes` | Render and inspect the source figure/table/page; record figure/table/panel pointer; verify x-axis values and units; verify y-axis metric and units; verify plotted SOA/distance/bin labels; verify model parameters/boundary/index values when shown; verify uncertainty display; cross-check plotted parameters against methods/results tables or text. | figure/table/panel pointer; visualization form; x and y encodings; PPS metric shown; model function if any; boundary/index definition; condition facets; uncertainty display; visual verification status for plotted parameters. |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: white noise | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 3, 2, 5 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 3, 2, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; left; right | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 3, 4, 8 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 3, 1, 2 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; baseline trials | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 4, 5, 6 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomized | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 3, 4, 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 250 trials | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 1, 2, 3 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 250 trials | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 96 blocks; 3.2 blocks; 1-7 blocks; 9 sessions | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 250 trials | artifacts/paper_metadata_audit/extracted/fallback/disorders_consciousness_2019/disorders_consciousness_2019.fallback.txt; source page/section(s) 2, 4, 5 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
