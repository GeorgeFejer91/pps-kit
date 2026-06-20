# Dashboard GUI Behavior

## View/Edit Mode

The HTML dashboard has a left-rail `View / Edit` mode switch. `View` is the safe default on page load, profile load, existing custom-study load, and refresh. In View mode, researchers can inspect, navigate, preview audio, open folders, launch already prepared profile-run actions, and save a prepared experiment as a reusable study profile, but mutation controls are locked.

Entering `Edit` on a bundled/read-only profile opens the existing custom-study naming modal first. After the custom copy is created, Edit mode unlocks source, trajectory, trial-sequence, baseline, repetition, block, and run-setup decisions for that custom working copy. Static hosted mode without a local companion cannot enter Edit mode.

## Downward Source Propagation

Top-level source-card labels are parent decisions for Segment 2 trial-sequence audio boxes. When a source card is removed in Edit mode, that label is pruned immediately from every downstream sequence box before save. When a source-card label changes, existing downstream labels are renamed to the new label. Future label pickers are rebuilt from the current source pool.

The backend also prunes stale custom-design `trial_strips[*].elements[*].source_labels` during save, so direct/API payloads cannot persist labels for deleted sources. Bundled profile preloads remain unchanged and read-only until copied.

## Study 5 Pink/White Variant

The tracked preload `study5_box_breathing_pps_pink_white` is a Study 5 lab-profile variant created through the dashboard Edit-mode workflow on 2026-06-20. The GUI-created working copy removed the `Blue frontal` and `Brown frontal` source cards, and the downward propagation mechanism pruned those labels from both Segment 2 looming-stimulus boxes. The committed bundled profile keeps only `Pink frontal` and `White frontal`, reuses the original Study 5 Pink/White WAVs, and retains the original Study 5 SOAs, trajectory, instruction audio, baseline/catch settings, block/run defaults, and Segment 4 repetition defaults. With two looming sources and unchanged repetitions, Segment 4 materializes 102 planned rows rather than the original four-source profile's 204 rows.

## Static Profile Segment 3-5 Previews

Hosted/static mode cannot write WAVs or CSVs, but finished bundled profiles must still show the same downstream decisions that the local companion would materialize. `staticStateForTemplate()` therefore derives read-only virtual Segment 3 trial files, Segment 4 repetition-pool rows, and Segment 5 block previews from the committed profile parameters. The Study 5 pink/white variant should show 44 virtual Segment 3 WAVs, 102 planned Segment 4 pool rows, and 6 accepted static block previews. These are inspection previews only; the local companion still performs the actual file/CSV materialization when launching or preparing a run.
