from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "For-AI/engineering/validation" / "scripts" / "run_tactile_waveform_capability_smoke.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_tactile_waveform_capability_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_tactile_waveform_capability_smoke_runs_duration_matrix(tmp_path: Path):
    smoke = _load_script()

    report = smoke.run_smoke(output_dir=tmp_path)

    assert report["schema"] == smoke.SCHEMA
    assert report["passed"]
    assert report["block_count"] == 1
    assert report["block_row_family_counts"] == {
        "audio_tactile": 14,
        "baseline": 2,
        "catch": 2,
    }
    assert report["executed_smoke_matrix"]["duration_delay_cells"] == {
        "duration_2s": 7,
        "duration_3s": 7,
    }
    assert report["event_counts"]["mouse_click"] == 16
    assert report["event_counts"]["response_marker_start"] == 16
    assert report["participant_trial_count"] == 18
    assert report["analysis_ready_trial_count"] == 16
    assert report["observed_direction"]["passed"]
    assert report["block_wav_facts"]["readable"]
    assert "80 Hz, 200 ms sawtooth tactile cues" in report["evidence_boundary"]
    assert "MATLAB HRTF" in report["remaining_record_boundary"]
    assert (tmp_path / "tactile_waveform_capability_smoke_report.json").exists()
    assert (tmp_path / "tactile_waveform_capability_smoke_report.md").exists()
