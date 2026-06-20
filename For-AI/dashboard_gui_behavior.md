# Dashboard GUI Behavior

## View/Edit Mode

The HTML dashboard has a left-rail `View / Edit` mode switch. `View` is the safe default on page load, profile load, existing custom-study load, and refresh. In View mode, researchers can inspect, navigate, preview audio, open folders, launch already prepared profile-run actions, and save a prepared experiment as a reusable study profile, but mutation controls are locked.

Entering `Edit` on a bundled/read-only profile opens the existing custom-study naming modal first. After the custom copy is created, Edit mode unlocks source, trajectory, trial-sequence, baseline, repetition, block, and run-setup decisions for that custom working copy. Static hosted mode without a local companion cannot enter Edit mode.

## Trajectory Preview

The Segment 1 trajectory preview is an embedded Three.js viewer. The right-side preview controls (`2D`, `3D`, view presets, zoom, fit radius, reset) are view-only camera controls and must stay usable in read-only, locked, and hosted/static modes. The left trajectory/source controls remain mutation controls and are gated by View/Edit mode.

The dashboard must not depend solely on catching the iframe `load` event before it sends preview payloads. If the viewer iframe loads before listeners are attached, `updateViewer()` should detect the viewer API when it becomes available, mark it ready, and push the current payload so online/static previews do not remain stuck on the viewer's initial placeholder 2D scene.

## Downward Source Propagation

Top-level source-card labels are parent decisions for Segment 2 trial-sequence audio boxes. When a source card is removed in Edit mode, that label is pruned immediately from every downstream sequence box before save. When a source-card label changes, existing downstream labels are renamed to the new label. Future label pickers are rebuilt from the current source pool.

The backend also prunes stale custom-design `trial_strips[*].elements[*].source_labels` during save, so direct/API payloads cannot persist labels for deleted sources. Bundled profile preloads remain unchanged and read-only until copied.

## Study 5 White/Pink Canonical Profile

The tracked preload `study5_box_breathing_pps` is the only Study 5 lab profile in the repository. Its stable ID is retained for compatibility, but its source pool is now the canonical white/pink version: exactly `Pink frontal` and `White frontal` looming sources plus `Inhale instruction` and `Exhale instruction` fixed clips from the original Study 5 audio. The profile retains the Study 5 SOAs, trajectory, instruction audio, baseline/catch settings, block/run defaults, and total trial-budget logic. Because the looming source pool has two noises, Segment 4 family repetitions are scaled to audio-tactile `6.0`, baseline `3.0`, and catch `6.0`; this preserves 204 planned rows and six 34-trial blocks.

In the HTML dashboard study selector, `study5_box_breathing_pps` should appear as the first/default bundled Study 5 profile. Do not add or restore a second Study 5 profile.

## Static Profile Segment 3-5 Previews

Hosted/static mode cannot write WAVs or CSVs, but finished bundled profiles must still show the same downstream decisions that the local companion would materialize. `staticStateForTemplate()` therefore derives read-only virtual Segment 3 trial files, Segment 4 repetition-pool rows, and already-randomized Segment 5 block previews from the committed profile parameters. Study 5 should show 44 virtual Segment 3 WAVs, 204 planned Segment 4 pool rows, and 6 accepted static block previews of 34 trials each. Static previews must use the same seeded, row-order-preserving Gellermann-style block scheduler concept as the local companion and expose `Download Randomization` for the browser-generated CSV/manifest. The local companion still performs actual file/CSV materialization when launching or preparing a run.

## Static Preview Parity Audit

Hosted/static no-companion mode must keep every profile visible in the static selector aligned with committed offline/local profile truth. Ready launchable profiles must match local dashboard preview counts and read-only Segment 3-6 summaries; blocked profiles must remain inspectable only as metadata/source/trajectory/blocker previews and must not appear launchable. Editing, baking, file import, saving, output-folder export, local-folder opening, and runner launch remain disabled until the hosted page connects to the local companion.

`validation_protocols/scripts/run_static_dashboard_preview_parity_audit.py` is the static-preview parity harness. It can force the dashboard into no-companion static mode with `forceStaticPreview=1`, read the query-gated sanitized browser snapshot exposed by `auditStaticPreview=1`, and compare all static-selectable profiles against preload/profile ledgers plus local Protocol 12 materialization for ready profiles. The audit surface must stay validation-only and must not expose local paths, participant data, generated outputs, or secrets.
