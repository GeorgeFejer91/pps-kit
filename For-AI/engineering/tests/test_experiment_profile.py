from __future__ import annotations

import csv
import json
import wave
from pathlib import Path

import pytest

from peripersonal_space_toolkit.design import default_design
from peripersonal_space_toolkit.designer_segments.registry import manifest_sha256
from peripersonal_space_toolkit.experiment_profile import (
    create_experiment_profile, experiment_profile_bytes, read_experiment_profile,
)


def test_json_profile_freezes_approved_order_and_rejects_changed_ingredient(tmp_path: Path) -> None:
    audio = tmp_path / "ingredient.wav"
    with wave.open(str(audio), "wb") as output:
        output.setparams((2, 2, 48_000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0" * 1920)
    trials = tmp_path / "block.csv"
    with trials.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["trial_file_path", "expected_response", "soa_ms"])
        writer.writeheader()
        writer.writerow({"trial_file_path": str(audio), "expected_response": "respond", "soa_ms": 300})
    order = tmp_path / "order.csv"
    with order.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["block_csv_path", "block_label", "participant_id"])
        writer.writeheader()
        writer.writerow({"block_csv_path": str(trials), "block_label": "First", "participant_id": "P001"})
    accepted = tmp_path / "accepted.json"
    accepted.write_text('{"accepted": true}', encoding="utf-8")
    setup = tmp_path / "setup.json"
    setup.write_text(json.dumps({
        "schema": "pps-experiment-run-setup.v1", "prepared": True,
        "source_segment5_manifest": str(accepted),
        "source_segment5_manifest_sha256": manifest_sha256(accepted), "csv_path": str(order),
    }), encoding="utf-8")
    design = default_design()
    profile = create_experiment_profile(design, setup, source_revision=7)
    destination = tmp_path / "experiment.json"
    destination.write_bytes(experiment_profile_bytes(profile))
    design.protocol.random_seed += 1
    loaded = read_experiment_profile(destination)
    assert loaded["source_revision"] == 7
    assert loaded["design"]["protocol"]["random_seed"] != design.protocol.random_seed
    assert loaded["assembly"]["blocks"][0]["rows"][0]["expected_response"] == "respond"
    assert loaded["files"][-1]["audio"]["channels"] == 2
    assert experiment_profile_bytes(loaded) == destination.read_bytes()
    audio.write_bytes(audio.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="ingredient changed"):
        read_experiment_profile(destination)
