# Dashboard GUI Behavior

## View/Edit Mode

The HTML dashboard has a left-rail `View / Edit` mode switch. `View` is the safe default on page load, profile load, existing custom-study load, and refresh. In View mode, researchers can inspect, navigate, preview audio, open folders, launch already prepared profile-run actions, and save a prepared experiment as a reusable study profile, but mutation controls are locked.

Entering `Edit` on a bundled/read-only profile opens the existing custom-study naming modal first. After the custom copy is created, Edit mode unlocks source, trajectory, trial-sequence, baseline, repetition, block, and run-setup decisions for that custom working copy. Static hosted mode without a local companion cannot enter Edit mode.

## Downward Source Propagation

Top-level source-card labels are parent decisions for Segment 2 trial-sequence audio boxes. When a source card is removed in Edit mode, that label is pruned immediately from every downstream sequence box before save. When a source-card label changes, existing downstream labels are renamed to the new label. Future label pickers are rebuilt from the current source pool.

The backend also prunes stale custom-design `trial_strips[*].elements[*].source_labels` during save, so direct/API payloads cannot persist labels for deleted sources. Bundled profile preloads remain unchanged and read-only until copied.
