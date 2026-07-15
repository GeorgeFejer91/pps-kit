from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "validation_protocols" / "scripts" / "run_iti_hazard_contract_capability_smoke.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_iti_hazard_contract_capability_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_iti_hazard_contract_capability_smoke_runs_metadata_contract(tmp_path: Path):
    smoke = _load_script()

    report = smoke.run_smoke(output_dir=tmp_path)

    assert report["schema"] == smoke.SCHEMA
    assert report["passed"]
    assert report["block_count"] == 1
    assert report["block_row_family_counts"] == {
        "audio_tactile": 2,
        "baseline": 1,
        "catch": 1,
    }
    assert report["block_row_expectancy_roles"] == {
        "baseline": 1,
        "catch": 1,
        "fixed": 1,
        "flat": 1,
    }
    assert report["event_counts"]["mouse_click"] == 3
    assert report["event_counts"]["response_marker_start"] == 3
    assert report["participant_trial_count"] == 4
    assert report["analysis_ready_trial_count"] == 3
    assert report["criteria"]["prepared_rows_preserve_iti_hazard_contract"]
    assert report["criteria"]["trigger_dictionary_preserves_iti_hazard_contract"]
    assert report["criteria"]["marker_payloads_preserve_iti_hazard_contract"]
    assert report["criteria"]["analysis_rows_preserve_iti_hazard_contract"]
    assert "physical loopback timing" in report["evidence_boundary"]
    assert (tmp_path / "iti_hazard_contract_capability_smoke_report.json").exists()
    assert (tmp_path / "iti_hazard_contract_capability_smoke_report.md").exists()
