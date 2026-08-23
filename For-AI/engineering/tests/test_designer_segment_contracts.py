from __future__ import annotations

import json
from pathlib import Path

import pytest

from peripersonal_space_toolkit import dashboard_app
from peripersonal_space_toolkit.designer_segments import (
    build_segment_lineage,
    downstream_definitions,
    ordered_definitions,
    validate_segment_lineage,
)


def test_segment_registry_is_one_ordered_output_to_input_chain() -> None:
    definitions = ordered_definitions()

    assert [definition.index for definition in definitions] == list(range(7))
    assert [definition.folder_name for definition in definitions] == [
        "0_profile",
        "1_core_audio_ingredients",
        "2_trial_sequence_designs",
        "3_tactile_and_baseline_trials",
        "4_trial_repetition_pool",
        "5_block_csv_preview",
        "6_experiment_run_setup",
    ]
    for previous, current in zip(definitions, definitions[1:]):
        assert current.upstream_key == previous.key
    assert [definition.key for definition in downstream_definitions("3_tactile_and_baseline_trials")] == [
        "4_trial_repetition_pool",
        "5_block_csv_preview",
        "6_experiment_run_setup",
    ]


def test_frontend_segment_registry_mirrors_backend_contract() -> None:
    source = (
        Path(__file__).resolve().parents[3]
        / "apps"
        / "designer"
        / "frontend"
        / "segment_registry.js"
    ).read_text(encoding="utf-8")

    offsets = []
    for definition in ordered_definitions():
        offset = source.index(f'key: "{definition.key}"')
        offsets.append(offset)
        assert f'folderName: "{definition.folder_name}"' in source
        assert f'manifestName: "{definition.manifest_name}"' in source
        assert f'upstreamKey: "{definition.upstream_key}"' in source
    assert offsets == sorted(offsets)


def test_segment_lineage_detects_changed_upstream_manifest(tmp_path: Path) -> None:
    upstream = tmp_path / "stimulus_ingredients_manifest.json"
    upstream.write_text(json.dumps({"version": 1}), encoding="utf-8")
    manifest = {
        "segment_lineage": build_segment_lineage(
            "2_trial_sequence_designs",
            upstream_manifest_path=upstream,
            design_signature="design-a",
        )
    }

    assert validate_segment_lineage(manifest, "2_trial_sequence_designs", upstream_manifest_path=upstream) == []
    upstream.write_text(json.dumps({"version": 2}), encoding="utf-8")
    assert "manifest changed" in validate_segment_lineage(
        manifest,
        "2_trial_sequence_designs",
        upstream_manifest_path=upstream,
    )[0]
    assert validate_segment_lineage({}, "2_trial_sequence_designs", upstream_manifest_path=upstream) == []


def test_failed_segment_rebuild_restores_last_complete_output(tmp_path: Path) -> None:
    root = tmp_path / "2_trial_sequence_designs"
    root.mkdir()
    (root / "manifest.json").write_text("last-known-good", encoding="utf-8")

    def failing_build() -> dict[str, object]:
        root.mkdir()
        (root / "partial.json").write_text("partial", encoding="utf-8")
        raise ValueError("validation failed")

    with pytest.raises(ValueError, match="validation failed"):
        dashboard_app._transactional_segment_rebuild(root, failing_build)

    assert (root / "manifest.json").read_text(encoding="utf-8") == "last-known-good"
    assert not (root / "partial.json").exists()
    assert not list(tmp_path.glob(".2_trial_sequence_designs.pps-backup-*"))


def test_successful_segment_rebuild_replaces_previous_output(tmp_path: Path) -> None:
    root = tmp_path / "5_block_csv_preview"
    root.mkdir()
    (root / "old.csv").write_text("old", encoding="utf-8")

    def successful_build() -> dict[str, object]:
        root.mkdir()
        (root / "new.csv").write_text("new", encoding="utf-8")
        return {"status": "baked"}

    assert dashboard_app._transactional_segment_rebuild(root, successful_build) == {"status": "baked"}
    assert not (root / "old.csv").exists()
    assert (root / "new.csv").read_text(encoding="utf-8") == "new"
    assert not list(tmp_path.glob(".5_block_csv_preview.pps-backup-*"))
