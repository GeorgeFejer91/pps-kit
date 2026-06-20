# Audio-Tactile PPS Paradigm Library

This project treats published paradigms as preloadable study profiles rather than hard-coded scripts. Each profile carries a saved `StimulusDesign`, citation metadata, source URL, DOI, verification status, reference parameters, and field-level provenance notes. Profiles preload trajectory, timing, protocol, noise/tone values, and a local catalog under `assets/preloads/<template_id>/`; the standardized FABIAN HRIR rendering resource stays under the hood.

## Consensus MVP Fields

The literature varies heavily, but a reusable audio-tactile PPS paradigm needs at least:

- tactile target site, duration, intensity calibration, and response mode
- auditory stimulus type, motion direction, distance/azimuth path, duration, and intensity envelope
- SOA values and corresponding spatial values at tactile onset
- repetitions per condition
- baseline/unisensory tactile schedule
- catch-trial percentage or exact count
- block structure, participants, randomization/counterbalancing, and seed
- analysis contrast: near vs far, baseline subtraction, sigmoid boundary, or expectancy-corrected looming/receding comparison
- source citation and verification status

## Bundled Templates

The current catalog contains two unpublished Study 5 workflows plus 20 published-study profiles. Each profile folder mirrors the HTML dashboard workflow with `01_profile`, `02_looming_stimuli`, `03_baseline_strategy`, `04_trial_designer`, and `05_run_setup`. The `02_looming_stimuli` segment contains prebaked auditory-only WAVs and source/trajectory metadata; tactile events are still added later from the trial/SOA schedule during session preparation. When a profile declares representable motion-direction factors, the catalog expands them into separate source assets and trajectory snapshots rather than collapsing the paper to one representative path. A `verified` profile means the fields represented in the current GUI have been checked against accessible methods or local reference material. A `partial` profile means the profile is useful as a structured starting point, but exact replication still requires fields or assets the current app does not yet model. See [PUBLISHED_PARADIGM_STRESS_TEST.md](PUBLISHED_PARADIGM_STRESS_TEST.md) for the per-study trial-family, SOA, jitter/procedure, and missing-parameter audit.

| Template | Status | Current fit | Main gap before exact replication |
|---|---:|---|---|
| `pfeiffer_2018_lateral_perihead_left_to_right.json` | verified | Bilateral lateral pink-noise trajectory/noise profile from the local simulator reference, with left-to-right and right-to-left prebaked source variants. | Full equivalence requires using the original spherical-head equations or the 3DTI native backend comparison report. |
| `canzoneri_2012_dynamic_sounds.json` | partial | Canonical dynamic audio-tactile PPS task with original T1-T5 timing, T0/T6 baseline metadata, and auditory-only catch count. | Direction-coupled tactile-only T0/T6 rows need a richer baseline subtype model. |
| `canzoneri_2013_tool_use_reshaping.json` | partial | Tool-use PPS reshaping scaffold based on the Canzoneri-family audio-tactile task. | Pre/post intervention phases, tool-use/control assignment, and body-representation co-tasks are metadata only. |
| `canzoneri_2013_amputation_prosthesis.json` | partial | Clinical amputation/prosthesis PPS scaffold using the dynamic audio-tactile task family. | Clinical group, prosthesis-worn state, tested-limb assignment, and calibration details are metadata only. |
| `noel_2015_bodily_self.json` | verified | Full-body-illusion PPS trial schedule and chest tactile site. | Full-body illusion stroking context remains outside the GUI. |
| `matsuda_2021_four_directions.json` | verified | Front/rear/left/right audio-tactile PPS block structure. | Original Unity/audio implementation details are represented as labels, not a full VR scene. |
| `tonelli_2019_echolocation.json` | partial | Seven-distance echolocation-style PPS scaffold. | Exact speaker control and training materials require original protocol/code. |
| `barumerli_2026_arm_movement_exp1.json` | verified | Arm-movement PPS Experiment 1 structure from open methods. | Exact motor-task apparatus remains protocol-level metadata. |
| `barumerli_2026_arm_movement_exp2.json` | verified | Arm-movement PPS Experiment 2 structure from open methods. | Exact motor-task apparatus remains protocol-level metadata. |
| `ferri_2015_artificial_looming_valence.json` | partial | Artificial negative/neutral looming-sound PPS scaffold. | Original emotional sound files, ratings, and gain envelopes are not bundled. |
| `ferri_2015_ecological_looming_valence.json` | partial | Ecological negative/neutral/positive looming-sound PPS scaffold. | Original ecological sound assets are not redistributed. |
| `taffou_2014_cynophobic_rear_looming.json` | partial | Rear-field dog/sheep binaural looming task with T1-T5 timing. | Exact dog/sheep sounds, LISTEN HRTFs, and left/right rear trajectories need asset support. |
| `teneggi_2013_social_face_pps.json` | partial | Face tactile PPS task with approaching/receding sound labels. | Exact distance/timing table still needs source extraction; social context is non-blocking for the PPS-task profile. |
| `serino_2015_toolless_sync_training.json` | partial | Synchronous/asynchronous far-audio and hand-tactile training scaffold with Canzoneri-family PPS measurement. | Electrical tactile calibration and voice-key capture details still need extraction; training context is non-blocking unless it changes task timing. |
| `serino_2015_peri_trunk_exp1.json` | partial | Peri-trunk D1-D6 looming/receding analog-apparatus scaffold recreated as a binaural trajectory. | Current profile passes the Segment 0-4 PPS-task recreation gate. |
| `serino_2015_peri_hand_exp3.json` | partial | Peri-hand D1-D5 looming/receding scaffold with analog-apparatus provenance. | Lateral hand position is not a first-class coordinate field yet. |
| `serino_2015_front_back_trunk_exp2.json` | partial | Front/back trunk pass-through trajectory scaffold. | Original 16-speaker array and detailed front/back block schedule are simplified. |
| `galli_2015_wheelchair_full_body.json` | partial | Wheelchair full-body PPS timing and front/back trunk tactile schedule. | Speaker-array Gaussian amplitude control is not represented yet; wheelchair context is non-blocking for the PPS-task profile. |
| `noel_2015_walking_full_body_action.json` | partial | Walking/treadmill PPS expansion scaffold. | Exact sound distances and trial counts still need extraction; locomotion and optic-flow factors are context notes unless they change task execution. |
| `lerner_2021_3d_audio_tactile_boundary.json` | partial | 3D Tune-In/Unity 3D PPS mapping scaffold with twelve prebaked direction trajectories for dynamic and flat source types. | Body-scaled distance mode and exact Unity/3D Tune-In condition logic are not implemented yet. |

## Literature Search Notes

The template inventory was seeded from accessible method sections and systematic-review leads, including Canzoneri et al. (2012), Canzoneri et al. (2013) tool-use/prosthesis variants, Teneggi et al. (2013), Taffou and Viaud-Delmon (2014), Noel et al. (2015), Ferri et al. (2015), Serino et al. (2015), Galli et al. (2015), Tonelli et al. (2019), Holmes et al. (2020), Matsuda et al. (2021), Lerner et al. (2021), and Lamia, Shabani, and Candidi (2026). Holmes et al. (2020) is especially useful because it reports that audiotactile PPS studies differ widely in auditory distances, stimuli, tactile target types, body parts, and PPS criteria.

For perfect replication, promote a `partial` profile to `verified` only after checking the original article, supplementary materials, and any shared experiment code.
