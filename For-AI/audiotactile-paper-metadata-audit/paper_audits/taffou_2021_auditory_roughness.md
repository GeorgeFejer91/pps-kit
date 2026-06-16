# Taffou et al. (2021)

- Record ID: `taffou_2021_auditory_roughness`
- DOI: `10.1038/s41598-020-79767-0`
- DOI URL: https://doi.org/10.1038/s41598-020-79767-0
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: rear-hemifield looming rough/non-rough sound with speeded tactile detection
- PDF status: `downloaded`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `0` (`existing_files`)
- Supplement extracted text files: `1`
- Extraction status: `parsed`
- Metadata confidence: `0.53` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 20/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 20/25 fields with candidate values

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
| `stimulus_reconstruction` | `completed` | 46 | sound; approaching; far; distance; near; auditory stimuli; db; hrtf; loudspeaker; speaker; spl; headphone | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 17 | delays; sound onset; duration; silence; temporal delay; sound offset; t1; t2; t3; t4; t5; tbefore | source page/section(s) 2, 3, 6, 7, 8, supplement |
| `trial_structure_intermixing` | `completed` | 25 | trial; sequence; order; trials; unimodal; condition; conditions; random; block; randomly; intermingled; audio-tactile | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 9 | catch; total; repetitions; blocks; for each; false alarm | source page/section(s) 3, 4, 5, 6, 7, supplement |
| `tactile_response_apparatus` | `completed` | 22 | response; reaction time; tactile stimulus; vibration; respond; button | source page/section(s) 1, 2, 3, 6, 7, 8, 9, supplement |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: 44,100 Hz; 500 Hz; 4 kHz; 70 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 2, 3 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: towards body; approaching trajectory; 20 cm; 166.67 cm | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 2, 1 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; duration relative to sound offset; 3000 ms; 1000 ms; 750 ms; 1500 ms; 2250 ms; 650 ms; 3650 ms | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 3, supplement |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; IN sound; rear; left | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 2, 3 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 76.5 dBA; 77.3 dBA; 0.8 dB | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 3, 2 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); headphones; HRTF | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 2 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 3, 4, 6 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 4, 3, 2 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 4, 2, 3 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: silence interval; 3000 ms; 1000 ms; 750 ms; 1500 ms; 2250 ms; 650 ms; 3650 ms | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 3 |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore auditory stimulus; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 4, 3 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 20 ms; 250 Hz; 750 ms; 1500 ms; 2250 ms; 3000 ms; 650 ms; 3650 ms; 44,100 Hz; 500 Hz; 70 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 2, 3 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 750 ms; 1500 ms; 2250 ms; 3000 ms; 650 ms; 3650 ms; T1, T2, T3, T4, T5, T after ) | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 3, supplement |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: silence baseline window | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 3 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: pre-sound tactile baseline; post-sound tactile baseline; 750 ms; 1500 ms; 2250 ms; 3000 ms; 650 ms; 3650 ms; 1000 ms; Tbefore; Tafter | artifacts/paper_metadata_audit/extracted/supplements/taffou_2021_auditory_roughness/41598_2020_79767_MOESM1_ESM.txt; source page/section(s) supplement, 3 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials; 32 trials | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 3, 5, 4 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 280 trials; 32 trials | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 3, 4 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 5, 4, 3 |
| `segment_4_counts` | `block_count` | `inferred_low_confidence` | Auto-mined candidates: 10 blocks | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 4, 2 |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 32 trials | artifacts/paper_metadata_audit/extracted/opendataloader/taffou_2021_auditory_roughness.json; source page/section(s) 3, 4 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
