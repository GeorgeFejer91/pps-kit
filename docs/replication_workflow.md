# Replication Workflow

This workflow describes the public, reusable path for reproducing the Study 5 audio-tactile PPS task or adapting it with the stimulus designer.

## 1. Install

Run the Windows setup script from the repository root:

```powershell
.\windows\Setup_Windows_App.ps1
```

The script creates a local virtual environment and installs the package in editable mode.

## 2. Review Or Edit The Design

Open the stimulus designer:

```bat
windows\Launch_Stimulus_Designer.bat
```

Use the Stimulus Design tab for noise types, azimuth/elevation, SOFA/HRIR source, custom looming files, prestimulus files, and trajectory geometry. Use the Trial Design tab for SOAs, spatial values, repetitions, catch trials, baseline trials, block structure, participant schedules, and randomization.

## 3. Generate Stimuli

Run a dry-run first:

```powershell
pps-generate --dry-run
```

Then generate participant sequences when required inputs are available:

```powershell
pps-generate --participants 50
```

Generated WAVs and participant sequences are written under `artifacts/`, which is ignored by Git.

## 4. Run The Experiment

List audio devices:

```powershell
pps-run --list-devices
```

Start the runner:

```powershell
pps-run
```

Local recordings, demographics, settings, and session outputs belong under `local_data/`, which is ignored by Git.

## 5. Decode Loopback Recordings

```powershell
pps-decode --input-dir local_data\loopback_recordings --output-dir artifacts\decoded
```

The decoder writes diagnostics and final CSV outputs under `artifacts/`.

## 6. Analyze The Deidentified Sample

```powershell
pps-analyze --sample
```

The sample command writes summary tables under `artifacts/analysis`.

## 7. Audit Before Publication

```powershell
python tools\release_audit.py
pytest
```

The audit checks required public files, seed assets, study templates, release boundaries, and private path leaks.
