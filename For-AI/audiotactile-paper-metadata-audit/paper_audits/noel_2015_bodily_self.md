# Noel et al. (2015a)

- Record ID: `noel_2015_bodily_self`
- DOI: `10.1016/j.cognition.2015.07.012`
- DOI URL: https://doi.org/10.1016/j.cognition.2015.07.012
- Coverage category: `covered_runnable_profile`
- Task family: chest tactile PPS with looming sound
- PDF status: `downloaded`
- Supplement status: `not_checked`
- Extraction status: `parsed`
- Metadata confidence: `0.45` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 14/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 14/25 fields with candidate values

## Known Prior Gaps

- None recorded in the prior coverage ledger.

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 24 | auditory stimuli; distance; spl; far; sound; loudspeaker; speaker; cm/s; receding | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 7, 8 |
| `timing_soa` | `completed` | 4 | t2; delays; soa; sound onset; t1; duration | OpenDataLoader page(s) 2, 3, 5, 6 |
| `trial_structure_intermixing` | `completed` | 26 | condition; order; conditions; random; randomly; block; trial; trials; intermingled; unimodal | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6, 8 |
| `baseline_catch_counts` | `completed` | 13 | for each; blocks; baseline; catch; unimodal tactile; no tactile; total | OpenDataLoader page(s) 2, 3, 4, 5, 6 |
| `tactile_response_apparatus` | `completed` | 14 | respond; vibro-tactile; reaction time; tactile stimulus; response; vibration; button | OpenDataLoader page(s) 1, 2, 3, 4, 5, 6 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: away from body; 90 cm | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 3, 2, 4 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `inferred_low_confidence` | Auto-mined candidates: duration relative to sound onset; 190 ms; 1.14 s; 100 ms; 50 ms; 500 ms | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 3, 1, 2 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_low_confidence` | Auto-mined candidates: 75 cm/s | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 3, 1, 2 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: front; left; right | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 4, 6, 1 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s); virtual audio source | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 3, 1, 2 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile trials; catch trials; baseline trials | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 3, 4 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 2, 3, 1 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `inferred_low_confidence` | Auto-mined candidates: 50 ms; 500 ms; 190 ms; 1.14 s; 100 ms; 343 ms; 12 ms; 387 ms; 16 ms | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 2, 3, 4 |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: button response | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 3, 2, 4 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 3, 4 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: vibrotactile stimulation; 190 ms; 100 ms; 50 ms; 500 ms; 2 Hz | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 3, 2, 5 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `inferred_low_confidence` | Auto-mined candidates: 190 ms; 100 ms | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 3, 1, 2 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `inferred_low_confidence` | Auto-mined candidates: unimodal tactile baseline | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 4, 5 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `inferred_low_confidence` | Auto-mined candidates: 50 ms; 500 ms; 190 ms; 1.14 s; 100 ms; T6 | artifacts/paper_metadata_audit/extracted/opendataloader/noel_2015_bodily_self.json; OpenDataLoader page(s) 1, 2, 3 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
