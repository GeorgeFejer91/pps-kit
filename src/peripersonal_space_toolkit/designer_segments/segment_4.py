"""Segment 4: CSV-only trial repetition pool ownership."""

from .contracts import SegmentDefinition


DEFINITION = SegmentDefinition(
    index=4,
    key="4_trial_repetition_pool",
    label="Trial repetition pool",
    folder_name="4_trial_repetition_pool",
    manifest_name="trial_repetition_pool_manifest.json",
    upstream_key="3_tactile_and_baseline_trials",
    actions=("build_trial_pool",),
)
