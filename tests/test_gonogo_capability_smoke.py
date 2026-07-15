from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "validation_protocols" / "scripts" / "run_gonogo_capability_smoke.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_gonogo_capability_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gonogo_capability_smoke_runs_response_contract(tmp_path: Path):
    smoke = _load_script()

    report = smoke.run_smoke(output_dir=tmp_path)

    assert report["schema"] == smoke.SCHEMA
    assert report["passed"]
    assert report["block_count"] == 1
    assert report["block_row_family_counts"] == {
        "audio_tactile": 3,
        "baseline": 2,
        "catch": 2,
    }
    assert report["block_row_expected_response_counts"] == {"respond": 2, "withhold": 5}
    assert report["event_counts"]["tactile_onset"] == 5
    assert report["event_counts"]["mouse_click"] == 3
    assert report["event_counts"]["response_marker_start"] == 3
    assert report["participant_outcome_counts"] == {"hit": 6, "miss": 1}
    assert report["analysis_ready_trial_count"] == 5
    assert report["analysis_ready_hit_count"] == 4
    assert report["topup_summary"]["tracked_tactile_trials"] == 2
    assert report["topup_summary"]["hit_count"] == 2
    assert report["topup_summary"]["missed_needs_topup_count"] == 0
    assert report["block_wav_facts"]["readable"]
    assert report["software_wired_loopback_wav_facts"]["readable"]
    assert "row-level respond-vs-withhold tactile expectations" in report["evidence_boundary"]
    assert (tmp_path / "gonogo_capability_smoke_report.json").exists()
    assert (tmp_path / "gonogo_capability_smoke_report.md").exists()


def test_gonogo_response_expectation_parser_handles_negative_target_labels():
    from peripersonal_space_toolkit import session_analysis, session_runner, topup

    helpers = [
        session_runner._response_expectation_decision,
        session_analysis._response_expectation_decision,
        topup._response_expectation_decision,
    ]
    for helper in helpers:
        assert helper("strong non target") is False
        assert helper("not a target") is False
        assert helper("respond to weak target; withhold strong") is None
