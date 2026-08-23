from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SMOKE_SCRIPT_PATH = ROOT / "For-AI/engineering/validation" / "scripts" / "run_ready_profile_runner_smoke.py"
LOOPBACK_SCRIPT_PATH = ROOT / "For-AI/engineering/validation" / "scripts" / "run_ready_profile_response_marker_loopback.py"


def _load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ready_profile_response_marker_loopback_recovers_smoke_markers():
    smoke = _load_script(SMOKE_SCRIPT_PATH, "run_ready_profile_runner_smoke_for_loopback_test")
    loopback = _load_script(LOOPBACK_SCRIPT_PATH, "run_ready_profile_response_marker_loopback")
    short_temp_parent = Path(tempfile.gettempdir()).anchor if os.name == "nt" else None
    with tempfile.TemporaryDirectory(prefix="pps-loop-", dir=short_temp_parent) as directory:
        output_dir = Path(directory)
        smoke_report = smoke.run_smoke(
            output_dir=output_dir / "smoke",
            templates=["pfeiffer_2018_lateral_perihead_left_to_right"],
        )
        report = loopback.run_validation(
            smoke_report=Path(smoke_report["report_json"]),
            output_dir=output_dir / "loopback",
        )

        assert report["schema"] == loopback.SCHEMA
        assert report["passed"]
        assert report["summary"]["profile_count"] == 1
        assert report["summary"]["passed_profile_count"] == 1
        assert report["summary"]["total_expected_markers"] == 3
        assert report["summary"]["total_detected_markers"] == 3
        assert report["summary"]["total_synthetic_recordings"] == 3
        assert "Synthetic per-ready-profile response-marker loopback" in report["evidence_boundary"]
        assert (output_dir / "loopback" / "ready_profile_response_marker_loopback_report.json").exists()
        assert (output_dir / "loopback" / "ready_profile_response_marker_loopback_report.md").exists()

        profile = report["profiles"][0]
        assert profile["template_id"] == "pfeiffer_2018_lateral_perihead_left_to_right"
        assert profile["passed"]
        assert all(profile["criteria"].values())
        assert profile["expected_marker_count"] == 3
        assert profile["detected_marker_count"] == 3
        assert profile["detection_rate"] == 1.0
        assert len(profile["synthetic_recordings"]) == 3
        assert Path(profile["synthetic_recordings"][0]).is_file()
        assert Path(profile["comparison_report"]).is_file()
        assert Path(profile["comparison_pairs_csv"]).is_file()
