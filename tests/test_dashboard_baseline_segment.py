from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from peripersonal_space_toolkit import dashboard_app
from peripersonal_space_toolkit.dashboard_app import DashboardController, create_app
from peripersonal_space_toolkit.design import ProtocolSpec, default_design, design_to_dict, save_design


def _compact_design():
    design = default_design()
    design.noises = design.noises[:1]
    design.protocol = ProtocolSpec(
        repetitions_per_condition=1,
        soa_values_ms=[300],
        spatial_values_cm=[100.0],
        pair_spatial_values_with_soas=True,
        auditory_motion_directions=["looming"],
        tactile_sites=["hand"],
        include_catch_trials=False,
        catch_trial_percentage=0.0,
        include_baseline_trials=False,
        respiratory_phases=["Inhale"],
        blocks=1,
        participants=1,
        random_seed=20250604,
    )
    return design


def _client(tmp_path: Path) -> TestClient:
    design_path = tmp_path / "design.json"
    render_dir = tmp_path / "rendered"
    render_dir.mkdir()
    wav_path = render_dir / "looming_pink_frontal.wav"
    sf.write(wav_path, np.zeros((441, 3), dtype=np.float32), 44100)
    (render_dir / "render_manifest.json").write_text(
        json.dumps({"schema": "pps-render-manifest.v1", "status": "rendered_reference"}),
        encoding="utf-8",
    )
    save_design(_compact_design(), design_path)
    controller = DashboardController(
        design_path=design_path,
        render_dir=render_dir,
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
    )
    return TestClient(create_app(controller))


def test_dashboard_static_assets_keep_numbered_baseline_and_block_segments():
    dashboard_files = files("peripersonal_space_toolkit.dashboard")
    html = dashboard_files.joinpath("index.html").read_text(encoding="utf-8")
    app_js = dashboard_files.joinpath("app.js").read_text(encoding="utf-8")

    assert "Baseline and Tactile Trial Design" in html
    assert "Trial Repetition Pool" in html
    assert "Repetition Controls" in html
    assert "Segment 3" in html
    assert "Segment 4" in html
    assert "Segment 5" in html
    assert "Segment 6" in html
    assert "Segment 7" not in html
    assert "Decision stage" not in html
    assert 'data-step-link="baseline"' in html
    assert 'data-step-link="schedule"' in html
    assert html.index("Trial Sequence Design") < html.index("Baseline and Tactile Trial Design")
    assert html.index("Baseline and Tactile Trial Design") < html.index("Trial Repetition Pool")
    assert html.index("Trial Repetition Pool") < html.index("Generate and Review Blocks")
    assert html.index('id="schedule"') < html.index('id="run"')
    assert 'id="baseline-enabled"' in html
    assert 'id="baseline-strategy"' in html
    assert 'id="baseline-options"' in html
    assert 'id="baseline-percent"' in html
    assert 'id="catch-percent"' in html
    assert 'id="baseline-soa-values"' in html
    assert 'id="single-baseline-anchor"' not in html
    assert 'id="composition-tree"' in html
    assert 'class="composition-sliders"' in html
    assert 'id="trial-pool-duration-calculus"' in html
    assert 'id="row-mix-overrides"' in html
    assert "Pool Preview" not in html
    assert 'id="trial-table"' not in html
    assert 'id="trial-pool-duration-summary"' not in html
    assert 'id="trial-pool-output-summary"' not in html
    assert "No baseline" in html
    assert 'type="checkbox" name="baseline-option"' in html
    assert "Use baseline trials" not in html
    assert "Minimum SOA anchor" in html
    assert "Maximum SOA anchor" in html
    assert "Full SOA tactile-only" in html
    assert "Full SOA stationary bursts" in html
    assert "Custom timings" in html
    assert 'id="baseline-custom-audio-tactile"' in html
    assert 'id="bake-trial-files"' in html
    assert 'id="baseline-factor-tree"' in html
    assert 'id="trial-file-output-summary"' not in html
    assert "Trial Sequence Design" in html
    assert "percent-mixer" not in html
    assert "Bake Trial Pool CSV" in html
    assert "Regenerate Blocks" in html
    assert "Accept Blocks" in html
    assert 'name="experiment-structure"' in html
    assert "Planned participants" in html
    assert "Prepare Experiment" in html
    assert "Run Setup" not in html
    assert "Block Permutation Preview" in html
    assert "Save Design and Start Experiment Runner" in html
    assert "Prepare Experiment + Open Runner" not in html
    assert 'id="participant-id"' not in html
    assert 'id="render-action"' not in html
    assert 'id="prepare-action"' not in html
    assert 'data-step-link="review"' not in html
    assert 'id="review"' not in html
    assert 'id="block-count"' in html
    assert 'id="block-build-progress-track"' in html
    assert 'id="block-csv-preview-list"' in html
    assert "count-strip" in html
    assert "Default baseline %" not in html
    assert "Default catch %" not in html
    assert "Continue To Baseline And Tactile" in html
    assert "BASELINE_STRATEGY_NOTES" in app_js
    assert "renderBaseline" in app_js
    assert "baselineCountEstimate" in app_js
    assert "blockCompositionEstimate" in app_js
    assert "renderCompositionTree" in app_js
    assert "renderRowMixOverrides" in app_js
    assert "renderLiveTrialPreviewTables" in app_js
    assert "min_max" in app_js
    assert "baseline_trial_percentage" in app_js
    assert "baseline_trials_exact" in app_js


def test_dashboard_saves_baseline_strategy_and_updates_summary(tmp_path: Path):
    client = _client(tmp_path)
    design = _compact_design()
    design.protocol.include_baseline_trials = True
    design.protocol.baseline_strategy = "soa_zero"
    design.protocol.baseline_trial_percentage = 20.0

    updated = client.post("/api/design", json={"participant_id": "P001", "design": design_to_dict(design)}).json()

    protocol = updated["design"]["protocol"]
    summary = updated["protocol_summary"]
    assert protocol["include_baseline_trials"] is True
    assert protocol["baseline_strategy"] == "soa_zero"
    assert protocol["baseline_trials_exact"] is None
    assert protocol["baseline_trial_percentage"] == pytest.approx(20.0)
    assert summary["baseline_trials"] == 1
    assert summary["baseline_actual_percent"] == pytest.approx(50.0)
    assert "estimated_participant_minutes" in summary


def test_full_soa_baseline_anchors_respect_custom_timing_list():
    design = _compact_design()
    design.protocol.include_baseline_trials = True
    design.protocol.soa_values_ms = [10, 50]
    design.protocol.baseline_strategy = "tactile_only"
    design.protocol.baseline_soa_values_ms = [50]

    assert dashboard_app._baseline_anchor_specs(design) == [
        {"anchor_label": "custom_50ms", "soa_ms": 50, "mode": "tactile_only"}
    ]

    design.protocol.baseline_soa_values_ms = []
    assert dashboard_app._baseline_anchor_specs(design) == [
        {"anchor_label": "full_soa_10ms", "soa_ms": 10, "mode": "tactile_only"},
        {"anchor_label": "full_soa_50ms", "soa_ms": 50, "mode": "tactile_only"},
    ]

    design.protocol.baseline_strategy = "stationary_burst"
    design.protocol.baseline_soa_values_ms = [50]
    assert dashboard_app._baseline_anchor_specs(design) == [
        {"anchor_label": "custom_stationary_burst_50ms", "soa_ms": 50, "mode": "stationary_burst"}
    ]
