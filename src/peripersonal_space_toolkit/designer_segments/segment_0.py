"""Segment 0: study and project registry ownership."""

from .contracts import SegmentDefinition


DEFINITION = SegmentDefinition(
    index=0,
    key="0_profile",
    label="Study project registry",
    folder_name="0_profile",
    manifest_name="project_manifest.json",
    actions=("activate_profile", "create_custom_profile"),
)
