# Calculation Model

Use this model to separate digital level control from acoustic calibration.

## Digital Level

For floating-point WAV data in the repo, full scale is `1.0` peak amplitude.

```text
peak_dbfs = 20 * log10(max(abs(samples)))
rms_dbfs = 20 * log10(sqrt(mean(samples^2)))
gain_db = 20 * log10(linear_gain)
```

A full-scale sine wave with peak amplitude `1.0` has RMS `0.7071`, or
`-3.0103 dBFS RMS`.

## Voltage Estimate

If a device's full-scale RMS headphone voltage is known:

```text
stimulus_vrms = full_scale_vrms
                 * 10^(stimulus_rms_dbfs / 20)
                 * software_gain
                 * os_gain_if_not_asio
```

When using ASIO exclusive playback, do not assume Windows endpoint volume is in
the signal path. If using WASAPI/DirectSound for diagnostics, record the Windows
volume and treat it as another gain term.

## Headphone Sensitivity Estimate

For HD 560S sensitivity of 110 dB SPL at 1 kHz / 1 Vrms:

```text
spl_1khz_estimate = 110 + 20 * log10(stimulus_vrms / 1.0)
```

If a sensitivity is specified per milliwatt instead:

```text
power_mw = 1000 * stimulus_vrms^2 / headphone_impedance_ohm
spl_estimate = sensitivity_db_spl_per_mw + 10 * log10(power_mw)
```

## Komplete Audio 6 MK2 Rough Check

Secondary Komplete Audio 6 MK2 specs list headphone output as `25 mW per
channel into 33 ohms`. If this is interpreted as a voltage-limited output:

```text
full_scale_vrms_estimate = sqrt(0.025 * 33) = 0.908 Vrms
hd560s_full_scale_1khz_spl = 110 + 20 * log10(0.908) = 109.2 dB SPL
```

This is a plausibility estimate only. It should not be reported as the
participant SPL because it depends on a secondary spec, the load condition is
not the HD 560S 120 ohm load, and it ignores headphone fit and ear acoustics.

## Measurement-Based Prediction

Once a calibration file is measured, use level differences:

```text
stimulus_spl = measured_calibration_spl
               + (stimulus_rms_dbfs - calibration_rms_dbfs)
               + (stimulus_software_gain_db - calibration_software_gain_db)
```

Use the same channel, headphone output, knob position, driver, sample rate, and
measurement rig for calibration and participant playback.

Example:

```text
measured calibration tone: 74.0 dB SPL at -20.0 dBFS RMS
looming final-window RMS: -28.0 dBFS RMS
same software gain

looming final-window SPL estimate = 74.0 + (-28.0 - -20.0) = 66.0 dB SPL
```

## Recommended Fields For `loudness_profile.json`

```json
{
  "profile_version": 1,
  "calibrated_on": "YYYY-MM-DD",
  "operator": "",
  "audio_interface": "Native Instruments Komplete Audio 6 MK2",
  "headphones": "Sennheiser HD 560S",
  "driver": "Komplete Audio ASIO Driver",
  "sample_rate_hz": 44100,
  "headphone_knobs": "maximum clockwise",
  "input_host_knob": "host",
  "windows_endpoint_volume": "not in ASIO path",
  "calibration_wav_sha256": "",
  "calibration_wav_rms_dbfs": -20.0,
  "measured_spl_db": null,
  "spl_weighting": "Z or A",
  "integration": "Leq/LAS/LAF/manual",
  "measurement_rig": "",
  "target_looming_final_window_spl_db": null,
  "max_allowed_spl_db": null,
  "instruction_offset_db": -6.0,
  "looming_match_tolerance_db": 1.0
}
```
