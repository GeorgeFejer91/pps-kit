# Segment Registry Contract

This file records the locked conceptual contract for the dashboard segment registry and project-file hierarchy. It is authoritative for the full Segment 0-6 chain unless the user explicitly asks to revise this `For-AI` contract. Future agents should treat implementation drift as technical debt to reconcile with this contract, not as permission to reinterpret the segment meanings.

Segments 4, 5, and 6 are active downstream registry layers. Segment 4 is the CSV-only trial repetition pool, Segment 5 is the block CSV preview/generation layer, and visible Segment 6 is the Profile Validation and Save layer. Segment 6 validates and locks a reusable profile; actual participant IDs/count, acquisition folders, capture settings, session materialization, and runtime timing belong to the Experiment Runner. There is no visible Segment 7 unless the user explicitly asks to create one later.

## Core Principle

The HTML dashboard segments are not only visual UI sections. They correspond to a hierarchical registry under the hood. Each segment owns a specific decision layer, and each layer should have a matching folder/file creation responsibility inside the active project. Later segments must consume the registry and manifests from earlier segments instead of guessing from UI state or filename text alone.

The local packaged HTML dashboard and the hosted/GitHub Pages HTML dashboard must expose the same visible Segment numbering used by the writable registry folders. Segment 0 maps to `0_profile`, Segment 1 maps to `1_core_audio_ingredients`, Segment 2 maps to `2_trial_sequence_designs`, Segment 3 maps to `3_tactile_and_baseline_trials`, Segment 4 maps to `4_trial_repetition_pool`, Segment 5 maps to `5_block_csv_preview`, and Segment 6 maps to `6_experiment_run_setup`.

The implementation must preserve this same modularity in all three representations:

- Backend ownership is split into one `designer_segments/segment_N.py` definition per visible UI segment, with the ordered graph and lineage checks in `designer_segments/registry.py`.
- Frontend workflow identity is mirrored in `dashboard/segment_registry.js`; UI components call named product operations through `dashboard/designer_api.js` rather than embedding transport details throughout the interface.
- AI-facing project memory describes the same Segment 0-6 names, folders, manifests, and upstream chain. `For-AI/` must not introduce a competing workflow model.

Every Segment 1-6 output consumes the previous segment manifest as its immediate input. New manifests carry `pps-segment-lineage.v1` with the current segment key, upstream segment key, upstream manifest path, and upstream SHA-256. A changed or missing upstream manifest makes the dependent segment stale. Legacy manifests without this additive field remain readable during migration. Profile copy/rebase operations must refresh both legacy dependency hashes and lineage hashes in order from Segment 1 through Segment 6.

Rebuilds of Segments 2-5 are rollback-protected. A failed validation, cooperative cancellation, or filesystem error restores the last complete segment folder, and successful publication replaces it. Committed changes still invalidate downstream segments explicitly; rollback must never leave a partial folder looking ready.

Segments 1-6 have short explicit action buttons where they create artifacts and a clear registry state. Registry state belongs in backend manifests, compact status chips, previews, and stage-appropriate Open Folder affordances; do not add generic registry feedback panels with `Status`/`Variants`/`WAVs`/`Folder`/`Message` summary rows to any visible segment. Researcher-facing action labels distinguish creation from rebuilding: Segment 1 uses contextual `Create Stimulus`/`Create Clip` and `Remake Stimulus`/`Update Clip` actions; Segment 2 uses `Create Trial Sequences`/`Rebuild Trial Sequences`; Segment 3 uses `Create Trial Files`/`Rebuild Trial Files`; Segment 4 uses `Create Trial Pool`/`Rebuild Trial Pool`; Segment 5 uses `Generate Blocks`/`Regenerate Blocks` plus `Accept Blocks & Continue`; Segment 6 owns validation/finalization. Segment 0 is deliberately simpler: profile selection activates an existing context automatically, while `Start New Custom Design` requires a name and creates the clean-slate project context without a separate Apply button. Artifact creation is the primary action until a stage is ready; `Save & Continue` becomes primary after validation and is the only action that confirms the current decision segment and advances sequential editing. Segment actions should not secretly bake downstream layers or advance the edit cursor.

Visible segment surfaces should not create their own scroll controls. The browser page/workspace is the central scroll surface; segment panels, tables, and row builders should grow or wrap content instead of using nested vertical or horizontal scrollbars.

Visible segment headings should be human-readable prose labels rather than registry folder names. Put backend folder and manifest details in the segment `About` modal, which should exist for every visible Segment 0-6.

Filenames should still encode human-readable identity and timing at millisecond precision, but they should stay short. Put row numbers, row labels, full provenance, hashes, and long explanatory details in folders/manifests rather than repeating them in every WAV name. The manifest/registry is authoritative; timing in filenames is a safety and inspection layer.

## Segment 0: Study And Project Registry

### Function

Segment 0 defines which study/project context the researcher is working in.

### User Decisions

- Select an immutable built-in template or an existing custom design from one grouped profile selector.
- Or use `Start New Custom Design` and provide a required name before the clean-slate draft is created.

### Folder And Registry Operations

- Every study profile should map to its own project folder.
- Choosing an existing profile should activate that profile folder.
- Starting a new custom design should create a dedicated project folder with the project name and timestamp baked into the folder name, so custom work is unique and traceable. The folder location is fixed by the researcher workspace and is not a Segment 0 user decision.
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

- Start a `New Ingredient`, then choose `Generate Looming Noise`, `Custom Looming Tone`, or `Custom Audio Clip` at the top of one merged workspace.
- Give every new ingredient a required name. Generated sources additionally choose scientific noise colour, burst-train or smooth mode, trajectory, and loudness settings. Custom looming tones choose a retained local source file, arbitrary display colour, trajectory, and loudness settings. Fixed custom clips choose a retained local source file, arbitrary display colour, name, and duration and remain unspatialized.
- Inspect or select existing ingredients from two compact groups: `Looming / spatialized stimuli` and `Fixed audio clips`. Selection loads the saved name, type, colour, timing, source settings, and source-owned trajectory snapshot without mutating the design.
- In Edit mode, remake the selected spatialized ingredient or update the selected fixed clip. A source cannot change category during remake; create a new ingredient and remove the old one instead. A generated source may change its scientific noise colour during remake.
- Use the advanced Segment 1 Loudness Contract as a shared policy rather than presenting calibration as a separate per-source property.
- Keep local stimulus clip cards neutral. Segment 1 should not decide which clip is attached to which source; Segment 2 owns that relationship through row/box order and alternatives.

### Workspace And Selection Contract

- The visual order is source-type selection; contextual settings beside the trajectory viewer; contextual create/remake action; grouped ingredient inventory; then the existing Segment 1 folder and `Save & Continue` footer. The settings/viewer columns stack on narrow screens.
- Inventory cards are selectable in View and Edit modes and show name, source/noise type, display swatch, duration, compact trajectory metadata where applicable, folder access, Edit-only removal, and a speaker play/stop control for the exact ingredient.
- All spatialized source trajectories remain visible in 2D and 3D. The active path is thicker and fully opaque; other paths are muted. Paths are independently clickable and select the corresponding inventory card. Overlapping paths use deterministic offsets and contrast outlines so their hit targets remain distinct for arbitrary light or dark imported-audio colours.
- Path selection must remain distinct from endpoint dragging, 2D panning, and 3D camera movement. View mode permits inventory/path selection, audio preview, and camera controls but locks all mutations.
- Selecting a fixed clip reports `Preserved audio clip — no trajectory` while retaining the muted spatialized inventory in the viewer.
- Editing happens in an isolated unsaved ingredient draft. Typing and card/path selection never update saved trajectory data. Switching source category, starting another ingredient, leaving Edit mode, or continuing to Segment 2 prompts before discarding an uncommitted draft.
- Create/remake is the only ingredient commit boundary. A remake renders/imports and validates through a temporary output before replacing the matching design and manifest row, propagating a rename to Segment 2 source labels, and invalidating Segments 2-6. Failure preserves the original ingredient and downstream artifacts.
- Every spatialized source owns its `trajectory_snapshot`; the design-level trajectory remains only the default for the next new spatialized ingredient. Imported looming tones retain a backend-managed dry source for future remakes. Legacy looming imports without that source may still be renamed/recoloured, but trajectory or acoustic changes require re-upload.
- Imported `AudioFileSpec` and manifest provenance may carry optional `display_color_hex` and `source_input_path`. Hex colours are normalized to uppercase `#RRGGBB`; legacy records derive their initial colour from `tone_type`. Generated noise colours remain tied to scientific noise type. Manual-audio colour editing uses a focus-trapped overlay with a visual picker, validated hex field, live swatch, and Apply/Cancel.

### Folder And File Operations

- Inside the active project folder, Segment 1 owns a folder whose name starts with `1_`.
- This folder stores core audio ingredient WAV files and their metadata.
- Generated stimuli are written here.
- Imported/preserved audio clips used as core ingredients are stored or referenced here through local backend-managed copies.
- Segment 1 outputs are reusable ingredients, not final trial designs.
- Segment 1 auditory outputs do not contain the tactile cue channel. Tactile is introduced in Segment 3.
- Published profiles such as Study 5 should materialize writable Segment 1 working copies from read-only preload/source catalogs when activated, while preserving provenance in the ingredient manifest.
- Segment 1 create/update/remake actions invalidate downstream Segments 2-6 when their committed ingredient or label changes, but must not silently rebuild them.

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
- Baseline trials still contain the tactile cue in channel 3. If the baseline strategy calls for absent looming/stimulus audio, only the looming/stimulus component is removed from channels 1 and 2; fixed instruction components such as inhale/exhale cues remain audible. Fully silent auditory channels are reserved for designs that deliberately have no non-looming audio components to preserve.
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
- Legacy tactile-only/no-looming baselines use `baseline_no_looming_...`;
  stationary-burst baselines, including the current Study 5 default, use
  `baseline_stationary_burst_...`.

Example:

```text
3_tactile_and_baseline_trials/
  row_01_inhale4000ms_plus_looming4000ms/
    target_audio_tactile/
      inhale4000ms_pinklooming4000ms_soa300ms_tac120ms_total8000ms_ch3.wav
      inhale4000ms_pinklooming4000ms_soa800ms_tac120ms_total8000ms_ch3.wav
    baseline/
      baseline_stationary_burst_inhale4000ms_pinklooming4000ms_soa300ms_tac120ms_total8000ms_ch3.wav
      baseline_stationary_burst_inhale4000ms_pinklooming4000ms_soa800ms_tac120ms_total8000ms_ch3.wav
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
- Segment 5 should distribute trial-pool rows deterministically across blocks while minimizing divergence across family, SOA, source lineage/noise type, and sequence identity within each preserved row family. Within each row-family queue it should use seeded Gellermann-style ordering: no immediate exact-condition repeats when avoidable and no more than two consecutive rows sharing a tracked feature when alternatives exist.
- The GUI should expose the active randomization strategy and seed, progress feedback while block CSVs are being written, one collapsible color-coded CSV preview per block, and exactly two bottom decision controls: `Generate Blocks` before the first build / `Regenerate Blocks` afterward to rerun with a fresh seed and overwrite current unaccepted Segment 5 CSVs, plus `Accept Blocks & Continue` to finalize the current block decision and advance sequential review.
- A `Download Randomization` affordance may appear outside the bottom decision-control footer. In hosted/static mode, every ready preloaded profile must derive an already randomized Segment 5 preview in the browser and allow downloading that generated CSV/manifest; it must still not write local files or launch the runner without the companion backend.
- Accepting Segment 5 must atomically rename `block_XX.csv` files to `block_XX_final.csv`, update `block_csv_preview_manifest.json`, confirm the Segment 5 decision, and advance the persisted cursor to Segment 6. Retrying after an interrupted response is idempotent. When an accepted Segment 5 is explicitly reopened, `Generate Blocks` asks before restoring editable CSV names and replacing the accepted set; unchanged accepted blocks can be reconfirmed without destructive regeneration.
- Block CSV rows should include separate columns for recurring distribution features: family, row, SOA, noise type, sequence labels/key, duration, WAV filename/path, repetition metadata, and color metadata.
- SOA coloring should use one continuous gradient over the active SOA range. Family, row, and noise type should use categorical colors so distribution regularities are easy to scan across blocks. Source lineage may remain internal for balancing, but it should not be exported or previewed as its own Segment 5 column unless explicitly requested.

## Segment 6: Profile Validation and Save

Segment 6 consumes the accepted Segment 5 block definitions and completes a reusable experiment profile. It does not choose an acquisition folder, require a study participant count, materialize participant audio, configure capture hardware, or launch a participant session.

- Segment 6 continues to use `6_experiment_run_setup/` and the legacy run-setup schema as a backward-compatible stored representation. New UI and APIs should describe this as the profile-completion/order-policy layer rather than as an already prepared acquisition session.
- Segment 6 presents a validation checklist for Segments 0-5, profile-level experiment structure (`1 part` or `2 parts`), optional instruction policy, and a compact deterministic block-order preview.
- The count beside the order preview is only the number of examples to display. It is stored in the legacy `participants` field for compatibility and mirrored to `participant_order_policy.preview_count`; it is never interpreted as the required eventual study size.
- The profile stores ordered block IDs, part membership, seed, and algorithm version. New profiles use `seeded_factoradic_cycle.v1`; legacy fixed, rotation, and seeded-random strategies remain readable.
- Before finalization, `Refresh Order Preview` may update the deterministic example table. The table labels rows as examples rather than participants.
- `Done — Lock Profile` is the sole primary pre-final action. It is enabled only after artifact validation and sequential confirmation of Segments 0-5. The request must carry the current workflow revision and is rejected when any reopened segment still needs review. Finalization status/timestamps are server-owned, the profile is registered in My Profiles on desktop, and both design settings and generated artifacts become read-only. Further scientific edits require copy-on-edit into a newly named custom profile with downstream decisions reopened.
- After finalization, portable `.pps-profile` export becomes available. Bundles carry profile identity, parent template/profile provenance, design/order policy, assets and trajectory snapshots, renderer provenance, and SHA-256 inventory under `pps-profile-bundle.v1`.
- Only finalized profiles may appear in the Runner catalogue. The Runner chooses actual participant IDs/count, output/acquisition folder, capture settings, and session timing, then calls the shared materializer for the selected participant index. It records the finalized profile identity/hash and produces an immutable session package.
- Old `experiment_block_order.csv`, `experiment_run_setup_manifest.json`, output-folder bridge, and dashboard-to-Focus-Mode launch paths remain readable for existing studies. They must not appear as normal Designer controls and must not redefine the new profile/Runner boundary.
- Participant-level block WAV synthesis, bulk participant generation, participant metadata, missed-trial top-up, LSL/LabRecorder behavior, trigger dictionaries, marker mirrors, session QC, and analysis outputs remain Runner responsibilities.

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
- Segment 6 source Segment 5 manifest hash, part structure, instruction policy, order-policy algorithm/version/seed, example preview count, finalized profile identity/hash, and legacy run-setup provenance when present

Do not replace this registry with filename parsing. Filenames are a redundant, human-readable inspection aid.
