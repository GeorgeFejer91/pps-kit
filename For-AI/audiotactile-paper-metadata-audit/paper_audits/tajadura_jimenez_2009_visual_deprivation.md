# Tajadura-Jimenez et al. (2009)

- Record ID: `tajadura_jimenez_2009_visual_deprivation`
- DOI: `10.1016/j.neuropsychologia.2009.07.025`
- DOI URL: https://doi.org/10.1016/j.neuropsychologia.2009.07.025
- Coverage category: `covered_runnable_profile`
- Task family: auditory, tactile, and audiotactile lateralization with crossed/uncrossed posture
- PDF status: `manual_reviewed_local_pdf`
- Supplement status: `not_found`
- Supplement acquisition attempts: `1` (`checked_no_supplement_candidates`)
- Supplement extracted text files: `0`
- Extraction status: `manual_review_completed`
- Metadata confidence: `0.89` (`high_confidence_extraction`)
- Confidence basis: Later manual review inspected the local publication PDF, rendered methods pages, Figure 1, fallback snippets, PubMed/Crossref routes, and Elsevier supplement routes. The local record ID remains legacy-mismatched; cite the paper as Collignon et al. (2009) for this DOI.
- Automated evidence mining: `no_extracted_source`; 0/25 fields with candidate values
- PPS visualization mining: `no_extracted_source`; 0/9 visualization-form candidates

## Current Profile Recreation Update

The GUI/profile recreation layer now represents this record with two runnable
posture-specific profiles: `tajadura_jimenez_2009_uncrossed_visual_deprivation`
and `tajadura_jimenez_2009_crossed_visual_deprivation`. They preserve the
paper-level minimum task parameters for the software runner: static external
left/right 100 ms pink-noise bursts, tactile-only baselines, auditory-only
response trials, congruent audio-tactile trials, crossed/uncrossed anatomical
hand mapping, 50 repetitions per side x modality, and 300 trials per posture.
The paper-specific validation report is
`artifacts/validation_runs/current_goal_tajadura_2009_known_parameter_20260715/tajadura_2009_known_parameter_validation_report.json`.
Exact noise seed/asset, ISI distribution, online timeout, and human
visual-deprivation effects remain caveats rather than runnable blockers.

## Known Prior Gaps

- no remaining software-runner blocker after the two posture-specific profiles; unresolved values are limited to exact noise seed/asset, ISI distribution, online timeout, and non-software human effect interpretation

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `checked_not_found` - Automated source routes found no supplement candidates; use publisher/source checks again before final missing-value decisions.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `source_unavailable` | 0 |  |  |
| `timing_soa` | `source_unavailable` | 0 |  |  |
| `trial_structure_intermixing` | `source_unavailable` | 0 |  |  |
| `baseline_catch_counts` | `source_unavailable` | 0 |  |  |
| `tactile_response_apparatus` | `source_unavailable` | 0 |  |  |
| `pps_visualization_reporting` | `source_unavailable` | 0 |  |  |

## PPS Visualization Candidates

- `no_extracted_source`: No extracted source text is available; inspect the publication PDF, figures, captions, and supplements manually before closing visualization review.

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
