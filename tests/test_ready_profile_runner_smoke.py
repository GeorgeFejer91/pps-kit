from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "validation_protocols" / "scripts" / "run_ready_profile_runner_smoke.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_ready_profile_runner_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ready_profile_runner_smoke_runs_prepared_profile_package(tmp_path: Path):
    smoke = _load_script()

    report = smoke.run_smoke(
        output_dir=tmp_path,
        templates=["pfeiffer_2018_lateral_perihead_left_to_right"],
    )

    assert report["schema"] == smoke.SCHEMA
    assert report["passed"]
    assert report["summary"]["profile_count"] == 1
    assert report["summary"]["passed_profile_count"] == 1
    assert report["summary"]["total_blocks_played"] == 3
    assert report["summary"]["total_response_markers"] == 3
    assert "software-only runner-contract smoke" in report["evidence_boundary"]
    assert (tmp_path / "ready_profile_runner_smoke_report.json").exists()
    assert (tmp_path / "ready_profile_runner_smoke_report.md").exists()

    profile = report["profiles"][0]
    assert profile["template_id"] == "pfeiffer_2018_lateral_perihead_left_to_right"
    assert profile["passed"]
    assert all(profile["criteria"].values())
    assert profile["analysis_ready_trial_count"] > 0
    assert profile["block_count"] == 3
    assert profile["analysis_ready_hit_count"] == 3
    assert profile["event_counts"]["response_marker_start"] == 3
    assert profile["event_counts"]["mouse_click"] == 3
    assert profile["recording_wav_count"] == profile["block_count"]
    assert all(item["readable"] for item in profile["block_wavs"])
    assert all(item["readable"] for item in profile["recording_wavs"])
