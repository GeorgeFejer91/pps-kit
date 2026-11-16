# Replication Workflow

This workflow describes the public, reusable path for reproducing the Study 5 audio-tactile PPS task or adapting it with the stimulus designer.

## Published study profiles

Select a published profile in the Planner and check its
[recreation status](PUBLISHED_STUDY_RECREATION_STATUS.md). Its citation, study
identifier, and known settings are in the profile metadata. The parameter
manifest lists the settings and apparatus that still need verification before
a participant run.

The catalogue covers 91 of 94 DOI records with 192 source-linked profiles.
It represents 193 reviewed primary assessment rows and one conference abstract
series. Repeated sessions with the same assessment may share a profile. Where
a publication reports a separate companion task or computational model, its
profile records the relevant conditions and output. Twenty-four profiles
across 17 publications pass the software launch checks.

- Ferri’s behavioral preview schedules 180 paired trials and 120 audio-only
  catches. The setup requires its two calibrated sound sources and electrical
  delivery.
- Serino’s hand-posture preview schedules 288 paired trials, 96 touch-only
  baselines, and 48 sound-only catches. Its virtual trajectory and block
  partition are software choices. The published physical placement and
  delivered timing need verification.
- Teneggi’s bargaining-game preview schedules 104 trials before the game and
  104 after. The software uses a virtual moving sound and placeholder response
  and touch channels. The lab setup requires the game, cheek stimulation,
  physical sound, and vocal response capture.
- Paredes’ two-point prediction can be rerun with the
  [pinned author notebooks](https://github.com/renatoparedes/SCZ_PPS_Model/tree/e881e2d74717d24fa24a5b30ed2f794b5d96b1db).
  The profile records the reproduced computational output and links the inputs.

Three sources have no original PPS task in this catalogue. They are the
[Serino commentary](https://doi.org/10.1016/j.tics.2016.01.005), the
[Dijkerman and Medendorp conceptual chapter](https://doi.org/10.1093/oso/9780198851738.003.0005),
and the [Flockton ASMR survey](https://doi.org/10.1101/2025.09.02.673729).
The survey reports subjective ASMR and affect ratings without a PPS measure.

## 1. Install

Run the Windows setup script from the repository root:

```powershell
.\For-AI\engineering\build\windows\Setup_Windows_App.ps1
```

The script creates a local virtual environment and installs the package in editable mode.

## 2. Review Or Edit The Design

Open the local HTML dashboard:

```bat
apps\designer\launchers\Launch_HTML_Dashboard.bat
```

or:

```powershell
pps-dashboard
```

The Qt stimulus designer remains available for comparison and fallback:

```bat
apps\designer\launchers\Launch_Stimulus_Designer.bat
```

Use the dashboard Segments for study profiles, noise types, custom looming files, prestimulus files, trajectory geometry, SOAs, repetitions, catch/baseline trials, block CSV preview, and experiment preparation. The fixed FABIAN/TU SOFA HRIR path is handled under the hood.

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

For designed experiments, use Segment 6 in the HTML dashboard:

1. Accept the Segment 5 block CSVs.
2. Set planned participants and experiment parts.
3. Press `Save Design and Start Experiment Runner`.
4. The local backend prepares the participant session package and starts native Focus Mode.
5. In Focus Mode, enter participant metadata and choose runner-owned options: optional fail-safe local recording, optional wired-loopback capture, optional full-session LabRecorder XDF capture, and optional missed-trial top-up at the end of each experiment part. Press `Submit setup` before starting the run; this prepares the session/controller metadata and creates the session-lifetime LSL outlets before playback is enabled. The LSL/event protocol, local marker mirror, trigger dictionary, `events.csv`, and analysis outputs are standard runner outputs.

The integrated runner writes session outputs under `local_data\sessions\<participant_id>_<timestamp>\`.

For designed experiments, use `events.csv` / `events.xdf`, the internal `PPSMarkersV2`/`PPSTriggerCodes` marker mirror, and optional runner-owned LabRecorder `<session_id>_external_labrecorder.xdf` as reconstruction records. The native LabRecorder XDF is written directly into the participant session folder beside `<session_id>_trials.csv`. The runner keeps the LSL outlets alive for the participant session after setup submission. When requested, it waits for the session LSL streams, refreshes LabRecorder's stream list, selects all visible network LSL streams by default, and starts LabRecorder through RCS before playback. Closing the Focus Mode runner also closes the owned LabRecorder child; normal session teardown still waits for the final marker settle interval before stopping it. The optional local audio evidence WAV is a data-heavy safety copy of the runner's mixed output buffers, including tactile-channel response marker clicks. Physical electrical loopback WAVs are validation-only traces used to quantify how well those software records match the physical outputs.

The legacy Tk runner is no longer a public launch path. Use Focus Mode through
the dashboard handoff or `apps\runner\launchers\Launch_Experiment_Runner.bat`.

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
python For-AI\engineering\release\tools\release_audit.py
pytest
```

The audit checks required public files, seed assets, study templates, release boundaries, and private path leaks.
