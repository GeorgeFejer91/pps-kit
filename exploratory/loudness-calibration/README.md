# Loudness Calibration Exploration

This folder collects the working evidence and draft policy for estimating and
standardizing the sound pressure level heard through the experiment headphones.
It is exploratory material, not a completed acoustic calibration certificate.

## Confirmed Setup

- Audio interface: Native Instruments Komplete Audio 6 MK2.
- Headphones: Sennheiser HD 560S, confirmed from the external dissertation
  scaffold Study 5 methods and bibliography entry `sennheiser_hd560s`.
- Current HTML GUI documentation only names a generic "Headphones" hardware
  node; it does not currently state the HD 560S model.
- Study 5 WAV generation and dashboard documentation currently describe digital
  levels and peak normalization, not calibrated dB SPL at the ear.

## Bottom Line

The final dB SPL heard by a participant cannot be known with publication-grade
certainty from WAV amplitude, Windows volume, Komplete knob position, and
headphone sensitivity alone. Those inputs are enough for an engineering estimate
and an upper-bound sanity check. The reliable answer requires an acoustic
measurement through the exact playback chain using a HATS, artificial ear,
calibrated coupler, or other documented headphone SPL measurement rig.

The best current policy is therefore:

1. Standardize every controllable setting.
2. Measure the standardized chain.
3. Store the measured calibration profile.
4. Refuse participant runs when the profile or stimulus level audit is missing
   or stale.

## Recommended Standard Settings

- Use the Komplete Audio ASIO route for experiment playback.
- Use Komplete Audio 6 MK2 headphone outputs for auditory channels 1/2.
- Set the Komplete headphone volume knobs fully clockwise only after software
  output caps are active and the calibration sound is known to be safe.
- Set the Komplete direct-monitor `INPUT/HOST` control fully to `HOST` during
  participant playback so live inputs are not mixed into the headphones.
- Treat Windows endpoint volume as outside the participant playback path when
  ASIO is active. For non-ASIO diagnostics, set the Windows endpoint volume to
  100 percent and record that fallback explicitly.
- Do not use the hardware knob or Windows volume for participant-specific
  adjustment once a run begins. Adjust the experiment's software `audio_volume`
  against a calibration profile instead.

## Target Policy

- Looming stimuli should be matched across noise types by a calibrated RMS or
  A-weighted RMS window, not by full-file peak alone.
- Preserve each looming file's within-file approach envelope.
- Match all Study 5 looming files within +/- 1 dB for the chosen calibration
  window, preferably the final 500 ms or final approach window.
- Keep rendered auditory peaks below -3 dBFS before runtime gain where possible;
  refuse any block with samples at or above digital full scale.
- Set inhale/exhale instruction audio below looming audio by a fixed offset,
  initially -6 dB relative to the looming calibration window unless a measured
  comfort pilot justifies another value.
- Do not normalize a whole trial after merging instruction and looming audio;
  that can silently change their intended relative loudness.
- Keep tactile and response-marker gains out of the auditory dB SPL policy.

## Required Measurement

For the HD 560S and Komplete Audio 6 MK2 chain:

1. Put Komplete headphone knobs at the standardized maximum setting.
2. Route through the same driver/API, sample rate, channel map, and software
   gain used for participant runs.
3. Play a calibration file with known dBFS RMS, for example a 1 kHz sine or
   band-limited pink/white noise at -20 dBFS RMS.
4. Measure SPL at the ear simulator or coupler.
5. Store the measured value, meter weighting, integration time, device serials,
   operator, date, and exact audio file hash in a calibration profile.
6. Predict stimulus SPL by level difference from the measured calibration file,
   not by headphone specifications alone.

## Fail-Safes To Implement Later

- Require a tracked or lab-local `loudness_profile.json` before participant
  mode can launch.
- Include hardware identity, headphone model, knob policy, driver route, sample
  rate, target dB SPL, max allowed dB SPL, calibration date, and calibration WAV
  hash in that profile.
- Add a stimulus-audit preflight that checks peak, RMS, final-window RMS, and
  clipping for every block WAV after routing and gain.
- Refuse participant mode if looming variants differ by more than the configured
  dB tolerance.
- Refuse participant mode if instruction RMS is not below looming RMS by the
  configured offset range.
- Record post-routing digital peak/RMS evidence in each run manifest.
- Start every calibration session with low software gain and require operator
  confirmation before enabling the max-knob profile.

## Files

- `hardware_sources.md`: confirmed hardware facts and source links.
- `calculation_model.md`: equations for converting WAV dBFS and measured or
  estimated output voltage into predicted SPL.
- `analyze_stimulus_levels.py`: local audit script for Study 5 looming and
  breathing WAV levels.
- `stimulus_level_audit_notes.md`: current audit interpretation; Brown looming
  is RMS-hotter than the other Study 5 looming variants despite matching peaks.
- `source_manifest.json`: source list and local cache hashes for downloaded
  pages stored under ignored `artifacts/loudness_calibration_sources/`.

## Consensus Literature Notes

The headphone calibration literature supports direct acoustic calibration of the
actual playback chain. A headphone listening-test calibration study recommends
using a head and torso simulator and fixing the entire system setting after the
target SPL is matched [1]. An automated binaural calibration method likewise
uses an artificial head and reports stimulus-level calibration to a tight
tolerance, which is the kind of evidence needed for reproducible experiments
[2]. Low-cost open-circuit-voltage calibration can differ substantially from
HATS-based calibration for headphone reproduction, so voltage-only estimates
should be treated as secondary checks rather than the primary SPL result [3],
[7]. Ear and placement acoustics can also create large errors at higher
frequencies, including standing-wave effects and retest variability [6], [18].

References from the 2026-06-20 Consensus query
`headphone sound pressure level calibration HATS artificial head listening tests headphones`:

[1] [A Study on Sound Level Calibration For Listening Tests Performed with Headphones in Architectural Acoustics](https://consensus.app/papers/details/7d4fb4b9634d5a6691d39e229fd9eb0c/?utm_source=unknown)
(Ezgi Türk Gürkan, 2021)

[2] [Automation of binaural headphone audio calibration on an artificial head](https://consensus.app/papers/details/4067e4cb77535331a8ec307fa321f54d/?utm_source=unknown)
(Kenneth Ooi et al., 2021, MethodsX)

[3] [Preliminary assessment of a cost-effective headphone calibration procedure for soundscape evaluations](https://consensus.app/papers/details/23d193c6f4d35d67a3383343a7cd1042/?utm_source=unknown)
(Bhan Lam et al., 2022)

[6] [Pure-Tone Audiometry With Forward Pressure Level Calibration Leads to Clinically-Relevant Improvements in Test-Retest Reliability](https://consensus.app/papers/details/feef7f16ec1d561287b614762d2b68b3/?utm_source=unknown)
(Judi A. Lapsley Miller et al., 2018, Ear and Hearing)

[7] [Assessment of a cost-effective headphone calibration procedure for soundscape evaluations](https://consensus.app/papers/details/1c8038e81e1e57999c07fefaae8f8886/?utm_source=unknown)
(Bhan Lam et al., 2022)

[18] [Amplitude variation in calibrated audiometer systems in clinical simulations](https://consensus.app/papers/details/5745b55c58af51f2aa55d3548eb2f56d/?utm_source=unknown)
(C. Barlow et al., 2014, Noise & Health)
