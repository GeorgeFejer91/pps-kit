# Loudness Calibration Project Memory

Created: 2026-06-20

This repo now has an exploratory loudness-calibration workspace at
`exploratory/loudness-calibration/`.

Key findings:

- Study 5 hardware uses Native Instruments Komplete Audio 6 MK2 and Sennheiser
  HD 560S headphones.
- The HD 560S model was confirmed from the external dissertation scaffold Study
  5 methods/bibliography, not from this repo's HTML dashboard.
- The current HTML dashboard hardware node still says only "Headphones"; no GUI
  update was made during this work.
- Sennheiser's HD 560S product page lists 110 dB SPL at 1 kHz / 1 Vrms, 120 ohm
  transducer text, dynamic open design, and 6 Hz to 38 kHz frequency response.
- Public Native Instruments pages confirm Komplete headphone-output controls,
  but a full manufacturer electrical headphone-output spec was not located in a
  directly downloadable current KA6 MK2 manual.
- Multiple reseller/spec pages list Komplete Audio 6 MK2 headphone output as
  2 x 25 mW at 33 ohms. Treat this as a secondary engineering estimate only.

Policy direction:

- The final participant dB SPL must be based on direct acoustic measurement of
  the standardized playback chain, preferably HATS/artificial-ear/coupler based.
- Specs can provide plausibility checks but not publication-grade SPL.
- The user's preferred max Komplete hardware-knob policy is acceptable only with
  software gain caps, a measured calibration profile, and startup fail-safes.
- ASIO playback should be treated as the standard route; Windows endpoint volume
  is only part of the policy for non-ASIO diagnostics.
- Looming stimuli should be matched by calibrated RMS/final-window RMS across
  noise types. Instruction audio should remain below looming audio by a fixed
  offset, initially documented as -6 dB pending pilot comfort measurement.

Future implementation should add participant-run preflight checks for a
`loudness_profile.json`, stimulus-level audit tolerance, clipping rejection, and
post-routing digital level evidence in run manifests.
