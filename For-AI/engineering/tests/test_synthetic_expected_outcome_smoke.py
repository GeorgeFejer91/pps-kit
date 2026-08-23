from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = ROOT / "For-AI" / "research" / "literature" / "preload-ledgers" / "audiotactile_expected_outcome_coverage.json"
SCRIPT_PATH = ROOT / "For-AI/engineering/validation" / "scripts" / "run_synthetic_expected_outcome_smoke.py"

READY_PROFILE_IDS = {
    "biggio_2017_racket_tool_use",
    "tajadura_jimenez_2009_visual_deprivation",
    "canzoneri_2012_dynamic_sounds",
    "canzoneri_2013_amputation_prosthesis",
    "galli_2015_wheelchair",
    "lamia_2026_arm_movement",
    "lerner_2021_3d_boundary",
    "matsuda_2021_four_directions",
    "noel_2015_bodily_self",
    "noel_2015_walking",
    "pfeiffer_2018_vestibular",
    "serino_2015_front_back_trunk_exp2",
    "serino_2015_peri_hand_exp3",
    "serino_2015_peri_trunk_exp1",
    "serino_2015_toolless_sync_training",
    "smartphone_rt_methods_2025",
    "tonelli_2019_echolocation",
}


def _load_script():
    spec = importlib.util.spec_from_file_location("run_synthetic_expected_outcome_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_synthetic_expected_outcome_smoke_generates_ready_profile_rows(tmp_path):
    module = _load_script()
    output_dir = tmp_path / "synthetic_outcome"

    report = module.run_smoke(ledger_path=LEDGER_PATH, output_dir=output_dir)

    assert report["schema"] == module.SCHEMA
    assert report["passed"] is True
    assert report["summary"] == {
        "ready_profile_record_count": 17,
        "synthetic_comparison_record_count": 17,
        "synthetic_direction_match_count": 17,
        "synthetic_direction_mismatch_count": 0,
        "human_behavioral_comparison_count_from_ledger": 0,
        "all_synthetic_direction_checks_passed": True,
    }
    assert {row["record_id"] for row in report["records"]} == READY_PROFILE_IDS
    assert (output_dir / "synthetic_expected_outcome_smoke_report.json").exists()
    assert (output_dir / "synthetic_expected_outcome_smoke_report.md").exists()

    for row in report["records"]:
        assert row["runnable_status"] == "runnable_profile_parameters_ready"
        assert row["ledger_observed_vs_expected_status"] == (
            "mouse_click_simulated_participant_like_comparison_available_behavioral_effect_unobserved"
        )
        assert row["comparison"] == {
            "status": "synthetic_direction_matches_expected",
            "pass": True,
            "criterion": "synthetic observed effect-direction label exactly equals the structured expected label",
        }
        assert row["synthetic_observation"]["model_id"] == module.MODEL_ID
        assert row["synthetic_observation"]["observed_effect_direction"] == row["expected"]["effect_direction"]
        assert "not human behavioral PPS evidence" in row["evidence_boundary"]


def test_synthetic_expected_outcome_smoke_report_round_trips_json(tmp_path):
    module = _load_script()
    output_dir = tmp_path / "round_trip"

    report = module.run_smoke(ledger_path=LEDGER_PATH, output_dir=output_dir)
    written = json.loads((output_dir / "synthetic_expected_outcome_smoke_report.json").read_text(encoding="utf-8"))

    assert written == report
    assert written["model"]["model_id"] == "direction_label_oracle.v1"
    assert written["model"]["model_inputs"] == ["structured expected_outcome.expected_effect_direction"]
    assert "not collected participant data" in written["model"]["assumption_boundary"]
