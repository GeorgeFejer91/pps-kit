# Hardware Setup

This toolkit is Windows-first for experiment running because WASAPI loopback recording is used to verify playback and decode stimulus/response timing. Stimulus generation, decoding, and sample analysis are intended to remain cross-platform where possible.

## Required Audio-Tactile Setup

- A Windows computer with the package installed in editable or packaged form.
- A stereo-capable output device.
- Audio channel 1 routed to the auditory stimulus path.
- Audio channel 2 routed to the tactile/vibrotactile path when using sound-card-driven tactile output.
- A mouse, keyboard, button box, or other response device supported by the runner.
- Optional WASAPI loopback recording support through `pyaudiowpatch` for synchronized playback capture.

## Optional Spatial Audio Inputs

SOFA/HRIR files are user-supplied and are not redistributed in this repository unless redistribution rights are verified. Place local SOFA/HRIR files in an ignored local folder or point the stimulus designer to their location.

## Calibration Values To Record

These values should be saved in the GUI or session notes whenever available:

- audio device name and channel routing
- tactile output device and channel routing
- auditory volume and measured SPL, if measured
- tactile intensity or participant threshold rule
- measured audio onset latency
- measured tactile onset latency
- response-device latency, if measured
