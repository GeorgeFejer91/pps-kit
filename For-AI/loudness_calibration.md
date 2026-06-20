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
- Looming stimuli should be matched by calibrated endpoint-window RMS across
  noise types, preferring the constant post-hold when present. Instruction audio
  should remain below looming audio by a fixed offset, initially documented as
  -6 dB pending pilot comfort measurement.

Implemented software policy:

- `src/peripersonal_space_toolkit/loudness.py` defines the shared
  `loudness_policy` schema and defaults: 55 dB SPL start, 75 dB SPL endpoint,
  -6 dB instruction offset, estimated 0 dBFS = 109.2 dB SPL for Komplete Audio
  6 MK2 at maximum headphone output into HD 560S, and -1 dBFS audio peak
  ceiling.
- The HTML dashboard now exposes a Segment 1 `Loudness Contract` panel instead
  of visible per-source gain controls. The old `gain` fields remain hidden for
  backward-compatible design loading; the intended calibration surface is the
  top-level loudness policy.
- Renderer loudness-control mode is active whenever a design declares
  `study_profile_reference_parameters.loudness_policy`. In that mode the
  Python SOFA/FABIAN renderer applies a linear-dB looming envelope, keeps
  pre/post trajectory holds constant at the start/endpoint SPL, disables hidden
  output peak normalization, disables direct-path distance gain, and scales the
  endpoint calibration window to the target RMS dBFS. If a 0.5 s post-hold is
  present, that post-hold is the preferred endpoint calibration window; otherwise
  the renderer falls back to the final active movement window.
- Segment 1 render manifests, Segment 2-6 dashboard manifests, study-settings
  manifests, and runner session manifests now carry the loudness policy. Segment
  6 is stale if the policy changes, and Segment 2 refuses to bake from referenced
  Segment 1 ingredients whose recorded loudness-policy provenance differs from
  the current design.
- Segment 2 fixed instruction clips are attenuated by the loudness policy
  instruction offset at sequence-assembly time. Source assets are not modified.

Future implementation should add participant-run preflight checks for a measured
`loudness_profile.json`, stimulus-level audit tolerance, physical SPL measurement
entry, and post-routing digital level evidence in run manifests.

Local source update:

- `exploratory/loudness-calibration/sources/` is the local-only publication
  review folder for this loudness work. PDFs there are ignored by Git.
- The Ferri et al. PPS paper is locally downloaded as
  `ferri_2015_emotion_inducing_approaching_sounds_pps.pdf` from UCL Discovery;
  tracked metadata, hash, page count, and short facts live in
  `exploratory/loudness-calibration/source_manifest.json`.
