# Hardware Vendor Documentation Cache

This repo keeps locally downloaded vendor documentation in an untracked local
hardware-doc cache.

That cache is intentionally ignored by Git.
Vendor manuals, support pages, and product spec sheets are third-party material;
do not move them into tracked/public release files unless redistribution rights
have been reviewed.

The local cache includes a manifest with source URLs and SHA-256 hashes.

## Cached Devices

### Native Instruments Komplete Audio 6

The local lab audio interface is documented elsewhere in this repo as
Komplete Audio 6 MK2. The cache therefore prioritizes MK2-relevant setup and
driver pages, while also preserving one older Komplete Audio 6 English manual
PDF because NI's current public manual path is no longer straightforward.

Cached files include:

- Official NI ASIO driver installation support page.
- Official NI KA6 MK2 control-panel recognition support page.
- Official NI KA6 troubleshooting guide.
- Official NI guidance on product manuals and hardware updates.
- B&H-hosted KA6 MK2 specs page for dimensions, weight, and electrical specs.
- B&H-hosted Native Instruments Komplete Audio 6 English manual PDF
  dated 06/2016; verify MK1/MK2 applicability before using it as authority.

Useful lab specs recorded from the cached KA6 MK2 spec page:

- Analog I/O: 4 in / 4 out at up to 192 kHz.
- Digital I/O: stereo S/PDIF in/out.
- Audio resolution: up to 192 kHz / 24-bit.
- Analog outputs: four 1/4-inch TRS line outputs plus two 1/4-inch headphone
  outputs.
- Host connection: USB-B, USB 2.0, USB bus powered.
- Physical size: 7.87 x 5.37 x 2.19 in / 19.99 x 13.64 x 5.56 cm.
- Weight: 1.9 lb / 0.9 kg.

NI's main KA6 quickstart and driver-listing pages were visible through browser
indexing but returned HTTP 403 to local scripted download tools on 2026-06-06.
The source URLs are recorded in the manifest as blocked/unavailable sources.

### Woojer Strap

The active latency-validation protocol assumes Woojer Strap 4 as the wired
analog tactile target. The cache also includes Strap 3 documentation for
backward reference, but new electrical loopback and experiment-wiring docs
should describe Strap 4 unless the physical lab unit is later corrected. For
this toolkit's synchronized tactile routing, prefer a wired analog connection
from the Komplete Audio 6 tactile output to the Woojer analog input; Bluetooth
paths add avoidable latency.

Cached files include:

- Official Woojer Strap 3 web manual.
- Official Woojer Strap 3 support article and attached PDF manual.
- Official Woojer Strap 3 getting-started page.
- Official Woojer Series 3 PC connection page.
- Official Woojer Strap 4 web manual.
- Official Woojer Strap-family overview/spec page.
- Official Woojer getting-started page.
- Official Woojer Strap 3 product page.

Useful lab specs recorded from the cached Woojer pages:

- Haptic frequency response: 1-250 Hz.
- Audio frequency response: 20 Hz-20 kHz.
- Transducer: one Osci V2 TRX.
- Strap 3 transducer impedance: 11 ohm.
- Audio input: 3.5 mm TRRS aux, USB stereo audio, Bluetooth A2DP.
- Audio output: 3.5 mm TRRS aux, Bluetooth A2DP.
- Bluetooth: Bluetooth 5.0 audio plus BLE app control/update.
- Charging: standard USB-C, 5 V, 3 h in the manual specs.
- Strap 3 battery: 1SP Li-Ion battery, 3.6 V.
- Strap 4 battery: 3.6 V, 3500 mAh.
- Headphone amplifier output: 138 mW.
- Headphone output S/N ratio: 98 dB.
- Strap-family overview lists current Strap weight as 250 g and battery life as
  10 h; record the exact physical unit generation before treating those as lab
  calibration values.

Older Strap Edge pages surfaced in search/browser results, but local download
attempts returned either HTTP 404 or repeated redirects on 2026-06-06. Those
URLs are recorded in the manifest as blocked/unavailable sources.
