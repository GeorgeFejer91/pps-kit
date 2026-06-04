# Replication Guide

## 1. Prepare Inputs

The repository includes the small reusable seed assets, spoken instruction WAVs, click cue, master blocks, and deidentified sample analysis files.

The following files are not redistributed and must be supplied locally if you regenerate the full stimulus set:

- `assets\0. Head-Related Impulse Response (HRIR) model\FABIAN_HRIR_measured_HATO_0.sofa`
- optional pregenerated looming files in `assets\1. Looming Stimuli\`
- optional licensed background music

## 2. Generate Stimuli

Check paths without writing files:

```powershell
.\.venv\Scripts\pps-generate.exe --dry-run
```

Generate from the HRIR file:

```powershell
.\.venv\Scripts\pps-generate.exe --participants 50
```

Or use pregenerated looming WAVs:

```powershell
.\.venv\Scripts\pps-generate.exe --use-pregenerated-looming --participants 50
```

Generated stimuli are written under `artifacts\stimuli\` and are intentionally ignored by Git.

## 3. Design Custom Stimuli

To draft variants before generating or piloting them:

```bat
windows\Launch_Stimulus_Designer.bat
```

The designer has separate `Stimulus Design` and `Trial Design` tabs. It lets you select a SOFA HRIR file, define noise types with azimuth/elevation orientations, preload custom looming and prestimulus audio files, tune looming trajectory radius, path direction, path length, and propagation speed, and specify the experiment schedule: repetitions, SOA values, spatial values, respiratory phases, block composition, participant count, and catch-trial percentage. Block contents stay fixed across participants, while participant block order is randomized or counterbalanced from the saved seed. Use `Save Settings` for local repeated runs, and keep published JSON design files with your protocol materials when running a non-default variant.

## 4. Run The Experiment

```bat
windows\Launch_PPS_App.bat
```

Use `--stimuli-dir`, `--instructions-dir`, `--recordings-dir`, or `--background-music` to override paths for a specific lab setup.

## 5. Decode Recordings

```powershell
.\.venv\Scripts\pps-decode.exe --input-dir local_data\loopback_recordings --output-dir artifacts\decoded
```

Decoded outputs are written under `artifacts\decoded\`.

## 6. Analyze Sample Data

```powershell
.\.venv\Scripts\pps-analyze.exe --sample
```

This writes a compact facilitation summary to `artifacts\analysis\sample_facilitation_summary.csv`.
