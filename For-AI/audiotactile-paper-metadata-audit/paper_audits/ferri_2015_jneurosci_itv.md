# Ferri et al. (2015), JNeurosci

- Record ID: `ferri_2015_jneurosci_itv`
- DOI: `10.1523/jneurosci.1696-15.2015`
- DOI URL: https://doi.org/10.1523/jneurosci.1696-15.2015
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: approaching auditory stimuli plus tactile RT PPS boundary task with fMRI endpoint
- PDF status: `downloaded`
- Supplement status: `paywalled`
- Supplement acquisition attempts: `2` (`supplement_routes_access_limited`)
- Supplement extracted text files: `0`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.47` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 16/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 16/25 fields with candidate values

## Known Prior Gaps

- extract exact behavioral audio-tactile PPS timing, distances, response settings, and auditory trajectory; fMRI/BOLD endpoint is non-blocking for audiotactile recreation

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 12 | sound; approaching; near; far; db; spl; loudspeaker; speaker; headphone; receding; distance; dba | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 10 | delays; t1; t2; t3; t4; t5; duration; temporal delay; soa; tafter | source page/section(s) 2, 3, 4, 5, 6, 7, 8, 9 |
| `trial_structure_intermixing` | `completed` | 12 | trial; trials; random; randomly; intermingled; block; sequence; condition; conditions; randomized; order; audio-tactile | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 8 | catch; total; blocks; for each | source page/section(s) 2, 3, 4, 5, 6, 7, 8, 9 |
| `tactile_response_apparatus` | `completed` | 12 | respond; response; stimulator; electrical; electrodes; button; threshold | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: SoundForge | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 6, 2, 3 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 7, 2, 1 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; receding trajectory | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 2, 7, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 1000 ms; 0.15 ms; 0.16 ms; 0.037 ms; 0.036 ms | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 2, 3, 6 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; IN sound; front; rear; left; right | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 7, 12, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); headphones | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 7, 2, 4 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 7, 4, 5 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: random combination of trials; randomized | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 4, 2, 7 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 4, 2, 7 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 1000 ms; 1500 ms; 2200 ms; 2700 ms; 7.75 s | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 2, 4, 3 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore auditory stimulus; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 2, 4, 5 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator; 1000 ms; 1500 ms; 2200 ms; 2700 ms | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 0.24 ms; 1500 ms; 2200 ms; 2700 ms; T1,T2,T3,T4,T5) | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 7, 4, 2 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 1000 ms; 1500 ms; 2200 ms; 2700 ms; 7.75 s; T6 | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials | artifacts/paper_metadata_audit/extracted/fallback/ferri_2015_jneurosci_itv/ferri_2015_jneurosci_itv.fallback.txt; source page/section(s) 4, 2, 5 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
