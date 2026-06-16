# Segment 1-4 Metadata Checklist

Use this checklist for every in-scope publication. Each field must carry one of the schema statuses and a short source pointer when a value is present.

## Segment 1 Stimulus Reconstruction

| Field | What to extract |
|---|---|
| `stimulus_type` | Noise, tone, ecological sound, speech, or custom/baked stimulus class. |
| `source_provenance` | Original asset, generated stimulus, licensed set, apparatus source, or supplement file. |
| `trajectory_count` | Distinct looming/receding/static paths, tones, or auditory conditions. |
| `trajectory_path` | Start/end distance, direction, body anchor, azimuth/elevation, and spatial coordinate frame. |
| `stimulus_duration` | Auditory stimulus duration and any pre/post padding. |
| `stimulus_speed` | Motion speed, path length, propagation timing, or distance-at-time mapping. |
| `auditory_conditions` | Valence, direction, semantic, movement, or apparatus conditions affecting the auditory stimulus. |
| `gain_envelope` | SPL, intensity law, gain curve, cross-fade, or amplitude-field information. |
| `renderer_or_apparatus` | Headphones, HRTF, Unity/3D Tune-In, physical speakers, arrays, or other rendering provenance. |

## Visual And Layout Approximation Strategies

Use visual inspection whenever the methods text is ambiguous or when speaker/participant geometry is shown mainly in a figure.

1. Render the methods, apparatus, timing, and design-figure pages to temporary PNGs and visually inspect them before finalizing Segment 1-4 values. Delete rendered pages before commit.
2. Record room/speaker coordinates separately from body-relative coordinates. Always note which direction the participant is facing relative to the speakers, whether the participant rotates between blocks, and whether the speakers or the participant define front, rear, left, and right.
3. For four-direction or front/rear studies, do not infer body-relative direction from the page drawing alone. Confirm whether the same physical speaker pair is reused while the observer faces different directions, whether speaker arrays move, or whether the sound is digitally rendered.
4. For two-speaker analog looming/receding sounds, identify the near/far speaker distances, body anchor, speaker height, gain/cross-fade law, and motion direction. Treat a trajectory as reported only when text/caption supplies enough geometry and timing; otherwise label figure-derived values as `derived` or `inferred_low_confidence`.
5. Extract numeric values hidden in figure labels, captions, axes, legends, and table footnotes: distances, SOAs, sound onset/offset times, SPL ranges, block labels, row percentages, and catch/baseline counts.
6. Track participant posture and stimulated body part as part of the spatial frame: sitting, supine, arm extended, chest/sternum, hand, back, shoulder, or trunk-centered setups can change the meaning of near/far or front/rear.
7. If visual scale is used because text is incomplete, write the approximation basis in `evidence_note` and keep the value conservative. Do not mark a visually estimated value as fully `reported`.

## Segment 2 Sequence And Intermixing

| Field | What to extract |
|---|---|
| `trial_rows_families` | Within-trial audio sequence families and task rows. |
| `condition_intermixing` | Whether systematic manipulations are intermixed with task trials or separated. |
| `blocked_or_random_order` | Blocked condition structure, random intermixing, and task-critical order constraints. |
| `iti_jitter_policy` | Fixed ITI, jitter values, jitter range, distribution, or hazard-control policy. |
| `response_window` | Allowed response interval, timeout, or scoring window. |
| `task_sequence_rules` | Special trial scheduling, target/no-target logic, or expectancy controls. |

## Segment 3 Tactile Soa Baseline

| Field | What to extract |
|---|---|
| `tactile_stimulus` | Tactile modality, body site, waveform, duration, frequency, amplitude, and calibration. |
| `soa_table` | SOA values, tactile timing values, or distance-at-tactile values. |
| `baseline_strategy` | Tactile-only, far/static, fastest-baseline, SOA-matched, direction-coupled, or other baseline type. |
| `baseline_timing` | Baseline SOA values, baseline timing relative to omitted sound, or fixed baseline schedule. |
| `catch_trial_type` | Auditory-only, tactile-only, omitted target, no-go, target-absent, or other catch rule. |

## Segment 4 Counts

| Field | What to extract |
|---|---|
| `repetitions_per_tactile_soa_condition` | Trial repetitions for each tactile SOA crossed with relevant conditions. |
| `baseline_count` | Baseline trial count or percentage. |
| `catch_count` | Catch/no-go/auditory-only trial count or percentage. |
| `block_count` | Number of blocks, sessions, or phases when task-relevant. |
| `total_trial_count` | Total trials per participant, block, condition, or experiment. |

## Missing-Value Rule

A field can be marked `not_reported_after_review` only after all of these attempts are logged:

1. Main publication PDF extraction with OpenDataLoader PDF.
2. Targeted review of methods, apparatus, procedure, trial-design tables, and figures.
3. Supplement search, including PDFs, spreadsheets, appendices, scripts, and project pages.
4. Fallback extraction or source check using pdfplumber/pypdf, publisher HTML, rendered pages, or a second source route.
5. Protocol-lineage search for terms such as adapted, previous, protocol, as described, based on, following, well-established, paradigm, front/frontal, and cited-methods references.

When a paper says it adapted or used an established paradigm, record the cited source study and inspect that source before deciding that low-level stimulus, trajectory, timing, or count details are unavailable.

When a parameter depends on a diagram, inspect the rendered page and explicitly record the coordinate frame: physical speaker layout, participant facing direction, body-relative direction, stimulated body part, and whether values are text-reported or visually approximated.

Keep tracked evidence short. Store raw PDF/text artifacts only under ignored `artifacts/paper_metadata_audit/`.
