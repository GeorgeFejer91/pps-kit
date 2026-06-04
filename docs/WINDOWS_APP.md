# Windows App Guide

This toolkit is designed to run as a local Windows experiment app from a cloned or downloaded repository.

## Setup

Run once:

```powershell
.\windows\Setup_Windows_App.ps1
```

The script creates `.venv`, installs the toolkit in editable mode, installs test and TTS extras, and creates local runtime folders.

## Launch

```bat
windows\Launch_PPS_App.bat
```

Create a desktop shortcut:

```powershell
.\windows\Create_Desktop_Shortcut.ps1
```

Open the stimulus design layer:

```bat
windows\Launch_Stimulus_Designer.bat
```

Useful launch variants:

```bat
windows\Launch_PPS_App.bat --stimuli-dir artifacts\stimuli\10.Participant_Sequences
windows\Launch_PPS_App.bat --background-music C:\path\to\licensed_music.wav
windows\Launch_PPS_App.bat --recordings-dir D:\PPS_Recordings
```

## Audio Device Check

```bat
windows\List_Audio_Devices.bat
```

The runner uses stereo routing:

- left channel: tactile/vibration output
- right channel: auditory stimulus output

The app also supports WASAPI loopback recording on Windows when `pyaudiowpatch` is available.

## Local Data

The app writes runtime settings, demographics, and loopback recordings under `local_data\` by default. That folder is ignored by Git and should not be published.
