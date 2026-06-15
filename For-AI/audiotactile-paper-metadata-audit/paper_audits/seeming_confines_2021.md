# Seeming confines (2021)

- Record ID: `seeming_confines_2021`
- DOI: `10.1016/j.cortex.2021.08.004`
- DOI URL: https://doi.org/10.1016/j.cortex.2021.08.004
- Coverage category: `not_yet_templated_missing_publication_parameters`
- Task family: audio-tactile PPS remapping after tool-use with electrophysiology
- PDF status: `needs_user_download`
- Supplement status: `not_checked`
- Extraction status: `pending_pdf`

## Known Prior Gaps

- extract PPS task timing, distances, tactile settings, response rules, and trial repetition counts separately from electrophysiology; electrophysiology context is non-blocking unless trigger timing changes task execution

## Review Attempts

- `main PDF OpenDataLoader extraction`: `pending` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `pending_pdf` - Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.
- `supplement search`: `pending_download_or_check` - Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.
- `fallback extractor/source check`: `pending_pdf` - Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `source_unavailable` |  |  |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `response_window` | `source_unavailable` |  |  |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `soa_table` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `source_unavailable` |  |  |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `source_unavailable` |  |  |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `source_unavailable` |  |  |
| `segment_4_counts` | `baseline_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `catch_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `block_count` | `source_unavailable` |  |  |
| `segment_4_counts` | `total_trial_count` | `source_unavailable` |  |  |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
