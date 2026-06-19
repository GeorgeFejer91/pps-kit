# Segment Registry Contract

This file records the locked conceptual contract for the dashboard segment registry and project-file hierarchy. It is authoritative for Segments 0-3 unless the user explicitly asks to revise this `For-AI` contract. Future agents should treat implementation drift as technical debt to reconcile with this contract, not as permission to reinterpret the segment meanings.

Segments 4, 5, and 6 are now active downstream registry layers. Segment 4 is the CSV-only trial repetition pool, Segment 5 is the block CSV preview/generation layer, and visible Segment 6 is the Prepare Experiment layer that assigns accepted block CSV orders to participants and experiment parts, then hands off to the local PC runner. There is no visible Segment 7 unless the user explicitly asks to create one later.

## Core Principle

The HTML dashboard segments are not only visual UI sections. They correspond to a hierarchical registry under the hood. Each segment owns a specific decision layer, and each layer should have a matching folder/file creation responsibility inside the active project. Later segments must consume the registry and manifests from earlier segments instead of guessing from UI state or filename text alone.

The local packaged HTML dashboard and the hosted/GitHub Pages HTML dashboard must expose the same visible Segment numbering used by the writable registry folders. Segment 0 maps to `0_profile`, Segment 1 maps to `1_core_audio_ingredients`, Segment 2 maps to `2_trial_sequence_designs`, Segment 3 maps to `3_tactile_and_baseline_trials`, Segment 4 maps to `4_trial_repetition_pool`, Segment 5 maps to `5_block_csv_preview`, and Segment 6 maps to `6_experiment_run_setup`.

Each locked Segment 0-6 must have a short explicit action button where it creates artifacts and a clear registry state. Registry state belongs in backend manifests, compact status chips, previews, and Open Folder affordances; do not add generic registry feedback panels with `Status`/`Variants`/`WAVs`/`Folder`/`Message` summary rows to any visible segment. Segment 1's action is `Bake Ingredient`; Segment 2's action is `Bake Trial Sequences`; Segment 3's action is `Bake Baseline/Tactile Trials`; Segment 4's action is `Bake Trial Pool CSV`; Segment 5 uses bottom decision buttons `Regenerate Blocks` and `Accept Blocks`; Segment 6 uses `Regenerate Sequence` and `Save Design and Start Experiment Runner`. Segment 0's action applies the profile/custom project and creates or activates the project folder. Segment actions should not secretly bake downstream layers.

Visible segment surfaces should not create their own scroll controls. The browser page/workspace is the central scroll surface; segment panels, tables, and row builders should grow or wrap content instead of using nested vertical or horizontal scrollbars.

Visible segment headings should be human-readable prose labels rather than registry folder names. Put backend folder and manifest details in the segment `About` modal, which should exist for every visible Segment 0-6.

Filenames should still encode human-readable identity and timing at millisecond precision, but they should stay short. Put row numbers, row labels, full provenance, hashes, and long explanatory details in folders/manifests rather than repeating them in every WAV name. The manifest/registry is authoritative; timing in filenames is a safety and inspection layer.

## Segment 0: Study And Project Registry

### Function

Segment 0 defines which study/project context the researcher is working in.

### User Decisions

- Select an existing study profile/preload.
- Or choose `Custom design (define manually)`.
- Provide or confirm the project/design name.

### Folder And Registry Operations

- Every study profile should map to its own project folder.
- Choosing an existing profile should activate that profile folder.
- Choosing custom should create a new project folder with the project name and timestamp baked into the folder name, so custom work is unique and traceable.
- Shared reusable assets may live next to the study/project folders. The tactile cue library belongs in shared assets rather than being duplicated into every study profile.
- Segment 0 must write a `study_manifest.json` in `0_profile/`. This file records the active study/default GUI settings and a lookup-style `gui_settings_inventory`, including baseline strategy, whether baseline file generation is enabled, the baseline file mode, the main SOA list, effective baseline SOAs, and the distinction between Segment 3 baseline-file generation and Segment 4 block-scheduling percentages.
- The dashboard state should report Segment 0 folder/manifest status through `project_segments["0_profile"]`.

Concrete writable shape:

```text
local_data/dashboard_projects/
  0_study_project_registry/
    shared_assets/
      tactile/
        default_tactile_cue.wav
    profile_<template_id>/
      0_profile/
        project_manifest.json
        study_manifest.json
        active_design.json
      1_core_audio_ingredients/
      2_trial_sequence_designs/
      3_tactile_and_baseline_trials/
      4_trial_repetition_pool/
      5_block_csv_preview/
      6_experiment_run_setup/
    custom_<project_name_slug>_<YYYYMMDD_HHMMSS>/
      0_profile/
        project_manifest.json
        study_manifest.json
        active_design.json
      1_core_audio_ingredients/
      2_trial_sequence_designs/
      3_tactile_and_baseline_trials/
      4_trial_repetition_pool/
      5_block_csv_preview/
      6_experiment_run_setup/
```

The concrete root may be implemented under the app's local workspace, but the hierarchy and responsibilities above are the contract.

## Segment 1: Core Audio Ingredients

### Function

Segment 1 creates, imports, stores, and catalogs the reusable auditory ingredients used by later trial-design layers.

### User Decisions

- Generate looming noise.
- Import a custom looming tone to spatialize with the selected trajectory.
- Import or preserve a custom audio clip for later sequence use.
- Define trajectory controls for generated/spatialized looming sources.
- Inspect the Segment 1 starting stimulus pool in the full-width `Stimulus Type Selection` box, arranged as generated stimuli and local stimulus clips with source cards filling two slots per row from left to right on desktop.
- Keep local stimulus clip cards neutral. Segment 1 should not decide which clip is attached to which source; Segment 2 owns that relationship through row/box order and alternatives.

### Folder And File Operations

- Inside the active project folder, Segment 1 owns a folder whose name starts with `1_`.
- This folder stores core audio ingredient WAV files and their metadata.
- Generated stimuli are written here.
- Imported/preserved audio clips used as core ingredients are stored or referenced here through local backend-managed copies.
- Segment 1 outputs are reusable ingredients, not final trial designs.
- Segment 1 auditory outputs do not contain the tactile cue channel. Tactile is introduced in Segment 3.
- Published profiles such as Study 5 should materialize writable Segment 1 working copies from read-only preload/source catalogs when activated, while preserving provenance in the ingredient manifest.
- Segment 1 baking/import actions may invalidate downstream Segment 2 and Segment 3 outputs, but must not silently rebuild them.

Filename convention:

- Include semantic source labels.
- Include duration in milliseconds.
- Include trajectory/source descriptors when useful.

Example:

```text
1_core_audio_ingredients/
  pink_frontal_looming4000ms.wav
  blue_frontal_looming4000ms.wav
  inhale_instruction4000ms.wav
  exhale_instruction4000ms.wav
```

## Segment 2: Trial Sequence Designs

### Function

Segment 2 combines Segment 1 ingredients into named within-trial sequence designs. This is the layer where researchers define stimulus combinations such as appending an inhale instruction before a looming stimulus.

### User Decisions

- Create one or more trial-sequence rows.
- Name each row/trial family.
- Add ordered audio boxes left-to-right.
- Put one or more existing Segment 1 source labels inside each audio box.
- Use multiple labels inside a box as alternatives that multiply variants.
- Use the speaker icon on each selected audio label to play that exact Segment 1 ingredient through the local companion backend for online or offline soundchecks; the icon highlights while its preview is active and returns to idle when playback finishes.
- Add jitter boxes when a timed silent interval is part of the sequence.

### Folder And File Operations

- Segment 2 creates one or more folders, depending on how many rows the user defines.
- Each row/trial family gets its own folder.
- Each row folder contains the concrete sequence-variant WAVs produced by crossing audio-box alternatives and jitter values.
- In the Study 5-like case, one row such as `Inhale instruction | Looming Stimulus` crossed with four looming sources produces four derived sequence WAVs.
- A second row such as `Exhale instruction | Looming Stimulus` gets its own folder and its own derived variants.

Filename convention:

- Encode component labels and component durations.
- Encode jitter durations when present, for example `jitter500ms`.
- Encode the total sequence duration in milliseconds.
- Do not include row numbers or processing-stage prefixes in the WAV filename. Row identity belongs in the row folder and manifest.
- Keep the manifest authoritative for exact timing, segment order, source paths, hashes, and generated output paths.
- Segment 2 must validate that every referenced audio label resolves to a registered Segment 1 ingredient with matching path, hash, duration, and channel count before writing outputs.
- Segment 2 must be baked explicitly before Segment 3. Its manifest should carry a design signature so the state API can mark it stale if rows or source-label choices change.
- Segment 2 sequence WAVs are always stereo/binaural audio-only outputs for downstream trial creation. Mono ingredients are centered by duplicating them to channels 1 and 2, stereo ingredients preserve both channels, wider inputs are trimmed to the first auditory pair, and jitter/silence boxes are written as stereo silence. The sequence bake must not let a mono first box collapse later stereo looming assets into mono.

Example:

```text
2_trial_sequence_designs/
  row_01_inhale4000ms_plus_looming4000ms/
    inhale4000ms_pinklooming4000ms_total8000ms.wav
    inhale4000ms_jitter500ms_pinklooming4000ms_total8500ms.wav
    inhale4000ms_bluelooming4000ms_total8000ms.wav
  row_02_exhale4000ms_plus_looming4000ms/
    exhale4000ms_pinklooming4000ms_total8000ms.wav
    exhale4000ms_bluelooming4000ms_total8000ms.wav
```

## Segment 3: Tactile And Baseline Trial Creation

### Function

Segment 3 turns Segment 2 sequence designs into final trial WAV assets: 3-channel audio-tactile targets, 3-channel tactile-bearing baselines, and optional audio-only catch files. This is the first locked layer where tactile stimuli are inserted.

### User Decisions

- Choose SOA values.
- Choose the baseline strategy.
- Choose custom baseline timings when applicable.
- Decide, for custom baselines, whether baseline files preserve full audio or silence auditory channels.
- Decide whether to include catch-trial-ready audio-only files.
- Confirm or use the default tactile cue from shared assets.

### Tactile Cue Rule

- Segment 3 must grab the tactile WAV from the shared assets layer, for example `shared_assets/tactile/default_tactile_cue.wav` or the repo-provided `assets/tactile/default_tactile_cue.wav`.
- Segment 3 always writes 3-channel WAV files for tactile-bearing target and baseline trials.
- Researcher-facing channel convention:
  - Channel 1: left auditory/binaural channel.
  - Channel 2: right auditory/binaural channel.
  - Channel 3: tactile cue channel.
- The tactile cue must always be placed in channel 3 for tactile-bearing trial files.
- Baseline trials still contain the tactile cue in channel 3. If the baseline strategy calls for silent audio, channels 1 and 2 are silent while channel 3 carries the tactile cue.
- Catch trial files are the exception: they are stereo/binaural audio-only copies of Segment 2 sequence WAVs and do not carry a tactile cue.

### Folder And File Operations

- Segment 3 consumes Segment 2 row folders and manifests.
- Segment 3 preserves the Segment 2 row lineage by creating one top-level row folder per Segment 2 row/trial family.
- Inside each row folder, Segment 3 creates `target_audio_tactile/`, `baseline/` when the selected baseline strategy includes baselines, and `catch_trials/` when catch file generation is enabled.
- This means Study 5 should produce two main row folders (`row_01__inhale_trial_type/` and `row_02__exhale_trial_type/`), each containing target, baseline, and catch leaf folders.
- Segment 3 must be aware of exact Segment 2 component lengths, total sequence duration, first looming onset, jitter durations, and SOA values before inserting tactile cues.
- It must not infer timing from filenames alone. It should consume a registry/manifest from Segment 2, with filenames serving as human-readable checks.
- Segment 3 must fail clearly if the Segment 2 manifest is missing, stale, hash-mismatched, duration-mismatched, or lacks component timing metadata. It should not auto-bake Segment 2.
- Segment 3 manifests should record the consumed Segment 2 manifest hash and a Segment 3 timing/baseline design signature so downstream status can detect stale final WAVs.

Filename convention:

- Include the minimal source/sequence descriptor needed to identify the trial content.
- Include SOA in milliseconds, for example `soa300ms`.
- Include tactile cue duration in milliseconds when known, using compact `tac120ms`.
- Include total trial duration in milliseconds.
- Mark that tactile is in channel 3.
- Do not include row numbers in the WAV filename. Row/family identity belongs in the folder and manifest.

Example:

```text
3_tactile_and_baseline_trials/
  row_01_inhale4000ms_plus_looming4000ms/
    target_audio_tactile/
      inhale4000ms_pinklooming4000ms_soa300ms_tac120ms_total8000ms_ch3.wav
      inhale4000ms_pinklooming4000ms_soa800ms_tac120ms_total8000ms_ch3.wav
    baseline/
      baseline_silent_inhale4000ms_pinklooming4000ms_soa300ms_tac120ms_total8000ms_ch3.wav
      baseline_silent_inhale4000ms_pinklooming4000ms_soa800ms_tac120ms_total8000ms_ch3.wav
    catch_trials/
      catch_inhale4000ms_pinklooming4000ms_total8000ms_audio.wav
```

## Segment 4: Trial Repetition Pool

Segment 4 is the first CSV-only downstream layer. It consumes the Segment 3 manifest and writes `4_trial_repetition_pool/trial_repetition_pool.csv` plus `trial_repetition_pool_manifest.json`.

- Segment 4 must not duplicate WAV files.
- Segment 4 lets users set a global repetition count, per Segment 3 leaf-folder repetition counts, and optional per-WAV overrides.
- Segment 4 shows live feedback for total trial rows, audio-tactile/baseline/catch percentages, estimated playback duration, average trial duration, and longest folder contribution.
- Segment 4 records the consumed Segment 3 manifest hash and must become stale if Segment 3 is changed or re-baked.
- Each CSV row is one planned trial occurrence and must include the Segment 3 WAV path, source hash, duration, family, folder identity, SOA/baseline metadata, sequence key/labels, and repetition index.

## Segment 5: Block CSV Preview

Segment 5 consumes the Segment 4 trial-pool CSV and creates per-block CSV files. It does not duplicate WAV files and does not prepare participant-run audio; it is a block-level schedule preview and inspection layer.

- Segment 5 owns `5_block_csv_preview/`.
- Segment 5 writes one CSV per generated block, named like `block_01.csv`, plus `block_csv_preview_manifest.json`.
- Segment 5 records the consumed Segment 4 manifest hash and must become stale if Segment 4 changes or is re-baked.
- Segment 5 must preserve Segment 2/3 row order as hard sequence structure within every generated block. Rows are not freely randomizable categories. For Study 5 this means the block CSV order cycles `row_01` inhale, `row_02` exhale, then repeats inhale/exhale until the block is complete. The randomization algorithm may shuffle which concrete trial from each row appears at that row slot, but it must not destroy the row sequence.
- Segment 5 should distribute trial-pool rows deterministically across blocks while minimizing divergence across family, SOA, source lineage/noise type, and sequence identity within each preserved row family.
- The GUI should expose progress feedback while block CSVs are being written, one collapsible color-coded CSV preview per block, and exactly two bottom decision controls: `Regenerate Blocks` to rerun the randomization with a fresh seed and overwrite the current unaccepted Segment 5 CSVs, and `Accept Blocks` to finalize the current block decision.
- Accepting Segment 5 must rename `block_XX.csv` files to `block_XX_final.csv`, update `block_csv_preview_manifest.json`, lock Segment 5 against regeneration or upstream overwrites, and unlock Segment 6. After acceptance the accept control becomes `Edit Blocks`; pressing it restores `block_XX.csv` names, clears the accepted flag, and reopens Segment 5 for changes.
- Block CSV rows should include separate columns for recurring distribution features: family, row, SOA, noise type, sequence labels/key, duration, WAV filename/path, repetition metadata, and color metadata.
- SOA coloring should use one continuous gradient over the active SOA range. Family, row, and noise type should use categorical colors so distribution regularities are easy to scan across blocks. Source lineage may remain internal for balancing, but it should not be exported or previewed as its own Segment 5 column unless explicitly requested.

## Segment 6: Prepare Experiment

Segment 6 consumes the accepted Segment 5 block CSV manifest and creates the participant-by-part block-order plan. It does not edit block CSV contents, rebake stimuli, or run participant timing in browser JavaScript. Its final action may hand off to the local companion backend, which prepares/reuses a native session package and launches Focus Mode.

- Segment 6 owns `6_experiment_run_setup/`.
- Segment 6 has top-level researcher decisions for participant count and experiment structure (`1 part` single experiment or `2 parts` pre/post experiment). It prepares the participant/phase/block-order manifest and launches the native runner. Capture choices and participant-runtime decisions do not belong in Segment 6: native Focus Mode / `PPSExperimentRunner.exe` collects participant metadata, treats LSL/event logging as the standard protocol, and owns the optional fail-safe local recording and per-part missed-trial top-up controls. `events.csv`, local marker mirrors, trigger dictionary, and standard analysis outputs remain runner-owned session outputs.
- The GUI should show the resulting block-order permutations in a compact table before preparation. For a single experiment, each participant receives one ordered set of all accepted final block CSVs. For a pre/post experiment, each participant receives one ordered set for `pre` and another for `post`.
- `Regenerate Sequence` changes the deterministic permutation seed and refreshes the preview only while Segment 6 is not prepared.
- `Save as New Study Profile` is available only after Segment 6 is prepared. It creates a reusable local profile snapshot in the dashboard registry, using `custom_<slug>_<YYYYMMDD_HHMMSS>` plus `_2`, `_3`, etc. on collisions, preserving Segment 0-6 manifests/assets, recording `source_profile_id`, and excluding participant session/raw acquisition outputs.
- `Prepare Output Folder for Data Collection` is available only after Segment 6 is prepared. It uses the output folder remembered by `PPSExperimentRunner.exe`, creates `Experiment_context_folder_DO_NOT_DELETE/`, copies the active profile into `profile_snapshot/<profile_id>/`, writes `project_state/dashboard_runner_bridge_manifest.v1.json`, updates `focus_runner_settings.v1.json`, appends `project_state/output_diary.v1.jsonl`, and keeps human-readable runner diaries under `runner_logs/`. Legacy `study_profile_snapshot_DO_NOT_DELETE/`, `study_profile_snapshot/`, and root-level metadata markers must remain readable for existing runs.
- `Save Design and Start Experiment Runner` writes `experiment_block_order.csv` plus `experiment_run_setup_manifest.json`, records the consumed Segment 5 manifest hash, marks the setup prepared, prepares/refreshes the active output folder bridge, materializes the selected participant's native session package under the active output folder, and launches Focus Mode through the local companion backend with packaged `PPSExperimentRunner.exe --session-manifest ...`. The normal dashboard launch does not pass operator capture choices; Focus Mode collects those runtime choices before playback. `PPSExperimentRunner.exe` is the only active operator experiment runner; `focus_app.py` imports are internal to the exe and validation harnesses, and direct Python/module launch is retired.
- After preparation, the same final control should behave as `Open Experiment Runner`, launching the runner again without rewriting the prepared Segment 6 files.
- A valid prepared Segment 6 manifest should not be silently overwritten. Changing the participant count, the single/pre-post structure, the seed, or accepted Segment 5 blocks makes the prepared setup stale and requires a deliberate new preparation path.
- Segment 6 CSV rows should include participant id/index, experiment structure, phase/part, block position, source block metadata, final block CSV path, trial count, duration, and sequence seed.
- Participant-level block WAV synthesis belongs to the native session-preparation backend, not browser JavaScript. The backend treats Segment 6 as authoritative for playback order, filters it to the selected participant, resolves the referenced Segment 5 final block CSVs, writes one continuous WAV per ordered participant block under `Experiment_context_folder_DO_NOT_DELETE/prepared_blocks/<session_id>/blocks/`, stores package manifests/session metadata under context, and creates a sparse participant data folder under the active output/acquisition root as `<participant_id>_<timestamp>/` with `execution_mode = participant_block_wavs`.
- The optional `Generate All Participant Sessions` action belongs in the native runner UI for labs that want every participant package prebuilt. Do not add this as a Segment 6 dashboard button.
- The native runner UI should make the Segment 6 source and selected participant package inspectable: show the active run setup, participant preparation state, resolved block order, participant metadata fields, runner-owned capture controls, and an `Open Session Folder` control. It should expose visible run controls and top-up approval rather than relying only on keyboard shortcuts.
- During Segment-prepared playback, the runner must use the participant block CSV sample-position/timing columns as the source of planned trial markers. The audio callback's `audio_sample_zero` event anchors planned trial starts, looming onsets, tactile onsets, response windows, and trial ends. The participant folder should receive the rolling `<session_id>_trials.csv`, per-block `block_XX_audio_evidence.wav`, and any external LabRecorder `block_XX.xdf` files. Verbose local mirrors (`events.csv`, internal `events.xdf`, `lsl_markers.csv`, `lsl_markers.xdf`, trigger dictionary, session metadata, timing QC, and exploratory/model analysis files) are context or `Data_Analytics` outputs rather than participant-folder clutter. The optional local audio evidence WAV records the runner's mixed output buffers; physical loopback remains an internal validation reference, not a normal participant-run dependency. The LSL marker outlet is continuous session infrastructure: it must be created once before the first instruction/block and remain online through the end of the participant session; LabRecorder may start/stop per block without restarting the LSL streams.

## Required Registry Data

At minimum, the hierarchical registry/manifests for Segments 0-5 should record:

- active project/study id and project folder
- custom project creation timestamp when applicable
- segment folder paths
- source labels and source paths
- component durations in milliseconds
- jitter values in milliseconds
- sequence row ids, row labels, and visual row order
- generated sequence variant keys
- first looming segment onset for each sequence variant
- SOA values and baseline strategy
- tactile cue source path and tactile cue duration
- output WAV path, channel count, channel role map, total duration, and hash
- Segment 4 repetition settings, source Segment 3 manifest hash, CSV row count, family counts/percentages, and playback-duration estimates
- Segment 5 source Segment 4 manifest hash, block count, per-block CSV paths, per-block family/row/SOA/noise/source counts, total duration, and color metadata for preview columns
- Segment 6 source Segment 5 manifest hash, participant count, single/pre-post structure, permutation seed, per-participant/per-part block order, prepared CSV path, and prepared manifest status

Do not replace this registry with filename parsing. Filenames are a redundant, human-readable inspection aid.
