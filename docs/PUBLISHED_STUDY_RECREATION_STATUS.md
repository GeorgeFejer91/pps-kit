# Published Study Recreation Status

This report separates three outcomes for catalogued audio-tactile PPS profiles:

- `GUI-recreatable`: Segment 0-4 profile parameters are complete and the toolkit can natively materialize later run artifacts.
- `Missing publication parameters`: required details or original assets are not reported or not encoded with enough specificity.
- `Toolkit structural gap`: the study uses an audiotactile task-execution structure, audio rendering mode, tactile/response option, or apparatus geometry that the current dashboard/backend does not yet model.

Only profiles in `GUI-recreatable` pass the Segment 0-4 profile checks for runnable toolkit inclusion. Segments after 4 are native app materialization and runner handoff, so they do not reject a paper profile unless an earlier profile segment is incomplete.

Structural gaps are limited to standardization constraints in the PPS task itself: trial-family and baseline logic, auditory stimulus type/provenance/rendering/gain law, spatial trajectory and apparatus geometry, tactile site/channel/calibration, response capture, and core timing/repetition parameters.

For integration decisions, the relevant question is whether the toolkit has a profile input/schema slot for the audiotactile task mechanic. The required published parameters must be complete through Segment 4: profile metadata/provenance, stimulus type/assets/trajectory, trial sequence including ITI or jitter boxes when task-relevant, SOAs and baseline/tactile strategy, and trial repetition count.

Two-speaker analog looming/receding apparatus is treated as source-apparatus provenance, not as a separate audio-source type. When the paper reports enough trajectory/timing/source parameters, the profile recreates that task as a binaural spatialized trajectory; exact original gain/envelope files are tracked as missing provenance only when exact author-stimulus equivalence is required.

Ordinary trial randomization and block order are treated as reproducible runner defaults, not publication-acceptance blockers, unless the paper's PPS task depends on a specific ITI/jitter, hazard, baseline, or repetition schedule.

A recreated profile is a toolkit recreation of reported parameters, not a claim to reproduce the authors' exact original stimulus set.
Clinical populations, interventions, and non-audiotactile experimental context are retained as notes but do not block profile inclusion unless they alter the audiotactile PPS task execution itself.

## GUI-recreatable

| Profile | Variant | Status | Main reasons |
|---|---|---|---|
| study5_box_breathing_pps | - | ready | All required current-GUI fields are present and materializable. |
| roussel_2025_dynaspace_mobile_pps | - | ready | All required current-GUI fields are present and materializable. |
| matsuda_2021_four_directions | - | ready | All required current-GUI fields are present and materializable. |
| barumerli_2026_arm_movement_exp1 | A | ready | All required current-GUI fields are present and materializable. |
| barumerli_2026_arm_movement_exp2 | B | ready | All required current-GUI fields are present and materializable. |
| noel_2015_bodily_self | A | ready | All required current-GUI fields are present and materializable. |
| noel_2015_bodily_self_back_space | B | ready | All required current-GUI fields are present and materializable. |
| pfeiffer_2018_lateral_perihead_left_to_right | - | ready | All required current-GUI fields are present and materializable. |
| study5_dynaspace_lateral_45_pps | - | ready | All required current-GUI fields are present and materializable. |
| biggio_2017_common_racket | A | ready | All required current-GUI fields are present and materializable. |
| biggio_2017_no_racket | B | ready | All required current-GUI fields are present and materializable. |
| biggio_2017_personal_racket | C | ready | All required current-GUI fields are present and materializable. |
| tajadura_jimenez_2009_crossed_visual_deprivation | A | ready | All required current-GUI fields are present and materializable. |
| tajadura_jimenez_2009_uncrossed_visual_deprivation | B | ready | All required current-GUI fields are present and materializable. |
| canzoneri_2012_dynamic_sounds | - | ready | All required current-GUI fields are present and materializable. |
| tonelli_2019_echolocation | - | ready | All required current-GUI fields are present and materializable. |
| galli_2015_wheelchair_full_body | - | ready | All required current-GUI fields are present and materializable. |
| lerner_2021_3d_audio_tactile_boundary | - | ready | All required current-GUI fields are present and materializable. |
| serino_2015_front_back_trunk_exp2 | A | ready | All required current-GUI fields are present and materializable. |
| serino_2015_peri_hand_exp3 | B | ready | All required current-GUI fields are present and materializable. |
| serino_2015_peri_trunk_exp1 | C | ready | All required current-GUI fields are present and materializable. |

## Missing publication parameters

| Profile | Variant | Status | Main reasons |
|---|---|---|---|
| canzoneri_2013_amputation_prosthesis | - | blocked_missing_parameters | exact trial count and tactile calibration table from full paper |
| canzoneri_2013_tool_use_reshaping | - | blocked_missing_parameters | exact trial count and ITI table from full paper |
| ferri_2015_artificial_looming_valence | A | blocked_missing_parameters | exact auditory files; paper-specific gain envelope |
| ferri_2015_ecological_looming_valence | B | blocked_missing_parameters | licensed ecological sounds; exact amplitude envelopes |
| noel_2015_walking_full_body_action | - | blocked_missing_parameters | exact sound distances and trial counts |
| serino_2007_blind_cane_users | - | blocked_missing_parameters | exact white-noise source asset, seed, and spectral recipe; exact electrical tactile pulse duration, waveform, current, and electrode impedance calibration; exact ITI or jitter distribution and numeric response window |
| serino_2015_toolless_sync_training | - | blocked_missing_parameters | electrocutaneous tactile calibration; voice-key response capture |
| taffou_2014_cynophobic_rear_looming | - | blocked_missing_parameters | exact dog/sheep source audio and Audacity amplitude/dynamic matching settings; LISTEN HRTF subject/filter identifier and renderer settings |
| teneggi_2013_social_face_pps | - | blocked_missing_parameters | exact distance/timing table from supplement |

## Toolkit structural gap

No profiles currently fall in this category.

## Machine-Readable Source

- `assets/preloads/profile_recreation_status.json`
