from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "validation_protocols" / "scripts" / "run_multi_speaker_switch_contract_capability_smoke.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("run_multi_speaker_switch_contract_capability_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_multi_speaker_switch_contract_capability_smoke_runs_multichannel_wav(tmp_path: Path):
    smoke = _load_script()

    report = smoke.run_smoke(output_dir=tmp_path)

    assert report["schema"] == smoke.SCHEMA
    assert report["passed"]
    assert report["block_count"] == 1
    assert report["block_row_family_counts"] == {"audio_tactile": 2}
    assert report["block_row_audio_output_modes"] == {"switched_speaker_array": 2}
    assert report["block_row_switch_channels"] == {"1|2|4": 1, "4|2|1": 1}
    assert report["block_wav_facts"]["channels"] >= 4
    assert report["speaker_switch_energy_summary"]["passed"]
    assert report["speaker_switch_energy_summary"]["channels"] >= 4
    assert report["event_counts"]["mouse_click"] == 2
    assert report["event_counts"]["response_marker_start"] == 2
    assert report["participant_trial_count"] == 2
    assert report["analysis_ready_trial_count"] == 2
    assert report["criteria"]["prepared_rows_preserve_multi_speaker_switch_contract"]
    assert report["criteria"]["marker_payloads_preserve_multi_speaker_switch_contract"]
    assert report["criteria"]["trigger_dictionary_preserves_multi_speaker_switch_contract"]
    assert report["criteria"]["participant_rows_preserve_multi_speaker_switch_contract"]
    assert report["criteria"]["analysis_rows_preserve_multi_speaker_switch_contract"]
    assert report["criteria"]["software_wired_loopback_written"]
    assert "physical loudspeaker-array validation" in report["evidence_boundary"]
    assert (tmp_path / "multi_speaker_switch_contract_capability_smoke_report.json").exists()
    assert (tmp_path / "multi_speaker_switch_contract_capability_smoke_report.md").exists()
