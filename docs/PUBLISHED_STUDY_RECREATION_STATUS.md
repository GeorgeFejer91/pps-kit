# Published Study Recreation Status

This is a configuration-compatibility report for catalogued audio-tactile PPS profiles. It does not replace the citation mapper's experiment-level review of eleven scientific contracts.

- `GUI-recreatable`: the saved configuration passes Segment 0-4 input checks, including any explicit software defaults or substitutions. This does not establish complete publication parameters or tested native capability.
- `Missing publication parameters`: required details or original assets are not reported or not encoded with enough specificity.
- `Toolkit structural gap`: the study uses an audiotactile task-execution structure, audio rendering mode, tactile/response option, or apparatus geometry that the current dashboard/backend does not yet model.

Only profiles in `GUI-recreatable` pass these Segment 0-4 configuration checks. Later materialization, native execution and physical qualification require separate evidence.

Structural gaps are limited to standardization constraints in the PPS task itself: trial-family and baseline logic, auditory stimulus type/provenance/rendering/gain law, spatial trajectory and apparatus geometry, tactile site/channel/calibration, response capture, and core timing/repetition parameters.

These checks cover current input/schema support for profile metadata, stimulus assets and trajectories, trial sequence, ITI/jitter, SOAs, tactile/baseline strategy and repetitions. A populated field may be reported, derived or a software substitute; consult its provenance and the experiment's reviewed source limitations.

A binaural spatialized profile derived from a two-speaker apparatus is a software approximation. Configuration support does not establish the original speaker transfer, gain law, envelope or stimulus-file equivalence; missing source details remain missing in the scientific review.

Ordinary trial randomization and block order may use explicitly labelled reproducible software defaults. A default never resolves an unreported publication parameter or becomes reported evidence.

Template availability, reviewed source parameters and tested native capability are separate states. A complete experiment inventory can still contain unresolved contracts and unavailable sources.
Clinical populations, interventions, and non-audiotactile experimental context remain part of the source record even where the saved software configuration can be materialized.

## GUI-recreatable

| Profile | Variant | Status | Main reasons |
|---|---|---|---|
| study5_box_breathing_pps | - | ready | All required current-GUI fields are present and materializable. |
| roussel_2025_dynaspace_mobile_pps | - | ready | All required current-GUI fields are present and materializable. |
| matsuda_2021_four_directions | - | ready | All required current-GUI fields are present and materializable. |
| barumerli_2026_arm_movement_exp1 | A | ready | All required current-GUI fields are present and materializable. |
| barumerli_2026_arm_movement_exp2 | B | ready | All required current-GUI fields are present and materializable. |
| noel_2015_walking_full_body_action | - | ready | All required current-GUI fields are present and materializable. |
| noel_2015_bodily_self | A | ready | All required current-GUI fields are present and materializable. |
| noel_2015_bodily_self_back_space | B | ready | All required current-GUI fields are present and materializable. |
| pfeiffer_2018_lateral_perihead_left_to_right | - | ready | All required current-GUI fields are present and materializable. |
| study5_dynaspace_lateral_45_pps | - | ready | All required current-GUI fields are present and materializable. |
| biggio_2017_common_racket | A | ready | All required current-GUI fields are present and materializable. |
| biggio_2017_no_racket | B | ready | All required current-GUI fields are present and materializable. |
| biggio_2017_personal_racket | C | ready | All required current-GUI fields are present and materializable. |
| canzoneri_2013_amputation_prosthesis | - | ready | All required current-GUI fields are present and materializable. |
| canzoneri_2013_tool_use_reshaping | - | ready | All required current-GUI fields are present and materializable. |
| tajadura_jimenez_2009_crossed_visual_deprivation | A | ready | All required current-GUI fields are present and materializable. |
| tajadura_jimenez_2009_uncrossed_visual_deprivation | B | ready | All required current-GUI fields are present and materializable. |
| canzoneri_2012_dynamic_sounds | - | ready | All required current-GUI fields are present and materializable. |
| tonelli_2019_echolocation | - | ready | All required current-GUI fields are present and materializable. |
| galli_2015_wheelchair_full_body | - | ready | All required current-GUI fields are present and materializable. |
| lerner_2021_3d_audio_tactile_boundary | - | ready | All required current-GUI fields are present and materializable. |
| serino_2015_front_back_trunk_exp2 | A | ready | All required current-GUI fields are present and materializable. |
| serino_2015_peri_hand_exp3 | B | ready | All required current-GUI fields are present and materializable. |
| serino_2015_peri_trunk_exp1 | C | ready | All required current-GUI fields are present and materializable. |
| serino_2015_toolless_sync_training | - | ready | All required current-GUI fields are present and materializable. |

## Missing publication parameters

| Profile | Variant | Status | Main reasons |
|---|---|---|---|
| ferri_2015_artificial_looming_valence | A | blocked_missing_parameters | exact auditory files; paper-specific gain envelope |
| ferri_2015_ecological_looming_valence | B | blocked_missing_parameters | licensed ecological sounds; exact amplitude envelopes |
| serino_2007_blind_cane_users | - | blocked_missing_parameters | exact white-noise source asset, seed, and spectral recipe; exact electrical tactile pulse duration, waveform, current, and electrode impedance calibration; exact ITI or jitter distribution and numeric response window |
| taffou_2014_cynophobic_rear_looming | - | blocked_missing_parameters | exact dog/sheep source audio and Audacity amplitude/dynamic matching settings; LISTEN HRTF subject/filter identifier and renderer settings |
| teneggi_2013_social_face_pps | - | blocked_missing_parameters | Experiment 3 exact repetition, integer catch and block counts are unreported; preview counts are software defaults; exact original pink-noise intensity envelope and speaker transfer; premade Gaussian burst train is a source substitution; 100-microsecond electrical pulse and voice-key response capture require external apparatus |

## Toolkit structural gap

No profiles currently fall in this category.

## Machine-Readable Source

- `assets/preloads/profile_recreation_status.json`
