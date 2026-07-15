# Noel et al. (2015b)

- Record ID: `noel_2015_walking`
- DOI: `10.1016/j.neuropsychologia.2014.08.030`
- DOI URL: https://doi.org/10.1016/j.neuropsychologia.2014.08.030
- Public PDF reviewed: https://noel-lab.org/wp-content/uploads/2024/05/nsy_5279_pps-walking.pdf
- Manual review: `For-AI/audiotactile-paper-metadata-audit/manual_reviews/noel_2015_walking.json`
- Coverage category: `covered_runnable_profile`
- Current template: `noel_2015_walking_full_body_action`
- Validation report: `artifacts/validation_runs/current_goal_noel_2015_known_parameter_20260715/noel_2015_known_parameter_validation_report.json`

## Extracted Minimum PPS Parameters

- Auditory stimulus: 50 dB white noise, approaching or receding over a 2 m path at 75 cm/s.
- Apparatus provenance: two 8-speaker JBL Control 1 Pro arrays, 50 cm lateral from the participant, driven by M-Audio FastTrack Ultra 8R.
- Locomotion factor: standing still versus treadmill walking at 0.70 m/s.
- Tactile stimulus: 100 ms chest vibration, documented as 150 Hz Precision MicroDrives shaftless model 312-101 metadata in the runnable profile.
- Response mode: right-thumb controller in the paper; mouse-click simulated participant-like responses in software validation.
- Tactile timings: T1-T5 = 440, 880, 1330, 1770, and 2220 ms.
- Distance-at-tactile mapping: D1-D5 = 33, 66, 100, 133, and 166 cm, derived from the reported speed/delay relation and interpreted as a unit typo in the PDF distance label.
- Direction mapping: looming maps T1-T5 to D5/D4/D3/D2/D1; receding maps T1-T5 to D1/D2/D3/D4/D5.
- Trial families: audio-tactile target trials, tactile-only T1/T5 baselines, and sound-only catch trials.
- Trial formula: 2 locomotion conditions x 2 sound directions x (5 distances + 2 baselines + 1 catch) x 16 repetitions = 512 trials.
- Expected outcome: standing facilitation is strongest near the body, while walking expands the facilitation range through the farthest sampled distance; receding does not show the same spatial modulation.

## Toolkit Validation

The paper-specific validator loads the profile through the HTML-dashboard backend controller, materializes Segments 2-6, prepares runnable block WAV/session packages, runs the experiment runner, writes software loopback sidecars, injects mouse-click simulated responses after tactile onset for tactile rows, withholds catch responses, and compares observed rows/events against the extracted PDF contract.

Retained validation result:

- 512 participant-like trial rows.
- 320 audio-tactile rows, 128 tactile-only baseline rows, and 64 sound-only catch rows.
- 448 response-required rows with simulated mouse clicks and 64 withhold rows.
- 256 standing and 256 walking rows.
- 256 looming and 256 receding rows.
- Eight runnable block WAVs and eight software loopback sidecars.
- Locomotion, sound direction, timing, distance, tactile waveform, and response-rule metadata preserved through runner/analysis rows.

## Remaining Caveats

The toolkit recreation is a software PPS-task validation, not a physical apparatus replication. Exact treadmill behavior, optic-flow display, physical SPL field, room acoustics, and the original two-array loudspeaker interpolation remain apparatus/provenance caveats outside the software-runner contract.
