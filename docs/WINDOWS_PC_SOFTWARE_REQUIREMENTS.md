# Windows PC Software Requirements

This document is the install checklist for a lab PC that will run the
Peripersonal Space Toolkit experiment runner, LSL logging, and the internal
latency/reliability validation protocols. It separates package dependencies
from vendor drivers and external recording tools.

Generated installers and downloaded third-party binaries must stay in ignored
local folders such as `local_data/software_installers/` and
`local_data/software_tools/`. Do not commit vendor installers, LabRecorder
binaries, participant data, XDF recordings, or local hardware notes.

## Supported Python Environment

- Python: 64-bit Python `>=3.10,<3.14`
- Current validated lab PC: Python `3.12.10`
- Recommended full lab install from the repository root:

```powershell
python -m pip install -e ".[gui,web,lsl,validation]"
```

For the smallest participant-running install without validation tools:

```powershell
python -m pip install -e ".[gui,web,lsl]"
```

Optional source-conversion and TTS extras remain separate:

```powershell
python -m pip install -e ".[mp3,tts]"
```

The `mp3` extra only installs Python-side MP3 helpers. If MP3 import/export is
needed, install `ffmpeg` separately and document the installed build.

The Windows source setup script installs the PPS Python/runtime package as one
environment, then runs the PC software audit:

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\Setup_Windows_App.ps1
```

If the audit cannot see the native Komplete Audio ASIO route, setup opens the
official Native Instruments driver page in the default browser and leaves the
audit report under `artifacts/validation_runs/setup_pc_software_requirements/`.

## Python Packages

| Package | Requirement | Needed for |
| --- | --- | --- |
| `numpy` | `>=2.0` | stimulus arrays, timing analysis, validation scripts |
| `scipy` | `>=1.12` | signal processing and pulse/onset detection |
| `soundfile` | `>=0.13.1` | WAV read/write |
| `sounddevice` | `>=0.4.7` | PortAudio playback/recording and ASIO callback timing |
| `sofar` | `>=1.1` | SOFA/HRIR handling |
| `netCDF4` | `>=1.6` | SOFA/NetCDF backend |
| `pyaudiowpatch` | `>=0.2.12`, Windows only | optional WASAPI loopback diagnostics |
| `pynput` | `>=1.7.7` | mouse/keyboard response capture |
| `PySide6` | `>=6.7,<7` | Qt designer and native Focus Mode |
| `fastapi` | `>=0.110,<1` | local HTML dashboard backend |
| `uvicorn` | `>=0.27,<1` | local dashboard server |
| `pylsl` | `>=1.16` | LSL marker output and probe scripts |
| `pyxdf` | `>=1.17` | offline XDF/LabRecorder import for validation |
| `pytest`, `build`, `Pillow`, `httpx` | see `pyproject.toml` | development and validation tests |

## Required Windows Driver

Install the official Native Instruments Komplete Audio 6 MK2 Windows driver
from the NI driver page or Native Access:

- Official source: <https://www.native-instruments.com/en/support/downloads/drivers-other-files/>
- Required ASIO component: `Komplete Audio ASIO Driver`
- Current lab PC audit: ASIO registry entry present and visible to
  `sounddevice` as a 6-input / 6-output ASIO device.

The PPS release downloader and setup scripts may open the official provider page
for this driver. They must not mirror, bundle, or silently redistribute the NI
driver installer unless written redistribution permission is recorded in the
release manifest. The expected operator workflow is:

1. Let the downloader/setup open the NI driver page, or open the page above.
2. Download `Komplete Audio 6 MK2 Driver 5.22.0 - Windows 10` or the current
   NI-listed successor.
3. Disconnect the interface, run `setup.exe` from the downloaded ZIP, reconnect
   the interface, restart `PPSExperimentRunner.exe`, and re-run the PC audit.

For publication-grade timing, use the native NI ASIO endpoint. Do not substitute
ASIO4ALL, FlexASIO, Voicemeeter, MME, DirectSound, or separate WASAPI stereo
endpoints for the experiment player. Those can be diagnostic tools, but they do
not prove one synchronized left/right/tactile multichannel output route.

FlexASIO is an optional open-source diagnostic fallback published by Etienne
Dechamps at <https://github.com/dechamps/FlexASIO/releases>. The PPS download
manifest may cache the pinned FlexASIO installer from its GitHub release with
SHA-256 verification, but the runner still marks it as an unvalidated fallback
until route identity, latency, and interchannel skew are revalidated.

## External LSL/XDF Recording Tool

Install or extract LabRecorder for external LSL recording:

- Official source: <https://github.com/labstreaminglayer/App-LabRecorder/releases>
- Current downloaded release on this PC: `v1.17.1`, Windows asset
  `LabRecorder-1.17.0-Win_amd64.zip`
- Local ignored cache:
  `local_data/software_installers/labrecorder/LabRecorder-1.17.0-Win_amd64.zip`
- Local ignored extracted tool:
  `local_data/software_tools/labrecorder/LabRecorder-1.17.0-Win_amd64/LabRecorder.exe`
- SHA-256 recorded in:
  `local_data/software_installers/labrecorder/downloaded_asset_sha256.json`

The toolkit uses `pylsl` to emit streams. LabRecorder is the external recorder
used to capture those streams into XDF files for independent validation or EEG
session recording.

Current validation PC check: `run_labrecorder_lsl_xdf_stress.py` records
`PPSMarkersV2` and `PPSTriggerCodes` with `LabRecorderCLI.exe`, loads the XDF
with `pyxdf`, and reconciles the captured samples against local marker logs.

## Report-Build Tooling

The internal validation report is LaTeX:

- Required command: `pdflatex`
- Current lab PC: MiKTeX `pdflatex.exe` found in the user MiKTeX install.
- Official source: <https://miktex.org/download>

The LaTeX tooling is not needed for participant playback, but it is required to
rebuild `artifacts/validation_runs/report_build/latency_reliability_validations.pdf`.

## Woojer And Tactile Tooling

The validated experiment route uses the Woojer through wired analog audio from
Komplete output 3. No Woojer USB/Bluetooth driver is required for the electrical
latency validation. Bluetooth must not be used for timing-sensitive tactile
validation.

Woojer firmware/app tooling can be maintained from the vendor support page:

- <https://www.woojer.com/pages/support>

Electrical channel-3 timing is not mechanical vibration onset. Mechanical
Woojer onset requires an external vibration sensor, accelerometer, or contact
microphone and the corresponding sensor driver/software.

## Verification Commands

Run the machine-readable PC audit:

```powershell
python .\validation_protocols\scripts\audit_pc_software_requirements.py
```

Expected key results on a ready lab PC:

- `missing_runtime_packages = []`
- `missing_validation_packages = []` for the validation workstation
- `missing_external_tools = []` if LabRecorder is on `PATH` or extracted under
  `local_data/software_tools/labrecorder/`
- `komplete_asio_registry_present = true`
- `komplete_asio_sounddevice_ready = true`

Check audio route readiness:

```powershell
python -m peripersonal_space_toolkit.audio_device_stress --device-query Komplete --channels 3 --latencies 0.010 --blocksizes 256
```

Check safe route identity before any publication latency baseline:

```powershell
python .\validation_protocols\scripts\run_dummy_output_route_sweep.py --device 31 --device-query Komplete --amplitude 0.05
python .\validation_protocols\scripts\analyze_dummy_signal_levels.py --run-dir artifacts\validation_runs\dummy_output_route_sweep_YYYYMMDD_HHMMSS
```

Proceed to `pps-latency-validate calibrate --establish-baseline` only when all
three outputs pass the same route-identity and signal-quality criteria at safe
amplitude.

Check external LSL/XDF recording:

```powershell
python .\validation_protocols\scripts\run_labrecorder_lsl_xdf_stress.py --output-dir artifacts\validation_runs\labrecorder_lsl_xdf_current
```

Expected ready-PC result: all expected rich and numeric PPS LSL markers are
present in the XDF with no missing IDs, duplicates, field mismatches, or trigger
code count mismatches.
