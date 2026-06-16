# Biggio et al. (2017)

- Record ID: `biggio_2017_racket_tool_use`
- DOI: `10.1016/j.neuropsychologia.2017.07.018`
- DOI URL: https://doi.org/10.1016/j.neuropsychologia.2017.07.018
- Coverage category: `not_yet_templated_requires_toolkit_structure`
- Task family: near/far audio-tactile PPS task while tennis players or novices hold a racket
- PDF status: `downloaded`
- Supplement status: `not_found`
- Supplement acquisition attempts: `1` (`checked_no_supplement_candidates`)
- Supplement extracted text files: `0`
- Extraction status: `parsed`
- Metadata confidence: `0.47` (`partial_extraction`)
- Confidence basis: Publication PDF is parsed and the automated Segment 1-4 miner found candidate values for 16/25 fields; values still require critical PDF/supplement review.
- Automated evidence mining: `source_mined`; 16/25 fields with candidate values

## Known Prior Gaps

- extract near/far auditory locations, tactile site/timing, verbal response capture, racket/handle geometry, conditions, and trial counts before templating; sport expertise is non-blocking context

## Review Attempts

- `main PDF OpenDataLoader extraction`: `available_for_run` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_review` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `checked_not_found` - Automated source routes found no supplement candidates; use publisher/source checks again before final missing-value decisions.
- `fallback extractor/source check`: `pending_review` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Five Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `completed` | 19 | sound; speaker; near; far; distance; pink noise; audio stimuli; loudspeaker; db; receding | source page/section(s) 1, 2, 3, 4 |
| `timing_soa` | `completed_no_hits` | 0 |  |  |
| `trial_structure_intermixing` | `completed` | 13 | order; trial; trials; condition; random; randomly; conditions | source page/section(s) 2, 3, 4 |
| `baseline_catch_counts` | `completed` | 1 | catch; repetitions | source page/section(s) 3 |
| `tactile_response_apparatus` | `completed` | 19 | tactile stimulus; respond; reaction time; response; stimulator; electrical; microphone | source page/section(s) 1, 2, 3, 4 |

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `inferred_low_confidence` | Auto-mined candidates: pink noise | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2, 3 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `inferred_low_confidence` | Auto-mined candidates: pink-noise samples | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2, 3 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `inferred_low_confidence` | Auto-mined candidates: near loudspeaker; far loudspeaker; 30 cm; 68.5 cm; 0.3 cm | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2, 3 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `inferred_low_confidence` | Auto-mined candidates: right | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2, 3 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `inferred_low_confidence` | Auto-mined candidates: 70 dB | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `inferred_low_confidence` | Auto-mined candidates: loudspeaker(s); speaker(s) | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2, 1 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `inferred_low_confidence` | Auto-mined candidates: catch trials | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 3, 2 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `inferred_low_confidence` | Auto-mined candidates: randomized/random order | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `inferred_low_confidence` | Auto-mined candidates: microphone response capture | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 1, 3 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `inferred_low_confidence` | Auto-mined candidates: catch/no-target trials; tactile target trials | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2, 3 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `inferred_low_confidence` | Auto-mined candidates: electrical tactile stimulation; tactile stimulator | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2, 3 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `inferred_low_confidence` | Auto-mined candidates: 30 trials | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 3, 2 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `inferred_low_confidence` | Auto-mined candidates: 30 trials | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 3, 2 |
| `segment_4_counts` | `baseline_count` | `inferred_low_confidence` | Auto-mined candidates: 90 trials; 30 trials | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2, 3 |
| `segment_4_counts` | `catch_count` | `inferred_low_confidence` | Auto-mined candidates: 30 trials; 90 trials | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 3, 2 |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `inferred_low_confidence` | Auto-mined candidates: 90 trials; 30 trials | artifacts/paper_metadata_audit/extracted/opendataloader/biggio_2017_racket_tool_use.json; source page/section(s) 2, 3 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
