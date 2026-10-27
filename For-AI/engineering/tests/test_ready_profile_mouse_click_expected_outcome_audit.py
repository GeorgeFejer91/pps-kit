from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "For-AI/engineering/validation" / "scripts" / "run_ready_profile_mouse_click_expected_outcome_audit.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_ready_profile_mouse_click_expected_outcome_audit", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ready_profile_mouse_click_expected_outcome_audit_runs_through_runner():
    audit = _load_script()
    # This audit creates a deep Segment 0-6 tree. Keep its Windows base path
    # short so the test exercises the supported runtime layout, not pytest's
    # much longer per-test directory prefix.
    short_temp_parent = Path(tempfile.gettempdir()).anchor if os.name == "nt" else None
    with tempfile.TemporaryDirectory(prefix="pps-mouse-", dir=short_temp_parent) as directory:
        output_dir = Path(directory)
        report = audit.run_audit(
            output_dir=output_dir,
            records=["canzoneri_2012_dynamic_sounds"],
            max_samples_per_condition=1,
        )

        assert report["schema"] == audit.SCHEMA
        assert report["passed"], {
            "summary": report["summary"],
            "comparisons": [record["comparison"] for record in report["records"]],
        }
        assert report["summary"]["record_count"] == 1
        assert report["summary"]["passed_record_count"] == 1
        # Six modeled distance/motion bins plus the explicit tactile controls.
        planned = report["summary"]["planned_click_count"]
        assert planned >= 6
        assert report["summary"]["mouse_click_count"] == planned
        assert report["summary"]["response_marker_start_count"] == planned
        assert report["summary"]["observed_analysis_hit_count"] == planned
        assert "SessionRunnerController.log_click()" in report["evidence_boundary"]
        assert (output_dir / "ready_profile_mouse_click_expected_outcome_audit_report.json").exists()
        assert (output_dir / "ready_profile_mouse_click_expected_outcome_audit_report.md").exists()

        record = report["records"][0]
        assert record["record_id"] == "canzoneri_2012_dynamic_sounds"
        assert record["status"] == "mouse_click_simulated_participant_like_comparison_passed"
        assert record["comparison"]["observed_effect_direction"] == "approaching_near_body_sounds_speed_tactile_rt"
        assert record["comparison"]["expected_effect_direction"] == "approaching_near_body_sounds_speed_tactile_rt"
        assert {
            f"{motion}_{distance}"
            for motion in ("approaching", "receding")
            for distance in ("near", "middle", "far")
        }.issubset(record["comparison"]["condition_mean_rt_ms"])


def test_source_conflicted_profile_cannot_pass_ready_profile_mouse_click_audit(tmp_path):
    audit = _load_script()
    report = audit.run_audit(
        output_dir=tmp_path,
        records=["smartphone_rt_methods_2025"],
        max_samples_per_condition=1,
    )
    assert report["passed"] is False
    assert report["criteria"]["ready_records_found"] is False
    assert report["summary"]["record_count"] == 0
    assert report["summary"]["mouse_click_count"] == 0
    assert report["records"] == []


def test_long_prepared_manifest_path_preserves_planner_soa_range(tmp_path):
    audit = _load_script()
    path = tmp_path / ("a" * 90) / ("b" * 90) / ("c" * 90) / "block.csv"
    filesystem_path = Path(audit._filesystem_path(path))
    filesystem_path.parent.mkdir(parents=True)
    filesystem_path.write_text("Family,SOA_ms\naudio_tactile,300\naudio_tactile,2700\n", encoding="utf-8")
    rows = [audit._normalize_row(row) for row in audit._read_csv(path)]
    assert len(rows) == 2
    stats = audit.PlannerStats(rows)
    assert (stats.soa_min, stats.soa_max) == (300.0, 2700.0)
