"""Segment 3: tactile, baseline, and catch trial-file ownership."""

from .contracts import SegmentDefinition


DEFINITION = SegmentDefinition(
    index=3,
    key="3_tactile_and_baseline_trials",
    label="Tactile and baseline trial files",
    folder_name="3_tactile_and_baseline_trials",
    manifest_name="baseline_tactile_trial_files_manifest.json",
    upstream_key="2_trial_sequence_designs",
    actions=("build_trial_files",),
)
