# Audio-Tactile PPS Paradigm Library

This project treats published paradigms as preloadable templates rather than hard-coded scripts. Each template carries a saved `StimulusDesign`, citation metadata, source URL, DOI, verification status, and field-level provenance notes.

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

- `canzoneri_2012_dynamic_sounds.json`: canonical dynamic audio-tactile PPS task, partial verification.
- `noel_2015_bodily_self.json`: full-body-illusion audio-tactile PPS task, verified trial counts from accessible methods.
- `matsuda_2021_four_directions.json`: front/rear/left/right audio-tactile PPS block, verified from open methods.
- `tonelli_2019_echolocation.json`: seven-speaker echolocation-training PPS task, partial timing verification.
- `barumerli_2026_arm_movement_exp1.json`: arm-movement audio-tactile PPS Experiment 1, verified from open methods.
- `barumerli_2026_arm_movement_exp2.json`: arm-movement audio-tactile PPS Experiment 2, verified from open methods.

## Literature Search Notes

The template inventory was seeded from accessible method sections and systematic-review leads, including Canzoneri et al. (2012), Noel et al. (2015), Matsuda et al. (2021), Tonelli et al. (2019), Holmes et al. (2020), and Barumerli et al. (2026). Holmes et al. (2020) is especially useful because it reports that audiotactile PPS studies differ widely in auditory distances, stimuli, tactile target types, body parts, and PPS criteria.

For perfect replication, promote a `partial` template to `verified` only after checking the original article, supplementary materials, and any shared experiment code.
