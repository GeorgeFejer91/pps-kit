"""Segment 5: block CSV generation and acceptance ownership."""

from .contracts import SegmentDefinition


DEFINITION = SegmentDefinition(
    index=5,
    key="5_block_csv_preview",
    label="Block CSV preview",
    folder_name="5_block_csv_preview",
    manifest_name="block_csv_preview_manifest.json",
    upstream_key="4_trial_repetition_pool",
    actions=("generate_blocks", "accept_blocks", "reopen_blocks"),
)
