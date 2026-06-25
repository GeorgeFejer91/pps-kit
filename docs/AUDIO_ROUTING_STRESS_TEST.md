# Audio Routing And Stress Test

## Decision

Rendered looming stimuli use three output channels:

- output 1: binaural left
- output 2: binaural right
- output 3: tactile or vibrotactile drive

These channels must be sent through one synchronized multichannel device. On the
local Komplete Audio 6 setup, that means the `Komplete Audio ASIO Driver`, not
the separate Windows `Output 1/2` and `Output 3/4` stereo endpoints.

The legacy Study 5 stereo blocks remain supported:

- legacy WAV left channel: tactile
- legacy WAV right channel: audio
- runner output mapping: WAV right -> output 1, WAV left -> output 2

The runner uses one persistent ASIO output stream for the experiment player when
the Komplete ASIO device is selected. Blocks, spoken instructions, background
audio, and click/tactile feedback are mixed into that one stream. This avoids
the ASIO single-client failure mode where a persistent click stream prevents a
second block stream from opening.

## Why ASIO Is The Correct Route Here

The Windows MME, DirectSound, and WASAPI Komplete endpoints expose the hardware
as separate stereo pairs. That is acceptable for old two-channel Study 5 blocks,
but it cannot guarantee sample-synchronous timing between binaural audio and a
separate tactile stream.

The ASIO endpoint exposes the interface as one device with six output channels.
That lets the runner open a single PortAudio stream and write left, right, and
tactile samples in the same callback buffer.

Relevant implementation references:

- `sounddevice.query_devices()` reports `max_output_channels`, and `check_output_settings()` checks whether a requested channel count/sample rate is supported: <https://python-sounddevice.readthedocs.io/en/0.4.7/api/checking-hardware.html>
- `sounddevice.AsioSettings(channel_selectors=...)` supports selecting specific zero-based ASIO channels and is passed through `extra_settings`: <https://python-sounddevice.readthedocs.io/en/0.4.7/api/platform-specific-settings.html>
- PortAudio streams are tied to devices/host APIs and support multichannel buffers; ASIO-specific behavior is constrained by the host API/driver: <https://portaudio.com/docs/v19-doxydocs/api_overview.html>
- PortAudio latency values are suggestions and actual latency is known after opening a stream; stress testing is therefore required on the target machine: <https://github.com/PortAudio/portaudio/wiki/BufferingLatencyAndTimingImplementationGuidelines>

## Driver Audit

Installed local Native Instruments driver:

- device: Komplete Audio 6 MK2
- installed driver: `5.22.0.17558`
- driver date: 2021-09-01
- ASIO registry entry: `Komplete Audio ASIO Driver`

Official Native Instruments driver listing checked on 2026-06-06:

- `Komplete Audio 6 MK2 Driver 5.22.0 - Windows 10`
- older fallback: `Komplete Audio 6 MK2 Driver 5.0.0 - Windows 10`
- firmware updater: `Firmware Updater for Komplete Audio 6 MK2 1.2.0 - Windows 10`

Conclusion: the installed NI driver is already the latest official driver listed
for this interface. Scripted ZIP download from the NI CDN returned HTTP 403
Access Denied; use the official NI browser page or Native Access for manual
reinstall/firmware-update workflows. Do not replace the native NI ASIO driver
with a generic wrapper for the experiment player.

Alternative-driver results:

- `ASIO4ALL v2` opened low-latency stereo streams but exposed only two outputs on
  this machine, so it cannot carry binaural left/right plus tactile.
- `Nahimic Easy Surround` exposed an 8-channel WDM-KS virtual endpoint with low
  reported latency, but it is not the physical Komplete output path and is not a
  suitable lab routing target for headphones plus tactile hardware.
- FlexASIO and Voicemeeter are wrapper/mixer approaches over Windows audio APIs.
  They can be useful for general routing but add another software layer and do
  not improve on the native NI ASIO endpoint for one physical multichannel
  interface.

## Commands

List devices:

```bat
windows\List_Audio_Devices.bat
```

Run the silent stress test:

```bat
windows\Stress_Audio_Device.bat
```

Or run a focused matrix manually:

```powershell
python -m peripersonal_space_toolkit.audio_device_stress --device-query Komplete --channels 3 4 2 --latencies low 0.003 0.005 0.010 0.020 --blocksizes 64 128 256 512
```

The stress test writes CSV and JSON results under `artifacts\audio_device_stress\`.

## Local Result

On the tested workstation, the device listing and `pps-audio-stress` dry-run
showed:

- `Komplete Audio ASIO Driver | ASIO | out:6` marked `spatial-ok`
- `Output 1/2`, `Output 3/4`, and SPDIF Komplete Windows endpoints marked
  `legacy-only` because they expose two output channels each

The focused write-mode silent stress matrix for device 31,
`Komplete Audio ASIO Driver`, passed all 60 tested combinations:

- channels: 3, 4, 2
- latencies: `low`, 0.003, 0.005, 0.010, 0.020
- block sizes: 64, 128, 256, 512

The callback-mode stress tests changed the runtime choice:

- short callback sweeps passed 3- and 4-channel Komplete ASIO playback
- `0.003` requested latency with blocksize 64 measured about 8.5 ms actual
  latency in short tests, but failed a longer persistent-stream test
- `0.010` requested latency with blocksize 256 passed 20-second and 60-second
  persistent 3-channel callback tests with no status flags, measuring about
  16.5 ms actual latency
- `0.020`/512 and `0.050`/1024 also passed but add more latency

Recommended runtime route:

- use `Komplete Audio ASIO Driver`
- open a 3-channel stream
- route output 1/2 to headphones or headphone amp
- route output 3 to the tactile transducer input
- leave output 4 unused unless a driver requires a padded 4-channel stream
- use requested latency `0.010` and blocksize `256` for the persistent runner
  stream

## QC Limitation

WASAPI loopback captures Windows endpoints such as `Output 1/2`; it may not
capture an ASIO multichannel stream. For publication-grade route validation,
use physical electrical loopback from the actual outputs back into matched
inputs. For normal participant runs, the optional local audio evidence WAV is a
software safety copy of the runner's mixed output buffers, while event timing
comes from callback-derived `events.csv`/LSL marker records.
