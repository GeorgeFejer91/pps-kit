"""Segment 1: reusable audio ingredient ownership."""

from .contracts import SegmentDefinition


DEFINITION = SegmentDefinition(
    index=1,
    key="1_core_audio_ingredients",
    label="Core audio ingredients",
    folder_name="1_core_audio_ingredients",
    manifest_name="stimulus_ingredients_manifest.json",
    upstream_key="0_profile",
    actions=("create_ingredient", "update_ingredient", "remove_ingredient"),
)
