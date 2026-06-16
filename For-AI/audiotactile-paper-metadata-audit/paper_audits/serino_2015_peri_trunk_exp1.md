# Serino et al. (2015), Exp. 1

- Record ID: `serino_2015_peri_trunk_exp1`
- DOI: `10.1038/srep18603`
- DOI URL: https://doi.org/10.1038/srep18603
- Coverage category: `covered_runnable_profile`
- Task family: trunk tactile PPS with two-speaker analog looming/receding setup reconstructed as a binaural trajectory
- PDF status: `downloaded`
- Supplement status: `downloaded`
- Supplement acquisition attempts: `0` (`existing_files`)
- Supplement extracted text files: `1`
- Extraction status: `parsed`
- Metadata confidence: `0.53` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 20/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 20/25 fields with candidate values

## Known Prior Gaps

- None recorded in the prior coverage ledger.

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `available_for_review` - Downloaded or locally provided supplement files are available for methods/table review.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 42 | auditory stimuli; approaching; receding; near; distance; far; sound; cm/s; spl; speaker; pink noise; loudspeaker | source page/section(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 7 | temporal delay; t2; delays; sound onset; t1; duration; inter-trial; t4 | source page/section(s) 2, 9, 11, 12, 13, supplement |
| `trial_structure_intermixing` | `completed` | 23 | trial; unimodal; condition; order; audio-tactile; trials; conditions; random; randomly | source page/section(s) 2, 3, 4, 5, 7, 8, 9, 10 |
| `baseline_catch_counts` | `completed` | 17 | baseline; unimodal tactile; for each; total; catch; absence of auditory; no tactile; repetitions | source page/section(s) 2, 3, 4, 5, 7, 8, 11, 12 |
| `tactile_response_apparatus` | `completed` | 18 | reaction time; response; respond; electrical; tactile stimulus; vibration; button | source page/section(s) 1, 2, 3, 5, 7, 10, 11, 12 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise; 44.1 kHz | artifacts/paper_metadata_audit/extracted/supplements/serino_2015_peri_trunk_exp1/41598_2015_BFsrep18603_MOESM1_ESM.txt; source page/section(s) supplement, 8, 1 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: SoundForge; Sonic Foundry; samples of pink noise; pink-noise samples | artifacts/paper_metadata_audit/extracted/supplements/serino_2015_peri_trunk_exp1/41598_2015_BFsrep18603_MOESM1_ESM.txt; source page/section(s) supplement, 12, 1 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `inferred_low_confidence` | Auto-mined candidates: approaching and receding motions | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 11, 12 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: far loudspeaker; approaching trajectory; receding trajectory; 100 cm; 5 cm | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 11, 12, supplement |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 12, 11, supplement |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 22 cm/s; 35 cm/s; 100 cm/s; 75 cm/s | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 11, 12, 3 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: receding; IN sound; front; left | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 11, 2, 7 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB; 55 dB | artifacts/paper_metadata_audit/extracted/supplements/serino_2015_peri_trunk_exp1/41598_2015_BFsrep18603_MOESM1_ESM.txt; source page/section(s) supplement, 11, 12 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: speaker(s); virtual audio source | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 11, 12 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: audio-tactile trials; unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 12 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 11, 12 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 12, 1 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 12 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 12, 2 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 12, 11, supplement |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline; tactile-only/no-sound baseline | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 12, 2, 4 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: no-tactile catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 12 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 240 trials; 372 trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 8, 12 |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 240 trials; 372 trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 12 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 240 trials; 372 trials | artifacts/paper_metadata_audit/extracted/opendataloader/serino_2015_peri_trunk_exp1.json; source page/section(s) 12 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
