# Ferri et al. (2015B)

- Record ID: `ferri_2015_ecological_valence`
- DOI: `10.1016/j.neuropsychologia.2015.03.001`
- DOI URL: https://doi.org/10.1016/j.neuropsychologia.2015.03.001
- Coverage category: `covered_blocked_missing_publication_parameters`
- Task family: dynamic ecological emotional sounds with tactile detection
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.56` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 22/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 22/25 fields with candidate values

## Known Prior Gaps

- licensed ecological sounds
- exact amplitude envelopes

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 61 | sound; approaching; near; receding; distance; loudspeaker; speaker; auditory stimuli; far; headphone; db; soundforge | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 12 | delays; duration; temporal delay; silence | OpenDataLoader page(s) 4, 8, 9, 10, 11, 12, 13 |
| `trial_structure_intermixing` | `completed` | 20 | order; audio-tactile; condition; trial; trials; intermingled; unimodal; conditions; random; randomly; block | OpenDataLoader page(s) 2, 4, 6, 9, 10, 11, 12, 13 |
| `baseline_catch_counts` | `completed` | 10 | catch; total; for each; without any sound; unimodal tactile; repetitions; blocks | OpenDataLoader page(s) 9, 10, 11, 12, 13 |
| `tactile_response_apparatus` | `completed` | 25 | response; respond; tactile stimulus; stimulator; electrical; electrodes; threshold; button; voice | OpenDataLoader page(s) 2, 3, 4, 5, 6, 7, 8, 9 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; white noise | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 15, 10, 11 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: SoundForge; Sonic Foundry | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 8, 10, 9 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 4, 9, 10 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: approaching trajectory; receding trajectory; 50-60 cm | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 4, 15 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: 3000 ms; 300 ms; 1000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 9, 8, 10 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; receding; front; rear | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 10, 23, 4 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 8, 13, 9 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); headphones | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 4, 8, 9 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile trials; catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 9, 10 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled; random combination of trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 11, 13, 9 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 11, 10, 13 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: pre/post trial silence; silence interval; 300 ms; 3000 ms; 1000 ms; 500 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 10, 9 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 10, 4 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 11, 9, 10 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator; 3000 ms; 5 mA; 300 ms; 500 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 9, 10, 13 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 300 ms; 3000 ms; 1000 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 10, 11 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline; tactile-only/no-sound baseline; silence baseline window | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 10, 13 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 300 ms; 3000 ms; 1000 ms; 500 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 10, 9 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials; 352 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 9, 11, 13 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 352 trials; 528 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 11, 13, 9 |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 352 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 9, 10, 11 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 352 trials; 528 trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_ecological_valence.json; OpenDataLoader page(s) 11, 13, 9 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
