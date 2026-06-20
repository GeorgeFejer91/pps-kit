from __future__ import annotations

import base64
import csv
import json
import math
import os
import subprocess
import time
from collections import Counter
from importlib.resources import files
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from peripersonal_space_toolkit import dashboard_app, focus_launch, profile_memory
from peripersonal_space_toolkit.dashboard_app import DashboardController, create_app
from peripersonal_space_toolkit.design import (
    AudioFileSpec,
    ProtocolSpec,
    default_design,
    design_from_dict,
    design_to_dict,
    load_design,
    point_from_distance_rotation_height,
    save_design,
    trajectory_point_at_time,
)
from peripersonal_space_toolkit.render_backend import (
    DEFAULT_BACKEND_EXE,
    RenderResult,
    app_to_3dti_coordinates,
    build_render_config,
    render_design_with_3dti,
    sha256_file,
)
from peripersonal_space_toolkit.output_layout import (
    output_metadata_dir,
    output_profile_snapshot_dir,
    output_project_state_dir,
    output_runner_logs_dir,
)
from peripersonal_space_toolkit.subprocess_utils import windows_no_console_kwargs


def test_windows_no_console_kwargs_requests_hidden_console_on_windows():
    kwargs = windows_no_console_kwargs()
    if os.name == "nt":
        assert int(kwargs.get("creationflags") or 0) & subprocess.CREATE_NO_WINDOW
    else:
        assert kwargs == {}
from peripersonal_space_toolkit.runner_diary import read_diary_entries


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


def _render_dir(tmp_path: Path) -> Path:
    render_dir = tmp_path / "rendered"
    render_dir.mkdir()
    wav_path = render_dir / "looming_pink_frontal.wav"
    sf.write(wav_path, np.zeros((441, 3), dtype=np.float32), 44100)
    (render_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "schema": "pps-render-manifest.v1",
                "status": "rendered_reference",
                "render_engine": "python-sofa-reference",
                "wav_outputs": [{"path": str(wav_path), "sha256": "test"}],
            }
        ),
        encoding="utf-8",
    )
    return render_dir


def _client(tmp_path: Path) -> TestClient:
    design_path = tmp_path / "design.json"
    save_design(_compact_design(), design_path)
    controller = DashboardController(
        design_path=design_path,
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "dashboard_projects" / "0_study_project_registry",
    )
    return TestClient(create_app(controller))


def _wait_job(client: TestClient, job_id: str) -> dict:
    for _ in range(1000):
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] in {"succeeded", "failed"}:
            return data
        time.sleep(0.05)
    raise AssertionError(f"Job did not finish: {job_id}")


def _read_json_file(path: str | Path) -> dict:
    return json.loads(dashboard_app._read_text_file(path, encoding="utf-8"))


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    with open(dashboard_app._filesystem_path(path), newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _register_segment1_wav(
    client: TestClient,
    design: dict,
    label: str,
    samples: np.ndarray,
    *,
    sample_rate: int = 44100,
    motion_mode: str = "looming",
    source_kind: str = "test_audio",
) -> Path:
    state = client.post("/api/design", json={"design": design}).json()
    context = dashboard_app._project_context_from_design(
        design_from_dict(state["design"]),
        Path(state["project"]["registry_root"]),
    )
    assert context is not None
    temp_path = context.segment1_dir / f"_test_{dashboard_app._slug(label)}.wav"
    sf.write(dashboard_app._soundfile_path(temp_path), samples, sample_rate)
    path = dashboard_app._materialize_ingredient_audio_file(temp_path, context.segment1_dir, label, motion_mode=motion_mode)
    dashboard_app._record_ingredient_file(
        context,
        path,
        label=label,
        source_kind=source_kind,
        trajectory_snapshot={},
        motion_mode=motion_mode,
        provenance={"test_fixture": True},
    )
    return path


def _assert_xyz(actual: dict, expected: dict, *, abs: float = 1e-9) -> None:
    assert actual["x_m"] == pytest.approx(expected["x_m"], abs=abs)
    assert actual["y_m"] == pytest.approx(expected["y_m"], abs=abs)
    assert actual["z_m"] == pytest.approx(expected["z_m"], abs=abs)


def _assert_dashboard_path_exists(root: Path, value: str) -> None:
    path = Path(value)
    target = path if path.is_absolute() else root / path
    assert dashboard_app._path_exists(target)


def test_custom_profile_id_timestamp_collision_never_overwrites(tmp_path: Path):
    registry = tmp_path / "registry"
    registry.mkdir()
    created_at = dashboard_app.datetime(2026, 6, 17, 17, 42, 30)

    first = profile_memory.generate_custom_profile_id("My Lab Pilot", registry, created_at=created_at)
    assert first == "custom_my_lab_pilot_20260617_174230"
    (registry / first).mkdir()
    second = profile_memory.generate_custom_profile_id("My Lab Pilot", registry, created_at=created_at)
    assert second == "custom_my_lab_pilot_20260617_174230_2"
    (registry / second).mkdir()
    third = profile_memory.generate_custom_profile_id("My Lab Pilot", registry, created_at=created_at)
    assert third == "custom_my_lab_pilot_20260617_174230_3"


def test_dashboard_static_assets_are_packaged():
    dashboard_files = files("peripersonal_space_toolkit.dashboard")
    viewer_files = files("peripersonal_space_toolkit.viewer")
    assert dashboard_files.joinpath("index.html").is_file()
    assert dashboard_files.joinpath("styles.css").is_file()
    assert dashboard_files.joinpath("app.js").is_file()
    assert dashboard_files.joinpath("hardware_pixel_art.js").is_file()
    assert viewer_files.joinpath("trajectory-viewer.js").is_file()

    html = dashboard_files.joinpath("index.html").read_text(encoding="utf-8")
    app_js = dashboard_files.joinpath("app.js").read_text(encoding="utf-8")
    hardware_pixel_js = dashboard_files.joinpath("hardware_pixel_art.js").read_text(encoding="utf-8")
    styles_css = dashboard_files.joinpath("styles.css").read_text(encoding="utf-8")
    viewer_js = viewer_files.joinpath("trajectory-viewer.js").read_text(encoding="utf-8")
    public_root = Path(__file__).resolve().parents[1]
    public_index = (public_root / "index.html").read_text(encoding="utf-8")
    public_docs = (public_root / "documentation" / "index.html").read_text(encoding="utf-8")
    public_download = (public_root / "download" / "index.html").read_text(encoding="utf-8")
    static_version = "20260620-static-preview-parity"
    assert f'href="styles.css?v={static_version}"' in html
    assert f'src="hardware_pixel_art.js?v={static_version}"' in html
    assert f'src="app.js?v={static_version}"' in html
    assert f"index.html?page=toolkit&v={static_version}" in public_index
    assert f"index.html?page=documentation&v={static_version}" in public_docs
    assert f"index.html?page=downloads&v={static_version}" in public_download
    assert "STUDY5_PINK_WHITE_TEMPLATE_ID" in app_js
    assert "Bundled study protocols" in app_js
    assert "PPS Toolkit Study 5 pink/white protocol variant" in app_js
    assert 'data-page-tab="toolkit"' in html
    assert 'data-page-tab="documentation"' in html
    assert 'data-page-tab="downloads"' in html
    assert 'class="site-tab-brand"' not in html
    assert "Researcher Workspace" not in html
    assert 'id="documentation-page"' in html
    assert html.count('class="doc-segment-rule"') == 8
    assert 'id="downloads-page"' in html
    assert 'id="toolkit-page"' in html
    assert f'src="../viewer/index.html?v={static_version}"' in html
    assert "PAGE_ROUTE_SEGMENTS" in app_js
    assert 'documentation: "documentation"' in app_js
    assert 'downloads: "download"' in app_js
    assert "pageFromLocation" in app_js
    assert "replaceRouteForPage" in app_js
    assert "enforceExternalLinkTargets" in app_js
    assert 'id="download-software" class="button-link primary-link" href="https://github.com/GeorgeFejer91/pps-kit/releases" target="_blank" rel="noopener noreferrer"' in html
    assert "renderHardwarePixelArt" in app_js
    assert 'data-hardware-pixel="komplete-audio6"' in html
    assert 'data-hardware-pixel="woojer-strap-4"' in html
    assert 'class="arch-hw-layout"' in html
    assert ".arch-hw-outputs" in styles_css
    assert "window.HARDWARE_PIXEL_ART" in hardware_pixel_js
    assert '"komplete-audio6"' in hardware_pixel_js
    assert '"woojer-strap-4"' in hardware_pixel_js
    assert ".hardware-pixel-frame" in styles_css
    assert "width: min(100%, 240px)" in styles_css
    assert "#documentation-page .info-segment" in styles_css
    assert ".doc-segment-rule" in styles_css
    assert "linear-gradient(90deg" in styles_css
    assert 'id="audio-file-input"' in html
    assert 'id="zoom-in-camera"' in html
    assert 'id="zoom-out-camera"' in html
    assert 'id="fit-radius-camera"' in html
    assert 'id="preload-asset-status"' in html
    assert 'id="profile-recreation-notice"' in html
    assert "Study/profile" in html
    assert "Save as New Study Profile" in html
    assert "Prepare Output Folder for Data Collection" in html
    assert "/api/profiles/save-prepared" in app_js
    assert "/api/run-sequence/export-bridge" in app_js
    assert 'id="edit-profile-rail"' in html
    assert "Edit As New Study" in html
    assert 'id="customize-modal"' in html
    assert 'id="existing-custom-project"' in html
    assert 'id="load-custom-project"' in html
    assert "Name This Study" in html
    assert 'id="segment-info-modal"' in html
    assert 'id="segment-info-modal-title"' in html
    assert 'id="segment-info-modal-close"' in html
    assert html.count('data-segment-info="') == 7
    assert "SEGMENT_INFO" in app_js
    assert "setActivePage" in app_js
    assert "info-page-active" in app_js
    assert "openSegmentInfoModal" in app_js
    assert "closeSegmentInfoModal" in app_js
    assert "Purpose" in html
    assert "Your Inputs" in html
    assert "Backend Work" in html
    assert "Used Next" in html
    for title in [
        "Choose or Create Study",
        "Build Looming Stimuli",
        "Trial Sequence Design",
        "Baseline and Tactile Trial Design",
        "Trial Repetition Pool",
        "Generate and Review Blocks",
        "Prepare Experiment",
    ]:
        assert title in html
    for slugged_title in [
        "0_profile Study Project Registry",
        "1_core_audio_ingredients Looming Stimuli Builder",
        "2_trial_sequence_designs Trial Sequence Design",
        "3_tactile_and_baseline_trials Baseline and Tactile Trial Design",
        "4_trial_repetition_pool Trial Repetition Pool",
    ]:
        assert slugged_title not in html
    assert "/api/project/customize" in app_js
    assert "/api/projects/${encodeURIComponent(projectId)}/load" in app_js
    assert "profile-readonly-mode" in app_js
    assert "collectProfileRunPayload" in app_js
    assert 'control.id === "prepare-experiment"' in app_js
    assert ".panel.profile-readonly #prepare-experiment" in styles_css
    assert ".modal-backdrop[hidden]" in styles_css
    assert ".panel.user-sized" in styles_css
    assert "min-height: var(--panel-user-height);" in styles_css
    assert "height: auto;" in styles_css
    assert "flex-wrap: wrap;" in styles_css
    assert ".filmstrip-sequence" in styles_css
    assert "overflow-x: auto;" not in styles_css
    assert "max-height: 420px;" not in styles_css
    assert "window.prompt" not in app_js
    assert "Published preload" not in html
    assert "not the exact stimulus set used in the original study" in app_js
    assert 'id="import-audio-spatialize"' in html
    assert 'id="import-audio-preserve"' in html
    assert 'id="import-audio-prestimulus"' not in html
    assert 'id="generated-noise-select"' in html
    assert 'id="bake-stimulus"' in html
    assert "Bake Ingredient" in html
    assert 'id="bake-trial-sequences"' in html
    assert "Bake Trial Sequences" in html
    assert 'id="open-profile-folder"' in html
    assert 'id="export-data-acquisition-folder"' in html
    assert 'id="open-data-acquisition-folder"' in html
    assert "/api/data-acquisition/export" in app_js
    assert "renderDataAcquisitionBridge" in app_js
    assert 'id="open-ingredient-folder"' in html
    assert 'id="open-trial-sequence-folder"' in html
    assert 'id="segment0-output-summary"' not in html
    assert 'id="segment1-output-summary"' not in html
    assert 'id="segment2-output-summary"' not in html
    assert 'id="trial-file-output-summary"' not in html
    assert "segment-output-summary" not in html
    assert "status-list" not in html
    assert "status-row" not in app_js
    assert "status-list" not in styles_css
    assert "status-row" not in styles_css
    assert "renderSegmentOutput" not in app_js
    assert 'id="bake-status"' in html
    assert 'id="stimulus-feedback"' not in html
    assert 'id="stimulus-feedback-list"' not in html
    assert 'id="stimulus-render-status"' not in html
    assert 'id="noise-list"' in html
    assert 'id="audio-list"' in html
    assert 'id="snippet-list"' in html
    assert 'id="snippet-counts"' in html
    assert 'id="assembly-list"' not in html
    assert 'id="builder-add-noise"' not in html
    assert 'id="builder-add-audio"' not in html
    assert 'id="builder-noise-type"' not in html
    assert 'id="source-counts"' in html
    assert 'id="stimulus-pool"' in html
    assert 'data-panel-id="stimulus-pool"' in html
    assert "stimulus-pool-columns" in html
    assert html.index('id="stimulus"') < html.index('data-panel-id="trajectory-preview"')
    assert html.index('data-panel-id="trajectory-preview"') < html.index('id="stimulus-pool"')
    assert 'id="add-audio-spatialize"' not in html
    assert 'id="add-audio-preserve"' not in html
    assert "Stimulus Type Selection" in html
    assert "Build Looming Stimuli" in html
    assert "Trajectory And Source" in html
    assert "Backend Feedback" not in html
    assert "Trial Sequence Design" in html
    assert "Baseline and Tactile Trial Design" in html
    assert "Trial Repetition Pool" in html
    assert html.index("Trial Sequence Design") < html.index("Baseline and Tactile Trial Design")
    assert html.index("Baseline and Tactile Trial Design") < html.index("Trial Repetition Pool")
    assert "Segment 1" in html
    assert "Segment 2" in html
    assert "Segment 3" in html
    assert "Segment 4" in html
    assert "Segment 5" in html
    assert "Segment 6" in html
    assert "Segment 7" not in html
    assert "Decision stage" not in html
    assert "data-step-link=\"baseline\"" in html
    assert "data-step-link=\"schedule\"" in html
    assert html.index("Trial Sequence Design") < html.index("Baseline and Tactile Trial Design")
    assert html.index("Trial Repetition Pool") < html.index("Generate and Review Blocks")
    assert html.index('id="schedule"') < html.index('id="run"')
    assert "Single-Trial Sequence Assembly" not in html
    assert "Custom Clips" not in html
    assert "Trial Sequence Rows" not in html
    assert 'aria-label="Add trial sequence row"' in app_js
    assert "Pool Oversight" in html
    assert "Repetition Controls" in html
    assert 'id="baseline-enabled"' in html
    assert 'id="baseline-strategy"' in html
    assert 'id="baseline-options"' in html
    assert 'id="baseline-percent"' in html
    assert 'id="catch-percent"' in html
    assert 'id="include-catch-trials"' in html
    assert "Include Catch Trials (audio only)" in html
    assert "No baseline" in html
    assert "Minimum SOA anchor" in html
    assert "Maximum SOA anchor" in html
    assert "Full SOA tactile-only" in html
    assert "Custom timings" in html
    assert 'id="baseline-custom-audio-tactile"' in html
    assert 'id="bake-trial-files"' in html
    assert 'id="baseline-factor-tree"' in html
    assert 'id="trial-file-output-summary"' not in html
    assert 'type="checkbox" name="baseline-option"' in html
    assert "Use baseline trials" not in html
    assert "Baseline % per row" not in html
    assert "Default baseline %" not in html
    assert "Default catch %" not in html
    assert 'id="baseline-soa-values"' in html
    assert 'id="single-baseline-anchor"' not in html
    assert 'id="composition-tree"' in html
    assert 'id="row-mix-overrides"' in html
    assert "Bake Trial Pool CSV" in html
    assert "Regenerate Blocks" in html
    assert "Accept Blocks" in html
    assert "Edit Blocks" in app_js
    assert "Bake Block CSVs" not in html
    assert 'id="block-count"' in html
    assert 'id="block-build-progress-track"' in html
    assert 'id="block-csv-preview-list"' in html
    assert "block-preview-card" in styles_css
    assert "No block CSVs yet." in html
    assert 'id="trial-pool-folder-list"' in html
    assert 'class="composition-sliders"' in html
    assert 'id="trial-pool-duration-calculus"' in html
    assert "Duration Calculus" in app_js
    assert 'step="0.5"' in html
    assert "pool-subslider" in styles_css
    assert "trialPoolFractionalStratum" in app_js
    assert "Half-step repetitions use deterministic" in app_js
    assert "startBakeBlockCsvs" in app_js
    assert "renderBlockPreviewCard" in app_js
    assert "soa_color_hex" in app_js
    assert "Pool Preview" not in html
    assert 'id="trial-table"' not in html
    assert 'id="trial-pool-duration-summary"' not in html
    assert 'id="trial-pool-output-summary"' not in html
    assert "percent-mixer" not in html
    assert "count-strip" in html
    assert 'id="block-soa-values"' in html
    assert html.index('id="block-soa-values"') > html.index('id="baseline"')
    assert html.index('id="block-soa-values"') < html.index('id="block"')
    assert html.index('id="repetitions"') > html.index('id="block"')
    assert html.index('id="blocks"') > html.index('id="block"')
    assert html.index('id="protocol-summary"') > html.index('id="block"')
    assert "Prepare Experiment" in html
    assert "Experiment-Level Parameters" in html
    assert "Run Setup" not in html
    assert html.index('id="run"') > html.index('id="schedule"')
    assert html.index('id="participants"') > html.index('id="run"')
    assert "Planned participants" in html
    assert 'name="experiment-structure"' in html
    assert "1 part" in html
    assert "2 parts" in html
    assert "Block Permutation Preview" in html
    assert 'id="run-sequence-summary"' in html
    assert 'id="run-sequence-table"' in html
    assert "Regenerate Sequence" in html
    assert "Save Design and Start Experiment Runner" in html
    assert 'id="capture-lsl"' not in html
    assert 'id="capture-xdf"' not in html
    assert 'id="capture-analysis"' not in html
    assert 'id="capture-backup"' not in html
    assert 'id="enable-topup"' not in html
    assert "Preload Instruction Audio Clips" in html
    assert 'id="run-instruction-slots"' in html
    assert "RUN_INSTRUCTION_SLOTS" in app_js
    assert "/api/run-instructions/import" in app_js
    assert "required: false" in app_js
    assert ".run-instruction-slot" in styles_css
    assert ".status-label.optional" in styles_css
    assert "capture_options" not in app_js
    assert '["capture-lsl", "capture-xdf", "capture-analysis", "capture-backup", "enable-topup"]' not in app_js
    assert "Prepare Experiment + Open Runner" not in html
    assert "Open Experiment Runner" in app_js
    assert "Save Design and Start Experiment Runner" in app_js
    assert "Profile run prepared; local runner opened" in app_js
    assert "/api/run-sequence/open-runner" in app_js
    assert ".block-csv-decision-actions" in styles_css
    assert ".run-sequence-actions" in styles_css
    assert 'id="participant-id"' not in html
    assert 'id="render-action"' not in html
    assert 'id="prepare-action"' not in html
    assert 'id="stress-action"' not in html
    assert 'id="focus-action"' not in html
    assert 'id="order-table"' not in html
    assert 'data-step-link="review"' not in html
    assert 'id="review"' not in html
    assert 'id="refresh-jobs"' not in html
    assert 'id="session-summary"' not in html
    assert "renderReview" not in app_js
    assert 'scrollToStep("review")' not in app_js
    assert "startRender" not in app_js
    assert "prepareSession" not in app_js
    assert "stressAudio" not in app_js
    assert "startFocus" not in app_js
    assert "Custom Stimulus Builder" not in html
    assert "Bake Ingredient" in html
    assert "Bake Stimulus" not in html
    assert "Filmstrip Trial Assembly" not in html
    assert "Add Trial Type" not in html
    assert "Choose noise type to bake" in html
    assert "Add generated noise..." not in html
    assert "Generate Looming Noise" in html
    assert "Custom Looming Tone" in html
    assert "Custom Audio Clip" in html
    assert "grid-auto-rows: 1fr" in styles_css
    assert "Dry Custom Tone" not in html
    assert "Already Looming / Control" not in html
    assert "Add Instruction Clip" not in html
    assert "Instruction Snippets" not in html
    assert "Instruction Snippet" not in app_js
    assert "/api/stimulus/bake" in app_js
    assert "/api/trials/preview-row" in app_js
    assert "/api/audio/preview-source" in app_js
    assert "data-preview-strip" in app_js
    assert "filmstrip-preview-button" in app_js
    assert "trial-row-empty" in app_js
    assert ".trial-row-add.trial-row-empty" in styles_css
    assert "data-add-strip-row" in app_js
    assert "data-add-box-label" in app_js
    assert "data-preview-source-label" in app_js
    assert "sequence-label-preview" in app_js
    assert "previewSourceLabel" in app_js
    assert "getSourcePreviewAudioContext" in app_js
    assert "decodeAudioData" in app_js
    assert "activeSourcePreviewClearTimer" in app_js
    assert "duration_s" in app_js
    assert 'control.matches?.("[data-preview-source-label]")' in app_js
    assert ".panel.profile-readonly [data-preview-source-label]" in styles_css
    assert "sequence-label-chip" in app_js
    assert "box-mode-toggle" in app_js
    assert "Audio box" in app_js
    assert "Fixed event" not in app_js
    assert "Randomizer event" not in app_js
    assert "Jitter / ITI event" in app_js
    assert "Jitter / ITI box" in app_js
    assert 'data-element-field="is_jitter"' in app_js
    assert "jitter_values_ms" in app_js
    assert "textarea" in app_js
    assert "One randomizer event per row" not in app_js
    assert "data-randomizer-soas" not in app_js
    assert "randomizer-count-row" not in app_js
    assert "randomizer-source-row" not in app_js
    assert "rowOrderText" not in app_js
    assert "plays first" not in app_js
    assert "plays after row" not in app_js
    assert "Randomizes across the selected stimulus sources" not in app_js
    assert "previewFilmstripRow" in app_js
    assert "Prelisten trial type" in app_js
    assert "Condition label" in app_js
    assert "audio_tactile_percentage" in app_js
    assert "catch_percentage" in app_js
    assert "baseline_percentage" in app_js
    assert "blockCompositionEstimate" in app_js
    assert "renderCompositionTree" in app_js
    assert "renderRowMixOverrides" in app_js
    assert "renderLiveTrialPreviewTables" in app_js
    assert "TRIAL_PREVIEW_LIMIT" in app_js
    assert "field.dataset.rowMixOverride" in app_js
    assert "min_max" in app_js
    assert "isCompanionDashboardOrigin" in app_js
    assert "http://127.0.0.1:8766" in app_js
    assert "STATIC_PRELOAD_INVENTORY_PATH" in app_js
    assert "study_templates/" in app_js
    assert "staticStateForTemplate" in app_js
    assert "DEFAULT_STUDY_TEMPLATE_ID = \"study5_box_breathing_pps\"" in app_js
    assert "Loaded Study 5 and committed preload assets from GitHub" in app_js
    assert "Start the local companion backend to create, bake, save, prepare, or open local experiment files." in app_js
    assert "Open Asset" in app_js
    assert "staticPreviewAssetForLabel" in app_js
    assert "Remove trial sequence row" in app_js
    assert "renderProtocolSummary" in app_js
    assert "Row label" not in app_js
    assert "BASELINE_STRATEGY_NOTES" in app_js
    assert "baselineCountEstimate" in app_js
    assert "updateBaselineDecision" in app_js
    assert "renderPreloadAssetStatus" in app_js
    assert "/api/local/open-folder" in app_js
    assert "data-open-folder" in app_js
    assert "Open Folder" in app_js
    assert "HTTP errors still mean the companion answered" in app_js
    assert "renderStimulusFeedback" not in app_js
    assert "callTrajectoryViewer" in app_js
    assert "fitTrajectoryRadius" in app_js
    assert "zoomTrajectoryCamera" in app_js
    assert "snapTrajectoryView" in app_js
    assert 'id="view-preset-control"' in html
    for preset in ("front", "back", "left", "right", "top", "iso"):
        assert f'data-view-preset="{preset}"' in html
    assert ".view-preset-control" in styles_css
    assert "startBakeStimulus" in app_js
    assert "stageGeneratedNoise" in app_js
    assert "IMPORTED_AUDIO_HANDLING" in app_js
    assert "PROCEDURAL_NOISE_TYPES" in app_js
    assert "STIMULUS_SNIPPET_PLACEMENTS" in app_js
    assert "STIMULUS_MOTION_MODES" not in app_js
    assert "noise-source-card" in app_js
    assert "audio-source-card" in app_js
    assert "stimulusTrajectoryHiddenFields" in app_js
    assert "sourceTrajectoriesFromDom" in app_js
    assert "source_trajectories" in app_js
    assert "stimulusTrajectoryTrace" in app_js
    assert "STIMULUS_TRAJECTORY_COLORS" in app_js
    assert "trajectoryColorSet" in app_js
    assert "trajectoryGradient" in app_js
    assert "trajectory_snapshot" in app_js
    assert "prebaked_path" in app_js
    assert "tone_type" in app_js
    assert "SOURCE_COLOR_OPTIONS" in app_js
    assert "sourceColorOptions" in app_js
    assert "applySourceCardColor" in app_js
    assert "Box color" in app_js
    assert "Attach to" not in app_js
    assert "Gap s" not in app_js
    assert "assembly-only" not in app_js
    assert "assembly-only" not in styles_css
    assert "Local path" not in app_js
    assert "--source-card-color" in styles_css
    assert "grid-template-columns: repeat(auto-fit" in styles_css
    assert ".stimulus-trajectory-trace" in styles_css
    assert ".stimulus-trajectory-line" in styles_css
    assert "--trajectory-gradient" in styles_css
    assert "assembly-list" not in app_js
    assert "dragstart" not in app_js
    assert "START_MARKER_COLOR" in viewer_js
    assert "END_MARKER_COLOR" in viewer_js
    assert "end_marker_color" in viewer_js
    assert "fit2DCameraToRadius" in viewer_js
    assert "TWO_D_RADIUS_PADDING" in viewer_js
    assert "controls.enabled = false" in viewer_js
    assert "activePan2D" in viewer_js
    assert "set2DViewCenter" in viewer_js
    assert "set2DVerticalSpan" in viewer_js
    assert "zoomTrajectoryCamera" in viewer_js
    assert "fitTrajectoryRadius" in viewer_js
    assert "two_d_radius_centered" in viewer_js
    assert "two_d_pan_enabled" in viewer_js
    assert "two_d_zoom_enabled" in viewer_js
    assert "three_d_pan_enabled" in viewer_js
    assert "three_d_roll_locked" in viewer_js
    assert "three_d_view_preset" in viewer_js
    assert "snapTrajectoryView" in viewer_js
    assert "VIEW_PRESETS" in viewer_js
    assert "fit3DCameraToRadius" in viewer_js
    assert "maxTargetRadius" in viewer_js
    assert "drawSourceTrajectoryInventory" in viewer_js
    assert "source_trajectory_count" in viewer_js
    assert "shared_tone_trajectory_group_count" in viewer_js
    assert "SOURCE_TRAJECTORY_OFFSET_M" in viewer_js
    assert "twoDFitVerticalSpanM" in viewer_js
    assert "radiusChanged" not in viewer_js
    assert "trajectory-viewer.js?v=" in viewer_files.joinpath("index.html").read_text(encoding="utf-8")
    assert "/api/" not in html


def test_dashboard_creates_profile_and_custom_project_folders(tmp_path: Path):
    client = _client(tmp_path)
    state = client.get("/api/state").json()
    project = state["project"]
    assert project["project_id"].startswith("profile_")
    assert state["custom_projects"] == []
    assert Path(project["profile_dir"]).joinpath("project_manifest.json").exists()
    assert Path(project["profile_dir"]).joinpath("active_design.json").exists()
    study_manifest_path = Path(project["profile_dir"]).joinpath("study_manifest.json")
    assert study_manifest_path.exists()
    study_manifest = json.loads(study_manifest_path.read_text(encoding="utf-8"))
    assert study_manifest["schema"] == "pps-dashboard-study-settings-manifest.v1"
    assert study_manifest["gui_settings_inventory"]["baseline_strategy"]["segment"] == "3_tactile_and_baseline_trials"
    assert study_manifest["default_settings"]["baseline_generation"]["strategy"] == "tactile_only"
    segments = state["project_segments"]
    assert segments["0_profile"]["status"] == "ready"
    assert Path(segments["0_profile"]["study_manifest_path"]).name == "study_manifest.json"
    assert segments["1_core_audio_ingredients"]["folder_name"] == "1_core_audio_ingredients"
    assert segments["2_trial_sequence_designs"]["folder_name"] == "2_trial_sequence_designs"
    assert segments["3_tactile_and_baseline_trials"]["folder_name"] == "3_tactile_and_baseline_trials"

    profile_project_dir = Path(project["project_dir"])
    forked = client.post("/api/project/customize", json={"name": "Study 5 editable fork"}).json()
    fork_project = forked["project"]
    fork_dir = Path(fork_project["project_dir"])
    assert fork_project["project_id"].startswith("custom_study_5_editable_fork_")
    assert fork_project["project_kind"] == "custom"
    assert fork_project["source_template_id"] == state["selected_template"]
    assert fork_dir != profile_project_dir
    assert forked["selected_template"] == ""
    assert forked["custom_workflow"]["is_custom"] is True
    fork_steps = {step["id"]: step for step in forked["custom_workflow"]["steps"]}
    assert fork_steps["stimulus"]["complete"] is True
    assert fork_steps["trials"]["complete"] is False
    assert "Bake Segment 2 trial sequences." in fork_steps["trials"]["missing"]
    assert forked["custom_workflow"]["current_step"] == "trials"
    assert forked["project_segments"]["1_core_audio_ingredients"]["status"] == "ready"
    for noise in forked["design"]["noises"]:
        assert str(fork_dir / "1_core_audio_ingredients") in noise["prebaked_path"]
        assert str(profile_project_dir) not in noise["prebaked_path"]
    for clip in forked["design"]["prestimulus_files"]:
        assert str(fork_dir / "1_core_audio_ingredients") in clip["path"]
        assert str(profile_project_dir) not in clip["path"]
    saved_projects = client.get("/api/state").json()["custom_projects"]
    assert [item["project_id"] for item in saved_projects] == [fork_project["project_id"]]
    reopened = client.post(f"/api/projects/{fork_project['project_id']}/load").json()
    assert reopened["project"]["project_id"] == fork_project["project_id"]
    assert reopened["project"]["project_kind"] == "custom"
    assert reopened["custom_workflow"]["is_custom"] is True
    assert reopened["project_segments"]["1_core_audio_ingredients"]["status"] == "ready"

    custom = client.post("/api/templates/__custom__/load").json()
    custom["design"]["name"] = "My Lab Pilot"
    updated = client.post("/api/design", json={"design": custom["design"], "participant_id": ""}).json()
    custom_project = updated["project"]
    assert custom_project["project_id"].startswith("custom_my_lab_pilot_")
    project_dir = Path(custom_project["project_dir"])
    assert project_dir.parts[-2] == "0_study_project_registry"
    assert (project_dir / "0_profile" / "project_manifest.json").exists()
    assert (project_dir / "0_profile" / "study_manifest.json").exists()
    assert (project_dir / "1_core_audio_ingredients").is_dir()
    assert (project_dir / "2_trial_sequence_designs").is_dir()
    assert (project_dir / "3_tactile_and_baseline_trials").is_dir()
    assert (project_dir / "4_trial_repetition_pool").is_dir()
    assert (project_dir / "5_block_csv_preview").is_dir()


def test_dashboard_exports_data_acquisition_folder_bridge(tmp_path: Path):
    client = _client(tmp_path)
    parent = tmp_path / "operator_selected_output"

    response = client.post("/api/data-acquisition/export", json={"selected_folder": str(parent)})

    assert response.status_code == 200
    state = response.json()
    result = state["data_acquisition_export_result"]
    acquisition_root = Path(result["data_acquisition_root"])
    diary_path = Path(result["diary_path"])
    bridge_manifest_path = Path(result["bridge_manifest_path"])
    design_export_dir = Path(result["dashboard_project_export_dir"])
    design_snapshot_path = Path(result["dashboard_design_snapshot_path"])
    runner_settings_path = Path(result["runner_settings_path"])
    assert acquisition_root.parent == parent
    assert acquisition_root.is_dir()
    assert dashboard_app._path_exists(diary_path)
    assert diary_path.name.endswith("_LOG-DIARY_DO_NOT_DELETE.txt")
    assert diary_path.parent == output_runner_logs_dir(acquisition_root)
    assert dashboard_app._path_exists(bridge_manifest_path)
    assert bridge_manifest_path.parent == output_project_state_dir(acquisition_root)
    assert design_export_dir.is_dir()
    assert design_export_dir.parent == output_profile_snapshot_dir(acquisition_root) / "dashboard_design_export"
    assert dashboard_app._path_exists(design_export_dir / "0_profile" / "project_manifest.json")
    assert dashboard_app._path_exists(design_export_dir / "0_profile" / "active_design.json")
    assert dashboard_app._path_exists(design_snapshot_path)
    bridge_manifest = dashboard_app._load_json(bridge_manifest_path)
    assert bridge_manifest["schema"] == "pps-dashboard-runner-bridge.v1"
    assert bridge_manifest["data_acquisition_root"] == str(acquisition_root)
    assert bridge_manifest["diary_path"] == str(diary_path)
    settings = json.loads(runner_settings_path.read_text(encoding="utf-8"))
    assert settings["schema"] == "pps-focus-runner-settings.v1"
    assert settings["current_output_project_root"] == str(acquisition_root)
    assert settings["session_root"] == str(acquisition_root)
    assert str(settings["diary_path"]).replace("\\\\?\\", "") == str(diary_path)
    assert state["data_acquisition"]["active"] is True
    assert state["data_acquisition"]["root"] == str(acquisition_root)
    entries = read_diary_entries(diary_path)
    assert [entry["event_type"] for entry in entries] == [
        "output_project_created",
        "dashboard_data_acquisition_folder_exported",
    ]


def test_dashboard_rejects_profile_mutation_and_blank_custom_names(tmp_path: Path):
    client = _client(tmp_path)
    state = client.get("/api/state").json()
    original_name = state["design"]["name"]

    blank = client.post("/api/project/customize", json={"name": "   "})
    assert blank.status_code == 400
    assert "Enter a study name" in blank.json()["detail"]

    mutated_design = dict(state["design"])
    mutated_design["name"] = "Direct API Profile Mutation"
    blocked = client.post("/api/design", json={"design": mutated_design})
    assert blocked.status_code == 400
    assert "read-only" in blocked.json()["detail"]
    unchanged = client.get("/api/state").json()
    assert unchanged["design"]["name"] == original_name
    assert unchanged["custom_workflow"]["is_custom"] is False

    assert client.post("/api/projects/..%2Foutside/load").status_code in {400, 404}
    assert client.post("/api/projects/profile_study5_box_breathing_pps/load").status_code == 404


def test_dashboard_payload_uses_normalized_trajectory_controls_for_render_and_bake():
    app_js = files("peripersonal_space_toolkit.dashboard").joinpath("app.js").read_text(encoding="utf-8")

    assert "const trajectoryControls = currentTrajectoryControls();" in app_js
    assert "trajectory_controls: trajectoryControls" in app_js
    assert ": [trajectoryControls.end_distance_cm]" in app_js
    assert 'body: JSON.stringify(collectPayload())' in app_js
    assert "payload.bake_recipe = recipe" in app_js
    assert 'movement_duration_s: clampNumber(numberValue("movement-duration", 3), 0.1, 30, 3)' in app_js
    assert 'start_hold_s: clampNumber(numberValue("start-hold", 0.5), 0, 30, 0.5)' in app_js
    assert 'end_hold_s: clampNumber(numberValue("end-hold", 0.5), 0, 30, 0.5)' in app_js


def test_dashboard_gui_to_3dti_config_handoff_stress_grid(tmp_path: Path):
    client = _client(tmp_path)
    control_cases = [
        {"start_distance_cm": 110, "end_distance_cm": 10, "start_rotation_deg": 0, "end_rotation_deg": 0, "movement_duration_s": 3.0, "start_hold_s": 0.5, "end_hold_s": 0.5},
        {"start_distance_cm": 90, "end_distance_cm": 20, "start_rotation_deg": 270, "end_rotation_deg": 0, "movement_duration_s": 1.2, "start_hold_s": 0.1, "end_hold_s": 0.2},
        {"start_distance_cm": 80, "end_distance_cm": 80, "start_rotation_deg": 270, "end_rotation_deg": 90, "movement_duration_s": 0.25, "start_hold_s": 0.0, "end_hold_s": 0.0},
        {"start_distance_cm": 250, "end_distance_cm": 25, "start_rotation_deg": 45, "end_rotation_deg": 315, "movement_duration_s": 4.5, "start_hold_s": 0.25, "end_hold_s": 0.75},
        {"start_distance_cm": 35, "end_distance_cm": 120, "start_rotation_deg": 180, "end_rotation_deg": 360, "movement_duration_s": 2.0, "start_hold_s": 0.05, "end_hold_s": 0.05},
        {"start_distance_cm": 999, "end_distance_cm": 1, "start_rotation_deg": 359.9, "end_rotation_deg": 180.1, "movement_duration_s": 30.0, "start_hold_s": 0.0, "end_hold_s": 0.1},
        {"start_distance_cm": 60, "end_distance_cm": 15, "start_rotation_deg": 135, "end_rotation_deg": 225, "movement_duration_s": 0.5, "start_hold_s": 0.2, "end_hold_s": 0.3},
        {"start_distance_cm": 10, "end_distance_cm": 110, "start_rotation_deg": 90, "end_rotation_deg": 270, "movement_duration_s": 6.0, "start_hold_s": 0.0, "end_hold_s": 0.0},
    ]
    noise_types = ["pink", "blue", "white", "brown", "violet", "pink", "blue", "white"]

    for index, controls in enumerate(control_cases, start=1):
        total_s = controls["start_hold_s"] + controls["movement_duration_s"] + controls["end_hold_s"]
        soas = sorted({max(0, int(round(total_s * fraction * 1000))) for fraction in (0.2, 0.5, 0.8)})
        spatial = [round(100.0 - index * 3.0 - offset, 3) for offset in range(len(soas))]
        design = _compact_design()
        design.name = f"GUI stress handoff {index}"
        design.noises[0].label = f"Stress source {index}"
        design.noises[0].noise_type = noise_types[index - 1]
        design.noises[0].gain = 0.25 + index * 0.1
        design.protocol.soa_values_ms = soas
        design.protocol.spatial_values_cm = spatial
        design.protocol.random_seed = 9000 + index
        payload = {
            "participant_id": f"P{index:03d}",
            "design": design_to_dict(design),
            "trajectory_controls": controls,
        }

        state = client.post("/api/design", json=payload).json()
        loaded = design_from_dict(state["design"])
        saved = load_design(tmp_path / "design.json")
        config = build_render_config(loaded, seed=loaded.protocol.random_seed, output_dir=tmp_path / f"case_{index}", samples_per_second=100.0)
        expected_start = point_from_distance_rotation_height(
            controls["start_distance_cm"], controls["start_rotation_deg"], 0.0
        )
        expected_end = point_from_distance_rotation_height(
            controls["end_distance_cm"], controls["end_rotation_deg"], 0.0
        )
        expected_path_length = math.dist(
            (expected_start["x_m"], expected_start["y_m"], expected_start["z_m"]),
            (expected_end["x_m"], expected_end["y_m"], expected_end["z_m"]),
        )

        assert state["participant_id"] == f"P{index:03d}"
        assert state["validation"] == []
        assert design_to_dict(saved) == state["design"]
        _assert_xyz(state["viewer_payload"]["start"], expected_start)
        _assert_xyz(state["viewer_payload"]["end"], expected_end)
        assert loaded.trajectory.path_length_m == pytest.approx(expected_path_length)
        assert loaded.trajectory.movement_duration_s == pytest.approx(controls["movement_duration_s"])
        assert loaded.trajectory.padding_pre_s == pytest.approx(controls["start_hold_s"])
        assert loaded.trajectory.padding_post_s == pytest.approx(controls["end_hold_s"])
        assert loaded.trajectory.propagation_speed_mps == pytest.approx(expected_path_length / controls["movement_duration_s"])
        assert config["design"] == state["design"]
        assert config["source"]["seed"] == loaded.protocol.random_seed
        assert config["source"]["noises"] == [
                {
                    "label": f"Stress source {index}",
                    "noise_type": noise_types[index - 1],
                    "tone_type": noise_types[index - 1],
                    "gain": pytest.approx(0.25 + index * 0.1),
                }
            ]
        assert config["protocol"]["soa_values_ms"] == soas
        assert config["protocol"]["spatial_values_cm"] == spatial
        assert config["trajectory"]["start_hold_s"] == pytest.approx(controls["start_hold_s"])
        assert config["trajectory"]["movement_duration_s"] == pytest.approx(controls["movement_duration_s"])
        assert config["trajectory"]["end_hold_s"] == pytest.approx(controls["end_hold_s"])
        _assert_xyz(config["trajectory"]["samples"][0], expected_start)
        _assert_xyz(config["trajectory"]["samples"][-1], expected_end)

        mapped_start = app_to_3dti_coordinates(expected_start["x_m"], expected_start["y_m"], expected_start["z_m"])
        assert mapped_start["x_m"] == pytest.approx(expected_start["y_m"])
        assert mapped_start["y_m"] == pytest.approx(-expected_start["x_m"])
        assert mapped_start["z_m"] == pytest.approx(expected_start["z_m"])
        assert len(config["tactile"]["events"]) == len(soas)
        for event, soa_ms, spatial_cm in zip(config["tactile"]["events"], soas, spatial):
            expected_at_tactile = trajectory_point_at_time(loaded.trajectory, soa_ms / 1000.0)
            assert event["soa_ms"] == soa_ms
            assert event["tactile_onset_s"] == pytest.approx(soa_ms / 1000.0)
            assert event["planned_spatial_value_cm"] == pytest.approx(spatial_cm)
            assert event["source_x_at_tactile_m"] == pytest.approx(expected_at_tactile["x_m"])
            assert event["source_y_at_tactile_m"] == pytest.approx(expected_at_tactile["y_m"])
            assert event["source_z_at_tactile_m"] == pytest.approx(expected_at_tactile["z_m"])


def test_dashboard_pages_companion_contract(tmp_path: Path):
    client = _client(tmp_path)

    root = client.get("/", follow_redirects=False)
    assert root.status_code in {302, 307}
    assert root.headers["location"] == "/dashboard/index.html"

    for origin in ("https://georgefejer91.github.io", "https://ppskit.qzz.io"):
        health = client.get("/api/health", headers={"Origin": origin})
        assert health.status_code == 200
        assert health.json()["service"] == "pps-dashboard-companion"
        assert health.json()["security"]["mutation_token_required"] is False
        assert health.headers["access-control-allow-origin"] == origin

    preloads = client.get("/api/preloads").json()
    assert preloads["schema"] == "pps-preload-asset-inventory.v1"
    assert preloads["segments"][0]["folder"] == "01_profile"
    assert len(preloads["profiles"]) >= 21
    assert all(item["status"] == "ready" for item in preloads["profiles"])
    assert all(item["catalog_segments"] for item in preloads["profiles"])
    study5 = next(item for item in preloads["profiles"] if item["template_id"] == "study5_box_breathing_pps")
    assert study5["status"] == "ready"
    assert study5["asset_mode"] == "bundled_local"
    assert study5["catalog_segments"][1]["folder"] == "02_looming_stimuli"
    assert study5["profile_parameters_manifest"].endswith("01_profile/profile_parameters_manifest.json")
    assert study5["runner_readiness"] == "ready"
    assert study5["profile_checks_passed"] is True
    assert study5["segment_0_to_4_profile_checks_passed"] is True
    assert study5["finished_profile"] is True
    assert study5["segment_6_launchable"] is True
    assert study5["profile_completion_status"] == "finished_segment_6_launchable"
    assert study5["primary_recreation_category"] == "gui_recreatable"
    assert study5["missing_parameter_count"] == 0
    assert study5["unsupported_structure_count"] == 0

    partial = next(item for item in preloads["profiles"] if item["template_id"] == "canzoneri_2012_dynamic_sounds")
    assert partial["runner_readiness"] == "blocked_unsupported_toolkit_structure"
    assert partial["profile_checks_passed"] is False
    assert partial["segment_0_to_4_profile_checks_passed"] is False
    assert partial["finished_profile"] is False
    assert partial["segment_6_launchable"] is False
    assert partial["profile_completion_status"] == "unfinished_preload"
    assert partial["missing_parameter_count"] > 0
    assert partial["unsupported_structure_count"] > 0

    synced = client.post("/api/preloads/study5_box_breathing_pps/sync").json()
    assert synced["status"] == "ready"
    assert synced["ready_asset_count"] == 4


def test_dashboard_companion_token_can_gate_mutating_routes(tmp_path: Path):
    design_path = tmp_path / "design.json"
    save_design(_compact_design(), design_path)
    controller = DashboardController(
        design_path=design_path,
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "dashboard_projects" / "0_study_project_registry",
    )
    client = TestClient(
        create_app(
            controller,
            web_origins=[],
            companion_token="test-token",
            require_mutation_token=True,
        )
    )

    health = client.get("/api/health").json()
    assert health["security"]["mutation_token_required"] is True
    assert health["security"]["token_header"] == "X-PPS-Companion-Token"

    missing = client.post("/api/design", json={})
    assert missing.status_code == 403
    assert missing.json()["reason"] == "missing_token"

    stale = client.post("/api/design", json={}, headers={"X-PPS-Companion-Token": "old-token"})
    assert stale.status_code == 403
    assert stale.json()["reason"] == "stale_or_invalid_token"

    accepted = client.post("/api/design", json={}, headers={"X-PPS-Companion-Token": "test-token"})
    assert accepted.status_code == 200
    security = client.get("/api/health").json()["security"]
    assert security["accepted_mutating_requests"] == 1
    assert security["rejected_mutating_requests"] == 2


def test_dashboard_static_assets_include_companion_token_header_control():
    dashboard_dir = files("peripersonal_space_toolkit.dashboard")
    html = (dashboard_dir / "index.html").read_text(encoding="utf-8")
    app_js = (dashboard_dir / "app.js").read_text(encoding="utf-8")

    assert 'id="companion-token"' in html
    assert "X-PPS-Companion-Token" in app_js
    assert "ppsDashboard.companionToken" in app_js


def test_dashboard_loads_unpublished_study5_preload_with_instruction_events(tmp_path: Path):
    client = _client(tmp_path)

    loaded = client.post("/api/templates/study5_box_breathing_pps/load").json()
    design = loaded["design"]

    assert loaded["selected_template"] == "study5_box_breathing_pps"
    assert design["study_profile_title"] == "Study 5 PPS box-breathing profile"
    assert design["study_profile_reference_parameters"]["publication_status"] == "unpublished_lab_profile"
    assert design["study_profile_reference_parameters"]["looming_assets_bundled"] is True
    assert design["study_profile_reference_parameters"]["custom_clips_preloaded"] is True
    assert loaded["custom_workflow"]["is_custom"] is False
    instruction_labels = [clip["label"] for clip in design["prestimulus_files"]]
    assert instruction_labels[:2] == ["Inhale instruction", "Exhale instruction"]
    assert len(instruction_labels) == 2
    assert all(clip["target_duration_s"] == 4.0 for clip in design["prestimulus_files"])
    assert all("/1_core_audio_ingredients/" in clip["path"].replace("\\", "/") for clip in design["prestimulus_files"])
    assert design["study_profile_reference_parameters"]["default_instruction_asset_variant"] == "original_study5"
    assert set(design["study_profile_reference_parameters"]["instruction_asset_variants"]) == {
        "british_kokoro",
        "original_study5",
    }
    custom_clip_assets = design["study_profile_reference_parameters"]["custom_clip_assets"]
    assert [clip["label"] for clip in custom_clip_assets[:2]] == ["Inhale instruction", "Exhale instruction"]
    assert [clip["variant"] for clip in custom_clip_assets[:2]] == ["original_study5", "original_study5"]
    assert all("assets/breathing/original_study5/" in clip["path"].replace("\\", "/") for clip in custom_clip_assets[:2])
    assert all(clip["duration_s"] == 4.0 for clip in custom_clip_assets)
    run_setup = design["study_profile_reference_parameters"]["dashboard_run_setup"]
    assert run_setup["experiment_structure"] == "pre_post"
    assert run_setup["seed"] == 20256604
    run_instruction_slots = {slot["slot"]: slot for slot in run_setup["instruction_profile"]["slots"]}
    assert set(run_instruction_slots) == {
        "before_experiment",
        "before_each_block",
        "after_each_block",
        "between_conditions",
        "after_experiment",
    }
    assert all(slot["enabled"] is True for slot in run_instruction_slots.values())
    assert all(slot["required"] is False for slot in run_instruction_slots.values())
    assert all("assets/breathing/original_study5/" in slot["path"].replace("\\", "/") for slot in run_instruction_slots.values())
    run_defaults = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "preloads"
            / "study5_box_breathing_pps"
            / "05_run_setup"
            / "run_defaults.json"
        ).read_text(encoding="utf-8")
    )
    assert run_defaults["instruction_profile"]["slots"] == run_setup["instruction_profile"]["slots"]
    assert len(design["prestimulus_files"]) == 2
    assert [asset["label"] for asset in design["noises"]] == [
        "Pink frontal",
        "Blue frontal",
        "White frontal",
        "Brown frontal",
    ]
    assert design["custom_looming_files"] == []
    assert all("/1_core_audio_ingredients/" in asset["prebaked_path"].replace("\\", "/") for asset in design["noises"])
    assert [asset["noise_type"] for asset in design["noises"]] == ["pink", "blue", "white", "brown"]
    assert len(loaded["viewer_payload"]["source_trajectories"]) == 4
    assert {item["tone_type"] for item in loaded["viewer_payload"]["source_trajectories"]} == {"pink", "blue", "white", "brown"}
    assert all("/1_core_audio_ingredients/" in item["local_path"].replace("\\", "/") for item in loaded["viewer_payload"]["source_trajectories"])
    assert loaded["preload_inventory"]["status"] == "ready"
    assert loaded["preflight"]["render_ready"] is True
    project = loaded["project"]
    segment1_dir = Path(project["segment_folders"]["1_core_audio_ingredients"])
    ingredient_manifest = json.loads((segment1_dir / "stimulus_ingredients_manifest.json").read_text(encoding="utf-8"))
    assert ingredient_manifest["ingredient_count"] == 6
    assert {item["label"] for item in ingredient_manifest["ingredients"]} == {
        "Pink frontal",
        "Blue frontal",
        "White frontal",
        "Brown frontal",
        "Inhale instruction",
        "Exhale instruction",
    }
    assert all(item["provenance"].get("read_only_catalog") is True for item in ingredient_manifest["ingredients"])
    assert loaded["project_segments"]["1_core_audio_ingredients"]["status"] == "ready"
    assert loaded["project_segments"]["1_core_audio_ingredients"]["wav_count"] == 6

    protocol = design["protocol"]
    assert protocol["include_catch_trials"] is True
    assert protocol["catch_trial_percentage"] == 0.0
    assert protocol["include_baseline_trials"] is True
    assert protocol["baseline_strategy"] == "tactile_only"
    assert protocol["baseline_custom_trial_mode"] == "tactile_only"
    assert protocol["baseline_soa_values_ms"] == []
    assert protocol["trial_pool_repetition_defaults"] == {
        "default": 3.0,
        "audio_tactile": 3.0,
        "baseline": 1.5,
        "catch": 3.0,
    }

    assert all(strip["catch_percentage"] == 0.0 for strip in protocol["trial_strips"])
    assert all(strip["audio_tactile_percentage"] == 100.0 for strip in protocol["trial_strips"])
    assert all(strip["baseline_percentage"] == 0.0 for strip in protocol["trial_strips"])
    study_manifest = json.loads((Path(project["profile_dir"]) / "study_manifest.json").read_text(encoding="utf-8"))
    assert study_manifest["study"]["profile_id"] == "study5_box_breathing_pps"
    assert study_manifest["study"]["profile_parameters_manifest"].endswith("01_profile/profile_parameters_manifest.json")
    assert study_manifest["study"]["runner_readiness"] == "ready"
    assert study_manifest["study"]["profile_checks_passed"] is True
    assert study_manifest["study"]["segment_0_to_4_profile_checks_passed"] is True
    assert study_manifest["study"]["finished_profile"] is True
    assert study_manifest["study"]["segment_6_launchable"] is True
    assert study_manifest["study"]["profile_completion_status"] == "finished_segment_6_launchable"
    assert study_manifest["study"]["primary_recreation_category"] == "gui_recreatable"
    assert study_manifest["study"]["missing_parameter_count"] == 0
    assert study_manifest["study"]["unsupported_structure_count"] == 0
    assert study_manifest["default_settings"]["baseline_generation"]["full_soa_uses_main_soa_values"] is True
    assert study_manifest["default_settings"]["baseline_generation"]["effective_soa_values_ms"] == [300, 800, 1500, 2200, 2700]
    assert study_manifest["default_settings"]["catch_generation"]["enabled"] is True
    assert study_manifest["default_settings"]["trial_pool_generation"]["family_repetitions"] == {
        "audio_tactile": 3,
        "baseline": 1.5,
        "catch": 3,
    }
    assert study_manifest["gui_settings_inventory"]["include_catch_trials"]["value"] is True
    assert study_manifest["gui_settings_inventory"]["baseline_strategy"]["value"] == "tactile_only"
    assert study_manifest["gui_settings_inventory"]["trial_pool_family_repetitions"]["value"]["baseline"] == 1.5

    strips = design["protocol"]["trial_strips"]
    assert [strip["label"] for strip in strips] == ["Inhale trial type", "Exhale trial type"]
    assert [strip["elements"][0]["source_label"] for strip in strips] == ["Inhale instruction", "Exhale instruction"]
    assert all(strip["elements"][1]["randomized"] for strip in strips)
    assert all(strip["elements"][1]["source_labels"] for strip in strips)
    assert loaded["trial_preview"]
    assert loaded["trial_preview"][0]["trial_type"] in {"Inhale trial type", "Exhale trial type"}
    assert loaded["trial_preview"][0]["type"] in {"Audio-Tactile", "Catch", "Baseline"}
    assert any("Inhale instruction | " in row["sequence"] for row in loaded["trial_preview"])
    assert any("Exhale instruction | " in row["sequence"] for row in loaded["trial_preview"])


def test_dashboard_blocks_runner_launch_for_incomplete_published_profile(tmp_path: Path):
    client = _client(tmp_path)

    loaded = client.post("/api/templates/canzoneri_2012_dynamic_sounds/load").json()
    assert loaded["selected_template"] == "canzoneri_2012_dynamic_sounds"
    assert loaded["templates"]
    template = next(item for item in loaded["templates"] if item["template_id"] == "canzoneri_2012_dynamic_sounds")
    assert template["runner_readiness"] == "blocked_unsupported_toolkit_structure"
    assert template["profile_checks_passed"] is False

    blocked = client.post("/api/run-sequence/open-runner")
    assert blocked.status_code == 400
    detail = blocked.json()["detail"]
    assert "not a finished Segment 6 launchable profile yet" in detail
    assert "A finished profile must pass the Segment 0-4 recreation gate" in detail
    assert "profile_parameters_manifest.json" in detail

    mutated_design = dict(loaded["design"])
    mutated_design["name"] = "Runner payload should not rename profile"
    blocked_with_payload = client.post(
        "/api/run-sequence/open-runner",
        json={"participant_id": "P999", "design": mutated_design, "run_setup": {"experiment_structure": "pre_post"}},
    )
    assert blocked_with_payload.status_code == 400
    state = client.get("/api/state").json()
    assert state["participant_id"] == "P999"
    assert state["design"]["name"] == loaded["design"]["name"]
    assert state["design"]["study_profile_id"] == "canzoneri_2012_dynamic_sounds"


def test_dashboard_launches_every_finished_profile_from_segment6(tmp_path: Path, monkeypatch):
    design_path = tmp_path / "design.json"
    save_design(_compact_design(), design_path)
    controller = DashboardController(
        design_path=design_path,
        render_dir=_render_dir(tmp_path),
        session_root=tmp_path / "s",
        import_dir=tmp_path / "imports",
        preview_dir=tmp_path / "previews",
        project_registry_root=tmp_path / "r",
    )
    preloads = controller.preload_inventory_payload()
    finished_profiles = [
        item["template_id"]
        for item in preloads["profiles"]
        if item.get("finished_profile") and item.get("segment_6_launchable")
    ]
    assert "study5_box_breathing_pps" in finished_profiles
    assert finished_profiles

    original_validate_run_setup = dashboard_app._validate_run_setup_manifest

    def fake_profile_materialization(self, project, design):
        manifest_path = dashboard_app._run_setup_manifest_path(project.project_dir)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "schema": "test-profile-segment6-launchable.v1",
                    "experiment_structure": "single",
                    "participant_count": 1,
                    "profile_id": design.study_profile_id,
                }
            ),
            encoding="utf-8",
        )
        return {
            "status": "materialized",
            "profile_id": design.study_profile_id,
            "steps": [{"segment": "6_experiment_run_setup", "status": "ready", "manifest_path": str(manifest_path)}],
            "local_only": True,
        }

    def fake_validate_run_setup(manifest, *, project_dir, design):
        if isinstance(manifest, dict) and manifest.get("schema") == "test-profile-segment6-launchable.v1":
            return []
        return original_validate_run_setup(manifest, project_dir=project_dir, design=design)

    def fake_prepare_segment_run_package(run_setup_manifest_path, participant_id, *, design=None, session_root, created_at=None):
        session_dir = Path(session_root) / f"{participant_id}_run"
        session_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = session_dir / "session_manifest.json"
        design_path = session_dir / "design.json"
        protocol_path = session_dir / "protocol_schedule.csv"
        manifest_path.write_text("{}\n", encoding="utf-8")
        design_path.write_text("{}\n", encoding="utf-8")
        protocol_path.write_text("participant_id\nP001\n", encoding="utf-8")
        return dashboard_app.RunPackage(
            participant_id=participant_id,
            session_id=session_dir.name,
            created_at="2026-06-14T00:00:00",
            session_dir=session_dir,
            design_path=design_path,
            protocol_path=protocol_path,
            manifest_path=manifest_path,
            render_manifest_path=None,
            blocks=[],
            execution_mode="participant_block_wavs",
            source_run_setup_manifest_path=Path(run_setup_manifest_path),
        )

    runner_calls = []

    class FakeRunnerProcess:
        pid = 4186

    original_popen = dashboard_app.subprocess.Popen

    def fake_focus_popen(args, **kwargs):
        command = [str(item) for item in args] if isinstance(args, (list, tuple)) else [str(args)]
        if "--session-manifest" in command:
            runner_calls.append((args, kwargs))
            return FakeRunnerProcess()
        return original_popen(args, **kwargs)

    monkeypatch.setattr(DashboardController, "_ensure_profile_run_artifacts", fake_profile_materialization)
    monkeypatch.setattr(dashboard_app, "_validate_run_setup_manifest", fake_validate_run_setup)
    monkeypatch.setattr(dashboard_app, "prepare_segment_run_package", fake_prepare_segment_run_package)
    monkeypatch.setattr(
        dashboard_app.subprocess,
        "Popen",
        fake_focus_popen,
    )

    for profile_id in finished_profiles:
        loaded = controller.load_template(profile_id)
        template = next(item for item in loaded["templates"] if item["template_id"] == profile_id)
        assert template["finished_profile"] is True
        assert template["segment_6_launchable"] is True

        state = controller.open_experiment_runner({"participant_id": "P001"})
        launch_result = state["experiment_runner_launch_result"]
        assert launch_result["execution_mode"] == "participant_block_wavs"
        assert launch_result["runner"] == "PPSExperimentRunner.exe"
        assert Path(launch_result["run_setup_manifest"]).is_file()
        assert Path(launch_result["session_manifest"]).is_file()
        assert state["profile_run_materialization_result"]["profile_id"] == profile_id

    assert len(runner_calls) == len(finished_profiles)
    if os.name == "nt":
        assert all(int(kwargs.get("creationflags") or 0) & subprocess.CREATE_NO_WINDOW for _args, kwargs in runner_calls)


def test_dashboard_validates_full_study5_segment0_to_3_pipeline(tmp_path: Path):
    client = _client(tmp_path)
    loaded = client.post("/api/templates/study5_box_breathing_pps/load").json()

    assert loaded["project_segments"]["0_profile"]["status"] == "ready"
    assert loaded["project_segments"]["1_core_audio_ingredients"]["status"] == "ready"
    assert loaded["project_segments"]["1_core_audio_ingredients"]["wav_count"] == 6
    loaded = client.post("/api/project/customize", json={"name": "Study 5 segment pipeline custom"}).json()
    assert loaded["custom_workflow"]["is_custom"] is True
    assert loaded["project_segments"]["1_core_audio_ingredients"]["status"] == "ready"

    sequence_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": loaded["design"],
            "bake_recipe": {"kind": "trial_sequence_batch", "label": "2_trial_sequence_designs"},
        },
    ).json()
    sequence_done = _wait_job(client, sequence_job["job_id"])
    assert sequence_done["status"] == "succeeded"
    assert sequence_done["result"]["variant_count"] == 8
    sequence_manifest = _read_json_file(sequence_done["result"]["manifest_path"])
    assert sequence_manifest["schema"] == "pps-trial-sequence-variants.v1"
    assert len(sequence_manifest["rows"]) == 2
    for item in sequence_manifest["variants"]:
        sequence_audio, _sr = sf.read(dashboard_app._soundfile_path(item["file_path"]), dtype="float32", always_2d=True)
        assert sequence_audio.shape[1] == 2
    assert any(
        "inhale_instruction4000ms" in Path(item["file_path"]).name
        and "pink_frontal_looming4000ms" in Path(item["file_path"]).name
        and "total8000ms" in Path(item["file_path"]).name
        for item in sequence_manifest["variants"]
    )

    tactile_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": loaded["design"],
            "bake_recipe": {"kind": "audiotactile_trial_batch", "label": "3_tactile_and_baseline_trials"},
        },
    ).json()
    tactile_done = _wait_job(client, tactile_job["job_id"])
    assert tactile_done["status"] == "succeeded"
    assert tactile_done["result"]["audio_tactile_count"] == 40
    assert tactile_done["result"]["baseline_count"] == 40
    assert tactile_done["result"]["catch_count"] == 8

    state = client.get("/api/state").json()
    assert state["project_segments"]["2_trial_sequence_designs"]["status"] == "ready"
    assert state["project_segments"]["2_trial_sequence_designs"]["variant_count"] == 8
    assert state["project_segments"]["3_tactile_and_baseline_trials"]["status"] == "ready"
    assert state["project_segments"]["3_tactile_and_baseline_trials"]["audio_tactile_count"] == 40
    assert state["project_segments"]["3_tactile_and_baseline_trials"]["baseline_count"] == 40
    assert state["project_segments"]["3_tactile_and_baseline_trials"]["catch_count"] == 8
    assert state["project_segments"]["3_tactile_and_baseline_trials"]["total_count"] == 88
    segment3_root = Path(tactile_done["result"]["root"])
    expected_row_folders = {"row_01__inhale_trial_type", "row_02__exhale_trial_type"}
    assert {path.name for path in segment3_root.iterdir() if path.is_dir() and not path.name.startswith("_")} == expected_row_folders
    expected_leaf_folders = {"target_audio_tactile", "baseline", "catch_trials"}
    for row_folder in expected_row_folders:
        for leaf_folder in expected_leaf_folders:
            leaf_path = segment3_root / row_folder / leaf_folder
            for _attempt in range(30):
                if dashboard_app._path_exists(leaf_path):
                    break
                time.sleep(0.05)
            assert dashboard_app._path_exists(leaf_path)
    tactile_manifest = _read_json_file(tactile_done["result"]["manifest_path"])
    baseline_row = next(item for item in tactile_manifest["files"] if item["family"] == "baseline")
    catch_rows = [item for item in tactile_manifest["files"] if item["family"] == "catch"]
    catch_row = catch_rows[0]
    baseline_wav, baseline_sr = sf.read(dashboard_app._soundfile_path(baseline_row["file_path"]), dtype="float32", always_2d=True)
    catch_wav, catch_sr = sf.read(dashboard_app._soundfile_path(catch_row["file_path"]), dtype="float32", always_2d=True)
    assert baseline_sr == baseline_row["sample_rate_hz"]
    assert baseline_wav.shape[1] == 3
    assert baseline_row["baseline_mode"] == "tactile_only"
    assert baseline_row["channel_role_map"]["3"] == "tactile cue"
    assert np.max(np.abs(baseline_wav[:, :2])) == pytest.approx(0.0)
    assert np.max(np.abs(baseline_wav[:, 2])) > 0.01
    assert catch_sr == catch_row["sample_rate_hz"]
    assert catch_wav.shape[1] == 2
    assert catch_row["channels"] == catch_wav.shape[1]
    assert all(item["channels"] == 2 for item in catch_rows)
    assert catch_row["baseline_mode"] == "audio_only"
    assert catch_row["tactile_channel"] == ""
    assert "catch_trials" in catch_row["file_path"]
    report = _read_json_file(Path(state["project"]["profile_dir"]) / "segment_validation_report.json")
    assert report["schema"] == "pps-segment-validation-report.v1"
    assert report["expected"]["3_tactile_and_baseline_trials"]["audio_tactile_count"] == 40
    assert report["expected"]["3_tactile_and_baseline_trials"]["baseline_count"] == 40
    assert report["expected"]["3_tactile_and_baseline_trials"]["catch_count"] == 8
    assert report["observed"]["3_tactile_and_baseline_trials"]["total_count"] == 88

    default_pool_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": loaded["design"],
            "bake_recipe": {
                "kind": "trial_repetition_pool",
                "label": "4_trial_repetition_pool",
            },
        },
    ).json()
    default_pool_done = _wait_job(client, default_pool_job["job_id"])
    assert default_pool_done["status"] == "succeeded"
    assert default_pool_done["result"]["unique_file_count"] == 88
    assert default_pool_done["result"]["total_count"] == 204
    assert default_pool_done["result"]["audio_tactile_count"] == 120
    assert default_pool_done["result"]["baseline_count"] == 60
    assert default_pool_done["result"]["catch_count"] == 24
    default_pool_manifest = _read_json_file(default_pool_done["result"]["manifest_path"])
    assert default_pool_manifest["settings"]["family_repetitions"] == {
        "audio_tactile": 3,
        "baseline": 1.5,
        "catch": 3,
    }
    assert default_pool_manifest["balance_warnings"] == []
    default_rows = _read_csv_rows(default_pool_done["result"]["csv_path"])
    assert len(default_rows) == 204
    assert {"base_repetitions", "fractional_remainder", "fractional_extra", "balancing_signature", "source_lineage"} <= set(default_rows[0])
    baseline_rows = [row for row in default_rows if row["family"] == "baseline"]
    assert sum(int(row["fractional_extra"]) for row in baseline_rows) == 20
    by_row_soa: dict[tuple[str, str], int] = {}
    for row in baseline_rows:
        key = (row["row_label"], row["soa_ms"])
        by_row_soa[key] = by_row_soa.get(key, 0) + 1
    assert set(by_row_soa.values()) == {6}
    assert {row["row_label"] for row in baseline_rows} == {"Inhale trial type", "Exhale trial type"}
    lineage_extras: dict[tuple[str, str], int] = {}
    for row in baseline_rows:
        if int(row["fractional_extra"]):
            key = (row["row_label"], row["source_lineage"])
            lineage_extras[key] = lineage_extras.get(key, 0) + 1
    by_phase: dict[str, list[int]] = {}
    for (phase, _lineage), count in lineage_extras.items():
        by_phase.setdefault(phase, []).append(count)
    assert all(max(counts) - min(counts) <= 1 for counts in by_phase.values())

    default_block_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": loaded["design"],
            "bake_recipe": {
                "kind": "block_csv_preview",
                "label": "5_block_csv_preview",
            },
        },
    ).json()
    default_block_done = _wait_job(client, default_block_job["job_id"])
    assert default_block_done["status"] == "succeeded"
    assert default_block_done["result"]["block_count"] == 6
    assert default_block_done["result"]["csv_count"] == 6
    assert default_block_done["result"]["total_count"] == 204
    default_block_manifest = _read_json_file(default_block_done["result"]["manifest_path"])
    assert [block["trial_count"] for block in default_block_manifest["blocks"]] == [34, 34, 34, 34, 34, 34]
    assert default_block_manifest["row_sequence_strategy"] == "cycle_preserved_segment_row_order_within_each_block"
    assert [row["row_label"] for row in default_block_manifest["row_order"]] == ["Inhale trial type", "Exhale trial type"]
    assert default_block_manifest["soa_color_gradient"]["minimum_soa_ms"] == 300
    assert default_block_manifest["soa_color_gradient"]["maximum_soa_ms"] == 2700
    first_block_rows = _read_csv_rows(default_block_manifest["blocks"][0]["csv_path"])
    assert {"family", "row_label", "row_color_hex", "soa_ms", "noise_type", "duration_ms"} <= set(first_block_rows[0])
    assert "source_lineage" not in first_block_rows[0]
    for block in default_block_manifest["blocks"]:
        block_rows = _read_csv_rows(block["csv_path"])
        row_labels = [row["row_label"] for row in block_rows]
        assert row_labels == ["Inhale trial type", "Exhale trial type"] * (len(block_rows) // 2)

    invalid_pool_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": loaded["design"],
            "bake_recipe": {
                "kind": "trial_repetition_pool",
                "label": "4_trial_repetition_pool",
                "default_repetitions": 1.25,
            },
        },
    ).json()
    invalid_pool_done = _wait_job(client, invalid_pool_job["job_id"])
    assert invalid_pool_done["status"] == "failed"
    assert "whole or half repetitions" in invalid_pool_done["error"]

    pool_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": loaded["design"],
            "bake_recipe": {
                "kind": "trial_repetition_pool",
                "label": "4_trial_repetition_pool",
                "default_repetitions": 6,
            },
        },
    ).json()
    pool_done = _wait_job(client, pool_job["job_id"])
    assert pool_done["status"] == "succeeded"
    assert pool_done["result"]["unique_file_count"] == 88
    assert pool_done["result"]["total_count"] == 528
    assert pool_done["result"]["audio_tactile_count"] == 240
    assert pool_done["result"]["baseline_count"] == 240
    assert pool_done["result"]["catch_count"] == 48
    pool_root = Path(pool_done["result"]["root"])
    assert not list(pool_root.rglob("*.wav"))
    pool_manifest = _read_json_file(pool_done["result"]["manifest_path"])
    assert pool_manifest["source_segment3_manifest_sha256"] == dashboard_app._local_file_sha256(Path(tactile_done["result"]["manifest_path"]))
    pool_rows = _read_csv_rows(pool_done["result"]["csv_path"])
    assert len(pool_rows) == 528
    assert pool_rows[0]["trial_file_path"].endswith(".wav")
    assert {"audio_tactile", "baseline", "catch"} <= {row["family"] for row in pool_rows}
    state = client.get("/api/state").json()
    assert state["project_segments"]["4_trial_repetition_pool"]["status"] == "ready"
    assert state["project_segments"]["4_trial_repetition_pool"]["total_count"] == 528


def test_dashboard_pink_white_profile_preserves_study5_trial_budget_after_source_prune(tmp_path: Path):
    client = _client(tmp_path)
    client.post("/api/templates/study5_box_breathing_pps_pink_white/load").json()
    loaded = client.post("/api/project/customize", json={"name": "Study 5 pink white invariant"}).json()

    assert loaded["custom_workflow"]["is_custom"] is True
    assert [item["label"] for item in loaded["design"]["noises"]] == ["Pink frontal", "White frontal"]
    assert loaded["design"]["protocol"]["trial_pool_repetition_defaults"] == {
        "default": 6.0,
        "audio_tactile": 6.0,
        "baseline": 3.0,
        "catch": 6.0,
    }

    sequence_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": loaded["design"],
            "bake_recipe": {"kind": "trial_sequence_batch", "label": "2_trial_sequence_designs"},
        },
    ).json()
    sequence_done = _wait_job(client, sequence_job["job_id"])
    assert sequence_done["status"] == "succeeded"
    assert sequence_done["result"]["variant_count"] == 4

    tactile_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": loaded["design"],
            "bake_recipe": {"kind": "audiotactile_trial_batch", "label": "3_tactile_and_baseline_trials"},
        },
    ).json()
    tactile_done = _wait_job(client, tactile_job["job_id"])
    assert tactile_done["status"] == "succeeded"
    assert tactile_done["result"]["audio_tactile_count"] == 20
    assert tactile_done["result"]["baseline_count"] == 20
    assert tactile_done["result"]["catch_count"] == 4

    pool_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": loaded["design"],
            "bake_recipe": {"kind": "trial_repetition_pool", "label": "4_trial_repetition_pool"},
        },
    ).json()
    pool_done = _wait_job(client, pool_job["job_id"])
    assert pool_done["status"] == "succeeded"
    assert pool_done["result"]["unique_file_count"] == 44
    assert pool_done["result"]["total_count"] == 204
    assert pool_done["result"]["audio_tactile_count"] == 120
    assert pool_done["result"]["baseline_count"] == 60
    assert pool_done["result"]["catch_count"] == 24

    pool_manifest = _read_json_file(pool_done["result"]["manifest_path"])
    assert pool_manifest["settings"]["family_repetitions"] == {
        "audio_tactile": 6,
        "baseline": 3,
        "catch": 6,
    }
    assert pool_manifest["balance_warnings"] == []
    pool_rows = _read_csv_rows(pool_done["result"]["csv_path"])
    assert len(pool_rows) == 204
    assert dict(Counter(dashboard_app._block_csv_noise_type(row) for row in pool_rows)) == {"pink": 102, "white": 102}
    assert dict(Counter((row["family"], dashboard_app._block_csv_noise_type(row)) for row in pool_rows)) == {
        ("audio_tactile", "pink"): 60,
        ("audio_tactile", "white"): 60,
        ("baseline", "pink"): 30,
        ("baseline", "white"): 30,
        ("catch", "pink"): 12,
        ("catch", "white"): 12,
    }

    block_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": loaded["design"],
            "bake_recipe": {"kind": "block_csv_preview", "label": "5_block_csv_preview"},
        },
    ).json()
    block_done = _wait_job(client, block_job["job_id"])
    assert block_done["status"] == "succeeded"
    assert block_done["result"]["block_count"] == 6
    assert block_done["result"]["csv_count"] == 6
    assert block_done["result"]["total_count"] == 204

    block_manifest = _read_json_file(block_done["result"]["manifest_path"])
    assert [block["trial_count"] for block in block_manifest["blocks"]] == [34, 34, 34, 34, 34, 34]
    assert block_manifest["row_sequence_strategy"] == "cycle_preserved_segment_row_order_within_each_block"
    for block in block_manifest["blocks"]:
        block_rows = _read_csv_rows(block["csv_path"])
        assert dict(Counter(row["family"] for row in block_rows)) == {
            "audio_tactile": 20,
            "baseline": 10,
            "catch": 4,
        }
        assert dict(Counter(row["noise_type"] for row in block_rows)) == {"pink": 17, "white": 17}
        assert dict(Counter((row["family"], row["noise_type"]) for row in block_rows)) == {
            ("audio_tactile", "pink"): 10,
            ("audio_tactile", "white"): 10,
            ("baseline", "pink"): 5,
            ("baseline", "white"): 5,
            ("catch", "pink"): 2,
            ("catch", "white"): 2,
        }
        assert [row["row_label"] for row in block_rows] == ["Inhale trial type", "Exhale trial type"] * 17


def test_dashboard_loads_all_preloads_with_trajectory_inventory(tmp_path: Path):
    client = _client(tmp_path)
    root = Path(__file__).resolve().parents[1]
    templates = client.get("/api/state").json()["templates"]

    assert templates
    for template in templates:
        loaded = client.post(f"/api/templates/{template['template_id']}/load").json()
        design = loaded["design"]
        sources = design["noises"] + design["custom_looming_files"]
        viewer_sources = loaded["viewer_payload"]["source_trajectories"]

        assert sources, template["template_id"]
        assert len(viewer_sources) == len(sources), template["template_id"]
        for source in sources:
            local_path = source.get("prebaked_path") or source.get("path") or ""
            assert local_path, (template["template_id"], source.get("label"))
            _assert_dashboard_path_exists(root, local_path)
            snapshot = source.get("trajectory_snapshot") or {}
            assert snapshot.get("schema") == "pps-stimulus-trajectory.v1", (template["template_id"], source.get("label"))
            assert snapshot.get("start_distance_cm") is not None, (template["template_id"], source.get("label"))
            assert snapshot.get("end_distance_cm") is not None, (template["template_id"], source.get("label"))
            assert snapshot.get("movement_duration_s") is not None, (template["template_id"], source.get("label"))
            assert snapshot.get("start") and snapshot.get("end"), (template["template_id"], source.get("label"))
        for viewer_source in viewer_sources:
            assert viewer_source["trajectory_snapshot"]["schema"] == "pps-stimulus-trajectory.v1"
            assert viewer_source["start"] and viewer_source["end"]
            assert viewer_source["color_hex"].startswith("#")
            assert viewer_source["local_path"]


def test_pfeiffer_preload_loads_bilateral_lateral_trajectories(tmp_path: Path):
    client = _client(tmp_path)
    root = Path(__file__).resolve().parents[1]
    template_id = "pfeiffer_2018_lateral_perihead_left_to_right"

    inventory = json.loads((root / "assets" / "preloads" / "preload_inventory.json").read_text(encoding="utf-8"))
    profile = next(item for item in inventory["profiles"] if item["template_id"] == template_id)
    assert len(profile["assets"]) == 2
    assert {asset["direction_label"] for asset in profile["assets"]} == {"left_to_right", "right_to_left"}

    loaded = client.post(f"/api/templates/{template_id}/load").json()
    design = loaded["design"]
    viewer_sources = loaded["viewer_payload"]["source_trajectories"]
    assert len(design["noises"]) == 1
    assert len(design["custom_looming_files"]) == 1
    assert len(viewer_sources) == 2
    assert {item["trajectory_snapshot"]["path_direction"] for item in viewer_sources} == {
        "left_to_right",
        "right_to_left",
    }
    rotations = {
        (
            item["trajectory_snapshot"]["start_rotation_deg"],
            item["trajectory_snapshot"]["end_rotation_deg"],
        )
        for item in viewer_sources
    }
    assert rotations == {(277.125, 82.875), (82.875, 277.125)}
    for item in viewer_sources:
        _assert_dashboard_path_exists(root, item["local_path"])


def test_lerner_preload_loads_twelve_3d_boundary_directions(tmp_path: Path):
    client = _client(tmp_path)
    root = Path(__file__).resolve().parents[1]
    template_id = "lerner_2021_3d_audio_tactile_boundary"

    inventory = json.loads((root / "assets" / "preloads" / "preload_inventory.json").read_text(encoding="utf-8"))
    profile = next(item for item in inventory["profiles"] if item["template_id"] == template_id)
    assert len(profile["assets"]) == 24
    assert profile["source_recipe_count"] == 24
    assert {asset["direction_label"] for asset in profile["assets"]} == {
        f"direction_{index:02d}" for index in range(1, 13)
    }

    loaded = client.post(f"/api/templates/{template_id}/load").json()
    design = loaded["design"]
    viewer_sources = loaded["viewer_payload"]["source_trajectories"]
    assert len(design["noises"]) == 2
    assert len(design["custom_looming_files"]) == 22
    assert design["protocol"]["auditory_motion_directions"] == ["source_trajectory"]
    assert len(viewer_sources) == 24
    assert {item["tone_type"] for item in viewer_sources} == {"pink", "white"}
    unique_geometries = {
        (
            tuple(item["trajectory_snapshot"]["start"][axis] for axis in ("x_m", "y_m", "z_m")),
            tuple(item["trajectory_snapshot"]["end"][axis] for axis in ("x_m", "y_m", "z_m")),
        )
        for item in viewer_sources
    }
    assert len(unique_geometries) == 12
    assert {item["trajectory_snapshot"]["movement_duration_s"] for item in viewer_sources} == {5.5}
    assert {item["trajectory_snapshot"]["start_distance_cm"] for item in viewer_sources} == {120.0}
    assert {item["trajectory_snapshot"]["end_distance_cm"] for item in viewer_sources} == {1.0}
    for item in viewer_sources:
        _assert_dashboard_path_exists(root, item["local_path"])


def test_preload_catalog_folders_mirror_dashboard_segments():
    root = Path(__file__).resolve().parents[1]
    inventory = json.loads((root / "assets" / "preloads" / "preload_inventory.json").read_text(encoding="utf-8"))
    expected_segments = [
        "01_profile",
        "02_looming_stimuli",
        "03_baseline_strategy",
        "04_trial_designer",
        "05_run_setup",
    ]
    assert [segment["folder"] for segment in inventory["segments"]] == expected_segments
    for profile in inventory["profiles"]:
        profile_dir = root / "assets" / "preloads" / profile["template_id"]
        assert profile_dir.is_dir()
        assert [segment["folder"] for segment in profile["catalog_segments"]] == expected_segments
        assert (profile_dir / "preload_manifest.json").exists()
        assert (profile_dir / "01_profile" / "profile_metadata.json").exists()
        assert (profile_dir / "02_looming_stimuli" / "stimulus_sources.json").exists()
        assert (profile_dir / "02_looming_stimuli" / "trajectory_inventory.json").exists()
        assert (profile_dir / "03_baseline_strategy" / "baseline_strategy.json").exists()
        assert (profile_dir / "04_trial_designer" / "trial_design.json").exists()
        assert (profile_dir / "05_run_setup" / "run_defaults.json").exists()
        for asset in profile["assets"]:
            path = root / asset["path"]
            assert path.exists()
            assert Path(asset["path"]).parts[-2] == "02_looming_stimuli"
            assert asset["trajectory_snapshot"]["schema"] == "pps-stimulus-trajectory.v1"


def test_dashboard_previews_study5_filmstrip_row_audio_locally(tmp_path: Path):
    client = _client(tmp_path)
    loaded = client.post("/api/templates/study5_box_breathing_pps/load").json()

    preview = client.post(
        "/api/trials/preview-row",
        json={
            "participant_id": "P001",
            "strip_index": 0,
            "design": loaded["design"],
        },
    ).json()

    assert preview["local_only"] is True
    assert preview["auditory_preview_only"] is True
    assert preview["sequence"][0] == "Inhale instruction"
    assert preview["selected_source_label"] in loaded["design"]["protocol"]["trial_strips"][0]["elements"][1]["source_labels"]
    assert preview["url"].startswith("/api/trial-row-previews/")
    preview_path = Path(preview["path"])
    assert preview_path.exists()
    assert preview_path.parent == tmp_path / "previews"
    info = sf.info(str(preview_path))
    assert info.channels == 2
    assert info.samplerate == 44100
    assert info.frames / info.samplerate == pytest.approx(8.0)
    assert client.get(preview["url"]).status_code == 200


def test_dashboard_state_templates_and_design_update(tmp_path: Path):
    client = _client(tmp_path)

    state = client.get("/api/state").json()
    assert state["design"]["name"]
    assert state["templates"]
    assert state["preload_inventory"]["status"] == "ready"
    assert state["render"]["wav_count"] >= 4

    template_id = state["templates"][0]["template_id"]
    loaded = client.post(f"/api/templates/{template_id}/load").json()
    assert loaded["selected_template"] == template_id

    custom = client.post("/api/templates/__custom__/load").json()
    assert custom["selected_template"] == ""
    assert custom["design"]["name"] == "Custom PPS design"
    assert custom["design"]["study_profile_id"] == ""
    assert custom["custom_workflow"]["is_custom"]
    assert not custom["custom_workflow"]["ready_to_render"]
    assert custom["design"]["noises"] == []
    assert custom["design"]["protocol"]["soa_values_ms"] == []
    assert custom["design"]["protocol"]["trial_strips"] == []

    blocked = client.post("/api/render", json={})
    assert blocked.status_code == 400
    assert "Custom design is incomplete" in blocked.json()["detail"]

    custom["design"]["name"] = "Manual lab approach design"
    custom["design"]["noises"] = [
        {"label": "Manual pink", "noise_type": "pink", "azimuth_deg": 0.0, "elevation_deg": 0.0, "gain": 1.0}
    ]
    custom["design"]["protocol"]["soa_values_ms"] = [300]
    custom["design"]["protocol"]["spatial_values_cm"] = [100.0]
    custom["design"]["protocol"]["trial_strips"] = [
        {
            "strip_id": "strip-1",
            "label": "Manual row",
            "elements": [
                {
                    "element_id": "looming-1",
                    "kind": "looming_stimulus",
                    "label": "Looming Stimulus",
                    "source_labels": ["Manual pink"],
                    "randomized": True,
                }
            ],
        }
    ]
    custom_needs_segment1 = client.post("/api/design", json={"participant_id": "", "design": custom["design"]}).json()
    assert not custom_needs_segment1["custom_workflow"]["ready_to_render"]
    assert custom_needs_segment1["custom_workflow"]["current_step"] == "stimulus"
    assert "Bake Segment 1 ingredients." in custom_needs_segment1["custom_workflow"]["missing"]

    custom["design"]["protocol"]["baseline_strategy"] = "none"
    custom["design"]["protocol"]["baseline_trial_percentage"] = 0.0
    custom["design"]["protocol"]["include_baseline_trials"] = False
    custom["design"]["protocol"]["soa_values_ms"] = []
    custom_needs_soa = client.post("/api/design", json={"participant_id": "", "design": custom["design"]}).json()
    assert not custom_needs_soa["custom_workflow"]["ready_to_render"]
    assert custom_needs_soa["custom_workflow"]["current_step"] == "stimulus"
    assert "Bake Segment 1 ingredients." in custom_needs_soa["custom_workflow"]["missing"]

    custom["design"]["protocol"]["soa_values_ms"] = [300]
    custom_ready = client.post("/api/design", json={"participant_id": "", "design": custom["design"]}).json()
    assert not custom_ready["custom_workflow"]["ready_to_render"]
    assert not custom_ready["custom_workflow"]["ready_to_prepare"]
    assert custom_ready["custom_workflow"]["current_step"] == "stimulus"
    workflow_steps = {step["id"]: step for step in custom_ready["custom_workflow"]["steps"]}
    assert workflow_steps["stimulus"]["label"] == "Stimulus Design"
    assert workflow_steps["stimulus"]["complete"] is False
    assert "Bake Segment 1 ingredients." in workflow_steps["stimulus"]["missing"]

    custom_run_ready = client.post("/api/design", json={"participant_id": "P042", "design": custom["design"]}).json()
    assert not custom_run_ready["custom_workflow"]["ready_to_prepare"]

    loaded = client.post(f"/api/templates/{template_id}/load").json()
    assert loaded["selected_template"] == template_id

    loaded["design"]["name"] = "Browser prototype design"
    blocked_profile_update = client.post(
        "/api/design",
        json={
            "participant_id": "Subject 01",
            "design": loaded["design"],
        },
    )
    assert blocked_profile_update.status_code == 400
    assert "read-only" in blocked_profile_update.json()["detail"]

    editable = client.post("/api/project/customize", json={"name": "Browser prototype design"}).json()
    editable["design"]["name"] = "Browser prototype design"
    updated = client.post(
        "/api/design",
        json={
            "participant_id": "Subject 01",
            "design": editable["design"],
            "trajectory_controls": {
                "start_distance_cm": 120,
                "end_distance_cm": 20,
                "start_rotation_deg": 0,
                "end_rotation_deg": 15,
                "movement_duration_s": 3,
                "start_hold_s": 0.5,
                "end_hold_s": 0.5,
            },
        },
    ).json()
    assert updated["participant_id"] == "Subject 01"
    assert updated["design"]["name"] == "Browser prototype design"
    assert updated["viewer_payload"]["path_length_m"] > 0


def test_custom_study_source_removal_prunes_stale_trial_sequence_labels(tmp_path: Path):
    client = _client(tmp_path)

    client.post("/api/templates/study5_box_breathing_pps/load").json()
    custom = client.post("/api/project/customize", json={"name": "Study 5 pink white source test"}).json()
    design = custom["design"]
    design["noises"] = [
        source
        for source in design["noises"]
        if source["label"] in {"Pink frontal", "White frontal"}
    ]

    updated = client.post("/api/design", json={"participant_id": "", "design": design}).json()

    assert [source["label"] for source in updated["design"]["noises"]] == ["Pink frontal", "White frontal"]
    looming_label_rows = [
        element["source_labels"]
        for strip in updated["design"]["protocol"]["trial_strips"]
        for element in strip["elements"]
        if element["kind"] == "looming_stimulus"
    ]
    assert looming_label_rows == [
        ["Pink frontal", "White frontal"],
        ["Pink frontal", "White frontal"],
    ]


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
    assert protocol["baseline_trial_percentage"] == pytest.approx(20.0)
    assert summary["baseline_trials"] == 1
    assert summary["baseline_actual_percent"] == pytest.approx(50.0)
    assert "estimated_participant_minutes" in summary


def test_dashboard_import_audio_is_local_only(tmp_path: Path):
    client = _client(tmp_path)
    source = tmp_path / "manual_loom.wav"
    sf.write(source, np.zeros((441, 2), dtype=np.float32), 44100)
    payload = {
        "filename": source.name,
        "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
        "use": "looming",
        "render_mode": "spatialize",
    }

    imported = client.post("/api/audio/import", json=payload).json()

    assert imported["local_only"] is True
    assert "online upload" in imported["message"]
    stored = Path(imported["audio"]["path"])
    assert dashboard_app._path_exists(stored)
    assert stored.parts[-2] == "1_core_audio_ingredients"
    assert stored.name.startswith("manual_loom_looming10ms")
    ingredient_manifest = json.loads(dashboard_app._read_text_file(stored.parent / "stimulus_ingredients_manifest.json", encoding="utf-8"))
    assert ingredient_manifest["schema"] == "pps-core-audio-ingredients.v1"
    assert any(
        item["descriptor"] == "manual_loom_looming10ms"
        for item in ingredient_manifest["ingredients"]
    )
    assert imported["audio"]["label"] == "manual_loom"
    assert imported["audio"]["target_duration_s"] > 0
    assert imported["audio"]["render_mode"] == "spatialize"

    snippet_payload = {
        "filename": source.name,
        "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
        "use": "prestimulus",
        "render_mode": "preserve",
        "placement": "after",
        "target_source_label": "Manual pink",
        "phase": "Inhale",
        "gap_s": 0.25,
        "sequence_order": 3,
        "motion_mode": "stationary",
    }
    snippet = client.post("/api/audio/import", json=snippet_payload).json()

    assert snippet["local_only"] is True
    assert snippet["audio"]["placement"] == "after"
    assert snippet["audio"]["target_source_label"] == "Manual pink"
    assert snippet["audio"]["phase"] == "Inhale"
    assert snippet["audio"]["gap_s"] == 0.25
    assert snippet["audio"]["sequence_order"] == 3
    assert snippet["audio"]["motion_mode"] == "stationary"


def test_dashboard_import_instruction_audio_is_segment6_local_only(tmp_path: Path):
    client = _client(tmp_path)
    source = tmp_path / "general_instruction.wav"
    sf.write(source, np.zeros((2205, 1), dtype=np.float32), 22050)
    payload = {
        "slot": "before_experiment",
        "filename": source.name,
        "content_base64": base64.b64encode(source.read_bytes()).decode("ascii"),
        "label": "Brief start message",
    }

    imported = client.post("/api/run-instructions/import", json=payload)

    assert imported.status_code == 200, imported.text
    state = imported.json()
    result = state["run_instruction_import_result"]
    assert result["local_only"] is True
    assert "local companion backend" in result["message"]
    stored = Path(result["audio"]["path"])
    assert dashboard_app._path_exists(stored)
    assert stored.parent.name == "instruction_library"
    assert stored.parent.parent.name == "6_experiment_run_setup"
    assert stored.name.startswith("before_experiment_brief_start_message")
    assert result["audio"]["sample_rate"] == 44100
    setup = state["design"]["study_profile_reference_parameters"]["dashboard_run_setup"]
    slots = {slot["slot"]: slot for slot in setup["instruction_profile"]["slots"]}
    slot = slots["before_experiment"]
    assert slot["enabled"] is True
    assert slot["label"] == "Brief start message"
    assert Path(slot["path"]) == stored
    assert slot["sample_rate"] == 44100
    assert slot["channels"] == 1
    assert slot["sha256"] == result["audio"]["sha256"]
    assert slot["source"] == "custom_import"


def test_dashboard_bake_stimulus_job_adds_source_after_render(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    custom = client.post("/api/templates/__custom__/load").json()
    trajectory_controls = {
        "start_distance_cm": 95.0,
        "end_distance_cm": 15.0,
        "start_rotation_deg": 270.0,
        "end_rotation_deg": 45.0,
        "movement_duration_s": 1.5,
        "start_hold_s": 0.2,
        "end_hold_s": 0.4,
    }
    expected_start = point_from_distance_rotation_height(95.0, 270.0, 0.0)
    expected_end = point_from_distance_rotation_height(15.0, 45.0, 0.0)
    custom["design"]["name"] = "Manual bake design"
    custom["design"]["protocol"]["soa_values_ms"] = [300]
    custom["design"]["protocol"]["spatial_values_cm"] = [100.0]
    custom["design"]["protocol"]["include_baseline_trials"] = False
    custom["design"]["protocol"]["baseline_strategy"] = "none"
    custom["design"]["protocol"]["baseline_trial_percentage"] = 0.0
    custom["design"]["protocol"]["trial_strips"] = [
        {
            "strip_id": "strip-1",
            "label": "Manual row",
            "elements": [
                {
                    "element_id": "looming-1",
                    "kind": "looming_stimulus",
                    "label": "Looming Stimulus",
                    "source_labels": ["Manual blue"],
                    "randomized": True,
                }
            ],
        }
    ]

    def fake_render(design_path, output_dir, *, seed, engine="auto", include_tactile=True, **_kwargs):
        design_data = json.loads(Path(design_path).read_text(encoding="utf-8"))
        label = design_data["noises"][0]["label"]
        wav_path = Path(output_dir) / "looming_manual_blue.wav"
        sf.write(wav_path, np.zeros((441, 2), dtype=np.float32), 44100)
        manifest = Path(output_dir) / "render_manifest.json"
        qc = Path(output_dir) / "render_qc.csv"
        tactile = Path(output_dir) / "render_tactile_events.csv"
        manifest.write_text(
            json.dumps({"status": "rendered_reference", "wav_outputs": [{"path": str(wav_path), "sha256": "test"}]}),
            encoding="utf-8",
        )
        qc.write_text("", encoding="utf-8")
        tactile.write_text("", encoding="utf-8")
        assert label == "Manual blue"
        assert seed == custom["design"]["protocol"]["random_seed"]
        assert engine == "python-sofa-reference"
        assert include_tactile is False
        assert design_data["trajectory"]["start_x_m"] == pytest.approx(expected_start["x_m"])
        assert design_data["trajectory"]["start_y_m"] == pytest.approx(expected_start["y_m"])
        assert design_data["trajectory"]["start_z_m"] == pytest.approx(expected_start["z_m"])
        assert design_data["trajectory"]["end_x_m"] == pytest.approx(expected_end["x_m"])
        assert design_data["trajectory"]["end_y_m"] == pytest.approx(expected_end["y_m"])
        assert design_data["trajectory"]["end_z_m"] == pytest.approx(expected_end["z_m"])
        assert design_data["trajectory"]["propagation_speed_mps"] == pytest.approx(
            math.dist(
                (expected_start["x_m"], expected_start["y_m"], expected_start["z_m"]),
                (expected_end["x_m"], expected_end["y_m"], expected_end["z_m"]),
            )
            / trajectory_controls["movement_duration_s"]
        )
        assert design_data["trajectory"]["padding_pre_s"] == pytest.approx(trajectory_controls["start_hold_s"])
        assert design_data["trajectory"]["padding_post_s"] == pytest.approx(trajectory_controls["end_hold_s"])
        return RenderResult("rendered_reference", 0, Path(output_dir), Path(design_path), manifest, qc, wav_paths=(wav_path,), tactile_events_path=tactile)

    monkeypatch.setattr(dashboard_app.render_backend, "render_design_with_3dti", fake_render)
    job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "",
            "design": custom["design"],
            "trajectory_controls": trajectory_controls,
            "bake_recipe": {"kind": "generated_noise", "noise_type": "blue", "label": "Manual blue", "gain": 0.7},
        },
    ).json()
    done = _wait_job(client, job["job_id"])
    state = client.get("/api/state").json()

    assert done["status"] == "succeeded"
    assert done["result"]["local_only"] is True
    assert done["result"]["include_tactile"] is False
    assert done["result"]["source_kind"] == "generated_noise"
    baked_noise = next(noise for noise in state["design"]["noises"] if noise["label"] == "Manual blue")
    baked_path = Path(done["result"]["wav_path"])
    assert baked_path.parts[-2] == "1_core_audio_ingredients"
    assert baked_path.name.startswith("manual_blue_looming10ms")
    assert Path(baked_noise["prebaked_path"]).name.startswith("manual_blue_looming10ms")
    ingredient_manifest = json.loads((baked_path.parent / "stimulus_ingredients_manifest.json").read_text(encoding="utf-8"))
    assert ingredient_manifest["schema"] == "pps-core-audio-ingredients.v1"
    assert ingredient_manifest["ingredients"][0]["descriptor"] == "manual_blue_looming10ms"
    assert baked_noise["noise_type"] == "blue"
    assert baked_noise["trajectory_snapshot"]["start_distance_cm"] == pytest.approx(95.0)
    assert baked_noise["trajectory_snapshot"]["end_distance_cm"] == pytest.approx(15.0)
    assert baked_noise["trajectory_snapshot"]["start_rotation_deg"] == pytest.approx(270.0)
    assert baked_noise["trajectory_snapshot"]["end_rotation_deg"] == pytest.approx(45.0)
    assert done["result"]["source"]["trajectory_snapshot"] == baked_noise["trajectory_snapshot"]
    assert state["render"]["wav_count"] >= 1
    assert state["custom_workflow"]["ready_to_render"] is False
    assert state["custom_workflow"]["current_step"] == "trials"
    assert "Bake Segment 2 trial sequences." in state["custom_workflow"]["missing"]


def test_dashboard_batch_bakes_trial_sequence_row_variant_folders(tmp_path: Path):
    client = _client(tmp_path)
    custom = client.post("/api/templates/__custom__/load").json()
    custom["design"]["name"] = "Segment 2 sequence bake"
    custom = client.post("/api/design", json={"design": custom["design"]}).json()
    inhale = _register_segment1_wav(
        client,
        custom["design"],
        "Inhale",
        np.zeros((32, 2), dtype=np.float32),
        motion_mode="stationary",
        source_kind="test_fixed_audio",
    )
    labels = ["White", "Pink", "Blue", "Brown"]
    noises = []
    for label in labels:
        path = _register_segment1_wav(
            client,
            custom["design"],
            label,
            np.zeros((32, 2), dtype=np.float32),
            motion_mode="looming",
            source_kind="test_looming_audio",
        )
        noises.append({"label": label, "noise_type": label.lower() if label != "Brown" else "brown", "prebaked_path": str(path)})

    custom["design"]["noises"] = noises
    custom["design"]["prestimulus_files"] = [
        {
            "label": "Inhale",
            "path": str(inhale),
            "target_duration_s": 0.001,
            "render_mode": "preserve",
            "motion_mode": "stationary",
        }
    ]
    custom["design"]["protocol"]["trial_strips"] = [
        {
            "strip_id": "row-1",
            "label": "Inhale noises",
            "elements": [
                {"kind": "fixed_audio", "label": "Audio box", "source_labels": ["Inhale"], "randomized": True},
                {"kind": "looming_stimulus", "label": "Audio box", "source_labels": labels, "randomized": True},
            ],
        },
        {
            "strip_id": "row-2",
            "label": "Inhale jitter noises",
            "elements": [
                {"kind": "fixed_audio", "label": "Audio box", "source_labels": ["Inhale"], "randomized": True},
                {"kind": "jitter", "label": "Jitter / ITI event", "jitter_values_ms": [10, 20], "randomized": True},
                {"kind": "looming_stimulus", "label": "Audio box", "source_labels": labels, "randomized": True},
            ],
        },
    ]

    job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "",
            "design": custom["design"],
            "bake_recipe": {"kind": "trial_sequence_batch", "label": "2_trial_sequence_designs"},
        },
    ).json()
    done = _wait_job(client, job["job_id"])

    assert done["status"] == "succeeded"
    result = done["result"]
    assert result["variant_count"] == 12
    assert [row["variant_count"] for row in result["rows"]] == [4, 8]
    root = Path(result["root"])
    assert root.parts[-1] == "2_trial_sequence_designs"
    assert root.parts[-3] == "0_study_project_registry"
    assert (root / "row_01__Inhale_noises").is_dir()
    assert (root / "row_02__Inhale_jitter_noises").is_dir()
    manifest = json.loads(dashboard_app._read_text_file(result["manifest_path"], encoding="utf-8"))
    assert manifest["schema"] == "pps-trial-sequence-variants.v1"
    assert manifest["variant_count"] == 12
    assert all("total" in Path(item["file_path"]).stem for item in manifest["variants"])
    assert all("content_descriptor" in item for item in manifest["variants"])
    assert all("row_" not in Path(item["file_path"]).name.lower() for item in manifest["variants"])
    assert any("inhale" in Path(item["file_path"]).name and "white_looming" in Path(item["file_path"]).name for item in manifest["variants"])
    assert any("jitter10ms" in Path(item["file_path"]).name for item in manifest["variants"])
    assert any("(10 ms)" in item["sequence_labels"] for item in manifest["variants"])
    assert any(item["jitter_values_ms"] == "20" for item in manifest["variants"])
    state = client.get("/api/state").json()
    assert state["project_segments"]["2_trial_sequence_designs"]["status"] == "ready"
    assert state["project_segments"]["3_tactile_and_baseline_trials"]["status"] == "missing"
    report = Path(state["project"]["profile_dir"]) / "segment_validation_report.json"
    assert report.exists()
    report_data = json.loads(report.read_text(encoding="utf-8"))
    assert report_data["schema"] == "pps-segment-validation-report.v1"


def test_dashboard_sequence_bake_preserves_stereo_looming_after_mono_instruction(tmp_path: Path):
    client = _client(tmp_path)
    custom = client.post("/api/templates/__custom__/load").json()
    sample_rate = 44100
    fixed_frames = 256
    looming_frames = 512

    custom["design"]["name"] = "Mono first stereo sequence"
    custom = client.post("/api/design", json={"design": custom["design"]}).json()
    mono_instruction = np.linspace(0.05, 0.25, fixed_frames, dtype=np.float32)[:, None]
    stereo_looming = np.column_stack(
        [
            np.linspace(0.10, 0.30, looming_frames, dtype=np.float32),
            np.linspace(-0.30, -0.10, looming_frames, dtype=np.float32),
        ]
    )
    inhale = _register_segment1_wav(
        client,
        custom["design"],
        "Inhale",
        mono_instruction,
        sample_rate=sample_rate,
        motion_mode="stationary",
        source_kind="test_fixed_audio",
    )
    looming = _register_segment1_wav(
        client,
        custom["design"],
        "Pink",
        stereo_looming,
        sample_rate=sample_rate,
        motion_mode="looming",
        source_kind="test_looming_audio",
    )
    custom["design"]["noises"] = [{"label": "Pink", "noise_type": "pink", "prebaked_path": str(looming)}]
    custom["design"]["prestimulus_files"] = [
        {
            "label": "Inhale",
            "path": str(inhale),
            "target_duration_s": fixed_frames / sample_rate,
            "render_mode": "preserve",
            "motion_mode": "stationary",
        }
    ]
    custom["design"]["protocol"]["soa_values_ms"] = [1]
    custom["design"]["protocol"]["spatial_values_cm"] = [100.0]
    custom["design"]["protocol"]["include_catch_trials"] = True
    custom["design"]["protocol"]["include_baseline_trials"] = False
    custom["design"]["protocol"]["trial_strips"] = [
        {
            "strip_id": "row-1",
            "label": "Inhale pink",
            "elements": [
                {"kind": "fixed_audio", "label": "Instruction", "source_labels": ["Inhale"], "randomized": True},
                {"kind": "looming_stimulus", "label": "Looming Stimulus", "source_labels": ["Pink"], "randomized": True},
            ],
        }
    ]

    sequence_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": custom["design"],
            "bake_recipe": {"kind": "trial_sequence_batch", "label": "2_trial_sequence_designs"},
        },
    ).json()
    sequence_done = _wait_job(client, sequence_job["job_id"])
    assert sequence_done["status"] == "succeeded"
    sequence_manifest = _read_json_file(sequence_done["result"]["manifest_path"])
    sequence_path = Path(sequence_manifest["variants"][0]["file_path"])
    sequence_audio, sequence_sr = sf.read(dashboard_app._soundfile_path(sequence_path), dtype="float32", always_2d=True)
    instruction_source, _ = sf.read(dashboard_app._soundfile_path(inhale), dtype="float32", always_2d=True)
    looming_source, _ = sf.read(dashboard_app._soundfile_path(looming), dtype="float32", always_2d=True)

    assert sequence_sr == sample_rate
    assert sequence_audio.shape == (fixed_frames + looming_frames, 2)
    assert np.max(np.abs(sequence_audio[:fixed_frames, 0] - instruction_source[:, 0])) <= 1 / 32768
    assert np.max(np.abs(sequence_audio[:fixed_frames, 1] - instruction_source[:, 0])) <= 1 / 32768
    assert np.max(np.abs(sequence_audio[fixed_frames:, 0] - looming_source[:, 0])) <= 1 / 32768
    assert np.max(np.abs(sequence_audio[fixed_frames:, 1] - looming_source[:, 1])) <= 1 / 32768
    assert np.max(np.abs(sequence_audio[fixed_frames:, 0] - sequence_audio[fixed_frames:, 1])) > 0.05

    tactile_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": custom["design"],
            "bake_recipe": {"kind": "audiotactile_trial_batch", "label": "3_tactile_and_baseline_trials"},
        },
    ).json()
    tactile_done = _wait_job(client, tactile_job["job_id"])
    assert tactile_done["status"] == "succeeded"
    tactile_manifest = _read_json_file(tactile_done["result"]["manifest_path"])
    catch_row = next(item for item in tactile_manifest["files"] if item["family"] == "catch")
    audio_row = next(item for item in tactile_manifest["files"] if item["family"] == "audio_tactile")
    catch_audio, catch_sr = sf.read(dashboard_app._soundfile_path(catch_row["file_path"]), dtype="float32", always_2d=True)
    audio_tactile, audio_sr = sf.read(dashboard_app._soundfile_path(audio_row["file_path"]), dtype="float32", always_2d=True)

    assert catch_sr == sample_rate
    assert catch_row["channels"] == 2
    assert catch_audio.shape == sequence_audio.shape
    assert np.max(np.abs(catch_audio - sequence_audio)) <= 1 / 32768
    assert audio_sr == sample_rate
    assert audio_row["channels"] == 3
    assert audio_tactile.shape[1] == 3
    assert np.max(np.abs(audio_tactile[:, :2] - sequence_audio)) <= 2 / 32768
    assert np.max(np.abs(audio_tactile[:, 2])) > 0.01


def test_dashboard_previews_each_segment2_source_label(tmp_path: Path):
    client = _client(tmp_path)
    custom = client.post("/api/templates/__custom__/load").json()
    fixed_path = _register_segment1_wav(
        client,
        custom["design"],
        "Inhale",
        np.ones((64, 1), dtype=np.float32) * 0.05,
        motion_mode="stationary",
        source_kind="test_fixed_audio",
    )
    looming_path = _register_segment1_wav(
        client,
        custom["design"],
        "Pink",
        np.ones((96, 2), dtype=np.float32) * 0.04,
        motion_mode="looming",
        source_kind="test_looming_audio",
    )
    custom["design"]["prestimulus_files"] = [
        {
            "label": "Inhale",
            "path": str(fixed_path),
            "target_duration_s": 64 / 44100,
            "render_mode": "preserve",
            "motion_mode": "stationary",
        }
    ]
    custom["design"]["noises"] = [
        {"label": "Pink", "noise_type": "pink", "gain": 0.5, "prebaked_path": str(looming_path)}
    ]
    custom["design"]["protocol"]["trial_strips"] = [
        {
            "strip_id": "row-1",
            "label": "Soundcheck row",
            "elements": [
                {"kind": "fixed_audio", "label": "Audio box", "source_labels": ["Inhale", "Pink"], "randomized": True},
            ],
        }
    ]

    for label in ("Inhale", "Pink"):
        preview = client.post("/api/audio/preview-source", json={"design": custom["design"], "label": label}).json()

        assert preview["label"] == label
        assert preview["local_only"] is True
        assert preview["auditory_preview_only"] is True
        assert preview["url"].startswith("/api/trial-row-previews/source_")
        assert Path(preview["path"]).exists()
        assert client.get(preview["url"]).status_code == 200


def test_dashboard_rejects_segment2_bake_when_segment1_sources_are_unregistered(tmp_path: Path):
    client = _client(tmp_path)
    custom = client.post("/api/templates/__custom__/load").json()
    source_dir = tmp_path / "loose_sources"
    source_dir.mkdir()
    inhale = source_dir / "inhale.wav"
    looming = source_dir / "pink.wav"
    sf.write(inhale, np.zeros((32, 2), dtype=np.float32), 44100)
    sf.write(looming, np.zeros((32, 2), dtype=np.float32), 44100)
    custom["design"]["noises"] = [{"label": "Pink", "noise_type": "pink", "prebaked_path": str(looming)}]
    custom["design"]["prestimulus_files"] = [
        {
            "label": "Inhale",
            "path": str(inhale),
            "target_duration_s": 0.001,
            "render_mode": "preserve",
            "motion_mode": "stationary",
        }
    ]
    custom["design"]["protocol"]["trial_strips"] = [
        {
            "strip_id": "row-1",
            "label": "Inhale pink",
            "elements": [
                {"kind": "fixed_audio", "label": "Audio box", "source_labels": ["Inhale"], "randomized": True},
                {"kind": "looming_stimulus", "label": "Audio box", "source_labels": ["Pink"], "randomized": True},
            ],
        }
    ]

    job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "",
            "design": custom["design"],
            "bake_recipe": {"kind": "trial_sequence_batch", "label": "2_trial_sequence_designs"},
        },
    ).json()
    done = _wait_job(client, job["job_id"])

    assert done["status"] == "failed"
    assert "Segment 1" in done["error"]


def test_dashboard_rejects_segment3_bake_before_segment2_manifest(tmp_path: Path):
    client = _client(tmp_path)
    custom = client.post("/api/templates/__custom__/load").json()
    sample_rate = 44100
    custom["design"]["name"] = "Segment 3 missing upstream"
    custom = client.post("/api/design", json={"design": custom["design"]}).json()
    inhale = _register_segment1_wav(
        client,
        custom["design"],
        "Inhale",
        np.zeros((64, 2), dtype=np.float32),
        sample_rate=sample_rate,
        motion_mode="stationary",
        source_kind="test_fixed_audio",
    )
    looming = _register_segment1_wav(
        client,
        custom["design"],
        "Pink",
        np.zeros((64, 2), dtype=np.float32),
        sample_rate=sample_rate,
        motion_mode="looming",
        source_kind="test_looming_audio",
    )
    custom["design"]["noises"] = [{"label": "Pink", "noise_type": "pink", "prebaked_path": str(looming)}]
    custom["design"]["prestimulus_files"] = [
        {"label": "Inhale", "path": str(inhale), "target_duration_s": 0.001, "render_mode": "preserve", "motion_mode": "stationary"}
    ]
    custom["design"]["protocol"]["soa_values_ms"] = [10]
    custom["design"]["protocol"]["trial_strips"] = [
        {
            "strip_id": "row-1",
            "label": "Inhale pink",
            "elements": [
                {"kind": "fixed_audio", "label": "Audio box", "source_labels": ["Inhale"], "randomized": True},
                {"kind": "looming_stimulus", "label": "Audio box", "source_labels": ["Pink"], "randomized": True},
            ],
        }
    ]

    job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": custom["design"],
            "bake_recipe": {"kind": "audiotactile_trial_batch", "label": "3_tactile_and_baseline_trials"},
        },
    ).json()
    done = _wait_job(client, job["job_id"])

    assert done["status"] == "failed"
    assert "Bake Segment 2" in done["error"]


def test_dashboard_bakes_baseline_tactile_trial_files_with_three_channels(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    custom = client.post("/api/templates/__custom__/load").json()
    sample_rate = 44100
    fixed_frames = int(0.05 * sample_rate)
    looming_frames = int(0.30 * sample_rate)

    custom["design"]["name"] = "Segment 3 trial file bake"
    custom = client.post("/api/design", json={"design": custom["design"]}).json()
    inhale = _register_segment1_wav(
        client,
        custom["design"],
        "Inhale",
        np.ones((fixed_frames, 2), dtype=np.float32) * 0.25,
        sample_rate=sample_rate,
        motion_mode="stationary",
        source_kind="test_fixed_audio",
    )
    looming = _register_segment1_wav(
        client,
        custom["design"],
        "Pink",
        np.ones((looming_frames, 2), dtype=np.float32) * 0.5,
        sample_rate=sample_rate,
        motion_mode="looming",
        source_kind="test_looming_audio",
    )
    custom["design"]["noises"] = [{"label": "Pink", "noise_type": "pink", "prebaked_path": str(looming)}]
    custom["design"]["prestimulus_files"] = [
        {
            "label": "Inhale",
            "path": str(inhale),
            "target_duration_s": fixed_frames / sample_rate,
            "render_mode": "preserve",
            "motion_mode": "stationary",
        }
    ]
    custom["design"]["protocol"]["soa_values_ms"] = [10, 50]
    custom["design"]["protocol"]["spatial_values_cm"] = [100.0]
    custom["design"]["protocol"]["include_baseline_trials"] = True
    custom["design"]["protocol"]["baseline_strategy"] = "tactile_only"
    custom["design"]["protocol"]["baseline_trial_percentage"] = 0.0
    custom["design"]["protocol"]["trial_strips"] = [
        {
            "strip_id": "row-1",
            "label": "Inhale pink",
            "elements": [
                {"kind": "fixed_audio", "label": "Audio box", "source_labels": ["Inhale"], "randomized": True},
                {"kind": "looming_stimulus", "label": "Audio box", "source_labels": ["Pink"], "randomized": True},
            ],
        }
    ]

    sequence_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": custom["design"],
            "bake_recipe": {"kind": "trial_sequence_batch", "label": "2_trial_sequence_designs"},
        },
    ).json()
    sequence_done = _wait_job(client, sequence_job["job_id"])
    assert sequence_done["status"] == "succeeded"

    job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": custom["design"],
            "bake_recipe": {"kind": "audiotactile_trial_batch", "label": "3_tactile_and_baseline_trials"},
        },
    ).json()
    done = _wait_job(client, job["job_id"])

    assert done["status"] == "succeeded"
    result = done["result"]
    assert result["audio_tactile_count"] == 2
    assert result["baseline_count"] == 2
    assert result["catch_count"] == 0
    root = Path(result["root"])
    assert root.parts[-1] == "3_tactile_and_baseline_trials"
    assert dashboard_app._path_exists(root / "row_01__inhale_pink" / "target_audio_tactile")
    assert dashboard_app._path_exists(root / "row_01__inhale_pink" / "baseline")

    manifest = json.loads(dashboard_app._read_text_file(result["manifest_path"], encoding="utf-8"))
    assert manifest["schema"] == "pps-baseline-tactile-trials.v1"
    assert manifest["trial_sequence_manifest_sha256"]
    assert manifest["design_signature"]
    assert manifest["channel_role_map"]["3"] == "tactile cue"
    assert manifest["tactile_cue_path"].endswith("assets\\tactile\\default_tactile_cue.wav") or manifest["tactile_cue_path"].endswith("assets/tactile/default_tactile_cue.wav")
    audio_row = next(item for item in manifest["files"] if item["family"] == "audio_tactile" and item["soa_ms"] == 10)
    baseline_row = next(item for item in manifest["files"] if item["family"] == "baseline" and item["soa_ms"] == 10)
    assert Path(audio_row["file_path"]).name.endswith("_ch3.wav")
    assert "row_" not in Path(audio_row["file_path"]).name.lower()
    assert "row_" not in Path(baseline_row["file_path"]).name.lower()
    assert "soa10ms" in Path(audio_row["file_path"]).name
    assert "tac" in Path(audio_row["file_path"]).name
    assert "baseline_silent" in Path(baseline_row["file_path"]).name
    assert audio_row["looming_segment_onset_s"] == pytest.approx(fixed_frames / sample_rate)
    assert audio_row["tactile_onset_s"] == pytest.approx(fixed_frames / sample_rate + 0.010)
    audio, sr = sf.read(dashboard_app._soundfile_path(audio_row["file_path"]), dtype="float32", always_2d=True)
    assert sr == sample_rate
    assert audio.shape[1] == 3
    onset = int(round(audio_row["tactile_onset_s"] * sr))
    assert np.max(np.abs(audio[:onset, 2])) == pytest.approx(0.0)
    assert np.max(np.abs(audio[onset:, 2])) > 0.01

    baseline, baseline_sr = sf.read(dashboard_app._soundfile_path(baseline_row["file_path"]), dtype="float32", always_2d=True)
    assert baseline_sr == sample_rate
    assert baseline.shape[1] == 3
    assert baseline_row["baseline_mode"] == "tactile_only"
    assert baseline_row["channel_role_map"]["3"] == "tactile cue"
    assert np.max(np.abs(baseline[:, :2])) == pytest.approx(0.0)
    assert np.max(np.abs(baseline[:, 2])) > 0.01
    state = client.get("/api/state").json()
    assert state["project_segments"]["2_trial_sequence_designs"]["status"] == "ready"
    assert state["project_segments"]["3_tactile_and_baseline_trials"]["status"] == "ready"
    report = json.loads((Path(state["project"]["profile_dir"]) / "segment_validation_report.json").read_text(encoding="utf-8"))
    assert report["observed"]["3_tactile_and_baseline_trials"]["total_count"] == 4

    trial_files = state["trial_file_bake"]["files"]
    audio_files = [item for item in trial_files if item["family"] == "audio_tactile"]
    baseline_files = [item for item in trial_files if item["family"] == "baseline"]
    pool_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": custom["design"],
            "bake_recipe": {
                "kind": "trial_repetition_pool",
                "label": "4_trial_repetition_pool",
                "default_repetitions": 1,
                "folder_repetitions": {
                    audio_files[0]["folder_key"]: 2,
                    baseline_files[0]["folder_key"]: 3,
                },
                "file_repetition_overrides": {
                    audio_files[0]["file_key"]: 5,
                },
            },
        },
    ).json()
    pool_done = _wait_job(client, pool_job["job_id"])
    assert pool_done["status"] == "succeeded"
    assert pool_done["result"]["total_count"] == 13
    assert pool_done["result"]["audio_tactile_count"] == 7
    assert pool_done["result"]["baseline_count"] == 6
    pool_manifest = json.loads(Path(pool_done["result"]["manifest_path"]).read_text(encoding="utf-8"))
    assert pool_manifest["settings"]["folder_repetitions"][audio_files[0]["folder_key"]] == 2
    assert pool_manifest["settings"]["file_repetition_overrides"][audio_files[0]["file_key"]] == 5
    assert not list(Path(pool_done["result"]["root"]).rglob("*.wav"))
    pool_rows = list(csv.DictReader(Path(pool_done["result"]["csv_path"]).open(encoding="utf-8")))
    assert len(pool_rows) == 13
    assert {"trial_pool_index", "trial_file_path", "configured_repetitions", "duration_ms"} <= set(pool_rows[0])

    custom["design"]["protocol"]["blocks"] = 2
    block_job = client.post(
        "/api/stimulus/bake",
        json={
            "participant_id": "P001",
            "design": custom["design"],
            "bake_recipe": {
                "kind": "block_csv_preview",
                "label": "5_block_csv_preview",
                "block_count": 2,
            },
        },
    ).json()
    block_done = _wait_job(client, block_job["job_id"])
    assert block_done["status"] == "succeeded"
    assert block_done["kind"] == "block_csv_preview"
    assert block_done["result"]["block_count"] == 2
    block_root = Path(block_done["result"]["root"])
    assert block_root.name.startswith("5_")
    block_manifest = json.loads(Path(block_done["result"]["manifest_path"]).read_text(encoding="utf-8"))
    assert block_manifest["schema"] == "pps-block-csv-preview.v1"
    assert block_manifest["source_segment4_manifest_sha256"] == dashboard_app._local_file_sha256(Path(pool_done["result"]["manifest_path"]))
    assert len(block_manifest["blocks"]) == 2
    block_counts = [block["trial_count"] for block in block_manifest["blocks"]]
    assert max(block_counts) - min(block_counts) <= 1
    assert sum(block_counts) == 13
    block_rows = list(csv.DictReader(Path(block_manifest["blocks"][0]["csv_path"]).open(encoding="utf-8")))
    assert {
        "family_color_hex",
        "row_color_hex",
        "soa_color_hex",
        "noise_type",
        "noise_color_hex",
    } <= set(block_rows[0])
    assert "source_lineage" not in block_rows[0]
    state = client.get("/api/state").json()
    assert state["project_segments"]["5_block_csv_preview"]["status"] == "ready"
    assert state["project_segments"]["5_block_csv_preview"]["accepted"] is False
    assert state["block_csv_preview"]["blocks"][0]["preview_rows"][0]["family_color_hex"].startswith("#")

    blocked_prepare = client.post("/api/session/prepare", json={"participant_id": "P001", "design": custom["design"]})
    assert blocked_prepare.status_code == 400
    assert "Accept Segment 5 block CSVs" in blocked_prepare.json()["detail"]

    accepted_response = client.post("/api/block-csv/accept", json={})
    assert accepted_response.status_code == 200
    accepted = accepted_response.json()
    assert accepted["project_segments"]["5_block_csv_preview"]["accepted"] is True
    assert accepted["custom_workflow"]["ready_to_render"] is True
    assert accepted["custom_workflow"]["ready_to_prepare"] is False
    assert accepted["custom_workflow"]["current_step"] == "run"
    assert "Prepare Segment 6 experiment." in accepted["custom_workflow"]["missing"]
    accepted_manifest = json.loads(Path(block_done["result"]["manifest_path"]).read_text(encoding="utf-8"))
    assert all(block["csv_file_name"].endswith("_final.csv") for block in accepted_manifest["blocks"])
    assert all(Path(block["csv_path"]).name.endswith("_final.csv") for block in accepted_manifest["blocks"])
    assert not (block_root / "block_01.csv").exists()
    assert (block_root / "block_01_final.csv").exists()

    blocked_regenerate = client.post(
        "/api/stimulus/bake",
        json={
            "bake_recipe": {
                "kind": "block_csv_preview",
                "label": "5_block_csv_preview",
                "block_count": 2,
            },
        },
    )
    assert blocked_regenerate.status_code == 400
    assert "Edit Blocks" in blocked_regenerate.json()["detail"]

    edit_response = client.post("/api/block-csv/edit")
    assert edit_response.status_code == 200
    edited = edit_response.json()
    assert edited["project_segments"]["5_block_csv_preview"]["accepted"] is False
    edited_manifest = json.loads(Path(block_done["result"]["manifest_path"]).read_text(encoding="utf-8"))
    assert all(not block["csv_file_name"].endswith("_final.csv") for block in edited_manifest["blocks"])
    assert (block_root / "block_01.csv").exists()
    assert not (block_root / "block_01_final.csv").exists()

    accepted_response = client.post("/api/block-csv/accept", json={})
    assert accepted_response.status_code == 200
    accepted = accepted_response.json()
    assert accepted["project_segments"]["5_block_csv_preview"]["accepted"] is True

    custom["design"]["protocol"]["participants"] = 2
    run_preview = client.post(
        "/api/run-sequence/preview",
        json={
            "design": custom["design"],
            "run_setup": {"experiment_structure": "pre_post"},
        },
    ).json()
    assert run_preview["run_sequence_setup"]["experiment_structure"] == "pre_post"
    assert run_preview["run_sequence_setup"]["participant_count"] == 2
    assert run_preview["run_sequence_setup"]["parts_per_participant"] == 2
    assert run_preview["run_sequence_setup"]["blocks_per_part"] == 2
    assert run_preview["run_sequence_setup"]["total_block_runs"] == 8
    assert len(run_preview["run_sequence_setup"]["rows"]) == 4
    assert {row["part"] for row in run_preview["run_sequence_setup"]["rows"]} == {"Condition 1", "Condition 2"}

    optional_instruction_profile = {
        "schema": "pps-run-instructions.v1",
        "slots": [
            {
                "slot": "before_experiment",
                "label": "Optional empty start message",
                "enabled": True,
                "required": False,
                "path": "",
                "continue_mode": "delay",
                "delay_s": 0.0,
            }
        ],
    }
    run_prepare = client.post(
        "/api/run-sequence/prepare",
        json={
            "design": custom["design"],
            "run_setup": {
                "experiment_structure": "pre_post",
                "seed": run_preview["run_sequence_setup"]["seed"],
                "instruction_profile": optional_instruction_profile,
            },
        },
    )
    assert run_prepare.status_code == 200
    run_prepared = run_prepare.json()
    assert run_prepared["project_segments"]["6_experiment_run_setup"]["status"] == "ready"
    assert run_prepared["custom_workflow"]["ready_to_prepare"] is True
    run_manifest = Path(run_prepared["run_sequence_setup"]["manifest_path"])
    run_csv = Path(run_prepared["run_sequence_setup"]["csv_path"])
    assert run_manifest.is_file()
    assert run_csv.is_file()
    run_manifest_payload = json.loads(run_manifest.read_text(encoding="utf-8"))
    assert "Optional instruction clip 'Optional empty start message' has no audio file" in run_manifest_payload["instruction_profile_warnings"][0]
    prepared_instruction_slots = {slot["slot"]: slot for slot in run_manifest_payload["instruction_profile"]["slots"]}
    assert prepared_instruction_slots["before_experiment"]["enabled"] is True
    assert prepared_instruction_slots["before_experiment"]["required"] is False
    assert prepared_instruction_slots["before_experiment"]["path"] == ""
    run_rows = list(csv.DictReader(run_csv.open(encoding="utf-8")))
    assert len(run_rows) == 8
    assert {row["phase"] for row in run_rows} == {"pre", "post"}
    assert {row["phase_label"] for row in run_rows} == {"Condition 1", "Condition 2"}
    assert all(row["block_csv_file"].endswith("_final.csv") for row in run_rows)

    saved_response = client.post("/api/profiles/save-prepared", json={"name": "My Lab Pilot"})
    assert saved_response.status_code == 200, saved_response.text
    saved = saved_response.json()
    saved_result = saved["saved_profile_result"]
    assert saved_result["profile_id"].startswith("custom_my_lab_pilot_")
    assert saved_result["source_profile_id"]
    saved_project_dir = Path(saved_result["project_dir"])
    assert saved_project_dir.is_dir()
    saved_manifest = json.loads((saved_project_dir / "0_profile" / "project_manifest.json").read_text(encoding="utf-8"))
    assert saved_manifest["project_label"] == "My Lab Pilot"
    assert saved_manifest["source_profile_id"] == saved_result["source_profile_id"]
    saved_run_manifest = saved_project_dir / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    assert saved_run_manifest.is_file()
    saved_run_payload = json.loads(saved_run_manifest.read_text(encoding="utf-8"))
    assert str(saved_project_dir) in saved_run_payload["csv_path"]
    assert str(run_manifest.parent.parent) not in saved_run_payload["csv_path"]
    catalog = client.get("/api/profile-catalog").json()
    catalog_entry = next(item for item in catalog["entries"] if item["profile_id"] == saved_result["profile_id"])
    assert catalog_entry["kind"] == "custom"
    assert catalog_entry["display_name"] == "My Lab Pilot"
    assert catalog_entry["segment_6_ready"] is True

    export_response = client.post("/api/run-sequence/export-bridge", json={"participant_id": "P001"})
    assert export_response.status_code == 200, export_response.text
    exported = export_response.json()["output_folder_export_result"]
    bridge_path = Path(exported["bridge_manifest_path"])
    metadata_dir = output_metadata_dir(tmp_path / "sessions")
    project_state_dir = output_project_state_dir(tmp_path / "sessions")
    profile_snapshot_dir = output_profile_snapshot_dir(tmp_path / "sessions")
    assert bridge_path.parent == project_state_dir
    assert bridge_path.name == "dashboard_runner_bridge_manifest.v1.json"
    assert bridge_path.is_file()
    bridge_payload = dashboard_app._load_json(bridge_path)
    assert bridge_payload["profile_id"] == saved_result["profile_id"]
    assert bridge_payload["kind"] == "custom"
    assert bridge_payload["participant_id"] == "P001"
    snapshot_dir = Path(bridge_payload["acquisition_profile_snapshot_dir"])
    assert snapshot_dir.is_dir()
    assert snapshot_dir.parent == profile_snapshot_dir
    assert (snapshot_dir / "6_experiment_run_setup" / "experiment_run_setup_manifest.json").is_file()
    settings_path = tmp_path / "dashboard_projects" / "dashboard_state" / "focus_runner_settings.v1.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["active_output_folder"] == str(tmp_path / "sessions")
    assert settings["active_profile_id"] == saved_result["profile_id"]
    diary = project_state_dir / "output_diary.v1.jsonl"
    diary_events = [json.loads(line) for line in diary.read_text(encoding="utf-8").splitlines()]
    assert {event["event_type"] for event in diary_events} >= {"profile_saved", "acquisition_folder_exported"}
    assert all("participant_name" not in event for event in diary_events)
    assert not (tmp_path / "sessions" / "output_diary.v1.jsonl").exists()
    assert not (tmp_path / "sessions" / "dashboard_runner_bridge_manifest.v1.json").exists()
    assert not (tmp_path / "sessions" / "study_profile_snapshot").exists()

    prepared_design = saved["design"]
    prepared_response = client.post("/api/session/prepare", json={"participant_id": "P001", "design": prepared_design})
    assert prepared_response.status_code == 200, prepared_response.text
    prepared = prepared_response.json()
    assert prepared["session"]["blocks"][0]["metadata"]["execution_mode"] == "participant_block_wavs"
    block_manifest = Path(prepared["session"]["blocks"][0]["manifest_path"])
    block_rows = list(csv.DictReader(block_manifest.open(encoding="utf-8")))
    assert "Trial_File_Path" in block_rows[0]
    assert any("target_audio_tactile" in row["Trial_File_Path"] for row in block_rows)
    assert any("baseline" in row["Trial_File_Path"] for row in block_rows)

    runner_calls = []
    packaged_runner = tmp_path / "PPSExperimentRunner.exe"
    packaged_runner.write_bytes(b"runner")
    monkeypatch.setenv("PPS_FOCUS_RUNNER_EXE", str(packaged_runner))

    class FakeRunnerProcess:
        pid = 2468

    monkeypatch.setattr(
        dashboard_app.subprocess,
        "Popen",
        lambda args, **kwargs: runner_calls.append((args, kwargs)) or FakeRunnerProcess(),
    )
    runner_launch = client.post(
        "/api/run-sequence/open-runner",
        json={
            "design": prepared_design,
            "run_setup": {
                "experiment_structure": "pre_post",
                "seed": run_preview["run_sequence_setup"]["seed"],
                "instruction_profile": {
                    "schema": "pps-run-instructions.v1",
                    "slots": [
                        {
                            "slot": "before_experiment",
                            "label": "Changed optional instruction after prepare",
                            "enabled": True,
                            "required": False,
                            "path": "missing_optional_instruction.wav",
                            "continue_mode": "click",
                        }
                    ],
                },
            },
            "capture_options": {
                "enable_lsl": False,
                "write_internal_xdf": False,
                "write_analysis_csvs": True,
                "start_backup_recording": False,
                "enable_missed_trial_topup": True,
            },
        },
    )
    assert runner_launch.status_code == 200
    runner_state = runner_launch.json()
    launch_result = runner_state["experiment_runner_launch_result"]
    assert launch_result["pid"] == 2468
    assert launch_result["local_only"] is True
    assert launch_result["runner"] == "PPSExperimentRunner.exe"
    assert launch_result["packaged_runner"] is True
    assert launch_result["runner_binary"] == str(packaged_runner)
    assert launch_result["execution_mode"] == "participant_block_wavs"
    assert launch_result["command"][0] == str(packaged_runner)
    assert "peripersonal_space_toolkit.focus_app" not in launch_result["command"]
    assert "--session-manifest" in launch_result["command"]
    assert "--manual-start" in launch_result["command"]
    assert "--no-lsl" not in launch_result["command"]
    assert "--no-internal-xdf" not in launch_result["command"]
    assert "--no-analysis-csv" not in launch_result["command"]
    assert "--no-backup-recording" not in launch_result["command"]
    assert "--enable-missed-trial-topup" not in launch_result["command"]
    assert Path(launch_result["runner_input_manifest"]).name == "session_manifest.json"
    assert Path(launch_result["session_manifest"]).is_file()
    assert Path(launch_result["run_setup_manifest"]).name == "experiment_run_setup_manifest.json"
    assert launch_result["runner_options"] == "collected by PPSExperimentRunner.exe"
    assert runner_calls

    second_prepare = client.post(
        "/api/run-sequence/prepare",
        json={
            "design": prepared_design,
            "run_setup": {"experiment_structure": "pre_post", "seed": run_preview["run_sequence_setup"]["seed"]},
        },
    )
    assert second_prepare.status_code == 400
    assert "already prepared" in second_prepare.json()["detail"]


def test_auditory_only_bake_render_writes_stereo_wav(tmp_path: Path):
    design = _compact_design()
    design_path = tmp_path / "design.json"
    render_dir = tmp_path / "render"
    save_design(design, design_path)

    result = dashboard_app.render_backend.render_design_with_3dti(
        design_path,
        render_dir,
        seed=20250604,
        engine="python-sofa-reference",
        include_tactile=False,
    )

    assert result.wav_paths
    assert sf.info(str(result.wav_paths[0])).channels == 2
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["tactile_events"]["enabled"] is False
    assert manifest["tactile_events"]["count"] == 0
    qc_rows = list(csv.DictReader(result.qc_path.open(encoding="utf-8")))
    assert qc_rows[0]["channels"] == "2"
    assert qc_rows[0]["tactile_events"] == "0"
    assert qc_rows[0]["tactile_channel"] == ""


def test_native_3dti_measured_wav_matches_dashboard_lateral_handoff(tmp_path: Path):
    if not DEFAULT_BACKEND_EXE.exists():
        pytest.skip("Native 3DTI renderer wrapper is not built on this machine.")
    client = _client(tmp_path)
    controls = {
        "start_distance_cm": 50.0,
        "end_distance_cm": 50.0,
        "start_rotation_deg": 270.0,
        "end_rotation_deg": 90.0,
        "movement_duration_s": 0.18,
        "start_hold_s": 0.0,
        "end_hold_s": 0.0,
    }
    design = _compact_design()
    design.name = "Native dashboard lateral measured stress"
    design.noises[0].label = "Native lateral source"
    design.protocol.soa_values_ms = [80]
    design.protocol.spatial_values_cm = [50.0]
    design.protocol.random_seed = 777

    state = client.post(
        "/api/design",
        json={
            "participant_id": "P777",
            "design": design_to_dict(design),
            "trajectory_controls": controls,
        },
    ).json()
    design_path = tmp_path / "native_dashboard_design.json"
    save_design(design_from_dict(state["design"]), design_path)

    result = render_design_with_3dti(
        design_path,
        tmp_path / "native_render",
        seed=design.protocol.random_seed,
        engine="native-3dti",
    )

    assert result.status == "rendered_3dti"
    assert result.exit_code == 0
    assert len(result.wav_paths) == 1
    audio, sample_rate = sf.read(result.wav_paths[0], always_2d=True)
    expected_frames = int(round(controls["movement_duration_s"] * sample_rate))
    assert sample_rate == 44100
    assert audio.shape == (expected_frames, 3)
    assert np.max(np.abs(audio[:, 0])) > 0.01
    assert np.max(np.abs(audio[:, 1])) > 0.01
    assert np.max(np.abs(audio)) < 1.0

    onset = int(round(0.08 * sample_rate))
    assert np.max(np.abs(audio[:onset, 2])) == pytest.approx(0.0)
    assert np.max(np.abs(audio[onset:, 2])) > 0.1

    midpoint = len(audio) // 2
    first_rms = np.sqrt(np.mean(audio[:midpoint, :2] * audio[:midpoint, :2], axis=0))
    second_rms = np.sqrt(np.mean(audio[midpoint:, :2] * audio[midpoint:, :2], axis=0))
    assert first_rms[0] > first_rms[1] * 1.2
    assert second_rms[1] > second_rms[0] * 1.2

    config = json.loads(result.config_path.read_text(encoding="utf-8"))
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert config["design"] == state["design"]
    assert config["trajectory"]["samples"][0]["x_m"] == pytest.approx(-0.5)
    assert config["trajectory"]["samples"][-1]["x_m"] == pytest.approx(0.5)
    assert manifest["render_engine"] == "native-3dti"
    assert manifest["tactile_events"]["count"] == 1
    assert result.tactile_events_path is not None
    assert manifest["tactile_events"]["sha256"] == sha256_file(result.tactile_events_path)
    assert manifest["wav_outputs"][0]["sha256"] == sha256_file(result.wav_paths[0])


def test_dashboard_open_folder_is_local_backend_action(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    wav_path = tmp_path / "rendered" / "looming_pink_frontal.wav"
    calls = []

    class FakeProcess:
        pid = 123

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", lambda args, **_kwargs: calls.append(args) or FakeProcess())
    opened = client.post("/api/local/open-folder", json={"path": str(wav_path)}).json()

    assert opened["local_only"] is True
    assert opened["folder"] == str(wav_path.parent.resolve())
    assert calls

    preload_path = dashboard_app.REPO_ROOT / "assets" / "preloads" / "study5_box_breathing_pps" / "looming_Pink_frontal.wav"
    opened_preload = client.post("/api/local/open-folder", json={"path": str(preload_path)}).json()
    assert opened_preload["local_only"] is True
    assert opened_preload["folder"] == str(preload_path.parent.resolve())


def test_custom_audio_render_mode_reaches_render_config(tmp_path: Path):
    source = tmp_path / "dry_tone.wav"
    sf.write(source, np.zeros((441, 1), dtype=np.float32), 44100)
    design = _compact_design()
    design.noises = []
    design.custom_looming_files = [
        AudioFileSpec(
            label="Dry local tone",
            path=str(source),
            target_duration_s=4.0,
            render_mode="spatialize",
            gain=0.75,
            sequence_order=2,
            motion_mode="stationary",
        )
    ]

    config = build_render_config(design, seed=20250604, output_dir=tmp_path)

    assert config["source"]["type"] == "imported_audio"
    imported = config["source"]["noises"][0]
    assert imported["source_kind"] == "imported_audio"
    assert imported["source_render_mode"] == "spatialize"
    assert imported["path"] == str(source)
    assert imported["gain"] == 0.75
    component = config["source"]["stimulus_assembly"]["components"][0]
    assert component["component_kind"] == "custom_audio"
    assert component["sequence_order"] == 2
    assert component["motion_mode"] == "stationary"


def test_dashboard_render_job_uses_existing_render_backend(tmp_path: Path, monkeypatch):
    client = _client(tmp_path)
    controls = {
        "start_distance_cm": 140.0,
        "end_distance_cm": 35.0,
        "start_rotation_deg": 315.0,
        "end_rotation_deg": 30.0,
        "movement_duration_s": 2.25,
        "start_hold_s": 0.15,
        "end_hold_s": 0.25,
    }
    expected_start = point_from_distance_rotation_height(140.0, 315.0, 0.0)
    expected_end = point_from_distance_rotation_height(35.0, 30.0, 0.0)
    design = _compact_design()
    design.name = "Render endpoint current GUI controls"
    design.protocol.random_seed = 5151

    def fake_render(design_path, output_dir, *, seed, **_kwargs):
        design_data = json.loads(Path(design_path).read_text(encoding="utf-8"))
        manifest = Path(output_dir) / "render_manifest.json"
        qc = Path(output_dir) / "render_qc.csv"
        tactile = Path(output_dir) / "render_tactile_events.csv"
        manifest.write_text(json.dumps({"status": "rendered_reference"}), encoding="utf-8")
        qc.write_text("", encoding="utf-8")
        tactile.write_text("", encoding="utf-8")
        assert seed == 5151
        assert design_data["name"] == "Render endpoint current GUI controls"
        assert design_data["trajectory"]["start_x_m"] == pytest.approx(expected_start["x_m"])
        assert design_data["trajectory"]["start_y_m"] == pytest.approx(expected_start["y_m"])
        assert design_data["trajectory"]["end_x_m"] == pytest.approx(expected_end["x_m"])
        assert design_data["trajectory"]["end_y_m"] == pytest.approx(expected_end["y_m"])
        assert design_data["trajectory"]["padding_pre_s"] == pytest.approx(controls["start_hold_s"])
        assert design_data["trajectory"]["padding_post_s"] == pytest.approx(controls["end_hold_s"])
        return RenderResult("rendered_reference", 0, Path(output_dir), Path(design_path), manifest, qc, wav_paths=(), tactile_events_path=tactile)

    monkeypatch.setattr(dashboard_app.render_backend, "render_design_with_3dti", fake_render)
    job = client.post(
        "/api/render",
        json={
            "participant_id": "P515",
            "design": design_to_dict(design),
            "trajectory_controls": controls,
        },
    ).json()
    done = _wait_job(client, job["job_id"])

    assert done["status"] == "succeeded"
    assert done["result"]["status"] == "rendered_reference"
    assert done["result"]["exit_code"] == 0


def test_dashboard_prepare_session_requires_packaged_runner_exe(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(focus_launch.FOCUS_RUNNER_ENV_VAR, raising=False)
    monkeypatch.setattr(focus_launch, "DEFAULT_PACKAGED_FOCUS_RUNNER", tmp_path / "missing.exe")
    client = _client(tmp_path)

    prepared = client.post("/api/session/prepare", json={"participant_id": "P001"}).json()
    assert prepared["session"]["session_id"].startswith("P001_")
    assert prepared["session"]["blocks"]

    response = client.post("/api/focus/start")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "PPSExperimentRunner.exe" in detail
    assert "Build_Experiment_Runner_Exe.ps1" in detail
