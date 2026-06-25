---
name: html-dashboard-orchestrator
description: Use when Codex changes an HTML/browser dashboard that controls local software through a companion backend, especially the PPS Toolkit dashboard. Applies to UI controls, static assets, local companion APIs, dashboard/backend schemas, GitHub Pages-hosted orchestrator pages, launcher behavior, privacy boundaries, Playwright/browser validation, and project-memory updates.
---

# HTML Dashboard Orchestrator

Use this workflow to change a browser-based GUI that is an orchestrator for local programs. The browser may be local or hosted on GitHub Pages, but the trusted work stays in the local backend.

## Core Rule

Keep the browser UI as a decision surface only. Do not move validated timing, stimulus rendering, file storage, participant data, audio stress, session preparation, or native Focus Mode execution into browser JavaScript.

Treat the packaged local dashboard and the online/static GitHub Pages dashboard as one synchronized interface. Every HTML/CSS/JS dashboard change must update and verify both surfaces in the same change set; do not leave the online page behind the local UI or the local UI behind the online page.

In this repo:

- Dashboard assets live in `src/peripersonal_space_toolkit/dashboard/`.
- The embedded trajectory viewer lives in `src/peripersonal_space_toolkit/viewer/`.
- The companion backend lives in `src/peripersonal_space_toolkit/dashboard_app.py`.
- Experiment schemas and render behavior live in `src/peripersonal_space_toolkit/design.py` and `src/peripersonal_space_toolkit/render_backend.py`.
- Preload asset readiness lives in `assets/preloads/preload_inventory.json`; the browser may display status, but the local companion verifies, downloads, or bakes profile assets.
- Preload profile file cabinets live under `assets/preloads/<template_id>/` and should mirror the dashboard decision segments (`01_profile`, `02_looming_stimuli`, `03_baseline_strategy`, `04_trial_designer`, `05_run_setup`). Rebuild them with `tools/build_preload_catalog.py` when preload sources, trajectories, or metadata change.
- Public/hosted static behavior must still use relative assets and connect to `127.0.0.1` for backend actions.

## Workflow

1. Classify the change.
   - UI-only: layout, labels, controls, visual state, panel sizing, viewer interaction.
   - Orchestration: UI calls existing backend action.
   - Contract: UI needs new saved fields, API payloads, render config, session manifest, or tests.
   - Boundary-sensitive: file imports, online-hosted page behavior, participant/session data, timing, audio device, render/start actions.

2. Trace the contract before editing.
   - Find existing IDs, event listeners, API endpoints, dataclasses, render config rows, and tests with `rg`.
   - Reuse local patterns before adding abstractions.
   - Preserve unrelated dirty worktree changes. Stage selectively when needed.

3. Keep the UI lab-oriented.
   - Build dense, quiet researcher controls rather than marketing/AI-dashboard surfaces.
   - Prefer explicit control groups, segmented buttons, tables, status chips, splitters, and direct manipulation.
   - Do not add visible instructional prose when the control itself can be clear.
   - Keep one-page navigation and direct panel resizing behavior intact.
   - Use one centralized workflow scroll surface. Do not add segment-local vertical or horizontal scroll controls; panels, tables, and Segment 2 filmstrip rows should expand or wrap with content, and stored panel resize heights should act as minimum heights rather than clipping content.
   - Treat one-page website sections as workflow segments. Each segment should represent one natural user decision stage, and panels should stay localized to the segment where that decision is made.
   - Do not let unrelated controls share a segment just because they fit on screen. Move participant/session/run controls, previews, backend feedback, or review panes to the functional segment that owns them.
   - For the PPS dashboard, preserve the visible numbered Segment hierarchy: Segment 0 Choose or Create Study, Segment 1 Build Looming Stimuli, Segment 2 Trial Sequence Design, Segment 3 Baseline and Tactile Trial Design, Segment 4 Trial Repetition Pool, Segment 5 Generate and Review Blocks, and Segment 6 Prepare Experiment. Segment headings must be short prose labels, not backend folder slugs; every visible segment should have an `About` modal that explains purpose, user inputs, backend folder/manifest work, and next-step handoff. When the user tasks work on a specific Segment, do not edit earlier completed Segments, move controls into them, or alter their visible ownership without explicit user permission. Segment 1 is a three-box workspace: `Trajectory And Source` plus `Trajectory Preview` in the top row with a splitter-controlled width ratio, and full-width `Stimulus Type Selection` underneath with a two-column starting stimulus pool. Do not add a separate `Backend Feedback` card or visible `Status`/`Ingredients`/`Variants`/`WAVs`/`Folder`/`Message` summary-row block to any segment. Segment 2 owns only within-trial sequence composition. Keep it visually minimal: custom designs start completely empty except for a single plus control. Clicking plus creates the first trial-family row with one empty audio box; later plus controls add ordered boxes or independent rows. Audio boxes hold existing clip/source labels as a vertical one-by-one list, where one label is fixed and multiple labels are alternatives that multiply that row's variants. A box can be toggled into a jitter box with one millisecond value per line. Left-to-right boxes concatenate and multiply by Cartesian product; rows add independent trial families and preserve visual row order for scheduling/interleaving. Do not show visible `Single-Trial Sequence Assembly`, `Custom Clips`, or `Trial Sequence Rows` subheadings in that builder. Do not put repetitions, block count, SOA count math, per-source counters, baseline counters, catch counters, or total-trial summaries in Trial Sequence Design. Segment 3 owns SOA values, baseline strategy checkboxes, custom baseline timing/mode, planned-file oversight, and the batch bake for row-preserving audio-tactile/baseline/catch trial WAV folders. Segment 4 owns CSV-only trial-pool repetition counts in 0.5 increments, top-level trial/family count feedback, read-only audio-tactile/baseline/catch percentage sliders with nested Inhale/Exhale sub-sliders, and a compact right-panel duration calculus showing `duration_ms x reps`; it must not duplicate WAVs, define blocks, or render a visible CSV pool preview table. `.5` repetitions are expanded by the backend as deterministic balanced extra rows across row/phase, SOA, and source lineage. Segment 5 owns block CSV generation and preview: it consumes the Segment 4 trial-pool CSV, writes individual CSVs under `5_block_csv_preview/`, renders each generated block as its own collapsible, color-coded CSV preview with the first block open by default, and exposes only two bottom decision controls: `Regenerate Blocks` and `Accept Blocks`/`Edit Blocks`. Accepting renames current `block_XX.csv` candidates to `block_XX_final.csv`, updates the manifest, locks Segment 5 against regeneration or upstream overwrites, and unlocks Segment 6; editing restores working names and clears acceptance. Recurring distribution features should have separate columns, including family, row, SOA, noise type, sequence, duration, and WAV identity; SOA uses one continuous gradient while family, row, and noise use distinct categorical colors. Source lineage remains internal for balancing and should not be shown/exported as its own Segment 5 column unless explicitly requested. Segment 6 is the final visible dashboard segment: it owns final experiment-level parameters, planned participant count, 1-part versus 2-part experiment structure, the block-order permutation preview, and the final `Save Design and Start Experiment Runner` button. That button writes the Segment 6 CSV/manifest and then asks the local companion backend to launch the PC runner program with the prepared Segment 6 manifest; do not reintroduce Segment 7 as an empty review page. Participant-level session WAV synthesis and optional `Generate All Participant Sessions` bulk generation belong in the native runner UI, not in Segment 6.
   - In Stimulus Type Selection, use the researcher-facing categories `Generate Looming Noise`, `Custom Looming Tone`, and `Custom Audio Clip`. Generated looming noise and custom looming tones are staged for backend baking; custom audio clips are preserved local source clips for later trial use rather than spatialized looming stimuli.
   - Segment 1 local clip cards are neutral inventory records. Do not add visible attach-to-source, attach-to-every-source, placement, phase-selection, or gap controls there; clip/source combinations are defined later in Segment 2 by row/box order and alternatives.
   - In Trial Designer, use `Custom Clips` for fixed audio row elements. Do not call this area `Instruction Snippets`, and do not expose a separate instruction-snippet import button. Study 5 should preload inhale/exhale custom clips so row assembly can use them immediately.
   - Preserve the active Study 5 preload shape: two frontal looming noise sources (`Pink frontal`, `White frontal`) in the generated/prebaked source inventory plus two gray non-looming custom clips using the decoded original Study 5 inhale/exhale WAVs by default. Those two fixed clips should appear in the Segment 1 local stimulus pool and remain usable in Trial Sequence Design. Do not store Study 5 looming WAVs as custom audio clips in the active design, and do not restore a separate second Study 5 profile.
   - Keep the profile DOI box DOI-only. For published-study preloads, place any replication caveat in a separate notice below the DOI: these profiles recreate reported study parameters within the local toolkit and are not the authors' exact original stimulus set.
   - For durable preload/catalog data, mirror this segmentation in local folders. Profile-level metadata belongs in `01_profile`; prebaked source WAVs, source recipes, tone types, and trajectory snapshots belong in `02_looming_stimuli`; baseline/catch defaults belong in `03_baseline_strategy`; trial rows/SOAs/snippets belong in `04_trial_designer`; participant/randomization defaults belong in `05_run_setup`.
   - When published-profile metadata declares representable motion-direction factors, expand them into concrete preload source assets and trajectory snapshots. Do not let a paper with left-to-right/right-to-left, looming/receding, front/back, rear-left/rear-right, or spherical 3D boundary paths display as one representative baked trajectory unless the missing direction is explicitly unsupported and documented. If direction is already encoded by the baked source assets, prevent scheduler double-crossing by treating the source trajectory as the direction factor.
   - Treat baked/preloaded source cards as an experiment stimulus inventory. When adding or editing source cards, preserve each source's own `trajectory_snapshot`; do not make baked-source displays silently follow later global trajectory edits. Keep source-card visuals compact and metadata-oriented, arrange them as a wrapped grid when space allows, color-code cards by noise/tone type, and let imported/custom audio expose a persisted box-color/tone selector. Render source trajectory representations inside the embedded Three.js trajectory viewer in both 2D and 3D modes, using color-coded overlay paths and parallel multi-color traces when different tones share one trajectory.
   - Treat each Trial Designer row as one independent row-level trial family: all audio and jitter boxes in the row define the variant set for that row, and rows are scheduled/interleaved top-to-bottom inside the block. Keep visible labels aligned with this mental model even if internal schema names still use `trial_strips` and `looming_stimulus` for backward compatibility. Do not reintroduce visible randomizer-event terminology.
   - `Bake Trial Sequences` may batch-materialize Trial Sequence row variants. The backend should create one row folder per trial-family under the active project registry, concatenate audio and silence segments in box order, and write JSON/CSV manifests mapping each derived WAV back to row id, sequence labels, source labels, jitter values, segment timing, scheduler variant key, duration, and hash. Segment 3 may then bake row-preserving trial files from those row variants using the tracked tactile cue: each Segment 2 row gets a top-level row folder containing `target_audio_tactile/`, `baseline/`, and optional `catch_trials/` leaf folders. Segment 4 consumes the Segment 3 manifest and writes `4_trial_repetition_pool/trial_repetition_pool.csv` plus a JSON manifest; it repeats rows by reference and never duplicates WAVs. Segment 5 consumes the Segment 4 CSV and writes `5_block_csv_preview/block_XX.csv` plus `block_csv_preview_manifest.json`; block CSV rows should include separate feature columns and color metadata for family, row, SOA, noise type, sequence, duration, and WAV identity. Generated dashboard WAV filenames should describe content with an informative minimum: Segment 1 ingredients use labels plus component duration (`inhale4000ms.wav`, `pink_frontal_looming4000ms.wav`), Segment 2 variants use component descriptors plus `jitter...` when present and `total...`, and Segment 3 tactile-bearing trial files use sequence identity plus `soa...`, compact tactile duration such as `tac120ms`, `total...`, and `ch3`. Row numbers and long provenance belong in folders/manifests, not every WAV filename.
   - Segment 0-4 registry generation must be button-owned and explicit. Segment 0 uses `Apply Profile / Create Project Folder`, Segment 1 uses `Bake Ingredient`, Segment 2 uses `Bake Trial Sequences`, Segment 3 uses `Bake Baseline/Tactile Trials`, and Segment 4 uses `Bake Trial Pool CSV`. Registry state stays in backend state/manifests plus compact status chips and previews; do not add generic registry feedback panels with `Status`/`Ingredients`/`Variants`/`WAVs`/`Folder`/`Message` summary rows to any segment. Every Segment 0-4 stage keeps an `Open Folder` action backed by `/api/state.project_segments`. Do not let Segment 1 secretly bake Segment 2, do not let Segment 3 auto-bake Segment 2, and do not let Segment 4 auto-bake Segment 3; downstream segments must fail clearly if upstream manifests are missing or stale.
   - Segment 5 row order is structural. Do not treat Segment 2/3 row labels as freely shufflable categories during block CSV generation. The block scheduler must cycle through the preserved row order inside each block and only randomize/balance the concrete trial selected for each row slot. For Study 5 this means inhale/exhale/inhale/exhale throughout every generated block.
   - Segment 0 must write `0_profile/study_manifest.json` beside `project_manifest.json` and `active_design.json`. The study manifest is the folder-level GUI settings inventory: include active/default study settings, baseline strategy, baseline mode, main SOAs, effective baseline SOAs, row scheduling percentages, Segment 4 repetition presets, and Segment 0-3 expected counts.
   - Study 5 profile activation should materialize four writable Segment 1 working-copy ingredients into `profile_study5_box_breathing_pps/1_core_audio_ingredients/`: two frontal looming preload WAVs plus inhale/exhale instruction clips. Active design paths should point to these writable copies, with provenance back to read-only preload/breathing catalogs in the ingredient manifest.
   - Study 5 defaults to full-SOA tactile-only Segment 3 baseline file generation: `include_baseline_trials = true`, `baseline_strategy = tactile_only`, `baseline_custom_trial_mode = tactile_only`, and empty `baseline_soa_values_ms` so the main SOA list drives baseline WAV creation. Keep row `baseline_percentage` scheduling separate; it can remain `0.0` while Segment 3 still bakes baseline files. Study 5 Segment 4 defaults to audio-tactile `6.0`, baseline `3.0`, and catch `6.0`, producing 120 audio-tactile, 60 baseline, and 24 catch CSV rows after Segment 3 has generated 44 trial files.

4. Keep source and file handling local.
   - File selection may happen in browser, but import/store/process must happen through the local companion backend.
   - Store local copies under ignored paths such as `local_data/` or `artifacts/`.
   - Never upload stimulus files, participant data, generated WAVs, or experiment artifacts to hosted services.
   - Distinguish baked/imported material from material the backend should transform.
   - Do not expose full local paths as ordinary editable dashboard text. Keep paths as hidden payload metadata and provide explicit local companion actions such as `Open Folder` when researchers need to inspect files on the PC.

5. Update both sides of every new control.
   - HTML: visible control, stable IDs, accessible grouping.
   - CSS: responsive dimensions, no overlap, no one-note palette drift.
   - JS: render existing state, collect payloads, handle events, keep live previews synchronized.
   - Backend: validate payloads, persist schema fields, preserve backward-compatible defaults.
   - Render/session code: record provenance in manifests/QC when behavior changes.

6. Validate like a product surface.
   - Run targeted Python tests for API/schema/render behavior.
   - Smoke-test the dashboard in a browser with the local backend running.
   - For viewer or canvas changes, verify the page is nonblank and interaction updates fields.
   - For static/hosted changes, push or otherwise update the GitHub Pages-facing files and verify the hosted URL with cache-busting query params.

7. Update project memory.
   - Update `For-AI/project_context.md` for durable architecture/boundary changes.
   - Update `For-AI/evolving_goals.md` for active GUI direction and decisions.
   - Update `For-AI/agent_update_protocol.md` when the maintenance workflow itself changes.
   - Keep memory concise and free of private paths, generated data, participant data, and unsupported claims.

## Transfer Pattern

For other projects, map the same roles:

- Static dashboard assets: HTML/CSS/JS files shown to the user.
- Local companion backend: the trusted process that can read files, run native tools, and write local artifacts.
- Domain engine: renderers, runners, validators, schedulers, or other heavy-lift modules.
- Hosted page: optional static UI that must connect back to local companion software.

The safe design pattern is: browser collects decisions, backend validates and acts, domain engine does the heavy work, manifests record what happened.

For UI layout transfer, use workflow segmentation before panel placement:

- Identify the user's required decision stages.
- Give each stage one anchored website section.
- Put only the controls, previews, and status feedback needed for that stage inside that section.
- Keep later-stage setup and review panels lower on the page, even if they are technically related to earlier data.
- Keep navigation, validation gates, and "continue" actions aligned with these same stages.
- When a decision changes the meaning of later counts, place it in the decision stage that owns those counts rather than hiding it in an unrelated editor. For the PPS dashboard, Trial Sequence Design must remain count-free; Baseline and Tactile Trial Design owns SOAs plus baseline/tactile/catch trial-file baking; Trial Repetition Pool owns repetition counts, read-only family percentage sliders, left-side trial/family count feedback, and right-side duration calculus. Segment 5 Block CSV Preview owns the block count, block CSV bake progress, and per-block color-coded CSV previews, consuming only the Segment 4 CSV. Jitter values in Trial Sequence Design are sequence timing choices inside jitter boxes; they multiply row variants through the same Cartesian-product logic as audio-box alternatives, while the resulting file counts are explained in Segment 3 and repetition-expanded CSV rows are materialized only through Segment 4's CSV bake/manifest outputs.

## References

Read `references/orchestrator-checklist.md` when planning a substantial dashboard change or when the change involves API contracts, file imports, hosted pages, render/session behavior, or privacy boundaries.
