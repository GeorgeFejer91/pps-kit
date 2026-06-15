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

Keep tracked evidence short. Store raw PDF/text artifacts only under ignored `artifacts/paper_metadata_audit/`.
