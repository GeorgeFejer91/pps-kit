# Stimulus Designer

The standard researcher-facing design surface is the local HTML dashboard:

```bat
apps\designer\launchers\Launch_HTML_Dashboard.bat
```

or:

```powershell
pps-dashboard
```

The Qt stimulus designer remains available for comparison and fallback. It is a
Windows UI for drafting custom looming-stimulus configurations while preserving
the Study 5 defaults as a reproducible baseline.

Launch the Qt designer with:

```bat
apps\designer\launchers\Launch_Stimulus_Designer.bat
```

Or from an installed environment:

```powershell
pps-design
```

The dashboard is served from `127.0.0.1` and is a local browser UI only. It
keeps the same Python design, rendering, session-preparation, audio-stress, and
native Focus Mode backends; it does not move validated participant timing into
browser JavaScript. Segment 6 prepares the participant session package and then
launches the packaged `PPSExperimentRunner.exe`.

The HTML dashboard is organized as a one-page workflow with a fixed floating
left navigation rail. The rail is navigation and companion-status only; panel
sizing happens directly in the workspace through draggable snapping splitters
and panel-edge handles, so researchers can resize the working panels without
using abstract slider controls.

The one-page workflow uses sequential decision segments: study/profile
selection, looming-stimulus building, trial sequence design, baseline/tactile
trial generation, trial-pool repetition, block CSV review, and Segment 6
experiment preparation. Segment 6 includes **Preload Instruction Audio Clips**
for run-level messages before the experiment, around block/condition
transitions, and after the experiment; within-trial instruction snippets remain
owned by Segment 2.

The dashboard can also be served as a GitHub Pages site. In that mode, start
`apps\designer\launchers\Start_Website_Companion.bat` on the research PC and use the left-rail
companion controls to connect the hosted page to the local backend. See
[GitHub Pages Dashboard](GITHUB_PAGES_DASHBOARD.md).

The browser interface is only an orchestrator. It does not upload local
stimulus files or experiment outputs online. Audio selected in the dashboard is
imported by the local companion backend and stored in ignored local data before
being used by the render/session pipeline.

Segment 6 instruction-audio imports are local-only as well. They are decoded to
WAV where possible, stored under the active project's
`6_experiment_run_setup\instruction_library\`, saved with continuation settings
in the run setup manifest, and copied into each prepared participant session.

Preload profiles use a local file-cabinet catalog under `assets\preloads\<template_id>\`.
The folder names mirror the HTML dashboard stages: `01_profile`,
`02_looming_stimuli`, `03_baseline_strategy`, `04_trial_designer`, and
`05_run_setup`. The looming segment stores prebaked auditory-only WAVs plus
source/tone/trajectory metadata; tactile cues are still introduced during
session preparation from the saved trial/SOA schedule.

## Design Controls

The designer has three workflow tabs:

- `Stimulus Design`: noise definitions, custom looming WAV preloads, custom prestimulus WAV preloads, and an embedded 2D/3D sound-path preview.
- `Trial Assembler`: an OpenSesame-inspired trial-building view with condition controls, trial families, block composition, generated trial preview, and participant block-order preview.
- `Experiment Runner`: an integrated Prepare/Run/Review workflow for the current design. It checks rendered looming WAVs, participant/session readiness, the fixed multichannel audio route, writes a run package under `local_data\sessions\`, and opens the full-screen Qt Focus Mode.

All three tabs use nested Qt split panels. Drag the splitter handles to resize panes, use `Reset Layout` to return the active tab to the balanced default, and use `Maximize Preview` / `Restore` on `Stimulus Design` when the trajectory viewer needs most of the workspace. Splitter positions are stored locally with Qt settings; they are not written into design JSON files.

The Qt UI uses a modern Fusion-styled control skin instead of native Windows chrome. Inputs, tables, tabs, buttons, scrollbars, and splitter handles are styled consistently, while trajectory start/end, timing, preview, trial conditions, trial families, block assembly, schedule previews, runner readiness, and runner review panes each have distinct tinted panels. The colors are functional signposts, not saved experiment parameters.

The designer uses the packaged PPS Toolkit icon for the window/taskbar entry.
The native participant runner now uses a light PySide Focus Mode shell with the
same visual identity. `For-AI\engineering\build\windows\Build_Experiment_Runner_Exe.ps1` packages it as
`dist\PPSExperimentRunner\PPSExperimentRunner.exe`; launchers activate that exe
only. `focus_app.py` imports remain internal to that exe and validation
harnesses; direct Python/module launch is retired.

The designer currently covers:

- procedural noise definitions for white, pink, blue, violet, and brown noise
- per-noise azimuth, elevation, and gain
- imported custom audio files, stored locally as named sources with target duration and explicit handling: dry tone to be spatialized along the trajectory, or already looming/control audio to preserve as-is
- custom prestimulus files, such as 4-second breathing or instruction chunks, stored as named preload paths with target duration
- `Starting Point` and `End Point` panels where each endpoint is defined by distance from the listener in cm and full 0-360 degree rotation around the listener
- under-the-hood start/end X/Y/Z sound-source coordinates relative to the listener, derived from those endpoint controls and stored for trajectory generation/export
- default horizontal trajectory placement on the listener head/ear plane; height controls are hidden in `2D bird's-eye` mode and only become editable after switching to `3D orbit`
- linear trajectory geometry with derived path length/speed, movement duration, Start hold, and End hold
- protocol schedule controls for repetitions per condition, SOA values, spatial values, catch-trial percentage, respiratory phases, blocks, participants, and random seed
- an HTML-dashboard baseline strategy segment for baseline tactic, baseline timing anchors, baseline proportion, live trial-count feedback, and duration estimates
- compact OpenSesame-style trial assembly controls that define condition factors, trial families, and which stimulus types are allowed in each block: audio-tactile, baseline, and catch
- live trial-table and participant block-order previews before protocol CSV export
- runner controls that prepare a participant run package from the current design, open the native Focus Mode app shell, collect participant/runtime metadata there, stress-test the preferred audio route, write standard event/LSL mirror/XDF/analysis outputs, and optionally save a fail-safe local recording WAV
- Segment 6 **Preload Instruction Audio Clips** controls for before-experiment, before-block, after-block, between-condition, and after-experiment messages with click, timed-delay, or runner-button continuation
- seeded trial randomization with balanced shuffle, no-immediate-repeat, or ordered strategies
- participant-level block order assignment using fixed order, seeded random permutation, or counterbalanced rotation
- auditory motion directions, tactile body sites, baseline-specific SOAs, and exact catch-trial counts for paradigms that report fixed trial counts
- preloadable published-study profiles with verification status, citation metadata, and saved reference parameters
- paper-level preload annotation in the profile bar, showing which published paper the selected profile is based on
- `Citation` actions for the selected profile: show the source citation, save BibTeX, or save CSL JSON for citation managers
- paired SOA/spatial values for distance-at-tactile designs, or full-factorial SOA x spatial designs for broader PPS variants
- compact segmented `2D` / `3D` controls in both the Stimulus Design panel and the Trajectory Preview panel
- one embedded trajectory preview with `2D bird's-eye` and `3D orbit` modes; 2D is the default, hides height, locks the camera to a top-down view, and lets researchers drag the green start marker and red end marker to update the matching distance and rotation controls
- live stimulus-preview synchronization: editing trajectory fields updates the preview immediately, and 2D marker drags update the Stimulus Design fields immediately; Apply/Continue/Render still perform the backend save
- resizable workspaces for stimulus controls, trajectory preview, protocol assembly, participant order previews, and runner readiness/review panes
- repeatable settings save/load
- JSON design save/load and Save As
- trajectory CSV export
- protocol CSV export
- `Render Looming WAVs`, which writes a 3DTI-compatible render config, trajectory/QC CSV, manifest, and generated WAVs. If the native 3DTI executable is available it is used; otherwise the bundled Python SOFA/FABIAN reference renderer produces the WAVs from the same saved trajectory/SOA config.

## Binaural Rendering

Binaural spatialization is achieved by convolving sound sources with head-related transfer functions (HRTFs) stored in the Spatially Oriented Format for Acoustics (SOFA), an AES-standardized container for spatial acoustic measurements (AES69-2022). The toolkit uses the FABIAN/TU Berlin HRIR dataset as its rendering reference, converting source trajectories—defined by azimuth, distance, looming duration, and timing parameters—into two-channel WAV files in which channels 1 and 2 carry the left and right auditory streams. All rendering decisions are captured in manifests recording trajectory samples, file hashes, and quality-control summaries to support post-hoc auditability.

The native rendering engine derives from the 3D Tune-In Toolkit (3DTI), an open-source C++ library for real-time binaural spatialisation (Cuevas-Rodriguez et al., 2019, PLOS ONE, DOI: 10.1371/journal.pone.0211899). The 3DTI authors have since migrated the core algorithms to the Binaural Rendering Toolbox (BRT Library), which the toolkit adopts as its primary forward-facing renderer while preserving 3DTI-compatible configurations and pinned source snapshots to maintain reproducibility for data collected under the earlier rendering path.

### References

- Gonzalez-Toledo, D., Molina-Tanco, L., Cuevas-Rodriguez, M., Majdak, P., & Reyes-Lecuona, A. (2023). The Binaural Rendering Toolbox. A Virtual Laboratory for Reproducible Research in Psychoacoustics. *Proceedings of the 10th Convention of the European Acoustics Association*. https://dael.euracoustics.org/confs/landing_pages/fa2023/001042.html
- Cuevas-Rodriguez, M., Picinali, L., Gonzalez-Toledo, D., Garre, C., de la Rubia-Cuestas, E., Molina-Tanco, L., & Reyes-Lecuona, A. (2019). 3D Tune-In Toolkit: An open-source library for real-time binaural spatialisation. *PLOS ONE*, 14(3), e0211899. https://doi.org/10.1371/journal.pone.0211899
- Audio Engineering Society. (2022). *AES69-2022: AES standard for file exchange — Spatial acoustic data file format* (SOFA).

## Output Files

The default saved design path is:

```text
configs\stimulus_design.generated.json
```

Use `Save Settings` to write the current UI state to this path, or to the currently loaded/saved design file. Use `Load Settings` to restore that same file without opening a file picker. The default generated settings file is ignored by Git, so a lab can reuse it locally while keeping published template/example JSON files stable.

Generated trajectory CSVs should be exported to `artifacts\`, which is ignored by Git.

`pps-render-design` and the GUI render action write reproducibility artifacts to the selected output folder:

- `render_config.3dti.json`
- `render_trajectory_samples.csv`
- `render_tactile_events.csv`
- `render_manifest.json`
- `render_qc.csv`
- `looming_<noise-label>.wav`

The render config preserves the GUI-level controls and adds the renderer handoff: one stationary listener, one generated noise source, the linear trajectory with Start/Movement/End phases, SOA-derived tactile cue events, and a multichannel output layout of binaural left, binaural right, and vibrotactile cue. The generated WAVs use channels 0 and 1 for binaural audio and channel 2 for the vibrotactile cue. `render_tactile_events.csv` records each SOA, tactile onset sample, tactile channel, and source X/Y/Z/radius at tactile onset. The old two-channel Study 5 layout remains documented only as a legacy replication mode because full binaural rendering needs both ear channels.

The native renderer uses 3DTI `HighQuality` anechoic spatialization. The app passes an explicit stationary listener model into `render_config.3dti.json`: head diameter, head radius, sound speed, customized ITD, propagation delay, 3DTI direct-path distance attenuation, near-field ILD/shadow processing, and disabled reverb. The Pfeiffer preload uses the reference simulator's `head_diam = 0.18 m`, so 3DTI receives a matching `0.09 m` listener head radius for customized ITD.

Audio levels are relative digital rendering levels, not calibrated SPL. Per-noise `gain` is a linear amplitude multiplier. 3DTI then applies its distance and near-field gains; the generated binaural channels are peak-normalized to `0.90` (`-0.92 dBFS`) and the final multichannel file is limited to `0.99` if needed. Pfeiffer's MATLAB reference contains `ref_dB = 100`, `att_factor = 40`, and directional left/right dB loss equations, but it also peak-normalizes the final output, so those dB values are preserved as provenance rather than treated as absolute output SPL.

When the native 3DTI wrapper is not present, the renderer uses the bundled Python SOFA/FABIAN reference path. This reference path is intended to keep the GUI and saved designs operational while the native 3DTI executable is still being packaged; manifests mark these outputs as `rendered_reference` with `render_engine: python-sofa-reference`.

The Experiment Runner tab uses `artifacts\qt_runner_render\` as its default rendered-stimulus handoff folder. Press `Render` there to write/update the current looming WAVs, then `Prepare` to create:

- `local_data\sessions\<participant_id>_<timestamp>\design.json`
- `local_data\sessions\<participant_id>_<timestamp>\protocol_schedule.csv`
- `local_data\sessions\<participant_id>_<timestamp>\session_manifest.json`
- per-block manifest CSVs and runnable concatenated WAVs under `blocks\`
- `events.csv`, `events.xdf`, `lsl_markers.csv`, `lsl_markers.xdf`, `trigger_dictionary.json`, `analysis_summary.txt`, `timing_qc.csv`, and analysis CSVs after Focus Mode runs

Reaction-time analysis now treats direct event timing as primary. Focus Mode logs mouse clicks immediately through the local event logger, the internal `PPSMarkersV2`/`PPSTriggerCodes` marker mirror, and optional external LSL streams. Planned tactile onsets are anchored to `audio_sample_zero`, which is emitted by the audio callback when the first block sample reaches the output buffer. A low-gain response marker pulse is also written to the tactile output channel for physical loopback QC; this marker is intended to be visible in validation recordings but below vibration threshold, and is not the primary RT source.

The optional fail-safe local recording is a digital output evidence WAV written from the already-mixed output buffers, after routing, gain, clipping limits, and tactile-channel mouse-click marker injection. It is not a physical latency measurement. Physical electrical loopback is retained as an internal validation reference for publication-quality timing checks, while WASAPI loopback remains diagnostic only for ASIO routes that may bypass Windows endpoint recording.

The local HTML dashboard is now the primary researcher workflow for pilot runs
of the currently designed experiment, and its final runner action starts native
PySide Focus Mode through the packaged `PPSExperimentRunner.exe`. Segment 6
prepares the participant/block-order manifest and then hands off runtime
decisions to Focus Mode. `events.csv`, local
`PPSMarkersV2`/`PPSTriggerCodes` mirrors, trigger dictionaries, and analysis
CSVs are standard runner outputs; live LSL is always attempted. Focus Mode
collects participant metadata, writes `session_metadata.json`, and lets the
operator choose the optional fail-safe local recording plus optional
missed-trial top-up at the end of each experiment part. When missed-trial
top-up is enabled, Focus Mode keeps a live tactile miss ledger, prepares one
shortened top-up block at the relevant part boundary, asks the operator for
approval before playing it, and marks any row-structure filler trials as QC-only
so they are excluded from primary rescue analysis.

The HTML dashboard covers the same researcher-facing decision layer: published
profile selection, custom manual designs, stimulus controls, noise/custom-audio
tables, trial previews, participant readiness, render, prepare, stress audio,
native Focus Mode launch, and session review. It preserves the existing saved
design/session contracts. When `Custom design (define manually)` is loaded, the
dashboard enforces the setup order: Study Profile, Stimulus Design, Trial
Assembly, Run Preparation, and Review. Future sections and run actions stay
locked until the minimum runnable custom profile is present: custom design name,
valid trajectory/noise information, SOA/spatial trial values, participant/block
counts, and participant ID.

For the bundled Pfeiffer-style preload, run `python For-AI\research\literature\tools\verify_pfeiffer_profile.py`.
The verifier checks the saved trajectory/noise/SOA parameters, renders the
profile, writes `pfeiffer_verification_report.json`, and checks that the
left-to-right trajectory is left-ear dominant in the first half and right-ear
dominant in the second half.

Bundled literature templates live in:

```text
study_templates\
```

The profile library now contains a stress-test set of published audio-tactile
PPS paradigms. The most tightly verified trajectory profile is `Pfeiffer EJN2018
lateral trajectory profile`, which preloads the reference simulator's pink-noise
lateral path at the ear/head center plane: source X from -40 cm to +40 cm, 5 cm
in front of the listener, 20 cm/s movement speed, and 44.1 kHz sample rate. Many
other profiles are intentionally marked `partial` because the current GUI can
represent their audio-tactile timing scaffold but not yet their full social,
locomotor, VR, speaker-array, or proprietary-sound manipulations. The FABIAN
neutral HRIR remains the standardized under-the-hood renderer resource for
everyone.

The profile selector displays paper-like labels, for example author/year plus the article title where the template citation can be parsed. In the HTML dashboard, choosing a published preload or `Custom design (define manually)` from the selector loads that profile immediately without a separate load button. Published profiles show a DOI URL plus a separate caveat that the dashboard recreates reported study parameters locally rather than using the exact original stimulus set from the paper. Use the `Citation` button in the Qt comparison UI to inspect or export the selected profile citation. Exported BibTeX and CSL JSON are generated from each template's stored `citation`, `doi`, `source_url`, verification status, and template id.

## Visual QA

Run the screenshot verification loop after UI changes:

```powershell
python For-AI\engineering\validation\scripts\ui_screenshot_check.py --iterations 2
```

The script opens the designer, captures `Stimulus Design`, `Trial Assembler`, and `Experiment Runner`, writes screenshots to `artifacts\ui_verification\`, and records a JSON report with tab, image, and widget-geometry checks. Use the screenshots for visual inspection before publishing a Windows build.

The screenshot check also captures the default stimulus layout and the maximized trajectory preview layout, and verifies that `Reset Layout`, `Maximize Preview`, `Restore`, the paper preload annotation, and `Citation` controls remain available.

## Relationship To Study 5 Replication

`pps-generate` remains the locked Study 5 replication path. The designer adds a configurable layer for future variants and pilot work. Designs are explicit JSON artifacts so changes to study profile, start/end distance, full 0-360 degree rotation, intentional 3D height offsets, derived X/Y/Z endpoints, path length, speed, SOAs, or tactile timing can be reviewed before they are used in a generated stimulus set. The fixed FABIAN/TU SOFA HRIR path is kept in the design data and render manifest for generation/export workflows, but it is not an experimenter-facing control.

The protocol CSV export materializes the requested trial family before audio generation: audio-tactile rows, optional tactile-only baselines, and catch trials computed from the target catch percentage.

Block contents are generated once from the saved design seed. The same block definitions and within-block trial orders are reused for every participant; participant schedules differ by block order according to the selected block-order randomization strategy. This supports the common cognitive-neuroscience pattern of fixed reproducible blocks with participant-level order counterbalancing.

Study profiles marked `partial` identify a published paradigm and preload its core structure, but should not be treated as exact replications until the original paper/protocol has been checked for every field.
