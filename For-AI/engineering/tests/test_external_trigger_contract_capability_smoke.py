from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "For-AI/engineering/validation" / "scripts" / "run_external_trigger_contract_capability_smoke.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_external_trigger_contract_capability_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_external_trigger_contract_capability_smoke_runs_marker_contract(tmp_path: Path):
    smoke = _load_script()

    report = smoke.run_smoke(output_dir=tmp_path)

    assert report["schema"] == smoke.SCHEMA
    assert report["passed"]
    assert report["block_count"] == 1
    assert report["block_row_family_counts"] == {
        "audio_tactile": 1,
        "baseline": 1,
        "catch": 1,
    }
    assert report["event_counts"]["mouse_click"] == 2
    assert report["event_counts"]["response_marker_start"] == 2
    assert report["participant_trial_count"] == 3
    assert report["analysis_ready_trial_count"] == 2
    assert report["criteria"]["trigger_dictionary_preserves_external_trigger_contract"]
    assert report["criteria"]["marker_payloads_preserve_external_trigger_contract"]
    assert report["criteria"]["local_marker_xdf_written"]
    assert "hardware TTL" in report["evidence_boundary"]
    assert (tmp_path / "external_trigger_contract_capability_smoke_report.json").exists()
    assert (tmp_path / "external_trigger_contract_capability_smoke_report.md").exists()
