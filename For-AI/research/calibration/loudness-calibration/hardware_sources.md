# Hardware Sources

This page records source pointers and the facts that matter for dB SPL
estimation. Vendor and reseller pages were also cached locally under ignored
`artifacts/loudness_calibration_sources/`; the tracked repo stores only source
metadata and hashes.

## Headphones

Model: Sennheiser HD 560S.

Model evidence:

- External dissertation scaffold, Study 5 methods Apparatus section: names
  "Sennheiser HD 560S open-back reference headphones".
- External dissertation scaffold bibliography: entry `sennheiser_hd560s` points
  to the Sennheiser HD 560S product page.
- Current HTML dashboard documentation only says "Headphones"; no model number
  was found in the dashboard or generated HTML docs during the 2026-06-20 audit.

Manufacturer facts used:

- Product page: https://eu.sennheiser-hearing.com/en-de/products/hd-560s
- SKU: 509144.
- Type: dynamic, open, over-ear.
- Frequency response: 6 Hz to 38,000 Hz.
- Sensitivity: 110 dB SPL at 1 kHz, 1 Vrms.
- THD: < 0.05 percent at 1 kHz / 90 dB SPL.
- Practical implication: if the headphone jack voltage is known, a first-order
  1 kHz estimate is `SPL = 110 + 20 * log10(Vrms / 1 Vrms)` before correction
  for stimulus spectrum, headphone response, fit, and ear/coupler acoustics.

## Audio Interface

Model: Native Instruments Komplete Audio 6 MK2.

Primary product/route facts:

- Native Instruments quickstart:
  https://www.native-instruments.com/en/komplete-audio-6-quickstart/
- The quickstart documents two headphone outputs and says the knob above each
  headphone output controls headphone volume.
- The same quickstart documents `OUT1/2 VOLUME` separately, so headphone volume
  and main line-output volume are distinct controls.
- The quickstart documents an `INPUT/HOST` control for headphone monitoring; for
  participant playback this should be fully toward host/computer playback.
- Native Instruments ASIO driver installation:
  https://support.native-instruments.com/hc/en-us/articles/360001194217-Installing-the-ASIO-Driver-for-KOMPLETE-AUDIO-1-2-6-MK2-Windows

Secondary electrical specification facts:

- B&H product/specification page:
  https://www.bhphotovideo.com/c/product/1477750-REG/native_instruments_25898_komplete_audio_6_mk2.html
- Accessible reseller pages with matching electrical specs:
  https://globalproductions.ee/toode/native-instruments-komplete-audio-6-mk2/
  and
  https://uae.microless.com/product/native-instruments-26440-komplete-audio-6-mk2-192-khz-24-bit-record-audio-4-analog-in-out-2-digital-in-out-2-headphone-out-midi-in-out-usb-2-0-26440/
- Repeated facts across those pages:
  - 4 analog inputs / 4 analog outputs plus S/PDIF I/O.
  - Up to 192 kHz / 24-bit.
  - USB 2.0 bus powered.
  - Balanced line outputs around +11.3 to +11.5 dBu.
  - Headphone output power listed as 2 x 25 mW at 33 ohms.
  - Headphone frequency response listed as 20 Hz to 20 kHz +/- 0.1 dB on
    accessible reseller pages.

Important caveat:

The Komplete Audio 6 MK2 headphone output voltage into the HD 560S 120 ohm load
is not proven by the 25 mW at 33 ohm secondary spec. If treated as a voltage
limit, 25 mW into 33 ohms implies about 0.908 Vrms:

`sqrt(0.025 W * 33 ohm) = 0.908 Vrms`

With the HD 560S 110 dB SPL / 1 Vrms sensitivity, that implies a rough
full-scale 1 kHz estimate near 109.2 dB SPL. This is not a calibration result.
The real maximum into 120 ohms may differ, and actual SPL will vary with
frequency content, headphone placement, and ear/coupler acoustics.

## Safety References

- WHO-ITU safe-listening standard:
  https://www.who.int/publications/i/item/9789241515276
- WHO gives two weekly sound allowance modes: adults at 80 dB for 40 hours per
  week and children/sensitive users at 75 dB for 40 hours per week.
- OSHA overview of occupational noise:
  https://www.osha.gov/noise
- OSHA summarizes NIOSH's recommendation to control occupational exposure below
  an 85 dBA 8-hour equivalent and to use a 3 dB exchange rate.

The experiment policy should target comfort and conservative exposure. Because
Study 5 stimuli are brief, the practical concern is avoiding startle,
participant discomfort, and accidental high output from max hardware knobs.
