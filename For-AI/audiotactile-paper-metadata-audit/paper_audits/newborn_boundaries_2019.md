# Identifying PPS boundaries in newborns (2019)

- Record ID: `newborn_boundaries_2019`
- DOI: `10.1038/s41598-019-45084-4`
- DOI URL: https://doi.org/10.1038/s41598-019-45084-4
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: newborn audio-tactile PPS boundary task with sound-intensity/distance and tactile response measures
- PDF status: `downloaded`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `10` (`not_file_html`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.52` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 19/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 19/25 fields with candidate values

## Known Prior Gaps

- extract auditory intensity/distance levels, tactile timing, response measure, and infant-specific apparatus separately from participant age

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 11 | sound; near; far; distance; pink noise; tone; auditory stimuli; approaching; receding; db; loudspeaker; speaker | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 6 | t1; delays; t3; sound onset; sound offset; t2; t4; t5 | source page/section(s) 1, 2, 6, 7, 8, 9 |
| `trial_structure_intermixing` | `completed` | 9 | audio-tactile; trial; trials; condition; random; randomly; order; unimodal; sequence; conditions | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 3 | auditory only; total | source page/section(s) 2, 8, 9 |
| `tactile_response_apparatus` | `completed` | 10 | tactile stimulus; respond; reaction time; response | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; pure tone; 2.5 Hz; 8000 Hz | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 2, 8, 7 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 8, 2, 6 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: four body-relative directions; approaching and receding motions | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 10, 8, 2 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: towards body; away from body; approaching trajectory; receding trajectory; 1 cm | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 7, 2, 9 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; duration relative to sound offset; 3000 ms; 2000 ms; 3 s; 2 s | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 8, 9, 7 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; IN sound; front; rear; left; right | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 7, 8, 10 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB; 0.005 dB; 55 dB; 56.5 dB; 59 dB; 62.5 dB; 76 dB; 68.5 dB; 47 dB | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 8, 7, 9 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); virtual audio source | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 8, 9, 7 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 8, 9, 4 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 8, 2, 7 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 2000 ms; 3 s; 2 s | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 7, 8, 9 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore sound; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 8, 9, 2 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 2000 ms | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 8, 9, 1 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 2000 ms; 3 s; 2 s | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 7, 8, 9 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 30 trials; 31 trials | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 7, 8, 9 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 30 trials; 31 trials | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 9, 7, 8 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 30 trials; 31 trials | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 8, 9, 2 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 30 trials; 31 trials | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 8, 2, 9 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 30 trials; 31 trials | artifacts/paper_metadata_audit/extracted/fallback/newborn_boundaries_2019/newborn_boundaries_2019.fallback.txt; source page/section(s) 9, 8, 2 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
