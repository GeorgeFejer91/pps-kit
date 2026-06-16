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
- Extraction status: `parsed`
- Metadata confidence: `0.49` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 17/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 17/25 fields with candidate values

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
| `stimulus_reconstruction` | `completed` | 85 | auditory stimuli; approaching; near; far; sound; db; receding; pink noise; soundforge; loudspeaker; speaker; headphone | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 26 | duration; temporal delay; delays; t1; t2; t3; t4; t5; sound onset | source page/section(s) 2, 3, 4, 5, 6, 7, 8, 9 |
| `trial_structure_intermixing` | `completed` | 60 | trial; trials; intermingled; sequence; random; randomly; block; condition; conditions; randomized; order; audio-tactile | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `baseline_catch_counts` | `completed` | 25 | catch; for each; total; blocks; false alarm | source page/section(s) 2, 3, 4, 5, 6, 7, 8, 9 |
| `tactile_response_apparatus` | `completed` | 64 | response; respond; tactile stimulus; stimulator; electrical; electrodes; threshold; button | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; 44.1 kHz | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2, 3, 4 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: SoundForge; Sonic Foundry; pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2, 6 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: near loudspeaker; approaching trajectory; receding trajectory; 100 cm | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 300 ms; 800 ms; 3100 ms; 100 s | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 4, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: approaching; right | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 3, 2 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB; 62.5 dB | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2, 3 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); headphones | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2, 7 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `inferred_low_confidence` | Auto-mined candidates: randomly intermingled; random combination of trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2, 4 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 2241 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms; 100 s; 300 ms; 800 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 3, 2 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2, 4 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: ignore auditory stimulus; catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2, 4 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator; 5 mA; 90 mA; 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms; 3100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 300 ms; 800 ms; 1500 ms; 2200 ms; 2700 ms; 1000 ms; 2241 ms; T1, T2, T3, T4, T5) | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2, 3 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 300 ms; 800 ms; 3100 ms; 100 s | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 4, 2 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: auditory-only catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/ferri_2015_jneurosci_itv.json; source page/section(s) 2, 5, 4 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
