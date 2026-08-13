"""Segment 6: profile validation and finalization ownership."""

from .contracts import SegmentDefinition


DEFINITION = SegmentDefinition(
    index=6,
    key="6_experiment_run_setup",
    label="Profile validation and save",
    folder_name="6_experiment_run_setup",
    manifest_name="experiment_run_setup_manifest.json",
    upstream_key="5_block_csv_preview",
    actions=("preview_order", "finalize_profile", "export_profile"),
)
