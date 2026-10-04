"""Planner JSON inventory acceptance against the existing Python owner."""
from __future__ import annotations

import csv
import json
import subprocess
import wave
from pathlib import Path

from peripersonal_space_toolkit.design import default_design
from peripersonal_space_toolkit.designer_segments.registry import manifest_sha256
from peripersonal_space_toolkit.experiment_profile import (
    create_experiment_profile,
    experiment_profile_bytes,
    read_experiment_profile,
)


ROOT = Path(__file__).resolve().parents[3]


def _profile(folder: Path) -> Path:
    folder.mkdir(parents=True)
    audio = folder / "ingredient.wav"
    with wave.open(str(audio), "wb") as output:
        output.setparams((2, 2, 48_000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0" * 1920)
    block = folder / "block.csv"
    with block.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["trial_file_path"])
        writer.writeheader()
        writer.writerow({"trial_file_path": str(audio)})
    order = folder / "order.csv"
    with order.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["block_csv_path", "block_label"])
        writer.writeheader()
        writer.writerow({"block_csv_path": str(block), "block_label": "First"})
    accepted = folder / "accepted.json"
    accepted.write_text('{"accepted": true}', encoding="utf-8")
    setup = folder / "setup.json"
    setup.write_text(json.dumps({
        "schema": "pps-experiment-run-setup.v1", "prepared": True,
        "source_segment5_manifest": str(accepted),
        "source_segment5_manifest_sha256": manifest_sha256(accepted),
        "csv_path": str(order),
    }), encoding="utf-8")
    profile = folder / "experiment.json"
    profile.write_bytes(experiment_profile_bytes(
        create_experiment_profile(default_design(), setup, source_revision=7)
    ))
    return profile


def _python_accepts(path: Path) -> bool:
    try:
        read_experiment_profile(path)
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return True


def _participant_profile(folder: Path) -> Path:
    profile_path = _profile(folder)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    setup_path = Path(profile["run_setup_path"])
    setup = json.loads(setup_path.read_text(encoding="utf-8"))
    order_path = Path(setup["csv_path"])
    first_block = folder / "block.csv"
    second_block = folder / "second.csv"
    with second_block.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["trial_file_path"])
        writer.writeheader()
        writer.writerows([{"trial_file_path": str(folder / "ingredient.wav")}] * 2)
    with order_path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=[
            "participant_id", "phase_index", "participant_block_position", "block_csv_path", "block_label",
        ])
        writer.writeheader()
        writer.writerows([
            {"participant_id": "P002", "phase_index": 1, "participant_block_position": 1,
             "block_csv_path": str(first_block), "block_label": "Other"},
            {"participant_id": "P001", "phase_index": 1, "participant_block_position": 2,
             "block_csv_path": str(second_block), "block_label": "Second"},
            {"participant_id": "P001", "phase_index": 1, "participant_block_position": 1,
             "block_csv_path": str(first_block), "block_label": "First"},
        ])
    setup["total_block_runs"] = 3
    setup_path.write_text(json.dumps(setup), encoding="utf-8")
    profile_path.write_bytes(experiment_profile_bytes(
        create_experiment_profile(default_design(), setup_path, source_revision=9)
    ))
    return profile_path


def test_rust_profile_inventory_matches_python_for_export_and_stale_sources(tmp_path: Path) -> None:
    valid = _profile(tmp_path / "valid")
    bom = valid.with_name("experiment-bom.json")
    bom.write_bytes(b"\xef\xbb\xbf" + valid.read_bytes())
    changed = _profile(tmp_path / "changed")
    (changed.parent / "ingredient.wav").write_bytes(b"changed")
    absent = _profile(tmp_path / "absent")
    (absent.parent / "ingredient.wav").unlink()
    stale_hash = _profile(tmp_path / "stale-hash")
    value = json.loads(stale_hash.read_text(encoding="utf-8"))
    value["files"][-1]["sha256"] = "0" * 64
    stale_hash.write_text(json.dumps(value), encoding="utf-8")
    missing_setup = _profile(tmp_path / "missing-setup")
    value = json.loads(missing_setup.read_text(encoding="utf-8"))
    value["files"] = [item for item in value["files"] if item["path"] != value["run_setup_path"]]
    missing_setup.write_text(json.dumps(value), encoding="utf-8")
    duplicate = valid.with_name("experiment-duplicate.json")
    value = json.loads(valid.read_text(encoding="utf-8"))
    value["files"].append(value["files"][0])
    duplicate.write_text(json.dumps(value), encoding="utf-8")
    wrong_schema = valid.with_name("experiment-wrong-schema.json")
    value = json.loads(valid.read_text(encoding="utf-8"))
    value["schema"] = "pps-experiment-profile.v999"
    wrong_schema.write_text(json.dumps(value), encoding="utf-8")
    paths = [valid, bom, changed, absent, stale_hash, missing_setup, duplicate, wrong_schema]
    completed = subprocess.run(
        ["cargo", "run", "--quiet", "--locked", "-p", "pps-session-package", "--example", "experiment_profile_probe"],
        cwd=ROOT, input=json.dumps({"paths": [str(path) for path in paths]}),
        text=True, capture_output=True, check=True,
    )
    rust = json.loads(completed.stdout)
    assert [row["accepted"] for row in rust] == [_python_accepts(path) for path in paths]
    assert [row["accepted"] for row in rust] == [True, True, False, False, False, False, False, False]
    assert rust[0]["ingredient_count"] == 5
    assert rust[5]["code"] == "profile_run_setup_missing"
    assert rust[6]["code"] == "profile_ingredient_invalid"
    assert rust[7]["code"] == "profile_schema_unsupported"


def test_rust_selects_existing_participant_block_order_and_rejects_profile_divergence(tmp_path: Path) -> None:
    valid = _participant_profile(tmp_path / "valid")
    tampered = valid.with_name("experiment-tampered.json")
    value = json.loads(valid.read_text(encoding="utf-8"))
    value["assembly"]["blocks"][0]["rows"][0]["trial_file_path"] = "different.wav"
    tampered.write_text(json.dumps(value), encoding="utf-8")
    unlisted = valid.with_name("experiment-unlisted.json")
    value = json.loads(valid.read_text(encoding="utf-8"))
    value["files"] = [item for item in value["files"] if Path(item["path"]).name != "ingredient.wav"]
    unlisted.write_text(json.dumps(value), encoding="utf-8")
    count_mismatch = _participant_profile(tmp_path / "count-mismatch")
    count_setup_path = Path(json.loads(count_mismatch.read_text(encoding="utf-8"))["run_setup_path"])
    count_setup = json.loads(count_setup_path.read_text(encoding="utf-8"))
    count_setup["total_block_runs"] = 99
    count_setup_path.write_text(json.dumps(count_setup), encoding="utf-8")
    count_mismatch.write_bytes(experiment_profile_bytes(
        create_experiment_profile(default_design(), count_setup_path, source_revision=10)
    ))
    cases = [
        {"profile_path": str(valid), "participant_id": "P001"},
        {"profile_path": str(valid), "participant_id": "P002"},
        {"profile_path": str(valid), "participant_id": "P999"},
        {"profile_path": str(tampered), "participant_id": "P001"},
        {"profile_path": str(unlisted), "participant_id": "P001"},
        {"profile_path": str(count_mismatch), "participant_id": "P001"},
    ]
    completed = subprocess.run(
        ["cargo", "run", "--quiet", "--locked", "-p", "pps-session-package", "--example", "experiment_plan_probe"],
        cwd=ROOT, input=json.dumps({"cases": cases}),
        text=True, capture_output=True, check=True,
    )
    rust = json.loads(completed.stdout)
    assert rust[:3] == [
        {"accepted": True, "code": "selected", "block_labels": ["First", "Second"], "trial_counts": [1, 2]},
        {"accepted": True, "code": "selected", "block_labels": ["Other"], "trial_counts": [1]},
        {"accepted": False, "code": "profile_participant_missing", "block_labels": [], "trial_counts": []},
    ]
    assert [row["code"] for row in rust[3:]] == [
        "profile_plan_invalid", "profile_plan_ingredient_not_listed", "profile_plan_invalid",
    ]
