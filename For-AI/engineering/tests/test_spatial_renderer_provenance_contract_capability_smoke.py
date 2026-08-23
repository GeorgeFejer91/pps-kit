from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "For-AI/engineering/validation" / "scripts" / (
    "run_spatial_renderer_provenance_contract_capability_smoke.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("run_spatial_renderer_provenance_contract_capability_smoke", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_spatial_renderer_provenance_contract_capability_smoke_runs_hrtf_metadata(tmp_path: Path):
    smoke = _load_script()

    report = smoke.run_smoke(output_dir=tmp_path)

    assert report["schema"] == smoke.SCHEMA
    assert report["passed"]
    assert report["block_count"] == 1
    assert report["block_row_family_counts"] == {
        "audio_tactile": 2,
        "catch": 1,
    }
    assert report["block_row_renderer_engines"] == {"original_matlab_hrtf_renderer": 3}
    assert report["block_row_hrtf_databases"] == {"paper_reported_or_unresolved_hrtf_database": 3}
    assert report["block_row_source_equivalence"] == {"proxy_binaural_runner_smoke_not_bitmatched": 3}
    assert report["event_counts"]["mouse_click"] == 2
    assert report["event_counts"]["response_marker_start"] == 2
    assert report["participant_trial_count"] == 3
    assert report["analysis_ready_trial_count"] == 2
    assert report["criteria"]["prepared_rows_preserve_spatial_renderer_contract"]
    assert report["criteria"]["marker_payloads_preserve_spatial_renderer_contract"]
    assert report["criteria"]["trigger_dictionary_preserves_spatial_renderer_contract"]
    assert report["criteria"]["participant_rows_preserve_spatial_renderer_contract"]
    assert report["criteria"]["analysis_rows_preserve_spatial_renderer_contract"]
    assert report["criteria"]["software_wired_loopback_written"]
    assert "not bit-matched MATLAB or HRTF rendering" in report["evidence_boundary"]
    assert (tmp_path / "spatial_renderer_provenance_contract_capability_smoke_report.json").exists()
    assert (tmp_path / "spatial_renderer_provenance_contract_capability_smoke_report.md").exists()
