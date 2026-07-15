from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "validation_protocols" / "scripts" / "run_ready_profile_mouse_click_expected_outcome_audit.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_ready_profile_mouse_click_expected_outcome_audit", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ready_profile_mouse_click_expected_outcome_audit_runs_through_runner(tmp_path: Path):
    audit = _load_script()

    report = audit.run_audit(
        output_dir=tmp_path,
        records=["smartphone_rt_methods_2025"],
        max_samples_per_condition=1,
    )

    assert report["schema"] == audit.SCHEMA
    assert report["passed"]
    assert report["summary"]["record_count"] == 1
    assert report["summary"]["passed_record_count"] == 1
    assert report["summary"]["planned_click_count"] == 2
    assert report["summary"]["mouse_click_count"] == 2
    assert report["summary"]["response_marker_start_count"] == 2
    assert report["summary"]["observed_analysis_hit_count"] == 2
    assert "SessionRunnerController.log_click()" in report["evidence_boundary"]
    assert (tmp_path / "ready_profile_mouse_click_expected_outcome_audit_report.json").exists()
    assert (tmp_path / "ready_profile_mouse_click_expected_outcome_audit_report.md").exists()

    record = report["records"][0]
    assert record["record_id"] == "smartphone_rt_methods_2025"
    assert record["status"] == "mouse_click_simulated_participant_like_comparison_passed"
    assert record["comparison"]["observed_effect_direction"] == "looming_faster_than_static"
    assert record["comparison"]["expected_effect_direction"] == "looming_faster_than_static"
