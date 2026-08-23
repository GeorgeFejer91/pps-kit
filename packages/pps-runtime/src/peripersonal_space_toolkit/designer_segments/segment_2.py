"""Segment 2: within-trial sequence ownership."""

from .contracts import SegmentDefinition


DEFINITION = SegmentDefinition(
    index=2,
    key="2_trial_sequence_designs",
    label="Trial sequence designs",
    folder_name="2_trial_sequence_designs",
    manifest_name="trial_sequence_variants_manifest.json",
    upstream_key="1_core_audio_ingredients",
    actions=("build_trial_sequences",),
)
