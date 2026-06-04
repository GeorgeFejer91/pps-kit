# Peripersonal Space Toolkit

A Windows-ready toolkit for running and reproducing the Study 5 audio-tactile peripersonal-space experiment. The repository packages the experiment runner, stimulus-generation pipeline, decoding helpers, small deidentified sample data, and Kokoro-generated spoken instruction assets.

The default layout keeps source files public and keeps participant data local. Runtime recordings, demographics, generated stimuli, and model downloads are written to ignored folders.

## Quick Start On Windows

1. Open PowerShell in the repository root.
2. Run:

```powershell
.\windows\Setup_Windows_App.ps1
```

3. List audio devices:

```bat
windows\List_Audio_Devices.bat
```

4. Generate experiment stimuli after placing the required HRIR file under:

```text
assets\0. Head-Related Impulse Response (HRIR) model\FABIAN_HRIR_measured_HATO_0.sofa
```

Then run:

```powershell
.\.venv\Scripts\pps-generate.exe --participants 50
```

5. Launch the experiment app:

```bat
windows\Launch_PPS_App.bat
```

Open the stimulus designer for custom looming trajectories, SOFA-based azimuth planning, repetitions, SOA/spatial values, and catch-trial percentages:

```bat
windows\Launch_Stimulus_Designer.bat
```

The designer can preload bundled published-paradigm templates from `study_templates\`; see [docs/PARADIGM_LIBRARY.md](docs/PARADIGM_LIBRARY.md).

Optional: create a desktop shortcut for the launcher:

```powershell
.\windows\Create_Desktop_Shortcut.ps1
```

## Spoken Audio Assets

The bundled spoken instruction WAV files are generated with Kokoro ONNX and are exactly 4.000 seconds long at 44.1 kHz. To regenerate them:

```bat
windows\Regenerate_Spoken_Assets.bat
```

The Kokoro model files download into `models\kokoro\`, which is ignored by Git. Only the generated study WAV files and manifest are intended for publication.

## Public Commands

```powershell
pps-generate --dry-run
pps-generate --participants 50
pps-run --list-devices
pps-run
pps-design
pps-decode --input-dir local_data\loopback_recordings
pps-analyze --sample
```

## Repository Layout

```text
assets\breathing\        Kokoro-generated 4-second spoken WAVs
assets\click\            Click/tactile cue seed asset
assets\master_blocks\    Study block templates
configs\                 Example experiment and stimulus-design configs
data\sample\             Deidentified sample analysis CSVs
docs\\                    Hardware setup, replication, privacy, Windows, protocol, and paradigm notes
src\                     Python package and command entry points
study_templates\         Literature-backed preloadable paradigm templates
tests\                   Smoke and release-readiness tests
tools\                   Asset generation and release audit scripts
windows\                 Ready-to-use Windows setup and launch scripts
```

## Privacy And Release Boundaries

Do not commit participant recordings, demographics, raw exports, or generated local experiment output. The ignored folders `local_data\`, `artifacts\`, and `models\` are intended for local use only. See [docs/hardware_setup.md](docs/hardware_setup.md), [docs/replication_workflow.md](docs/replication_workflow.md), and [docs/privacy_boundary.md](docs/privacy_boundary.md). Run this before publishing a release:

```powershell
python tools\release_audit.py
pytest
```

## License

Source code is released under the MIT License. Deidentified sample data and documentation are released under CC BY 4.0 unless a file states otherwise. Third-party files that must be supplied by the user, such as HRIR/SOFA files or background music, are not redistributed here.
