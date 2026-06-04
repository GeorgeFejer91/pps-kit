# Audio-Tactile PPS GUI Metadata Checklist and Literature Audit

Status: GUI-focused metadata checklist for recreating published audio-tactile peripersonal-space (PPS) paradigms. This document only tracks variables that can reasonably be exposed, saved, preloaded, validated, or analyzed through the Windows app GUI.

Non-GUI details such as participant demographics, ethics text, complete clinical history, full VR scene aesthetics, and general theory are intentionally excluded unless they change an audio-tactile stimulus, trial schedule, event marker, or analysis setting.

## Scope

The target is a reusable GUI for audio-tactile PPS experiments: speaker-based, headphone/HRTF, SOFA/HRIR, imported looming audio, generated noise trajectories, tactile go/no-go events, block randomization, response capture, XDF events, and immediate PPS curve fitting.

A field belongs in this checklist only if it can become one of these app surfaces:

- Stimulus Design tab
- Trial Design tab
- Runner/Event Capture tab
- Analysis tab
- Template metadata/provenance panel
- Asset import/validation panel

Holmes et al. (2020) remains the systematic anchor for this audit because it reviewed the audiotactile PPS family and extracted task, distances, sound/tactile types, response mode, body part, PPS criterion, errors, RTs, and effect sizes.

## Current GUI-Implementable Metadata Checklist

### Stimulus Design Tab

| GUI field | Current status | Why it matters for PPS replication |
|---|---:|---|
| design name | implemented | Saved/preloaded experiment identity. |
| study template preload | implemented | Lets users load published paradigms as starting points. |
| SOFA/HRIR file path | implemented | Enables reproducible spatial audio rendering. |
| noise label | implemented | Names condition-level auditory stimuli. |
| noise type | implemented | Supports pink, blue, white, and brown noise variants. |
| auditory azimuth | implemented | Required for front/rear/left/right and lateral PPS designs. |
| auditory elevation | implemented | Required for 3D PPS designs such as Lerner et al. |
| auditory gain | implemented | Encodes relative intensity between sound conditions. |
| snap noise locations to SOFA grid | implemented | Prevents impossible or unsupported HRIR coordinates. |
| custom looming audio file | implemented | Lets users preload published or externally generated looming stimuli. |
| custom prestimulus audio file | implemented | Lets users preload instruction, pre-cue, or baseline/prestimulus files. |
| target imported audio duration | implemented | Useful for enforcing fixed 4 s imported chunks. |
| trajectory start radius | implemented | Defines far/initial sound distance. |
| trajectory end radius | implemented | Defines near/final sound distance. |
| trajectory direction | implemented | Supports approach, recede, lateral, and custom paths. |
| path length | implemented | Defines physical/virtual distance traveled by the auditory stimulus. |
| propagation speed | implemented | Needed for Canzoneri/Noel/Tonelli/Lerner-style looming timing. |
| start/end azimuth | implemented | Supports changing horizontal direction along the path. |
| elevation | implemented | Supports 3D trajectory height. |
| lead/tail padding | implemented | Controls silence/prestimulus and poststimulus audio padding. |
| sample rate | model-only | Stored in the model, but not yet exposed as a GUI control. |
| inverse-square gain law | model-only | Stored in the model, but not yet exposed as a GUI control. |

### Trial Design Tab

| GUI field | Current status | Why it matters for PPS replication |
|---|---:|---|
| repetitions per condition | implemented | Recreates study-level trial density. |
| SOA values | implemented | Main audio-tactile timing variable. |
| spatial values at tactile onset | implemented | Links SOA to perceived/virtual distance. |
| pair SOA and spatial values | implemented | Supports fixed SOA-distance mappings. |
| auditory motion directions | implemented | Supports looming, receding, static, and custom labels. |
| tactile body sites | implemented | Supports hand, chest/sternum, neck, face/head, foot, etc. |
| catch-trial percentage | implemented | Recreates go/no-go proportion. |
| exact catch-trial count | implemented | Required when papers report exact catch counts. |
| include tactile-only baseline | implemented | Supports baseline RT correction. |
| baseline SOA values | implemented | Supports tactile-only/far/fastest-baseline timing variants. |
| respiratory/phase labels | implemented | Useful for Study 5 and interoceptive variants; can be set to Any. |
| number of blocks | implemented | Defines block structure. |
| block stimulus-type membership | implemented | Blocks can allow audio-tactile, baseline, and catch trials. |
| trial randomization strategy | implemented | Supports balanced shuffle, no immediate repeats, and ordered schedules. |
| block-order randomization | implemented | Supports fixed, seeded random permutation, and counterbalanced rotation. |
| max consecutive same trial type | implemented | Basic cognitive-neuroscience randomization constraint. |
| participants / schedule count | implemented | Generates participant-level block orders. |
| random seed | implemented | Makes trial/block generation reproducible. |

### Runner and Analysis Metadata

| GUI field | Current status | Why it matters for PPS replication |
|---|---:|---|
| response event type | runner-only | Mouse/click events exist in runner code, but not yet a design setting. |
| auditory onset marker | runner/model planned | Needed for XDF and latency verification. |
| tactile onset marker | runner/model planned | Needed for XDF and SOA verification. |
| false alarm / miss marker | runner/model planned | Needed for catch-trial analysis. |
| XDF output path/session metadata | runner/model planned | Needed for reproducible experiment logs. |
| RT exclusion window | recommended | Needed to recreate published cleaning rules. |
| outlier rule | recommended | Needed for 2 SD, 2.5 SD, Grubbs, or study-specific trimming. |
| baseline correction method | recommended | Needed for tactile-only, far, fastest-baseline, or SOA-matched correction. |
| PPS fit model | recommended | Needed for sigmoid, linear, GLMM, or near/far contrasts. |
| sigmoid parameter policy | recommended | Needed for exact boundary/slope feedback. |

## New GUI Parameters Worth Implementing

These are the highest-value additions revealed by the literature audit. They are GUI-implementable and would materially improve replication fidelity.

1. Auditory duration mode

Current trajectory duration is derived from path length, speed, and padding, while imported audio has a target duration. Add a clear control for generated stimulus duration or a lock that solves speed/path/padding to a desired total duration. This matters because studies use 3000 ms, 4000 ms, and 5500 ms sounds, while this project also needs exact 4 s chunks.

2. Auditory envelope and gain law

Add controls for constant intensity, linear rising intensity, inverse-square, two-speaker crossfade, custom start/end SPL, and custom gain curve. This is essential for Canzoneri, Ferri, Barumerli, and speaker-array variants.

3. Spatial rendering mode

Add a dropdown for physical speakers, stereo crossfade, SOFA/HRIR binaural, HMD/ambisonic, imported baked audio, and intensity-only looming. The current SOFA field is useful, but the app should know how the sound is supposed to be rendered.

4. Tactile stimulus specification

Add tactile type, duration, frequency, pulse width, amplitude/intensity, calibration rule, and body landmark. The current GUI stores tactile sites, but published paradigms often need electrical 100 us pulses, 20 ms vibration, 100 ms haptic-belt vibration, or participant-threshold calibration.

5. Catch-trial type

Add catch/no-go subtype: auditory-only catch, tactile-only catch, omitted tactile event, omitted response target, or baseline catch. Current catch percentage/count is not enough to reproduce what actually happens in a catch trial.

6. Baseline trial type

Add baseline subtype: tactile-only, auditory-only, far/static, fastest-baseline, SOA-matched baseline, receding-control baseline. Current include-baseline plus baseline SOAs is a good start but not specific enough.

7. ITI and response window

Add prestimulus interval, inter-trial interval distribution, response window, and timeout. These are GUI-safe and are often necessary to recreate RT experiments.

8. Block-level factor assignment

Current blocks define which trial types are allowed. Add block-specific factors: allowed noise types, motion directions, body sites, azimuths/directions, SOA sets, and baseline/catch policy. This would let the GUI reproduce Matsuda-style directional blocks and Barumerli-style condition blocks cleanly.

9. Body-scaled distance mode

Add distance units: absolute cm/m, percent arm length, arm-length multiplier, or custom body landmark distance. This matters for Lerner et al., where tactile distances are 0.7 to 1.7 arm lengths.

10. Response device and response rule

Add response device/mode: mouse click, keyboard, button box, vocal trigger, HMD controller, plus respond-to-tactile/ignore-sound instruction label. This should feed the XDF event schema and analysis.

11. Latency calibration fields

Add optional measured audio onset latency, tactile onset latency, and response latency fields. Even if the app cannot measure them automatically yet, it can save and display them.

12. Analysis configuration tab

Add RT min/max, outlier rule, baseline correction, fit model, sigmoid bounds/start values, and grouping variables. This is needed for immediate feedback to be reproducible rather than just exploratory.

13. Asset manifest panel

Add file hash, sample rate, duration, channel count, license/provenance, and validation status for imported looming/prestimulus files and SOFA/HRIR files. This is a GUI metadata feature, not a literature footnote.

## Published Study Coverage by GUI Variables

| Study | GUI-ready variables available | GUI-relevant missing fields |
|---|---|---|
| Canzoneri, Magosso & Serino (2012) | noise type, duration, near/far trajectory, SOAs, repetitions, catch count, tactile site, tactile pulse duration, sigmoid model | exact noise files, near speaker coordinate, gain/crossfade equation, C.I.R.O script, randomization seed/order, latency values |
| Noel et al. (2015) | front/back trajectory labels, velocity, SOAs, distances, tactile site, baseline/catch counts, response device | exact audio rendering files, randomization, tactile calibration, latency, full baseline subtype details |
| Ferri et al. (2015) | affective/custom sounds, 3000 ms duration, tactile site, 10 SOAs, catch counts, sigmoid boundary | proprietary IADS assets, exact artificial sounds, envelope/gain curve, randomization, Matlab/Cogent scripts, latency |
| Matsuda et al. (2021) | direction blocks, approach/recede, SOAs, chest tactile site, trial counts, block counterbalancing | exact Unity audio settings, assets, tactile stim specs, randomization seed/order, latency |
| Lerner, Tahar, Bar, Koren & Flash (2021) | 3D azimuth/elevation/radius, SOFA/HRIR-like spatialization, pink noise, 5.5 s duration, 22 cm/s speed, sternum tactile site, arm-length-scaled distances, sigmoid fit | Unity/MATLAB scripts, 3D Tune-In parameter files, HRIR/ITD values, exact trial table, randomization, latency, tactile calibration values |
| Tonelli et al. (2019) | seven distances, white-noise motion, 3 s duration, neck tactile site, catch/unimodal counts, response mode | exact speaker-control code, white-noise files, ITI distribution, randomization, latency |
| Barumerli, Geronazzo & Cesari (2026), Exp. 1/2 | duration, SOAs, approach/recede, tactile body sites, repetitions, catch counts, baseline SOAs, block factors, GLMM/linear analysis need | exact samples, E-Prime scripts, envelope equation/SPL details, randomization, latency |
| Holmes et al. (2020) | static near/far template fields, response rules, trial counts, public code/data claim | depends on OSF completeness; less useful for dynamic looming generation |

## GUI Metadata To Store Per Saved Experiment

The saved design package should contain only GUI-operational metadata:

- `study.json`: template title, citation, source URL/DOI, verification status, notes.
- `stimulus_design.json`: noise definitions, audio files, SOFA/HRIR file, rendering mode, trajectory, envelope, tactile stimulus settings.
- `trial_design.json`: SOAs, spatial values, repetitions, blocks, catch/baseline settings, randomization, participant schedule seed.
- `trial_table.csv`: materialized trials generated from GUI settings.
- `participant_schedule.csv`: block orders generated from GUI settings.
- `events.xdf`: runner event stream and response events.
- `analysis_config.json`: GUI-selected RT cleaning, baseline correction, PPS fit model.
- `assets_manifest.json`: file hashes and validation status for audio, tactile waveform, and SOFA/HRIR files.

## Sources Used

- Holmes et al. (2020), systematic review/meta-analysis of audiotactile PPS: https://pmc.ncbi.nlm.nih.gov/articles/PMC7181441/ and https://doi.org/10.1007/s00221-020-05771-5
- Canzoneri, Magosso & Serino (2012), PLOS ONE: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0044306
- Noel et al. (2015), Cognition PDF: https://noel-lab.org/wp-content/uploads/2024/05/noet-et-al-cognition-2015.pdf
- Ferri et al. (2015), author manuscript: https://discovery.ucl.ac.uk/1464805/1/Ferri%2CEmotion-inducing_approaching.._Neuropsychologia_Authors_copy-1.pdf
- Matsuda et al. (2021), Scientific Reports: https://www.nature.com/articles/s41598-021-90784-5
- Lerner, Tahar, Bar, Koren & Flash (2021), Frontiers in Virtual Reality: https://doi.org/10.3389/frvir.2021.644214
- Tonelli et al. (2019), Experimental Brain Research: https://link.springer.com/article/10.1007/s00221-019-05469-3
- Barumerli, Geronazzo & Cesari (2026), Scientific Reports: https://www.nature.com/articles/s41598-026-36796-5
