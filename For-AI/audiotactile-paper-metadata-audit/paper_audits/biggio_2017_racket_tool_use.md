# Biggio et al. (2017)

- Record ID: `biggio_2017_racket_tool_use`
- DOI: `10.1016/j.neuropsychologia.2017.07.018`
- DOI URL: https://doi.org/10.1016/j.neuropsychologia.2017.07.018
- Coverage category: `covered_runnable_profile`
- Task family: near/far audio-tactile PPS task while tennis players or novices hold no racket, a common racket, or a personal racket
- PDF status: `manual_reviewed_local_pdf`
- Supplement status: `not_found`
- Extraction status: `manual_review_completed`
- Metadata confidence: `0.84` (`high_confidence_extraction`)
- Manual review source: `For-AI/audiotactile-paper-metadata-audit/manual_reviews/biggio_2017_racket_tool_use.json`
- Current templates: `biggio_2017_no_racket`, `biggio_2017_common_racket`, `biggio_2017_personal_racket`
- Known-parameter validation report: `artifacts/validation_runs/current_goal_biggio_2017_known_parameter_20260715/biggio_2017_known_parameter_validation_report.json`

## Current Profile Recreation Status

The paper is now represented by three parsimonious session-context profiles rather than by a randomization-heavy study archive. The profiles preserve the publication-bearing stimulus, timing, response, and count parameters needed to run the software task through the PPS Toolkit HTML dashboard and experiment runner:

- `study_templates/biggio_2017_no_racket.json`
- `study_templates/biggio_2017_common_racket.json`
- `study_templates/biggio_2017_personal_racket.json`

The validation script loads each profile through `DashboardController`, bakes Segments 2-5, prepares Segment 6, runs `SessionRunnerController` with software wired-loopback sidecars, and injects mouse-click simulated participant-like responses for tactile target rows. Each profile produces a 90-row session: 30 near target, 30 far target, 15 near catch, and 15 far catch trials. The observed runner output matches that extracted row contract with 60 response-required target rows, 30 withhold catch rows, 60 mouse-click events, 60 response-marker events, and preserved `tool_condition` metadata.

## Segment Field Status

| Segment | Field | Status | Value | Source pointer |
|---|---|---|---|---|
| `segment_1_stimulus_reconstruction` | `stimulus_type` | `reported` | Static near/far pink-noise bursts; no looming trajectory | Manual PDF review, methods/procedure |
| `segment_1_stimulus_reconstruction` | `source_provenance` | `reported_with_asset_caveat` | Pink noise, 150 ms duration | Manual PDF review; exact file/seed/spectrum not public |
| `segment_1_stimulus_reconstruction` | `auditory_conditions` | `reported` | Near and far auditory source locations | Manual PDF review, apparatus/procedure |
| `segment_1_stimulus_reconstruction` | `distance_table_cm` | `reported_and_derived` | Near 30 cm from body; far encoded as 98.5 cm from body from the reported 68.5 cm near-far spacing | Manual PDF review; far body distance derived from reported geometry |
| `segment_1_stimulus_reconstruction` | `loudness` | `reported` | 70 dB SPL at the right ear; near/far volumes adjusted | Manual PDF review, auditory calibration notes |
| `segment_2_sequence_and_intermixing` | `trial_rows_families` | `reported` | Audio-tactile target rows and sound-only catch rows for near and far space | Manual PDF review, procedure |
| `segment_2_sequence_and_intermixing` | `tool_contexts` | `reported` | No racket, common racket, personal racket | Manual PDF review, session/condition description |
| `segment_2_sequence_and_intermixing` | `response_mode` | `reported` | Verbal/microphone response to tactile target; withhold for sound-only catches | Manual PDF review, task instructions |
| `segment_2_sequence_and_intermixing` | `iti_jitter_policy` | `not_reported_nonblocking` | Toolkit default/randomization handles run order; exact ITI/jitter not saved as a source parameter | Missing from source detail |
| `segment_2_sequence_and_intermixing` | `response_window` | `not_reported_nonblocking` | Toolkit response window used for emulated runner validation | Missing exact source deadline |
| `segment_3_tactile_soa_baseline` | `tactile_stimulus` | `reported_with_calibration_caveat` | Electrical stimulation at the right wrist, DS7AH HV Digitimer context | Manual PDF review; exact current/pulse calibration not public |
| `segment_3_tactile_soa_baseline` | `soa_table` | `reported_and_derived` | Near audio-tactile SOA 0 ms; far tactile onset derived as 2 ms after audio for propagation | Manual PDF review plus geometry-derived propagation offset |
| `segment_3_tactile_soa_baseline` | `baseline_strategy` | `reported_absent` | No tactile-only baseline rows represented for this task | Manual PDF review, trial design |
| `segment_3_tactile_soa_baseline` | `catch_trial_type` | `reported` | Sound-only near/far catch trials | Manual PDF review, trial design |
| `segment_4_counts` | `repetitions_per_condition` | `reported` | 30 near target, 30 far target, 15 near catch, 15 far catch per tool context | Manual PDF review, trial counts |
| `segment_4_counts` | `baseline_count` | `reported_absent` | 0 tactile-only baselines | Manual PDF review |
| `segment_4_counts` | `catch_count` | `reported` | 30 sound-only catches per session context | Manual PDF review |
| `segment_4_counts` | `block_count` | `parsimonious_profile_setting` | One runnable PPS Toolkit block per tool-context profile | Toolkit profile implementation |
| `segment_4_counts` | `total_trial_count` | `reported` | 90 trials per tool-context session | Manual PDF review |

## Expected Outcome Encoding

The expected-outcome ledger treats this as a tool-use/racket context PPS modulation record with near/far tactile detection/response behavior compared across no-racket, common-racket, and personal-racket contexts. The current validation is not a human effect replication. It verifies that the extracted paper parameters can be encoded, loaded in the HTML GUI, transformed into runnable WAV/session packages, and executed by the runner with mouse-click simulated participant-like responses that match the extracted trial contract.

## Nonblocking Caveats

- Exact original pink-noise asset, seed, and spectrum are not public.
- Exact far tactile lead is geometry/propagation-derived rather than explicitly reported as a separate SOA parameter.
- Exact electrical pulse shape, current, electrode calibration, and participant thresholding are not public.
- Exact ITI/jitter, response deadline, voice-key threshold, and voice-key latency correction are not public.
- Software wired-loopback and mouse-click validation do not prove physical microphone timing, tactile current delivery, tactile perception, participant behavior, or the scientific PPS effect.

Do not paste long source text here; use short page/section pointers and concise paraphrases.
