# Stimulus Designer

The stimulus designer is a Windows UI for drafting custom looming-stimulus configurations while preserving the Study 5 defaults as a reproducible baseline.

Launch it with:

```bat
windows\Launch_Stimulus_Designer.bat
```

Or from an installed environment:

```powershell
pps-design
```

## Design Controls

The designer is split into two main tabs:

- `Stimulus Design`: SOFA/HRIR source, noise definitions, azimuth/elevation orientations, custom looming WAV preloads, custom prestimulus WAV preloads, and looming trajectory preview.
- `Trial Design`: repetitions, SOA values, spatial values, auditory motion labels, tactile sites, baseline/catch-trial settings, respiratory phases, block composition, randomization strategy, participants, and seed.

The designer currently covers:

- SOFA HRIR file selection and validation through the `sofar` package
- noise definitions for pink, blue, white, and brown noise
- per-noise azimuth, elevation, and gain
- snapping noise orientations to the nearest available SOFA source position
- custom looming stimulus files, stored as named preload paths with target duration
- custom prestimulus files, such as 4-second breathing or instruction chunks, stored as named preload paths with target duration
- looming trajectory radius, path direction, path length, propagation speed, start/end azimuth, elevation, and lead/tail padding
- protocol schedule controls for repetitions per condition, SOA values, spatial values, catch-trial percentage, respiratory phases, blocks, participants, and random seed
- block design controls that define which stimulus types are allowed in each block: audio-tactile, baseline, and catch
- seeded trial randomization with balanced shuffle, no-immediate-repeat, or ordered strategies
- participant-level block order assignment using fixed order, seeded random permutation, or counterbalanced rotation
- auditory motion directions, tactile body sites, baseline-specific SOAs, and exact catch-trial counts for paradigms that report fixed trial counts
- preloadable published-study templates with verification status and citation metadata
- paired SOA/spatial values for distance-at-tactile designs, or full-factorial SOA x spatial designs for broader PPS variants
- a top-down trajectory preview
- repeatable settings save/load
- JSON design save/load and Save As
- trajectory CSV export
- protocol CSV export

## Output Files

The default saved design path is:

```text
configs\stimulus_design.generated.json
```

Use `Save Settings` to write the current UI state to this path, or to the currently loaded/saved design file. Use `Load Settings` to restore that same file without opening a file picker. The default generated settings file is ignored by Git, so a lab can reuse it locally while keeping published template/example JSON files stable.

Generated trajectory CSVs should be exported to `artifacts\`, which is ignored by Git.

Bundled literature templates live in:

```text
study_templates\
```

## Visual QA

Run the screenshot verification loop after UI changes:

```powershell
python tools\ui_screenshot_check.py --iterations 2
```

The script opens the designer, captures `Stimulus Design` and `Trial Design`, writes screenshots to `artifacts\ui_verification\`, and records a JSON report with tab, image, and widget-geometry checks. Use the screenshots for visual inspection before publishing a Windows build.

## Relationship To Study 5 Replication

`pps-generate` remains the locked Study 5 replication path. The designer adds a configurable layer for future variants and pilot work. Designs are explicit JSON artifacts so changes to azimuth, radius, direction, path length, or speed can be reviewed before they are used in a generated stimulus set.

The protocol CSV export materializes the requested trial family before audio generation: audio-tactile rows, optional tactile-only baselines, and catch trials computed from the target catch percentage.

Block contents are generated once from the saved design seed. The same block definitions and within-block trial orders are reused for every participant; participant schedules differ by block order according to the selected block-order randomization strategy. This supports the common cognitive-neuroscience pattern of fixed reproducible blocks with participant-level order counterbalancing.

Templates marked `partial` identify a published paradigm and preload its core structure, but should not be treated as exact replications until the original paper/protocol has been checked for every field.
