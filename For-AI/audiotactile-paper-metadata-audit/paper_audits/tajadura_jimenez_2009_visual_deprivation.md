# Tajadura-Jimenez et al. (2009)

- Record ID: `tajadura_jimenez_2009_visual_deprivation`
- DOI: `10.1016/j.neuropsychologia.2009.07.025`
- DOI URL: https://doi.org/10.1016/j.neuropsychologia.2009.07.025
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: auditory, tactile, and audiotactile lateralization with crossed/uncrossed posture
- PDF status: `downloaded`
- Supplement status: `not_found`
- Supplement acquisition attempts: `1` (`checked_no_supplement_candidates`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.33` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 6/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 6/25 fields with candidate values

## Known Prior Gaps

- extract lateralization response mapping, posture/body-coordinate rules, and stimulus timing

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `checked_not_found` - Automated source routes found no supplement candidates; use publisher/source checks again before final missing-value decisions.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 13 | near; tone; far; sound; speaker; auditory stimuli; db | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `timing_soa` | `completed` | 1 | t2 | source page/section(s) 5 |
| `trial_structure_intermixing` | `completed` | 21 | condition; conditions; order; sequence; unimodal; trial; trials; random; randomly; block | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |
| `baseline_catch_counts` | `completed` | 3 | total; for each; blocks | source page/section(s) 3 |
| `tactile_response_apparatus` | `completed` | 17 | reaction time; respond; tactile stimulus; response; button | source page/section(s) 1, 2, 3, 4, 5, 6, 7 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: away from body | artifacts/paper_metadata_audit/extracted/opendataloader/tajadura_jimenez_2009_visual_deprivation.json; source page/section(s) 2, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: front; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/tajadura_jimenez_2009_visual_deprivation.json; source page/section(s) 3, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/tajadura_jimenez_2009_visual_deprivation.json; source page/section(s) 2, 3 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order; 2 blocks | artifacts/paper_metadata_audit/extracted/opendataloader/tajadura_jimenez_2009_visual_deprivation.json; source page/section(s) 3, 2 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/opendataloader/tajadura_jimenez_2009_visual_deprivation.json; source page/section(s) 3, 2 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 2 blocks | artifacts/paper_metadata_audit/extracted/opendataloader/tajadura_jimenez_2009_visual_deprivation.json; source page/section(s) 3, 2 |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
