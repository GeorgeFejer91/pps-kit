# Segment 1-4 Metadata Checklist

Use this checklist for every in-scope publication. Each field must carry one of the schema statuses and a short source pointer when a value is present.

## Segment 1 Stimulus Reconstruction

| Field | What to extract |
|---|---|
| `stimulus_type` | Noise, tone, ecological sound, speech, or custom/baked stimulus class. |
| `source_provenance` | Original asset, generated stimulus, licensed set, apparatus source, or supplement file. |
| `trajectory_count` | Distinct looming/receding/static paths, tones, or auditory conditions. |
| `trajectory_path` | Start/end distance, movement direction, participant-facing direction, speaker/source position, body anchor, azimuth/elevation, and spatial coordinate frame. |
| `stimulus_duration` | Auditory stimulus duration and any pre/post padding. |
| `stimulus_speed` | Motion speed, path length, propagation timing, or distance-at-time mapping. |
| `auditory_conditions` | Valence, direction, semantic, movement, or apparatus conditions affecting the auditory stimulus. |
| `gain_envelope` | SPL, intensity law, gain curve, cross-fade, or amplitude-field information. |
| `renderer_or_apparatus` | Headphones, HRTF, Unity/3D Tune-In, physical speakers, arrays, room/speaker layout, or other rendering provenance. |

## Visual And Layout Approximation Strategies

Use visual inspection whenever the methods text is ambiguous or when speaker/participant geometry is shown mainly in a figure.

1. Render the methods, apparatus, timing, and design-figure pages to temporary PNGs and visually inspect them before finalizing Segment 1-4 values. Delete rendered pages before commit.
2. Record room/speaker coordinates separately from body-relative coordinates. Always note which direction the participant is facing relative to the speakers, whether the participant rotates between blocks, and whether the speakers or the participant define front, rear, left, and right.
3. Treat orientation as a two-vector relation: participant face/head/trunk vector versus speaker/source vector. A valid note states both before assigning a body-relative label.
4. For four-direction or front/rear studies, do not infer body-relative direction from the page drawing alone. Confirm whether the same physical speaker pair is reused while the observer faces different directions, whether speaker arrays move, or whether the sound is digitally rendered.
5. For two-speaker analog looming/receding sounds, identify the near/far speaker distances, body anchor, speaker height, gain/cross-fade law, and motion direction. Treat a trajectory as reported only when text/caption supplies enough geometry and timing; otherwise label figure-derived values as `derived` or `inferred_low_confidence`.
6. Extract numeric values hidden in figure labels, captions, axes, legends, and table footnotes: distances, SOAs, sound onset/offset times, SPL ranges, block labels, row percentages, and catch/baseline counts.
7. Track participant posture and stimulated body part as part of the spatial frame: sitting, supine, arm extended, chest/sternum, hand, back, shoulder, or trunk-centered setups can change the meaning of near/far or front/rear.
8. If visual scale is used because text is incomplete, write the approximation basis in `evidence_note` and keep the value conservative. Do not mark a visually estimated value as fully `reported`.
9. Always write the drawing viewpoint before the conclusion: top view, side view, front view, photograph, screenshot, or unclear. Only translate page-left/page-right into participant-left/participant-right when body orientation is explicit.
10. If a paper includes both a participant movement and an auditory trajectory, assign speeds carefully. Hand, arm, head, or body speed belongs in the caveat/task context unless the text or timing table ties it to the auditory stimulus path.
11. When the figure supplies a qualitative direction but no scale, preserve the useful geometry while leaving numeric fields missing: for example, `trajectory_path = derived qualitative`, `stimulus_speed = not_reported_after_review`.

Visual approximation decision ladder:

1. Record the page, figure, caption, and panel that produced the clue.
2. Identify the participant posture, head/trunk facing direction, gaze/fixation instruction, blindfold/eyes-closed state, and any block-wise participant rotation.
3. Identify the room/apparatus frame: speaker/source positions, near/far labels, height, azimuth/elevation, source movement, and whether the speaker array, participant, or digital renderer changes across conditions.
4. Translate the page/apparatus frame into the participant/body frame: front, rear, left, right, ipsilateral, contralateral, approaching, receding, proximal, or distal relative to the tactile anchor.
5. Extract numbers only from printed labels, axes, tables, captions, or a scaled diagram. If the drawing is unscaled, keep the value qualitative and mark it `inferred_low_confidence`.
6. Cross-check figure-derived geometry against supplement files and protocol-lineage citations when the methods text is incomplete or inconsistent.
7. Run an arithmetic sanity check when possible: distance / duration, duration x speed, SOA-to-distance mapping, condition rows x repetitions, and baseline/catch percentages. Note mismatches instead of silently choosing one value.

Visual approximation worksheet fields:

| Worksheet field | What to write |
|---|---|
| Raw visual clue | Literal page clue before interpretation, such as `speaker drawn page-left of hand` or `near/far line shown in top view`. |
| Participant-facing vector | Head/trunk/body facing direction relative to the page, room, or speakers; write `unclear` if the face/body-front cue is missing. |
| Speaker/source vector | Physical or virtual source direction in room/apparatus coordinates, including whether the source, participant, or renderer moves. |
| Face/source relation | Relation between participant-facing vector and source vector: front, rear, left, right, above/below, sagittal, coronal, or unclear. |
| Body-relative translation | The body-relative trajectory label that is actually supported relative to the tactile anchor, or `body-relative mapping unclear`. |
| Approximation grade | `reported` only for text/table/caption values; `derived` for scaled or arithmetically recoverable values; `inferred_low_confidence` for unscaled schematic/photo clues. |
| Unsupported labels | Direction words that appeared in the paper but were not safe to assign to auditory trajectory, such as anatomical `frontal` or response-side labels. |

Orientation ambiguity examples to preserve:

| Figure clue | Safe audit wording |
|---|---|
| Speaker drawn on page-left, participant facing not visible | `speaker page-left in schematic; participant-facing direction unclear; body-relative left/right not assigned` |
| Participant icon faces the speaker line in a top view | `participant appears to face sagittal speaker line; body-relative near/far mapping derived from figure, exact azimuth not reported` |
| Same room speaker pair used while participant rotates | `physical speaker coordinates fixed; body-relative direction changes by participant rotation; record each block separately` |
| Drawing shows arrows but no body-front cue | `apparatus movement direction visible; participant-facing vector unclear; do not assign front/rear/left/right body mapping` |
| Caption reports frontal stimulation but methods use frontal EEG/anatomy language elsewhere | `frontal auditory direction accepted only from caption/methods context, not from anatomical-analysis uses of frontal` |
| Source moves virtually through headphones | `room speaker frame not applicable; record renderer/HRTF coordinate frame, virtual azimuth/elevation, gain/motion law if reported` |

For every reviewed paper, add a short orientation ledger to the manual review notes before closing Segment 1:

| Orientation item | Required question |
|---|---|
| Participant-facing direction | Which way is the participant's head/trunk/body facing relative to the speakers or virtual source? |
| Speaker/source layout | Where are the physical speakers, virtual sources, or headphone-rendered sources in room/apparatus coordinates? |
| Face/source relation | Does the source lie in front of, behind, left of, right of, above/below, or along the sagittal/coronal axis of the participant-facing vector? |
| Body-relative mapping | How does the paper map those sources onto front/rear/left/right/near/far/approaching/receding relative to the stimulated body site? |
| Tactile anchor | Which body part and side receive the tactile target, and does that anchor change between blocks? |
| Movement implementation | Is motion physical source movement, speaker switching, gain/cross-fade, amplitude field, HRTF/renderer motion, or only inferred from timing? |
| Evidence class | Is the geometry text-reported, caption-reported, figure-derived, supplement-reported, protocol-lineage-reported, or low-confidence inferred? |

If a diagram is the only source, keep the status modest. A scaled figure with printed values can support `derived`; an unscaled schematic supports only qualitative direction unless the caption supplies the missing numbers. When the participant icon faces left/right/up/down on the page, explicitly translate page direction into body-relative direction only if the caption or surrounding text makes that mapping clear.

## PPS Visualization Reporting Checklist

In addition to apparatus geometry, extract every form used to visualize or summarize the PPS result itself. Use `pps_visualization_inventory.csv` as the running triage ledger, then confirm each candidate against the actual figure, caption, table, or supplement before promoting it into a manual review. Confirmation requires visual verification of plotted parameters, not just text extraction.

| Visualization form | What to extract |
|---|---|
| RT/facilitation by SOA or distance curve | Figure/panel, x-axis encoding, y-axis metric, point/line style, baseline correction, uncertainty display, and visually checked SOA/distance values. |
| Sigmoid/logistic/psychometric fit | Model family, fitted metric, boundary/midpoint definition, slope/shape parameter, fit statistic, and visually checked fitted/boundary values if plotted. |
| PPS boundary or size/index summary | Boundary units, derivation rule, condition/group facets, whether it is shown as points/bars/boxes/table, and visually checked boundary/index values. |
| Near/far or distance-bin plot | Bin labels, distance/SOA mapping, discrete comparisons, whether bins replace a continuous curve, and visually checked bin values. |
| Spatial map, heatmap, or body boundary | Body-centered coordinate frame, map/contour/heat encoding, view direction, body anchor, color scale, and visually checked spatial scale/legend values. |
| Apparatus or trajectory schematic | Participant, tactile site, source path, speaker/virtual-source positions, whether this is only a task schematic or also a claimed PPS map, and visually checked plotted labels. |
| Neural trace, topography, or brain map | ERP/EEG/MEP/fMRI metric, time window, scalp/brain coordinates, relationship to behavioral PPS boundary, and visually checked scale/time-window values. |
| Model-parameter or fit table | Parameter names, boundary/index fields, model comparison metrics, conditions/groups represented, and visual table-to-text consistency checks. |

Plotted-parameter visual verification must answer:

1. Which figure/table/panel was visually inspected?
2. What x-axis values, bins, SOAs, distances, or coordinates are plotted, and what units are shown?
3. What y-axis metric and units are plotted?
4. What model parameters, boundary/index values, fit statistics, or color-scale values are shown?
5. What uncertainty encoding is visible: SEM, SD, CI, range band, individual points, or none?
6. Do plotted values match the methods/results text, tables, or supplement values? Record mismatches explicitly.

Manual visualization note template:

`PPS visualization <figure/table/panel>; form <curve/map/bar/box/table/topography/schematic>; x <encoding and visually checked values/units>; y <metric and visually checked units>; model <none/sigmoid/linear/log/etc.>; boundary/index <definition and visually checked value or none>; facets <condition/group/phase/body site>; uncertainty <SEM/SD/CI/range/none>; visual parameter check <matches text/table, mismatch noted, or no text/table comparator>; evidence <text/caption/figure/supplement>; status <reported/derived/inferred_low_confidence>.`

Hidden-parameter search routes to check before declaring a value absent:

1. Scan prose around Methods, Apparatus, Procedure, Stimuli, Design, EEG/TMS/task sections, and Results footnotes.
2. Search abbreviations and synonyms: D1-Dn, T1-Tn, SOA, ISI, ITI, jitter, delay, near/far, close/distant, proximal/distal, IN/OUT, looming/receding, front/frontal/anterior, back/rear/posterior, lateral, ipsilateral, contralateral, sagittal, coronal, azimuth, elevation, height, fixation, gaze, facing, rotation, seated, supine, eyes closed, blindfolded.
3. Inspect figures/captions/tables for labels that do not appear in extracted text, especially small speaker-distance labels, row formulas, block diagrams, timing axes, and supplement-only tables.
4. Search supplements and source bundles for scripts, spreadsheets, appendix methods, trial lists, figure source data, or exported article PDFs.
5. Follow protocol-lineage citations when the paper says the task was adapted, based on a previous paradigm, or performed as described elsewhere.

## Tucked-Away Parameter Triage Matrix

When a Segment 1-4 value is not obvious in Methods prose, search for the same value by function rather than by the exact field name. Papers often report the information needed for recreation in scattered, indirect forms.

| Parameter need | Where it is often hidden | Semantic clues to search | How to record it |
|---|---|---|---|
| Sound identity/source | Stimulus paragraphs, equipment lists, supplement scripts, figure captions, software/version notes. | noise, pink, white, pure tone, harmonic, rough, Audacity, SoundForge, Matlab, Max/MSP, WAV, sample, generated. | `stimulus_type` and `source_provenance`; use `source_unavailable` only when no paper/supplement/lineage source identifies the sound class. |
| Trajectory path | Apparatus figures, speaker photos, distance-axis labels, timing diagrams, captions, participant-position diagrams. | approaching, receding, looming, far-to-near, near-to-far, front, rear, lateral, sagittal, coronal, left, right, azimuth, elevation, source position. | `trajectory_path`; separate room coordinates from body-relative direction and cite the figure/panel if visual. |
| Participant orientation | Apparatus diagrams, participant cartoons, instruction text, blindfold/fixation notes, block descriptions. | seated, standing, supine, facing, fixation, gaze, eyes closed, blindfolded, rotated, head, trunk, body midline. | `orientation_ledger`; never infer participant-left/right from figure-left/right without a body-facing cue. |
| Movement implementation | Apparatus methods, audio-generation notes, speaker-array diagrams, HRTF/renderer descriptions, intensity/gain formulas. | speaker switching, cross-fade, fade in/out, intensity, SPL, gain, attenuation, HRTF, binaural, virtual, renderer, array, source moved. | `renderer_or_apparatus`, `gain_envelope`, and `trajectory_path`; mark visual-only movement mechanisms as `inferred_low_confidence`. |
| Speed and duration | Figure axes, tactile-delay tables, distance-at-touch labels, captions, audio filenames, reported distance/speed formulas. | ms, s, cm/s, m/s, distance at touch, D1-Dn, T1-Tn, onset, offset, duration, propagation, constant velocity. | `stimulus_duration` and `stimulus_speed`; derive speed only when distance and time are both reported or a scaled figure explicitly supports it. |
| SOAs and baseline timing | Timing diagrams, ERP/TMS trigger diagrams, delay labels, response-correction formulas, supplement tables. | SOA, ISI, delay, D0, D1-Dn, Tbefore, Tafter, tactile onset, sound onset, baseline, unimodal, no sound. | `soa_table`, `baseline_strategy`, and `baseline_timing`; preserve sign conventions relative to sound/tactile onset. |
| Intermixing and jitter | Trial-design paragraphs, block diagrams, randomization constraints, task scripts, table notes. | randomized, pseudo-random, intermixed, intermingled, blocked, order, sequence, ITI, jitter, shuffled, no more than, consecutive. | `condition_intermixing`, `blocked_or_random_order`, `iti_jitter_policy`, and `task_sequence_rules`. |
| Counts and catch trials | Design formulas, percentage descriptions, table footnotes, block summaries, supplement trial lists. | repetitions, trials per condition, catch, no-go, auditory-only, tactile-only, baseline, block, session, percentage, total. | `repetitions_per_tactile_soa_condition`, `baseline_count`, `catch_count`, `block_count`, and `total_trial_count`; show derivation in `evidence_note` when multiplying factors. |

Use this triage matrix alongside keyword search. A useful manual review is allowed to say "the exact value is not reported", but it should be clear which alternate hiding places were checked.

Segment-specific hiding places to inspect:

| Segment | Hidden evidence route | What to recover |
|---|---|---|
| Segment 1 | Apparatus photos, source bundle scripts, audio software/version notes, SPL calibration notes, distance labels, captions. | Sound class/provenance, trajectory count/path, duration, speed, gain/envelope, renderer/speaker apparatus. |
| Segment 2 | Randomization sentences, block schematics, pseudo-random constraints, ITI/ISI clauses, task instructions, sequence scripts. | Intermixing, blocked/random order, jitter/range/distribution, response window, task row families. |
| Segment 3 | Timing diagrams, trigger schematics, D/T labels, baseline analysis descriptions, tactile device specs. | Tactile stimulus, SOAs, baseline SOAs/timing, catch-trial type. |
| Segment 4 | Design formulas, percentages, trial-table supplements, block summaries, results denominators after exclusions. | Repetition counts, baseline counts, catch counts, block counts, total trial count and derivation. |

## Six-Pass Semantic Search Strategy

Every manual review should include six different semantic searches, even when OpenDataLoader finds many candidate fields:

1. Stimulus reconstruction pass: search for sound/noise/tone, waveform, source, SPL, gain, envelope, speaker, headphone, renderer, HRTF, Matlab, Unity, SoundForge, Audacity, and apparatus terms.
2. Visual/spatial geometry pass: search for figure, schematic, apparatus, frontal, front, rear, posterior, anterior, sagittal, coronal, left, right, ipsilateral, contralateral, lateral, near, far, proximal, distal, distance, elevation, height, body part, gaze, fixation, eyes closed, blindfolded, participant facing, rotation, and coordinate-frame clues; then inspect rendered pages.
3. Trial sequence pass: search for randomized, blocked, intermingled, intermixed, pseudo-random, order, sequence, condition, family, percentage, row, block, trial type, ITI, jitter, and response-window terms.
4. Tactile/SOA/baseline pass: search for tactile, vibrotactile, electrical, vibration, delay, SOA, temporal, onset, baseline, unimodal, pre, post, timing, target, non-target, and correction terms.
5. Count/catch/protocol-lineage pass: search for repetition, total, catch, no-go, auditory-only, tactile-only, supplement, appendix, protocol, adapted, previous, based on, following, well-established, and cited-methods references.
6. PPS visualization reporting pass: search for figure, plot, graph, curve, RT, facilitation, sigmoid, psychometric, boundary, threshold, PPS size, index, heatmap, map, bar graph, boxplot, model, topography, ERP, EEG, MEP, and table terms; then inspect actual figures/captions.

For the visual/spatial pass, the mandatory output is not just a trajectory label. Record the participant-facing direction, speaker/source direction in room coordinates, body-relative label used by the authors, stimulated body part, and whether movement is physical, speaker-switching, cross-fade/gain-based, or digitally rendered.

For the PPS visualization reporting pass, the mandatory output is not just `figure present`. Record what the graph encodes, what metric/model/boundary is shown, how conditions are separated, how uncertainty or individual data are displayed, and whether plotted parameter values were visually verified against text/tables.

For any value derived from a figure or photograph, explicitly separate `raw visual clue`, `participant-facing vector`, `speaker/source vector`, `face/source relation`, and `body-relative translation`. This prevents page-left/page-right, experimenter-view diagrams, and participant-rotated speaker setups from being mistaken for participant-left/participant-right trajectories.

After those six passes, do a brief consistency pass before closing the review. This is not a replacement for source evidence; it catches extraction mistakes. Check whether speeds match path length/duration, whether SOAs map onto reported distances, whether trial totals equal rows x repetitions x blocks, whether baseline/catch percentages match counts, whether any speed/direction you extracted actually belongs to a participant movement or control manipulation instead of the auditory stimulus, and whether visualization labels match the plotted axes/model.

Suggested orientation note template for `orientation_ledger` or a field `evidence_note`:

`Participant <posture> facing <reported/unclear direction>; speakers/sources <room/apparatus locations>; tactile anchor <body site/side>; authors label direction as <front/rear/left/right/near/far/approaching/receding>; movement implemented by <physical movement/speaker switching/gain envelope/HRTF renderer/unclear>; evidence <text/caption/figure/supplement/lineage>, page/figure <pointer>.`

If the figure shows a participant from above or side view, first describe the diagram literally, then translate only the supported part into body coordinates. Example: "diagram shows near/far speaker pair on page-left of the hand; participant-facing direction is not specified, so lateral body mapping remains ambiguous." This preserves useful visual evidence without pretending the paper reported more than it did.

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
