# Taffou et al. (2021)

- Record ID: `taffou_2021_auditory_roughness`
- DOI: `10.1038/s41598-020-79767-0`
- DOI URL: https://doi.org/10.1038/s41598-020-79767-0
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: rear-hemifield looming rough/non-rough sound with speeded tactile detection
- PDF status: `downloaded`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `13` (`downloaded`)
- Supplement extracted text files: `1`
- Extraction status: `parsed_with_warnings`
- Metadata confidence: `0.56` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 22/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 22/25 fields with candidate values

## Known Prior Gaps

- extract exact rough/non-rough sound synthesis, binaural rendering filters, rear trajectory implementation, and tactile/response timing before templating

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `available_for_review` - Downloaded or locally provided supplement files are available for methods/table review.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 12 | sound; approaching; near; far; distance; auditory stimuli; loudspeaker; speaker; headphone; db; spl; hrtf | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 7 | delays; sound onset; duration; temporal delay; sound offset; t1; t2; t3; t4; t5; silence; tbefore | source page/section(s) 2, 3, 4, 6, 7, 8, supplement |
| `trial_structure_intermixing` | `completed` | 10 | trial; sequence; order; trials; unimodal; condition; conditions; random; block; randomly; intermingled; audio-tactile | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 6 | catch; total; repetitions; for each; blocks; false alarm | source page/section(s) 3, 4, 5, 6, 7, supplement |
| `tactile_response_apparatus` | `completed` | 12 | response; reaction time; tactile stimulus; vibration; respond; button | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: 70 Hz; 44,100 Hz; 500 Hz; 4 kHz; 250 Hz | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 2, 3, 5 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 2, 3, 1 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: towards body; approaching trajectory; receding trajectory; 20 cm; 166.67 cm; 10 cm | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 2, 1, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; duration relative to sound offset; 1 ms; 3000 ms; 1000 ms; 750 ms; 1500 ms; 2250 ms; 650 ms; 3650 ms | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 3, 4, supplement |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; IN sound; rear; left; right | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 3, 2, 1 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 76.5 dBA; 77.3 dBA; 0.8 dB | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 3, 2, 1 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); headphones; HRTF; virtual audio source | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 2, 1, 3 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 3, 6, 4 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 4, 3, 1 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 3, 4, 2 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: silence interval; 1 ms; 3000 ms; 1000 ms; 750 ms; 1500 ms; 2250 ms; 650 ms; 3650 ms | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 3, 4, 1 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore auditory stimulus; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 3, 4, 1 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 70 Hz; 3000 ms; 44,100 Hz; 500 Hz; 20 ms; 250 Hz; 1 ms; 1000 ms; 750 ms; 1500 ms; 2250 ms; 650 ms; 3650 ms | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 2, 3, 4 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 1 ms; 1000 ms; 750 ms; 1500 ms; 2250 ms; 650 ms; 3650 ms; T1, T2, T3, T4, T5, Tafter) | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 4, 3, supplement |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: silence baseline window | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 4, 3, 7 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: pre-sound tactile baseline; post-sound tactile baseline; 1 ms; 3000 ms; 1000 ms; 750 ms; 1500 ms; 2250 ms; 650 ms; 3650 ms; Tbefore; Tafter | artifacts/paper_metadata_audit/extracted/supplements/taffou_2021_auditory_roughness/41598_2020_79767_MOESM1_ESM.txt; source page/section(s) supplement, 3, 6 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials; 32 trials | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 3, 5, 4 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 4, 6, 7 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 4, supplement, 3 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 5, 3, 4 |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 10 blocks | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 4, 3, 1 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/fallback/taffou_2021_auditory_roughness/taffou_2021_auditory_roughness.fallback.txt; source page/section(s) 3, 4, 5 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
