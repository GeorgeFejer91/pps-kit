from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "For-AI/engineering/validation" / "scripts" / (
    "run_audiovisual_trisensory_contract_capability_smoke.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("run_audiovisual_trisensory_contract_capability_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_audiovisual_trisensory_contract_capability_smoke_runs_serino_metadata(tmp_path: Path):
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
    assert report["block_row_multisensory_families"] == {
        "audiovisual_catch": 1,
        "audiovisuotactile": 1,
        "unimodal_tactile_baseline": 1,
    }
    assert report["block_row_exteroceptive_sets"] == {
        "auditory+visual": 2,
        "none": 1,
    }
    assert report["event_counts"]["mouse_click"] == 2
    assert report["event_counts"]["response_marker_start"] == 2
    assert report["participant_trial_count"] == 3
    assert report["analysis_ready_trial_count"] == 2
    assert report["criteria"]["prepared_rows_preserve_audiovisual_contract"]
    assert report["criteria"]["marker_payloads_preserve_audiovisual_contract"]
    assert report["criteria"]["trigger_dictionary_preserves_audiovisual_contract"]
    assert report["criteria"]["participant_rows_preserve_audiovisual_contract"]
    assert report["criteria"]["analysis_rows_preserve_audiovisual_contract"]
    assert report["criteria"]["software_wired_loopback_written"]
    assert "not VR/HMD rendering" in report["evidence_boundary"]
    assert "PPS boundary lies between D3 and D4" in report["paper_parameter_basis"]["expected_outcome"]
    assert (tmp_path / "audiovisual_trisensory_contract_capability_smoke_report.json").exists()
    assert (tmp_path / "audiovisual_trisensory_contract_capability_smoke_report.md").exists()
