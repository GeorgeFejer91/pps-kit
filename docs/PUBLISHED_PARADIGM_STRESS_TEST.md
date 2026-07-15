# Published Audio-Tactile PPS Stress Test

Status: working audit for converting published audio-tactile peripersonal-space paradigms into preloadable study profiles. The stricter runnable-profile gate now lives in `docs/PUBLISHED_STUDY_RECREATION_STATUS.md`; the broader literature coverage ledger lives in `docs/AUDIOTACTILE_PPS_LITERATURE_COVERAGE_AUDIT.md`.

## Result

The current preload library contains 30 JSON profiles in `study_templates/`: two unpublished Study 5 workflows and 28 published-study profile variants. A profile is considered runnable for exact toolkit recreation only when its `01_profile/profile_parameters_manifest.json` passes the profile checks. Loading through `load_templates()` or having generated preload WAVs is not sufficient by itself.

The strongest current coverage is the Canzoneri-style dynamic audio-tactile family: a moving task-irrelevant sound, speeded tactile detection, SOA/distance mapping, baseline or catch trials, and RT-based PPS estimation. Current standardization gaps should be interpreted narrowly as PPS-task execution constraints: unsupported trial families, baseline/catch logic, audio rendering or source-asset types, tactile/response mappings, core timing/repetition rules, body-relative coordinate systems, or apparatus geometry. Clinical populations, interventions, non-audiotactile stimuli, and experimental contexts are notes only unless they change those audiotactile task mechanics.

## Parameter Groups

The audit separates parameters into four groups so the GUI does not become a long list of rare technical options.

| Group | Examples | GUI policy |
|---|---|---|
| Core visible controls | start/end distance and rotation, movement duration/speed/path length, SOA values, spatial values, repetitions, catch count, baseline on/off | Keep visible in the main tabs. |
| Profile-level advanced metadata | catch subtype, baseline subtype, target probability, ITI/jitter policy, response rule, analysis rule | Store in profile/design metadata; edit only in grouped advanced panels if the toolkit later exposes them. |
| Renderer/hardware metadata | fixed HRTF resource, 3DTI/FABIAN version, channel layout, tactile output channel, audio sample rate | Keep under the hood; surface status and warnings only. |
| Deferred context metadata | VR scene, treadmill/wheelchair training, social partner/mannequin context, clinical prosthesis state | Store as provenance notes, not blockers, unless they require a different audio-tactile task execution. |

## Per-Study Audit

| Profile | Trial families | SOA/spatial contract | Jitter/procedure contract | Current gap |
|---|---|---|---|---|
| `canzoneri_2012_dynamic_sounds` | Bimodal IN/OUT target trials, tactile-only T0/T6 controls, auditory-only catch trials | T1-T5 at 300, 800, 1500, 2200, 2700 ms from sound onset; T0/T6 during 1000 ms pre/post silence | Original paper reports 8 target repetitions per temporal delay and 76 catch trials; randomization and two-block procedure are not acceptance blockers | Current profile passes the PPS-task recreation gate with direction-coupled tactile-only baselines and a distributed two-block trial pool. |
| `canzoneri_2013_tool_use_reshaping` | Canonical dynamic PPS measurement before/after tool-use training | Canzoneri-family T1-T5 scaffold | Training/control context is non-blocking for the PPS-task profile | Needs exact trial count and ITI table from the paper. |
| `canzoneri_2013_amputation_prosthesis` | Canonical dynamic PPS measurement across prosthesis states | Canzoneri-family T1-T5 scaffold | Clinical/prosthesis context is non-blocking for the PPS-task profile | Needs exact trial count, ITI/baseline/repetition details, and tactile calibration table. |
| `serino_2015_toolless_sync_training` | Bimodal IN/OUT target trials plus auditory-only catch trials | T1-T5 at 300, 800, 1500, 2200, 2700 ms | Training context is non-blocking for the PPS-task profile | Needs electrocutaneous tactile calibration source values. |
| `teneggi_2013_social_face_pps` | Face tactile detection with approaching/receding sound labels | Five distance samples inherited from the social PPS method | Social/economic-game context is non-blocking for the PPS-task profile | Needs exact distance/timing table from supplement. |
| `ferri_2015_artificial_looming_valence` | Bimodal emotional artificial looming sounds, catch/baseline scaffold | Canzoneri-family five SOA/distance samples | Valence is a sound-condition factor; exact gain envelope needs source materials | Needs licensed/validated sound assets and envelope metadata. |
| `ferri_2015_ecological_looming_valence` | Ecological negative/neutral/positive looming labels | Canzoneri-family five SOA/distance samples | Same as artificial variant, with more asset dependence | Needs import manifest and license/provenance checks for ecological audio. |
| `serino_2015_peri_trunk_exp1` | Trunk tactile, looming/receding, baseline/catch scaffold | Six distances from far to near; SOAs stored as profile values | Original two-speaker apparatus is reconstructed as a binaural near-far trajectory | Current profile passes the Segment 0-4 PPS-task recreation gate. |
| `serino_2015_front_back_trunk_exp2` | Front/back trunk tactile with pass-through sound directions | Published 13-sample internal schedule along the 1 m front-to-1 m back axis | Physical speaker-array provenance is recreated as a linear binaural moving-source path | Current profile passes the Segment 0-4 PPS-task recreation gate with 372 runnable trials; exact Gaussian speaker-array synthesis and the 14-delay/13-distance wording mismatch remain caveats. |
| `serino_2015_peri_hand_exp3` | Hand tactile, looming/receding, baseline/catch scaffold | Five hand-centered distances | Lateral hand coordinate is not a first-class GUI field | Needs body-part anchored coordinate frames. |
| `galli_2015_wheelchair_full_body` | Front/back trunk tactile PPS with baseline/catch scaffold | Six timing/distance samples | Wheelchair context is non-blocking for the PPS-task profile; physical Gaussian speaker arrays are represented as front/back virtual moving-source trajectories | Current profile passes the Segment 0-4 PPS-task recreation gate with exact 144/48/24 audio-tactile/baseline/catch row counts; exact Gaussian gain/SPL and original broadband source remain caveats. |
| `noel_2015_bodily_self` | Full-body-illusion context plus chest tactile PPS schedule | Six SOA/distance samples | Full-body-illusion context is non-blocking for the PPS-task profile | Current profile passes the PPS-task recreation gate. |
| `noel_2015_walking_full_body_action` | Standing/walking full-body PPS profile | White-noise looming/receding motion between 2 m and the body at 75 cm/s, T1-T5 = 440/880/1330/1770/2220 ms mapped to 33/66/100/133/166 cm, plus tactile-only baselines and sound-only catches | Walking/treadmill/optic-flow context is preserved as locomotion metadata and remains an apparatus caveat, not a profile blocker | Current profile passes the paper-parameter runner validation with the reported 512-trial formula split over eight blocks; exact physical treadmill, optic-flow display, SPL field, and two-array speaker interpolation remain outside software recreation. |
| `matsuda_2021_four_directions` | Bimodal, unimodal, and catch trials in four direction blocks | Tbefore/Tafter plus T1-T5; T1-T5 are 300, 800, 1500, 2200, 2700 ms | Four body-relative directions are encoded as profile source trajectories | Current profile passes the PPS-task recreation gate. |
| `taffou_2014_cynophobic_rear_looming` | Dog/sheep rear-field audio-tactile, baseline, catch scaffold | Tbefore/T1-T5/Tafter-style timing with rear-left/rear-right hemispaces | Threat category and hemifield are block/trial factors | Needs licensed audio assets and HRTF/source-specific provenance. |
| `tonelli_2019_echolocation` | Seven-speaker audio-tactile, tactile-only, and catch scaffold | Seven SOA/distance samples from a lateral speaker array | Echolocation training context is non-blocking for the PPS-task profile | Current profile passes with a virtual seven-distance lateral moving-source trajectory and exact 84/28/28 audio-tactile/baseline/catch row counts; exact speaker switching/gain, original noise asset, response timeout, and unfixed ITI remain provenance caveats. |
| `lerner_2021_3d_audio_tactile_boundary` | Dynamic and flat 3D audio with tactile belt events | Six arm-length-scaled timepoints represented with a declared 70 cm reference arm length | Twelve source directions are prebaked into dynamic moving pink-noise and flat stationary pink-noise trajectory assets; subject-specific head/arm measures and Unity behavior remain metadata | Current profile passes with 24 source assets and 144 preview trial rows; exact Unity/3D Tune-In rendering and live participant body/head scaling remain provenance caveats. |
| `barumerli_2026_arm_movement_exp1` | Looming/receding audio-tactile blocks, catch, baseline | T1-T5 at 300, 800, 1500, 2200, 2700 ms | Motor/static hand-status is non-blocking for the PPS-task profile | Current profile passes the PPS-task recreation gate. |
| `barumerli_2026_arm_movement_exp2` | Looming/receding audio-tactile blocks, catch, full baseline SOA set | T1-T5 at 800, 1300, 2000, 2700, 3200 ms | Same as Experiment 1 with longer sound duration | Current profile passes the PPS-task recreation gate. |
| `pfeiffer_2018_lateral_perihead_left_to_right` | Trajectory/noise profile for the local simulator reference | Lateral X trajectory with profile-derived distance-at-tactile values | Reference script includes its own head model and level equations | Current profile passes the PPS-task recreation gate, while exact acoustic equivalence remains provenance-scoped. |

## Deferred Candidate Studies

Some published studies are relevant but should not yet become runnable profiles because their core manipulation is not represented by the current model.

| Study | Reason to defer |
|---|---|
| Bassolino et al. 2010 mouse-use PPS | Primarily near/far static audio-tactile rather than a continuous generated trajectory; needs static near/far trial family support. |
| Recent sound-only looming motor-preparation studies | Useful for auditory PPS, but not audio-tactile tactile-detection paradigms. Keep separate from the audio-tactile profile library. |
| Speaker-only static near/far APPS tasks | Need a static-spatial stimulus family before they can be represented honestly. |

## Missing Parameters To Implement

These are the minimum schema additions that would remove most current partial-profile gaps without exposing excessive choices.

1. `TrialFamilySpec`

Add a compact family definition for `audio_tactile`, `tactile_only_baseline`, `audio_only_catch`, `auditory_only_control`, `training`, and `calibration`. Each family should carry `target_present`, `audio_present`, `tactile_present`, `response_required`, and `subtype`. The main GUI should show these as simple trial-family toggles; the subtype should normally come from the study profile.

2. `TimingPolicySpec`

Add `pre_sound_silence_ms`, `post_sound_silence_ms`, `iti_policy`, `iti_min_ms`, `iti_max_ms`, `iti_fixed_ms`, `response_window_ms`, and `break_every_n_trials`. Routine users should see only a compact `Timing` summary. Exact values should load from profiles.

3. `BlockFactorSpec`

Current blocks only filter trial types. Add optional filters for motion direction, noise label, tactile site, body-relative direction, baseline subtype, and catch subtype. This covers Matsuda-style direction blocks, Lamia-style looming/receding blocks, front/back body mapping, and valence sound blocks without adding separate GUI controls for each paper.

4. `TactileStimulusSpec`

Add tactile modality, duration, frequency, pulse width, amplitude/intensity, calibration rule, and output channel. The main GUI can display one sentence such as `100 us electrical pulse, threshold calibrated`; exact values belong in profile details.

5. `DistanceUnitSpec`

Add absolute cm/m, percent arm length, arm-length multiplier, and body-landmark reference. Lerner-style 3D body-scaled boundaries can run when a reference arm length is declared, but live participant-specific scaling should become a first-class control without altering the simple cm controls unless a profile needs it.

6. `AnalysisSpec`

Add RT min/max, outlier rule, baseline correction, PPS fit model, sigmoid bounds, and grouping variables. This belongs in an Analysis tab or read-only profile checklist until the analysis workflow is implemented.

## GUI Strategy

The main UI should remain profile-driven:

- `Study profile` loads all rare study-specific assumptions.
- `Core controls` stay visible: endpoint geometry, sound duration/speed, SOAs, spatial values, repetitions, catch/baseline count, and participants.
- `Profile details` shows read-only trial-family, timing, jitter/ITI, tactile, response, and analysis assumptions.
- `Advanced overrides` is collapsed and grouped by Timing, Trial Families, Blocks, Tactile, and Analysis.
- `Exact replication checklist` flags missing source assets, unsupported trial/baseline/audio/tactile/response mechanics, unverified jitter/ITI, missing repetition counts, and renderer mismatches.

This preserves the simple workflow while making the replication contract explicit enough for preregistration, Zenodo archiving, and later publication review.

## Sources Checked

- Canzoneri et al. 2012, PLOS ONE, https://doi.org/10.1371/journal.pone.0044306
- Serino et al. 2015, Scientific Reports, https://doi.org/10.1038/srep18603
- Serino et al. 2015, Frontiers in Behavioral Neuroscience, https://doi.org/10.3389/fnbeh.2015.00004
- Matsuda et al. 2021, Scientific Reports, https://doi.org/10.1038/s41598-021-90784-5
- Lerner et al. 2021, Frontiers in Virtual Reality, https://doi.org/10.3389/frvir.2021.644214
- Holmes et al. 2020, Experimental Brain Research, https://doi.org/10.1007/s00221-020-05771-5
