# Hardware Setup

This toolkit is Windows-first for experiment running because the validated lab route uses a synchronized multichannel ASIO output device for binaural audio plus tactile drive. Stimulus generation, decoding, and sample analysis are intended to remain cross-platform where possible.

## Required Audio-Tactile Setup

- A Windows computer with the package installed in editable or packaged form.
- A stereo-capable output device for legacy Study 5 blocks.
- A synchronized 3+ channel output device for rendered binaural+tactile looming blocks.
- Legacy Study 5 routing: audio output 1 is auditory; audio output 2 is tactile.
- Rendered trajectory routing: outputs 1/2 are binaural left/right; output 3 is tactile.
- A mouse, keyboard, button box, or other response device supported by the runner.
- Optional local full-audio evidence WAV written by the runner from mixed output buffers.
- Optional WASAPI loopback diagnostics through `pyaudiowpatch`; this is not the core ASIO validation path.

For the local Komplete Audio 6 setup, use the `Komplete Audio ASIO Driver` for
rendered trajectories. The separate Windows `Output 1/2` and `Output 3/4`
endpoints are stereo-only and are treated as legacy-only. See
[Audio Routing And Stress Test](AUDIO_ROUTING_STRESS_TEST.md).

Physical electrical loopback from output 1/2/3 to input 1/2/3 is an internal
validation reference for measuring latency, interchannel skew, and software
recording accuracy. It is not required during normal participant experiments.

Vendor hardware manuals and spec snapshots for the Komplete Audio 6 and Woojer
Strap are indexed in [Hardware Vendor Documentation Cache](HARDWARE_VENDOR_DOCS.md).
Downloaded vendor files live in an untracked local hardware-doc cache and are
intentionally not tracked until redistribution rights are reviewed.

## Standard Spatial Audio Resource

The configurable designer uses the bundled standardized FABIAN/TU SOFA HRIR resource for binaural rendering. Study profiles should vary trajectory, timing, and noise parameters, not expose arbitrary SOFA selection to experimenters. Public release bundles include the FABIAN file together with an attribution/hash manifest.

## Calibration Values To Record

These values should be saved in the GUI or session notes whenever available:

- audio device name and channel routing
- tactile output device and channel routing
- auditory volume and measured SPL, if measured
- tactile intensity or participant threshold rule
- measured audio onset latency
- measured tactile onset latency
- response-device latency, if measured
