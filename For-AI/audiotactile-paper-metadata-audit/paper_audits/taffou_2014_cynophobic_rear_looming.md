# Taffou & Viaud-Delmon (2014)

- Record ID: `taffou_2014_cynophobic_rear_looming`
- DOI: `10.3389/fpsyt.2014.00122`
- DOI URL: https://doi.org/10.3389/fpsyt.2014.00122
- Coverage category: `covered_blocked_missing_publication_parameters`
- Task family: rear-field dog/sheep audio-tactile PPS task
- PDF status: `needs_user_download`
- Supplement status: `needs_user_download`
- Supplement acquisition attempts: `2` (`not_file_html`)
- Supplement extracted text files: `0`
- Extraction status: `pending_pdf`
- Metadata confidence: `0.75` (`publisher_html_methods_review`)
- Confidence basis: Main publication PDF is not yet cached locally, but the publisher HTML methods/results were manually reviewed on 2026-07-15 for Segment 1-4 parameters and expected-outcome pointers.
- Automated evidence mining: `no_extracted_source`; 0/25 fields with candidate values
- PPS visualization mining: `no_extracted_source`; 0/9 visualization-form candidates

## Known Prior Gaps

- exact dog/sheep source audio and Audacity amplitude/dynamic matching settings
- LISTEN HRTF subject/filter identifier and renderer settings

## Review Attempts

- `main PDF OpenDataLoader extraction`: `pending` - Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.
- `targeted methods/table search`: `completed_publisher_html` - Publisher HTML lines 357-372 provide the main Segment 1-4 task parameters; lines 405-425 provide the expected outcome.
- `supplement search`: `pending_manual_download` - Supplement-like sources were found or access was limited; manual download/check is still needed.
- `fallback extractor/source check`: `completed_publisher_html` - Publisher HTML was used because the local PDF cache is still absent.

## Six Semantic Review Passes

| Strategy | Status | Hits | Matched terms | Pages |
|---|---|---:|---|---|
| `stimulus_reconstruction` | `manual_publisher_html_review` | 9 | dog growling; sheep bleating; 3000 ms; 44100 Hz; LISTEN HRTF; rear hemifield; 520 to 20 cm | Frontiers HTML lines 357-360, 366 |
| `timing_soa` | `manual_publisher_html_review` | 7 | Tbefore; T1; T2; T3; T4; T5; Tafter | Frontiers HTML lines 366, 369-372 |
| `trial_structure_intermixing` | `manual_publisher_html_review` | 5 | random combination; 28 conditions; hemispaces; sound type; eight blocks | Frontiers HTML lines 371-372 |
| `baseline_catch_counts` | `manual_publisher_html_review` | 5 | tactile-only silent periods; 224 tactile targets; 32 catches; eight 32-trial blocks | Frontiers HTML lines 367, 371-372 |
| `tactile_response_apparatus` | `manual_publisher_html_review` | 7 | left index finger; 20 ms; 250 Hz; right-index button response; Presentation | Frontiers HTML lines 360, 363, 367 |
| `pps_visualization_reporting` | `manual_publisher_html_review` | 4 | sigmoid fit; inflection point; dog-fearful; threatening/non-threatening | Frontiers HTML lines 410-425 |

## PPS Visualization Candidates

- `manual_publisher_html_review`: Figure 3/report text describes RT-by-delay sigmoid fits and PPS-boundary inflection points. Visual axis/legend verification from the PDF/figure image is still pending before treating the plotted form as a final visualization audit.

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `reported` | threatening dog growling and non-threatening sheep bleating, edited to continuous 3000 ms sounds | Frontiers HTML lines 357-358 |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `missing_publication_parameter` | exact source WAVs and Audacity matching settings unavailable | Frontiers HTML line 358 |
| `segment_1_stimulus_reconstruction` | `trajectory_count` | `reported` | two rear hemispaces: right 135 degrees and left -135 degrees | Frontiers HTML line 366 |
| `segment_1_stimulus_reconstruction` | `trajectory_path` | `reported` | virtual sound source varied from 520 cm to 20 cm from head center in rear hemifield | Frontiers HTML line 366 |
| `segment_1_stimulus_reconstruction` | `stimulus_duration` | `reported` | 3000 ms auditory stimulus | Frontiers HTML lines 358, 366 |
| `segment_1_stimulus_reconstruction` | `stimulus_speed` | `inferred_from_reported_path` | 5 m over 3 s = 1.6667 m/s | Frontiers HTML line 366 |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `reported` | dog growl threatening and sheep bleat non-threatening | Frontiers HTML lines 358, 372 |
| `segment_1_stimulus_reconstruction` | `gain_envelope` | `missing_publication_parameter` | sounds were made similar in temporal dynamic and amplitude, but exact Audacity settings are absent | Frontiers HTML line 358 |
| `segment_1_stimulus_reconstruction` | `renderer_or_apparatus` | `reported_but_unbundled` | non-individual LISTEN HRTF database, Sennheiser HD650 headphones | Frontiers HTML lines 358-359 |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `reported` | tactile-target rows plus auditory-only catches | Frontiers HTML lines 367, 371-372 |
| `segment_2_sequence_and_intermixing` | `condition_intermixing` | `reported` | random combination of 28 tactile-target conditions with 32 catch trials | Frontiers HTML lines 371-372 |
| `segment_2_sequence_and_intermixing` | `blocked_or_random_order` | `reported` | trials equally divided into eight 32-trial blocks | Frontiers HTML line 372 |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `reported` | 1000 ms pre-sound silence and 2700-3300 ms silence after sound offset | Frontiers HTML line 366 |
| `segment_2_sequence_and_intermixing` | `response_window` | `reported` | respond as quickly as possible to tactile stimuli; exact timeout not reported | Frontiers HTML line 367 |
| `segment_2_sequence_and_intermixing` | `task_sequence_rules` | `reported` | ignore auditory stimuli, respond with right index finger to left-index tactile vibration | Frontiers HTML lines 363, 367 |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `reported` | 20 ms 250 Hz sinusoidal vibration via small loudspeaker on palmar left index finger | Frontiers HTML line 360 |
| `segment_3_tactile_soa_baseline` | `soa_table` | `reported` | T1-T5 at 0, 750, 1500, 2250, and 3000 ms from sound onset | Frontiers HTML line 369 |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `reported` | tactile-only unimodal measurements during silent periods before and after sound | Frontiers HTML line 371 |
| `segment_3_tactile_soa_baseline` | `baseline_timing` | `reported` | Tbefore at 350 ms and Tafter at 4650 ms from trial start | Frontiers HTML line 371 |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `reported` | auditory-only catch trials, 12.5 percent of trials | Frontiers HTML lines 367, 372 |
| `segment_4_counts` | `repetitions_per_tactile_soa_condition` | `reported` | eight target stimuli in each of 28 conditions | Frontiers HTML line 371 |
| `segment_4_counts` | `baseline_count` | `reported` | 64 inferred from 2 silent timings x 2 hemispaces x 2 sound types x 8 repetitions | Frontiers HTML lines 371-372 |
| `segment_4_counts` | `catch_count` | `reported` | 32 catch trials | Frontiers HTML line 372 |
| `segment_4_counts` | `block_count` | `reported` | eight blocks of 32 trials | Frontiers HTML line 372 |
| `segment_4_counts` | `total_trial_count` | `reported` | 224 tactile-target trials plus 32 catch trials = 256 total | Frontiers HTML line 372 |

Do not paste long source text here; use short page/section pointers and concise paraphrases.
