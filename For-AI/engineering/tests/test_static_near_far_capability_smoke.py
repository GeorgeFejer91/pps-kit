from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "For-AI/engineering/validation" / "scripts" / "run_static_near_far_capability_smoke.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_static_near_far_capability_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_static_near_far_capability_smoke_runs_generated_block(tmp_path: Path):
    smoke = _load_script()

    report = smoke.run_smoke(output_dir=tmp_path)

    assert report["schema"] == smoke.SCHEMA
    assert report["passed"]
    assert report["block_count"] == 1
    assert report["block_row_family_counts"] == {
        "audio_tactile": 4,
        "baseline": 2,
        "catch": 2,
    }
    assert report["audio_tactile_distance_label_counts"] == {"far": 2, "near": 2}
    assert report["expected_tactile_response_count"] == 6
    assert report["event_counts"]["mouse_click"] == 6
    assert report["event_counts"]["response_marker_start"] == 6
    assert report["analysis_ready_hit_count"] == 6
    assert report["block_wav_facts"]["readable"]
    assert "static near/far audio-tactile rows" in report["evidence_boundary"]
    assert (tmp_path / "static_near_far_capability_smoke_report.json").exists()
    assert (tmp_path / "static_near_far_capability_smoke_report.md").exists()
