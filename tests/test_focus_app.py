from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import soundfile as sf

from peripersonal_space_toolkit.focus_layout import (
    focus_palette_contrast_report,
    render_focus_layout_profile,
)
from peripersonal_space_toolkit.output_layout import (
    output_metadata_dir,
    output_profile_snapshot_dir,
    output_project_state_dir,
    output_runner_logs_dir,
)
from peripersonal_space_toolkit.session_runner import RUN_PACKAGE_SCHEMA, SessionCaptureOptions, load_run_package


def _write_minimal_session_manifest(
    tmp_path: Path,
    *,
    participant_id: str = "P001",
    source_run_setup_manifest_path: Path | None = None,
    blocks: list[dict[str, object]] | None = None,
) -> Path:
    session_dir = tmp_path / f"{participant_id}_20260613_120000"
    session_dir.mkdir()
    manifest_path = session_dir / "session_manifest.json"
    payload = {
        "schema": RUN_PACKAGE_SCHEMA,
        "participant_id": participant_id,
        "session_id": f"{participant_id}_20260613_120000",
        "created_at": "2026-06-13T12:00:00",
        "design_path": "design.json",
        "protocol_path": "protocol_schedule.csv",
        "render_manifest_path": "",
        "execution_mode": "participant_block_wavs",
        "blocks": blocks or [],
    }
    if source_run_setup_manifest_path is not None:
        payload["source_run_setup_manifest_path"] = str(source_run_setup_manifest_path)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def test_validation_start_gate_waits_for_ready_file(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    ready_file = tmp_path / "external_labrecorder.ready"
    records: list[dict[str, object]] = []
    state: dict[str, object] = {}
    monkeypatch.setenv("PPS_FOCUS_VALIDATION_START_READY_FILE", str(ready_file))
    monkeypatch.setenv("PPS_FOCUS_VALIDATION_START_READY_TIMEOUT_S", "10")

    assert not focus_app._validation_start_gate_ready(records, state, source="test")
    ready_file.write_text("ready\n", encoding="utf-8")
    assert focus_app._validation_start_gate_ready(records, state, source="test")

    labels = [str(record["label"]) for record in records]
    assert labels == ["start_gate_waiting", "start_gate_released"]


def _collect_widget_texts(widget, widget_type) -> list[str]:
    texts: list[str] = []
    for child in widget.findChildren(widget_type):
        if hasattr(child, "text"):
            try:
                text = child.text()
            except TypeError:
                text = ""
            if text:
                texts.append(str(text))
    return texts


def _write_focus_preview_block_csv(path: Path, *, block_offset: int = 0) -> None:
    path.write_text(
        "\n".join(
            [
                "Trial_Number,Trial_UID,Trial_Type,Family,Row_Label,Fixed_Audio_Labels,SOA_ms,Trial_Start_S,Trial_End_S,Tactile_Onset_S,Sample_Rate_Hz",
                f"1,T{block_offset + 1:03d},Audio-Tactile,audio_tactile,Inhale,Frontal looming,300,0.0,8.0,4.3,1000",
                f"2,T{block_offset + 2:03d},Baseline,baseline,Exhale,Baseline,800,8.0,16.0,8.8,1000",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_focus_preview_session_manifest(tmp_path: Path) -> Path:
    block_1_csv = tmp_path / "block_01.csv"
    block_2_csv = tmp_path / "block_02.csv"
    block_3_csv = tmp_path / "block_03.csv"
    _write_focus_preview_block_csv(block_1_csv)
    _write_focus_preview_block_csv(block_2_csv, block_offset=10)
    _write_focus_preview_block_csv(block_3_csv, block_offset=20)
    blocks = [
        {
            "index": 1,
            "label": "Block 01",
            "manifest_path": str(block_1_csv),
            "wav_path": str(tmp_path / "block_01.wav"),
            "trial_count": 2,
            "duration_s": 16.0,
            "metadata": {"part_number": 1, "phase": "pre", "phase_label": "Condition 1", "sample_rate_hz": 1000},
        },
        {
            "index": 2,
            "label": "Block 02",
            "manifest_path": str(block_2_csv),
            "wav_path": str(tmp_path / "block_02.wav"),
            "trial_count": 2,
            "duration_s": 16.0,
            "metadata": {"part_number": 1, "phase": "pre", "phase_label": "Condition 1", "sample_rate_hz": 1000},
        },
        {
            "index": 3,
            "label": "Block 03",
            "manifest_path": str(block_3_csv),
            "wav_path": str(tmp_path / "block_03.wav"),
            "trial_count": 2,
            "duration_s": 16.0,
            "metadata": {"part_number": 2, "phase": "post", "phase_label": "Condition 2", "sample_rate_hz": 1000},
        },
    ]
    manifest = _write_minimal_session_manifest(tmp_path, blocks=blocks)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["instruction_profile"] = {
        "schema": "pps-run-instructions.v1",
        "slots": [
            {"slot": "before_experiment", "label": "General", "enabled": True, "path": "general.wav", "duration_s": 85.7, "continue_mode": "button"},
            {"slot": "before_block", "label": "Pre-Block", "enabled": True, "path": "pre_block.wav", "duration_s": 8.4, "continue_mode": "click"},
            {"slot": "after_block", "label": "Post-Block", "enabled": True, "path": "post_block.wav", "duration_s": 8.8, "continue_mode": "click"},
            {"slot": "between_conditions", "label": "Interim", "enabled": True, "path": "interim.wav", "duration_s": 10.1, "continue_mode": "button"},
            {"slot": "after_experiment", "label": "Finish", "enabled": True, "path": "finish.wav", "duration_s": 7.0, "continue_mode": "button"},
        ],
    }
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _write_analysis_review_outputs(session_dir: Path) -> dict[str, Path]:
    analysis_dir = session_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    session_id = session_dir.name
    scope = "Part 1 / Inhale / pink"
    pooled_scope = "All parts / Inhale / pink"
    curves = analysis_dir / f"{session_id}_pps_curve_points.csv"
    curves.write_text(
        "\n".join(
            [
                "scope,aggregation_mode,aggregation_label,soa_ms,fit_metric,facilitation_ms,facilitation_sem_ms,mean_rt_ms,n",
                f"{scope},separate_parts,Separate parts,100,facilitation_ms,10,2,320,3",
                f"{scope},separate_parts,Separate parts,200,facilitation_ms,20,3,300,3",
                f"{scope},separate_parts,Separate parts,400,facilitation_ms,35,4,280,3",
                f"{scope},separate_parts,Separate parts,800,facilitation_ms,44,3,260,3",
                f"{pooled_scope},pooled_parts,Pool parts,100,facilitation_ms,12,2,318,6",
                f"{pooled_scope},pooled_parts,Pool parts,200,facilitation_ms,22,3,298,6",
                f"{pooled_scope},pooled_parts,Pool parts,400,facilitation_ms,34,4,282,6",
                f"{pooled_scope},pooled_parts,Pool parts,800,facilitation_ms,43,3,262,6",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fits = analysis_dir / f"{session_id}_model_fits.csv"
    fits.write_text(
        "\n".join(
            [
                "scope,aggregation_mode,aggregation_label,model,fit_metric,n_points,intercept,slope,log_slope,lower,upper,pps_boundary_soa_ms,aic,r2,rmse",
                f"{scope},separate_parts,Separate parts,linear,facilitation_ms,4,8,0.05,, ,,,14,0.91,2.0",
                f"{scope},separate_parts,Separate parts,logarithmic_decay,facilitation_ms,4,-12,,8,,,,12,0.94,1.6",
                f"{scope},separate_parts,Separate parts,sigmoid,facilitation_ms,4,,0.01,,5,50,300,10,0.97,1.1",
                f"{pooled_scope},pooled_parts,Pool parts,linear,facilitation_ms,4,9,0.047,,,,,13,0.92,1.9",
                f"{pooled_scope},pooled_parts,Pool parts,logarithmic_decay,facilitation_ms,4,-10,,7,,,,11,0.94,1.5",
                f"{pooled_scope},pooled_parts,Pool parts,sigmoid,facilitation_ms,4,,0.009,,4,48,320,9,0.98,1.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    comparison = analysis_dir / f"{session_id}_model_fit_comparison.csv"
    comparison.write_text(
        "scope,aggregation_mode,aggregation_label,best_model,best_aic,best_r2,fit_metric,n_points\n"
        f"{scope},separate_parts,Separate parts,sigmoid,10,0.97,facilitation_ms,4\n"
        f"{pooled_scope},pooled_parts,Pool parts,sigmoid,9,0.98,facilitation_ms,4\n",
        encoding="utf-8",
    )
    summary = analysis_dir / f"{session_id}_summary.csv"
    summary.write_text(
        "scope,aggregation_mode,n,hit_rate\n"
        f"{scope},separate_parts,4,1.0\n"
        f"{pooled_scope},pooled_parts,8,1.0\n",
        encoding="utf-8",
    )
    behavior = analysis_dir / "data_behavior_by_scope.csv"
    behavior.write_text(
        "scope,aggregation_mode,signal,feature,message,evidence\n"
        f"{scope},separate_parts,Expected pattern,RT or facilitation by SOA/distance,The recording has enough SOA points for common PPS curve review,points=4\n"
        "Session,,Technical caveat,Timing evidence,Timing evidence is available for review,timing_qc_rows=1\n",
        encoding="utf-8",
    )
    behavior_summary = analysis_dir / "exploratory_quality_summary.json"
    behavior_summary.write_text(
        json.dumps(
            {
                "schema": "pps-exploratory-data-behavior.v1",
                "interpretation_note": "Exploratory data-behavior signals are not scientific conclusions or participant-readiness certification.",
                "signal_counts": {"Expected pattern": 1, "Technical caveat": 1},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (session_dir / "analysis_summary.txt").write_text("Tactile trials reconstructed: 4\n", encoding="utf-8")
    return {
        "curves": curves,
        "model_fits": fits,
        "model_fit_comparison": comparison,
        "summary": summary,
        "data_behavior_by_scope": behavior,
        "exploratory_quality_summary": behavior_summary,
    }


def test_focus_mode_run_plan_numbers_topup_slots_by_play_order():
    from peripersonal_space_toolkit import focus_app

    package = SimpleNamespace(
        blocks=[
            SimpleNamespace(
                index=index,
                label=f"Block {index:02d}",
                duration_s=1.0,
                metadata={"part_number": 1 if index <= 6 else 2},
            )
            for index in range(1, 13)
        ]
    )

    plan = focus_app._run_plan_text(package, include_topup_slots=True)

    assert "Part 01:" in plan
    assert "6 Block 06" in plan
    assert "7 Top-up if needed" in plan
    assert "Part 02:" in plan
    assert "1 Block 07" in plan
    assert "6 Block 12" in plan
    assert "7 Top-up if needed" in plan
    assert focus_app._run_plan_total(package, include_topup_slots=True) == 14


def _assert_widget_inside_dialog(widget, dialog) -> None:
    top_left = widget.mapTo(dialog, widget.rect().topLeft())
    bottom_right = widget.mapTo(dialog, widget.rect().bottomRight())
    assert top_left.x() >= 0
    assert top_left.y() >= 0
    assert bottom_right.x() <= dialog.width()
    assert bottom_right.y() <= dialog.height()
    assert widget.visibleRegion().boundingRect().width() > 0
    assert widget.visibleRegion().boundingRect().height() > 0


def _widget_rect(widget, dialog) -> dict[str, int]:
    top_left = widget.mapTo(dialog, widget.rect().topLeft())
    bottom_right = widget.mapTo(dialog, widget.rect().bottomRight())
    return {
        "x": int(top_left.x()),
        "y": int(top_left.y()),
        "right": int(bottom_right.x()),
        "bottom": int(bottom_right.y()),
        "width": int(widget.width()),
        "height": int(widget.height()),
    }


def test_focus_layout_renderer_preserves_legibility_baselines():
    constrained = render_focus_layout_profile(1024, 600)
    compact = render_focus_layout_profile(1366, 768)
    standard = render_focus_layout_profile(1920, 1080)

    assert constrained.screen_class == "constrained"
    assert compact.screen_class in {"compact", "standard"}
    assert standard.screen_class == "spacious"
    assert constrained.window_width <= 1024
    assert constrained.window_height <= 600
    assert constrained.body_font_pt >= 10.5
    assert constrained.button_min_height >= 30
    assert constrained.response_panel_side >= constrained.target_min_height
    assert constrained.target_min_height >= 76
    assert constrained.target_max_height == constrained.target_min_height
    assert constrained.experiment_control_min_height >= 152
    assert compact.experiment_control_min_height >= 212
    assert standard.experiment_control_min_height >= 280
    assert constrained.experiment_control_min_height >= constrained.experiment_control_content_min_height
    assert compact.experiment_control_min_height >= compact.experiment_control_content_min_height
    assert standard.experiment_control_min_height >= standard.experiment_control_content_min_height
    assert constrained.experiment_control_initial_height >= constrained.experiment_control_min_height
    assert compact.experiment_control_initial_height > constrained.experiment_control_initial_height
    assert standard.experiment_control_initial_height > compact.experiment_control_initial_height
    for width, height in ((1920, 1000), (1600, 900), (1536, 864), (1366, 768)):
        laptop = render_focus_layout_profile(width, height)
        assert laptop.experiment_control_initial_height >= laptop.experiment_control_content_min_height
        assert laptop.experiment_control_min_height >= laptop.experiment_control_content_min_height
    assert constrained.right_stack_mode == "tabs"
    assert compact.right_stack_mode == "resizable"
    assert standard.right_stack_mode == "resizable"
    assert constrained.recording_chip_columns == 2
    assert standard.recording_chip_columns == 3
    assert standard.target_min_height > constrained.target_min_height
    assert standard.target_max_height == standard.target_min_height
    assert standard.response_panel_side > constrained.response_panel_side

    contrasts = focus_palette_contrast_report()
    assert contrasts["text_on_background"] >= 7.0
    assert contrasts["text_on_surface"] >= 7.0
    assert contrasts["muted_on_background"] >= 4.5
    assert contrasts["muted_on_surface"] >= 4.5
    assert contrasts["primary_button_text"] >= 4.5


def test_focus_mode_shell_visual_smoke(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image, ImageStat
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(
            enable_lsl=False,
            write_internal_xdf=True,
            write_analysis_csvs=True,
            start_backup_recording=False,
        ),
        enable_missed_trial_topup=True,
    )
    window_type = q["Qt"].WindowType
    flags = window.dialog.windowFlags()
    assert flags & window_type.WindowSystemMenuHint == window_type.WindowSystemMenuHint
    assert flags & window_type.WindowMinimizeButtonHint == window_type.WindowMinimizeButtonHint
    assert flags & window_type.WindowMaximizeButtonHint == window_type.WindowMaximizeButtonHint
    assert flags & window_type.WindowCloseButtonHint == window_type.WindowCloseButtonHint
    assert window.dialog.isSizeGripEnabled()
    window.dialog.resize(1040, 720)
    window.dialog.show()
    app.processEvents()

    texts = _collect_widget_texts(window.dialog, q["QWidget"])
    joined = "\n".join(texts)
    assert "PPS Experiment Runner" in joined
    assert "Native Focus Mode" in joined
    assert "Part -" in joined
    assert "Participant Response" in joined
    assert "Participant Setup" in joined
    if window.operator_tabs is not None:
        assert window.operator_tabs.tabText(0) == "Data Logging / Experiment Settings"
    else:
        assert "Data Logging / Experiment Settings" in joined
    assert "Data Logging" in joined
    assert "Experiment Control" in joined
    assert "Part 1" in joined
    assert "Part 2" in joined
    if window.layout_profile.screen_class != "constrained":
        assert "Block Order" in joined
        assert "Stimulus / Tactile / Click Timeline" in joined
    assert "Next tactile" in joined
    assert "Instruction clips" in joined
    assert "No preloaded clips" in joined
    assert "Include name in LSL/session markers" in joined
    assert "events.csv on" not in joined
    assert "LSL/event protocol" not in joined
    assert "Save additional fail-safe local recording" in joined
    assert "estimated extra file" in joined
    assert "Record wired loopback from Input 4" in joined
    assert "Top up missed tactile trials at part end" in joined
    assert "CLICK" in joined
    assert window.participant_code_combo.objectName() == "runnerParticipantCombo"
    assert not window.participant_code_combo.isEditable()
    assert window.participant_code_combo.currentData() == "P001"
    assert window.part_buttons["1"].isEnabled()
    assert not window.part_buttons["2"].isEnabled()
    assert window.preview_display_block_index is None
    placeholders = [line.placeholderText() for line in window.dialog.findChildren(q["QLineEdit"])]
    assert "Participant code" not in placeholders
    assert window.include_name_lsl_checkbox.objectName() == "nameSharingCheckbox"
    assert "(opt-in)" in window.include_name_lsl_checkbox.text()
    assert window.include_name_lsl_checkbox.minimumHeight() >= window.layout_profile.button_min_height + 8
    assert window.backup_recording_checkbox.objectName() == "failSafeRecordingCheckbox"
    assert window.wired_loopback_checkbox.objectName() == "wiredLoopbackCheckbox"
    assert not window.wired_loopback_checkbox.isChecked()
    QTest.mouseClick(window.wired_loopback_checkbox, q["Qt"].MouseButton.LeftButton)
    app.processEvents()
    assert window._runtime_capture_options().wired_loopback_mode == "output4_tactile_proxy"
    QTest.mouseClick(window.wired_loopback_checkbox, q["Qt"].MouseButton.LeftButton)
    app.processEvents()
    assert window._runtime_capture_options().wired_loopback_mode == "off"
    assert window.data_columns_widget.objectName() == "dataSettingsColumns"
    assert window.data_logging_column.objectName() == "dataLoggingColumn"
    assert window.experiment_settings_column.objectName() == "experimentSettingsColumn"
    assert "estimated extra file" in window.backup_recording_checkbox.text()
    assert window.response_panel.width() == window.response_panel.height()
    assert window.response_panel.width() == window.layout_profile.response_panel_side
    assert window.output_panel is not window.processing_panel
    assert window.processing_splitter is None
    response_rect = _widget_rect(window.response_panel, window.dialog)
    output_rect = _widget_rect(window.output_panel, window.dialog)
    response_cell_rect = _widget_rect(window.response_cell, window.dialog)
    processing_rect = _widget_rect(window.processing_panel, window.dialog)
    workspace_rect = _widget_rect(window.workspace_splitter, window.dialog)
    assert output_rect["y"] >= response_rect["bottom"]
    assert output_rect["x"] >= response_cell_rect["x"]
    assert output_rect["right"] <= response_cell_rect["right"]
    assert processing_rect["width"] >= workspace_rect["width"] - 8

    screenshot = tmp_path / "focus_mode_shell.png"
    assert window.dialog.grab().save(str(screenshot))
    image = Image.open(screenshot).convert("RGB")
    stat = ImageStat.Stat(image)
    assert image.width >= 900
    assert image.height >= 600
    assert min(stat.stddev) > 2.0

    target_screenshot = tmp_path / "focus_mode_target.png"
    assert window.target_button.grab().save(str(target_screenshot))
    target_image = Image.open(target_screenshot).convert("RGB")
    target_colors = target_image.getcolors(maxcolors=100_000) or []
    assert target_image.width == target_image.height == window.target_button.width()
    assert len(target_colors) >= 4
    assert target_image.getpixel((target_image.width // 2, target_image.height // 2)) != target_image.getpixel((4, 4))
    window.dialog.close()


def test_focus_mode_participant_dropdown_switches_loaded_package(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    run_setup = tmp_path / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    run_setup.parent.mkdir(parents=True)
    run_setup.write_text("{}", encoding="utf-8")
    package_p001 = load_run_package(
        _write_minimal_session_manifest(tmp_path, participant_id="P001", source_run_setup_manifest_path=run_setup)
    )
    package_p002 = load_run_package(
        _write_minimal_session_manifest(tmp_path, participant_id="P002", source_run_setup_manifest_path=run_setup)
    )
    prepared: list[str] = []

    monkeypatch.setattr(focus_app, "segment_run_setup_participants", lambda _path: ["P001", "P002"])
    monkeypatch.setattr(
        focus_app,
        "prepared_session_asset_statuses",
        lambda _path, _participants, **_kwargs: {
            "P001": {
                "participant_id": "P001",
                "generated": True,
                "status": "ready",
                "data_collected": False,
                "message": "Ready.",
            },
            "P002": {
                "participant_id": "P002",
                "generated": True,
                "status": "ready",
                "data_collected": True,
                "data_collection_message": "Completed participant data found.",
                "message": "Ready.",
            },
        },
    )

    def fake_prepare_segment_run_package(run_setup_path, participant_id, **_kwargs):
        assert run_setup_path == run_setup
        prepared.append(participant_id)
        return package_p002

    monkeypatch.setattr(focus_app, "prepare_segment_run_package", fake_prepare_segment_run_package)

    window = focus_app.FocusModeWindow(q, package_p001)
    window.dialog.show()
    app.processEvents()

    combo = window.participant_code_combo
    assert combo.count() == 2
    p002_index = combo.findData("P002")
    assert p002_index >= 0
    assert focus_app.DATA_COLLECTED_MARK in combo.itemText(p002_index)
    assert combo.itemData(p002_index, q["Qt"].ItemDataRole.ForegroundRole) is not None

    combo.setCurrentIndex(p002_index)
    app.processEvents()

    assert prepared == ["P002"]
    assert window.package.participant_id == "P002"
    assert window._runner_metadata()["participant_code"] == "P002"
    assert window.session_participant_value.text() == "P002"
    assert "P002" in window.dialog.windowTitle()
    assert window.participant_name_input.text() == ""
    assert not window.include_name_lsl_checkbox.isChecked()
    assert window.progress_label.text() == "Waiting to start"
    window.dialog.close()


def test_focus_mode_block_plan_click_previews_trial_composition_and_live_bar(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI smoke deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package, enable_missed_trial_topup=True)
    window.dialog.resize(1180, 760)
    window.dialog.show()
    app.processEvents()

    assert window.selected_part_key == "1"
    assert window.part_buttons["1"].isEnabled()
    assert window.part_buttons["2"].isEnabled()
    assert window.preview_display_block_index == 1
    assert [segment.clip_label for segment in window.timeline_preview_state.trial_segments] == ["Inhale", "Exhale"]
    assert [segment.trial_label for segment in window.timeline_preview_state.trial_segments] == ["Audio-tactile", "Baseline"]
    assert [segment.soa_ms for segment in window.timeline_preview_state.trial_segments] == ["300", "800"]
    assert [segment.label for segment in window.timeline_preview_state.instruction_segments] == ["General", "Pre-block", "Post-block"]
    timeline_debug = window.layout_validation_snapshot()["timeline_debug"]
    assert timeline_debug["row_names"] == ["Resp", "Type", "SOA", "Tactile", "Clicks"]
    assert timeline_debug["row_count"] == 5
    assert "Instr" not in timeline_debug["row_names"]
    block_strip_entries = window.block_plan_widget._layout_items()
    instruction_entries = [entry for entry in block_strip_entries if entry.get("entry_kind") == "instruction"]
    assert {entry.get("slot") for entry in instruction_entries} >= {
        "before_experiment",
        "before_each_block",
        "after_each_block",
        "between_conditions",
    }
    assert all(int(entry["width"]) <= 13 for entry in instruction_entries)
    legend_entries = window.instruction_legend_widget._layout_items()
    assert [entry.get("slot") for entry in legend_entries] == [
        "before_experiment",
        "before_each_block",
        "after_each_block",
        "between_conditions",
        "after_experiment",
    ]

    QTest.mouseClick(
        window.block_plan_widget,
        q["Qt"].MouseButton.LeftButton,
        q["Qt"].KeyboardModifier.NoModifier,
        window.block_plan_widget.item_center(1),
    )
    app.processEvents()

    assert window.selected_display_block_index == 1
    assert window.preview_display_block_index == 1
    assert window._timeline_display_state() is window.timeline_preview_state
    assert [segment.clip_label for segment in window.timeline_preview_state.trial_segments] == ["Inhale", "Exhale"]
    assert [segment.trial_label for segment in window.timeline_preview_state.trial_segments] == ["Audio-tactile", "Baseline"]
    assert [segment.soa_ms for segment in window.timeline_preview_state.trial_segments] == ["300", "800"]
    assert [cue.soa_ms for cue in window.timeline_preview_state.cues] == ["300", "800"]
    assert "Block preview: Block 1 | 2 trials | 2 tactile cues" in window.block_preview_label.text()

    QTest.mouseClick(
        window.block_plan_widget,
        q["Qt"].MouseButton.LeftButton,
        q["Qt"].KeyboardModifier.NoModifier,
        window.block_plan_widget.item_center(3),
    )
    app.processEvents()

    assert window.selected_display_block_index == 3
    assert window.preview_display_block_index == 3
    assert not window.timeline_preview_state.trial_segments
    assert "top-up" in window.block_preview_label.text()

    window._handle_topup_draft(
        {
            "ui_event": "topup_draft",
            "missed_trials": [
                {
                    "part_number": "1",
                    "block_number": "1",
                    "trial_number": "2",
                    "trial_uid": "T002",
                    "trial_type": "Baseline",
                    "family": "baseline",
                    "respiratory_phase": "Exhale",
                    "soa_ms": "800",
                }
            ],
        }
    )
    app.processEvents()
    assert len(window._visible_topup_draft_items()) == 1
    assert "1 missed trial(s) in draft" in window.block_preview_label.text()

    QTest.mouseClick(window.part_buttons["2"], q["Qt"].MouseButton.LeftButton)
    app.processEvents()
    assert window.selected_part_key == "2"
    assert [item["part_block_number"] for item in window.block_plan_items] == [1, 2]
    part2_instruction_entries = [entry for entry in window.block_plan_widget._layout_items() if entry.get("entry_kind") == "instruction"]
    assert "after_experiment" in {entry.get("slot") for entry in part2_instruction_entries}
    assert window.preview_display_block_index == 4
    assert "Condition 2" in window.timeline_preview_state.phase_label

    window._handle_block_schedule(
        {
            "part_number": 1,
            "phase_label": "Condition 1",
            "block_index": 1,
            "display_block_index": 1,
            "display_block_count": 3,
            "block_label": "Block 01",
            "duration_s": 16.0,
            "tactile_events": [
                {"trial_number": 1, "trial_uid": "T001", "time_s": 4.3, "soa_ms": "300", "row_label": "Inhale"},
                {"trial_number": 2, "trial_uid": "T002", "time_s": 8.8, "soa_ms": "800", "row_label": "Exhale"},
            ],
            "trial_segments": [
                {
                    "trial_number": 1,
                    "trial_uid": "T001",
                    "start_s": 0.0,
                    "end_s": 8.0,
                    "clip_label": "Inhale",
                    "trial_label": "Audio-tactile",
                    "soa_ms": "300",
                },
                {
                    "trial_number": 2,
                    "trial_uid": "T002",
                    "start_s": 8.0,
                    "end_s": 16.0,
                    "clip_label": "Exhale",
                    "trial_label": "Baseline",
                    "soa_ms": "800",
                },
            ],
        }
    )
    window._update_tactile_progress(5.0)
    app.processEvents()

    assert window.preview_display_block_index is None
    assert window.selected_display_block_index == 1
    assert window._timeline_display_state() is window.timeline_state
    assert [segment.soa_ms for segment in window.timeline_state.trial_segments] == ["300", "800"]
    assert window.progress.value() == int((5.0 / 16.0) * 1000)
    progress_margins = window.progress_track_widget.layout().contentsMargins()
    assert progress_margins.left() == focus_app.TIMELINE_LABEL_WIDTH
    assert progress_margins.right() == focus_app.TIMELINE_RIGHT_MARGIN
    response_click = window.timeline_state.record_click(4.6)
    off_cue_click = window.timeline_state.record_click(8.1)
    assert response_click.response_status == "tactile_response"
    assert off_cue_click.response_status == "off_cue"

    timeline_screenshot = tmp_path / "live_timeline_red_bar.png"
    assert window.tactile_timeline_widget.grab().save(str(timeline_screenshot))
    timeline_image = Image.open(timeline_screenshot).convert("RGB")
    pixels = timeline_image.load()
    red_pixels = sum(
        1
        for y in range(timeline_image.height)
        for x in range(timeline_image.width)
        if pixels[x, y][0] > 150 and pixels[x, y][1] < 70 and pixels[x, y][2] < 70
    )
    assert red_pixels > 60
    timeline_debug = window.tactile_timeline_widget.timeline_debug_snapshot()
    assert timeline_debug["row_names"] == list(focus_app.TIMELINE_ROW_NAMES)
    assert timeline_debug["label_fit"]["drawn"] > 0
    assert timeline_debug["label_fit"]["overlap_count"] == 0
    cue_linked_click_pixels = sum(
        1
        for y in range(timeline_image.height)
        for x in range(timeline_image.width)
        if pixels[x, y][0] < 90 and pixels[x, y][1] > 110 and pixels[x, y][2] < 170
    )
    off_cue_click_pixels = sum(
        1
        for y in range(timeline_image.height)
        for x in range(timeline_image.width)
        if pixels[x, y][0] > 180 and 70 < pixels[x, y][1] < 150 and pixels[x, y][2] < 90
    )
    height = timeline_image.height
    if height < 55:
        tactile_y = 3 + 29
    elif height < 84:
        tactile_y = 3 + 47
    elif height < 96:
        tactile_y = 6 + 59
    else:
        tactile_y = 10 + 91
    cue_band_click_pixels = sum(
        1
        for y in range(max(0, tactile_y - 5), min(timeline_image.height, tactile_y + 6))
        for x in range(timeline_image.width)
        if (
            (pixels[x, y][0] < 90 and pixels[x, y][1] > 110 and pixels[x, y][2] < 170)
            or (pixels[x, y][0] > 180 and 70 < pixels[x, y][1] < 150 and pixels[x, y][2] < 90)
        )
    )
    assert cue_linked_click_pixels > 8
    assert off_cue_click_pixels > 8
    assert cue_band_click_pixels > 8
    window.dialog.close()


@pytest.mark.parametrize("available_width,available_height", [(1024, 600), (1366, 768), (1920, 1080)])
def test_focus_mode_shell_layout_profile_keeps_controls_visible(tmp_path: Path, available_width: int, available_height: int):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    profile = render_focus_layout_profile(available_width, available_height)
    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(
            enable_lsl=False,
            write_internal_xdf=True,
            write_analysis_csvs=True,
            start_backup_recording=False,
        ),
        enable_missed_trial_topup=True,
        layout_profile=profile,
    )
    window.dialog.resize(profile.window_width, profile.window_height)
    window.dialog.show()
    app.processEvents()

    assert window.dialog.width() <= available_width
    assert window.dialog.height() <= available_height
    assert window.target_button.minimumWidth() == profile.target_min_height
    assert window.target_button.maximumWidth() == profile.target_min_height
    assert window.target_button.minimumHeight() == profile.target_min_height
    assert window.target_button.maximumHeight() == profile.target_min_height
    assert window.include_name_lsl_checkbox.minimumHeight() >= profile.button_min_height + 8
    assert window.output_summary.minimumHeight() == profile.output_min_height
    snapshot = window.layout_validation_snapshot()
    content_min = snapshot["experiment_control_debug"]["content_min_height"]
    assert window.processing_panel.minimumHeight() >= profile.experiment_control_min_height
    assert window.processing_panel.minimumHeight() >= content_min
    assert snapshot["timeline_debug"]["row_names"] == ["Resp", "Type", "SOA", "Tactile", "Clicks"]
    assert snapshot["timeline_debug"]["row_count"] == 5
    assert window.workspace_splitter.sizes()[1] >= min(profile.experiment_control_initial_height, window.processing_panel.height())
    assert window.response_panel.minimumWidth() == profile.response_panel_side
    assert window.response_panel.minimumHeight() == profile.response_panel_side
    assert window.response_panel.maximumWidth() == profile.response_panel_side
    assert window.response_panel.maximumHeight() == profile.response_panel_side
    assert window.response_panel.geometry().width() == window.response_panel.geometry().height()
    assert window.output_panel is not window.processing_panel
    assert window.processing_splitter is None
    assert window.run_splitter.count() == 2
    data_rect = _widget_rect(window.data_logging_column, window.dialog)
    settings_rect = _widget_rect(window.experiment_settings_column, window.dialog)
    if window.data_settings_columns_mode == "stacked":
        assert settings_rect["y"] >= data_rect["bottom"]
    else:
        assert abs(settings_rect["y"] - data_rect["y"]) <= 8
        assert settings_rect["x"] >= data_rect["right"]

    visible_widgets = [
        window.target_button,
        window.response_panel,
        window.participant_code_combo,
        window.include_name_lsl_checkbox,
        window.start_button,
        window.pause_button,
        window.stop_button,
        window.close_button,
        window.processing_panel,
        window.output_panel,
        window.part_selector_widget,
        window.part_buttons["1"],
        window.part_buttons["2"],
        window.block_plan_widget,
        window.instruction_legend_widget,
        window.output_summary,
        window.tactile_timeline_widget,
    ]
    if window.topup_draft_widget.isVisible():
        visible_widgets.append(window.topup_draft_widget)
    if window.block_preview_label.isVisible():
        visible_widgets.append(window.block_preview_label)
    for widget in visible_widgets:
        _assert_widget_inside_dialog(widget, window.dialog)

    assert window.target_button.geometry().width() == profile.target_min_height
    assert window.target_button.geometry().height() == profile.target_min_height
    assert window.start_button.geometry().height() >= profile.button_min_height
    assert window.output_summary.geometry().height() >= profile.output_min_height
    assert window.processing_panel.geometry().height() >= profile.experiment_control_min_height
    response_rect = _widget_rect(window.response_panel, window.dialog)
    output_rect = _widget_rect(window.output_panel, window.dialog)
    response_cell_rect = _widget_rect(window.response_cell, window.dialog)
    run_rect = _widget_rect(window.run_splitter, window.dialog)
    processing_rect = _widget_rect(window.processing_panel, window.dialog)
    workspace_rect = _widget_rect(window.workspace_splitter, window.dialog)
    assert output_rect["y"] >= response_rect["bottom"]
    assert output_rect["x"] >= response_cell_rect["x"]
    assert output_rect["right"] <= response_cell_rect["right"]
    assert processing_rect["y"] >= run_rect["bottom"]
    assert processing_rect["width"] >= workspace_rect["width"] - 8
    assert not window.layout_validation_failures()
    window.dialog.close()


@pytest.mark.parametrize("available_width,available_height", [(1024, 600), (1366, 768), (1536, 864), (1600, 900), (1920, 1000)])
def test_focus_mode_lower_control_panel_resists_splitter_compression(
    tmp_path: Path,
    available_width: int,
    available_height: int,
):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))
    profile = render_focus_layout_profile(available_width, available_height)
    window = focus_app.FocusModeWindow(q, package, enable_missed_trial_topup=True, layout_profile=profile)
    window.dialog.resize(profile.window_width, profile.window_height)
    window.dialog.show()
    app.processEvents()

    total = max(1, int(window.workspace_splitter.height()))
    window.workspace_splitter.setSizes([max(1, total - 24), 24])
    app.processEvents()
    window._clamp_workspace_splitter_for_experiment_control()
    app.processEvents()

    snapshot = window.layout_validation_snapshot()
    debug = snapshot["experiment_control_debug"]
    assert window.processing_panel.height() >= debug["content_min_height"]
    assert window.tactile_timeline_widget.height() >= focus_app.TIMELINE_MINIMUM_VISIBLE_HEIGHT
    assert debug["clipped_widgets"] == []
    assert debug["overlap_pairs"] == []
    assert debug["hidden_required_widgets"] == []
    assert not window.layout_validation_failures()
    window.dialog.close()


@pytest.mark.parametrize("available_width,available_height", [(1366, 768), (1600, 900), (1920, 1000)])
def test_focus_mode_lower_control_panel_handles_long_timeline_labels(
    tmp_path: Path,
    available_width: int,
    available_height: int,
):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))
    profile = render_focus_layout_profile(available_width, available_height)
    window = focus_app.FocusModeWindow(q, package, enable_missed_trial_topup=True, layout_profile=profile)
    window.dialog.resize(profile.window_width, profile.window_height)
    window.dialog.show()
    app.processEvents()

    long_label = "Very long respiratory condition and tactile cue detail " * 6
    window.next_tactile_label.setText(f"Next tactile: {long_label}")
    window.next_tactile_label.setToolTip(window.next_tactile_label.text())
    window.tactile_count_label.setText("999 / 999 cues | 999 clicks")
    window.topup_draft_items = [
        {
            "part_number": "1",
            "block_number": "1",
            "trial_number": str(index),
            "respiratory_phase": long_label,
            "trial_type": "Audio-Tactile",
            "family": "audio_tactile",
            "soa_ms": "2200",
        }
        for index in range(1, 7)
    ]
    window._refresh_topup_draft_widget()
    window._refresh_experiment_control_minimum_height()
    app.processEvents()

    debug = window.layout_validation_snapshot()["experiment_control_debug"]
    if profile.compact or profile.available_height <= 900:
        assert not window.topup_draft_widget.isVisible()
    else:
        assert window.topup_draft_widget.isVisible()
    assert debug["clipped_widgets"] == []
    assert debug["overlap_pairs"] == []
    assert not window.layout_validation_failures()
    window.dialog.close()


def test_focus_mode_instruction_continue_accepts_target_click_and_keyboard(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()

    click_event = threading.Event()
    click_payload = {
        "context": {"mode": "button", "instruction_label": "General instructions", "button_label": "Continue"},
        "approved": False,
        "event": click_event,
    }
    window._handle_instruction_continue(click_payload)
    assert window.target_button.isEnabled()
    assert window.instruction_button.isVisible()

    window._click()

    assert click_payload["approved"] is True
    assert click_event.is_set()
    assert window.pending_instruction_request is None

    keyboard_event = threading.Event()
    keyboard_payload = {
        "context": {"mode": "click", "instruction_label": "Pre-block"},
        "approved": False,
        "event": keyboard_event,
    }
    window._handle_instruction_continue(keyboard_payload)

    window._handle_primary_action_shortcut()

    assert keyboard_payload["approved"] is True
    assert keyboard_event.is_set()
    assert window.pending_instruction_request is None
    window.dialog.close()


def test_focus_mode_primary_shortcut_starts_when_not_editing(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()

    starts: list[bool] = []
    window.start = lambda: starts.append(True)  # type: ignore[method-assign]

    window.participant_name_input.setFocus()
    app.processEvents()
    window._handle_primary_action_shortcut()
    assert starts == []

    window.start_button.setFocus()
    app.processEvents()
    window._handle_primary_action_shortcut()
    assert starts == [True]
    window.dialog.close()


def test_focus_mode_operator_keyboard_shortcuts_control_ui(tmp_path: Path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_focus_preview_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package, enable_missed_trial_topup=True)
    window.dialog.show()
    window.dialog.activateWindow()
    window.dialog.setFocus(q["Qt"].FocusReason.ShortcutFocusReason)
    app.processEvents()

    shortcut_map = window.keyboard_shortcut_map()
    assert shortcut_map["pause_resume"] == ["Ctrl+P"]
    assert shortcut_map["stop"] == ["Ctrl+Shift+S"]
    assert shortcut_map["select_part_2"] == ["Alt+2"]
    assert set(window.operator_action_shortcuts) >= {
        "pause_resume",
        "stop",
        "close",
        "select_part_1",
        "select_part_2",
        "select_topup_preview",
    }

    class FakeController:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def pause(self) -> None:
            self.calls.append("pause")

        def resume(self) -> None:
            self.calls.append("resume")

        def stop(self) -> None:
            self.calls.append("stop")

    fake = FakeController()
    window.controller = fake  # type: ignore[assignment]
    window.pause_button.setEnabled(True)
    window.stop_button.setEnabled(True)
    ctrl = q["Qt"].KeyboardModifier.ControlModifier
    ctrl_shift = q["Qt"].KeyboardModifier.ControlModifier | q["Qt"].KeyboardModifier.ShiftModifier
    alt = q["Qt"].KeyboardModifier.AltModifier

    QTest.keyClick(window.dialog, q["Qt"].Key.Key_P, ctrl)
    app.processEvents()
    QTest.keyClick(window.dialog, q["Qt"].Key.Key_P, ctrl)
    app.processEvents()
    QTest.keyClick(window.dialog, q["Qt"].Key.Key_S, ctrl_shift)
    app.processEvents()

    assert fake.calls == ["pause", "resume", "stop"]

    QTest.keyClick(window.dialog, q["Qt"].Key.Key_2, alt)
    app.processEvents()
    assert window.selected_part_key == "2"

    QTest.keyClick(window.dialog, q["Qt"].Key.Key_T, ctrl)
    app.processEvents()
    selected = window._run_plan_item_by_number(window.selected_display_block_index or 0)
    assert selected is not None
    assert selected["kind"] == "topup"
    window.dialog.close()


def test_focus_mode_hardware_start_injects_ui_thread_audio_engine(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()

    class FakeEngine:
        def __init__(self) -> None:
            self.shutdown_count = 0

        def shutdown(self) -> None:
            self.shutdown_count += 1

    fake_engine = FakeEngine()
    created_on_threads: list[str] = []
    injected_engines: list[object] = []

    def fake_create_engine() -> FakeEngine:
        created_on_threads.append(threading.current_thread().name)
        return fake_engine

    class FakeController:
        def __init__(self, package_obj, *, audio_engine=None, capture_options=None, **_kwargs):
            self.package = package_obj
            self.audio_engine = audio_engine
            self.capture_options = capture_options
            injected_engines.append(audio_engine)

        def run(self, *, progress_callback=None, event_callback=None):
            return SimpleNamespace(
                completed=True,
                interrupted=False,
                summary_text="done",
                session_dir=self.package.session_dir,
                events_csv=self.package.session_dir / "events.csv",
                events_xdf=self.package.session_dir / "events.xdf",
                lsl_markers_csv=None,
                lsl_markers_xdf=None,
                trigger_dictionary_path=None,
                session_metadata_path=None,
                recording_paths=[],
                warnings=[],
                capture_options=(self.capture_options.as_dict() if self.capture_options is not None else {}),
            )

    monkeypatch.setattr(window, "_create_real_audio_engine_on_ui_thread", fake_create_engine)
    monkeypatch.setattr(focus_app, "SessionRunnerController", FakeController)

    window.start()
    assert created_on_threads == [threading.current_thread().name]
    assert injected_engines == [fake_engine]
    assert window.thread is not None
    window.thread.join(timeout=2)
    assert not window.thread.is_alive()
    window._drain()

    assert window.result is not None
    assert window.result.completed is True
    assert fake_engine.shutdown_count == 1
    window.dialog.close()


def test_focus_mode_opens_post_run_analysis_review_dialog(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("PPS_FOCUS_DISABLE_ANALYSIS_POPUP", raising=False)
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()
    outputs = _write_analysis_review_outputs(package.session_dir)

    result = SimpleNamespace(
        completed=True,
        session_dir=package.session_dir,
        summary_text="Tactile trials reconstructed: 4",
        analysis_outputs=outputs,
        capture_options={"write_analysis_csvs": True},
    )

    window._maybe_open_analysis_review(result)
    app.processEvents()

    assert window.analysis_review_dialog is not None
    dialog = window.analysis_review_dialog.dialog
    assert dialog.isVisible()
    model_combo = dialog.findChild(q["QComboBox"], "analysisModelCombo")
    scope_combo = dialog.findChild(q["QComboBox"], "analysisScopeCombo")
    metric_combo = dialog.findChild(q["QComboBox"], "analysisMetricCombo")
    source_combo = dialog.findChild(q["QComboBox"], "analysisSourceCombo")
    grouping_combo = dialog.findChild(q["QComboBox"], "analysisGroupingCombo")
    overview_table = dialog.findChild(q["QTableWidget"], "analysisOverviewTable")
    details = dialog.findChild(q["QTextEdit"], "analysisDetailsText")
    assert model_combo is not None and model_combo.count() == 5
    assert "Compare all three" in [model_combo.itemText(index) for index in range(model_combo.count())]
    assert metric_combo is not None and "Hit rate" in [metric_combo.itemText(index) for index in range(metric_combo.count())]
    assert source_combo is not None and "Logged but excluded events" in [source_combo.itemText(index) for index in range(source_combo.count())]
    assert grouping_combo is not None and "By SOA/distance bin" in [grouping_combo.itemText(index) for index in range(grouping_combo.count())]
    assert scope_combo is not None and scope_combo.count() == 1
    assert overview_table is not None and overview_table.rowCount() == 1
    part_buttons = [button for button in dialog.findChildren(q["QPushButton"], "analysisSegmentButton")]
    assert {button.text() for button in part_buttons}.issuperset({"Data Behavior", "Model Fits", "Responses", "Timing Evidence", "Top-Up", "Artifacts", "Separate parts", "Pool parts"})
    toggles = [box.text() for box in dialog.findChildren(q["QCheckBox"], "analysisPlotToggle")]
    assert {"Observed means", "Uncertainty band", "Raw trial points", "Rejected / extra clicks", "Top-up rescues", "PPS boundary", "All model fits", "Low-N markers"}.issubset(set(toggles))
    assert details is not None and "Exploratory data-behavior signals" in details.toPlainText()
    assert "Expected pattern" in details.toPlainText()
    assert "participant-readiness certification" in details.toPlainText()
    assert "pass" not in details.toPlainText().lower()
    assert "fail" not in details.toPlainText().lower()
    assert "Best model by AIC" in details.toPlainText()
    assert "Displayed range: +/- SEM" in details.toPlainText()
    compare_index = model_combo.findText("Compare all three")
    assert compare_index >= 0
    model_combo.setCurrentIndex(compare_index)
    app.processEvents()
    assert "Displayed models: Sigmoid, Linear, Logarithmic decay" in details.toPlainText()
    assert "Sigmoid PPS boundary" in details.toPlainText()
    pooled = next(button for button in part_buttons if button.text() == "Pool parts")
    pooled.click()
    app.processEvents()
    assert scope_combo.currentText() == "All parts / Inhale / pink"
    assert "Part summary: Pool parts" in details.toPlainText()
    screenshot = tmp_path / "analysis_review_dialog.png"
    assert dialog.grab().save(str(screenshot))
    assert screenshot.stat().st_size > 0
    dialog.close()
    window.dialog.close()


def test_focus_mode_skips_analysis_review_for_interrupted_or_disabled_analysis(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("PPS_FOCUS_DISABLE_ANALYSIS_POPUP", raising=False)
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    outputs = _write_analysis_review_outputs(package.session_dir)
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()

    window._maybe_open_analysis_review(
        SimpleNamespace(completed=False, session_dir=package.session_dir, analysis_outputs=outputs, capture_options={"write_analysis_csvs": True})
    )
    assert window.analysis_review_dialog is None

    window._maybe_open_analysis_review(
        SimpleNamespace(completed=True, session_dir=package.session_dir, analysis_outputs=outputs, capture_options={"write_analysis_csvs": False})
    )
    assert window.analysis_review_dialog is None
    window.dialog.close()


def test_focus_mode_recenter_uses_pyautogui_backend(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.focus_timeline import TactileTimelineCue
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI smoke dependencies unavailable: {exc}")

    moves: list[tuple[int, int, int]] = []

    class FakePyAutoGUI:
        FAILSAFE = True
        PAUSE = 0.1

        @staticmethod
        def moveTo(x, y, duration=0):
            moves.append((int(x), int(y), int(duration)))

    monkeypatch.setitem(sys.modules, "pyautogui", FakePyAutoGUI)

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    package = load_run_package(_write_minimal_session_manifest(tmp_path))
    window = focus_app.FocusModeWindow(q, package)
    window.dialog.show()
    app.processEvents()
    monkeypatch.setattr(window, "_offscreen_platform", lambda: False)

    cue = TactileTimelineCue(cue_id=1, trial_number=1, trial_uid="T001", time_s=4.0)
    window._move_cursor_to_target(cue)

    assert moves
    assert window.recenter_records[-1]["mode"] == "pyautogui"
    assert window.recenter_records[-1]["trial_uid"] == "T001"
    window.dialog.close()


def test_tactile_timeline_uses_four_second_response_window():
    from peripersonal_space_toolkit.focus_timeline import TactileTimelineState

    state = TactileTimelineState()
    state.load_block(
        duration_s=10.0,
        tactile_events=[
            {"trial_number": 1, "trial_uid": "T001", "time_s": 1.0},
        ],
    )

    accepted = state.record_click(5.0, trial_uid="T001")
    rejected = state.record_click(5.002, trial_uid="T001")

    assert accepted.response_status == "tactile_response"
    assert accepted.rt_s == pytest.approx(4.0)
    assert rejected.response_status == "off_cue"


def test_validation_realtime_audio_engine_waits_for_buffer_deadlines(tmp_path: Path):
    from peripersonal_space_toolkit.focus_app import _ValidationFastAudioEngine

    sample_rate = 1000
    duration_s = 0.12
    wav_path = tmp_path / "short_block.wav"
    sf.write(wav_path, [0.0] * int(sample_rate * duration_s), sample_rate)

    engine = _ValidationFastAudioEngine(chunk_frames=10, realtime=True)
    started = time.perf_counter()
    assert engine.play_block(str(wav_path))
    elapsed = time.perf_counter() - started

    assert elapsed >= duration_s * 0.85
    assert engine.played_block_durations_s == pytest.approx([duration_s])


def test_launcher_first_screen_is_environment_gate():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image, ImageStat
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []

    def inspect_launcher() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.windowTitle() == "PPS Experiment Runner"]
            assert dialogs
            dialog = dialogs[0]
            assert dialog.findChild(q["QComboBox"], "participantCombo") is None
            output_field = dialog.findChild(q["QLineEdit"], "outputFolderField")
            assert output_field is not None
            assert output_field.isReadOnly()
            assert output_field.property("gateState") == "locked"
            profile_combo = dialog.findChild(q["QComboBox"], "environmentProfileCombo")
            assert profile_combo is not None
            assert not profile_combo.isEnabled()
            assert profile_combo.property("gateState") == "locked"
            session_field = dialog.findChild(q["QLineEdit"], "sessionNameField")
            assert session_field is not None
            assert session_field.isReadOnly()
            assert session_field.property("gateState") == "locked"
            step_label = dialog.findChild(q["QLabel"], "gateStepLabel")
            assert step_label is not None
            assert "Step 1" in step_label.text()
            assert step_label.property("attention") == "current"
            choose_button = dialog.findChild(q["QPushButton"], "chooseOutputFolderButton")
            assert choose_button is not None
            assert choose_button.text().startswith("2 ")
            assert choose_button.property("decisionTone") == "folder"
            initiate_button = dialog.findChild(q["QPushButton"], "initiateEnvironmentButton")
            assert initiate_button is not None
            assert not initiate_button.isEnabled()
            assert initiate_button.property("attention") == "locked"
            resume_button = dialog.findChild(q["QPushButton"], "resumeExperimentButton")
            assert resume_button is not None
            assert resume_button.text().startswith("1 ")
            assert resume_button.property("decisionTone") == "resume"
            labels = _collect_widget_texts(dialog, q["QLabel"])
            assert labels.index("Output Folder") < labels.index("Experiment Profile")
            assert labels.index("Experiment Profile") < labels.index("Session Name")
            placeholders = [line.placeholderText() for line in dialog.findChildren(q["QLineEdit"])]
            assert "Participant ID" not in placeholders
            assert "1-10" not in placeholders
            button_labels = [button.text() for button in dialog.findChildren(q["QPushButton"])]
            assert "Generate Audio Assets" not in button_labels
            assert "Generate Range" not in button_labels
            assert "Run Selected Profile" not in button_labels
            screenshot = Path.cwd() / ".pytest_cache" / "launcher_environment_gate.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            assert dialog.grab().save(str(screenshot))
            image = Image.open(screenshot).convert("RGB")
            assert image.width >= 760
            assert image.height >= 520
            assert max(ImageStat.Stat(image).stddev) > 0.0
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
        finally:
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, inspect_launcher)
    exit_code = focus_app.run_launcher_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
        initial_message="inspection",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert exit_code == 1
    assert errors == []


def test_launcher_resume_shortcut_opens_environment_operations(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()
    errors: list[BaseException] = []
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        focus_app,
        "load_profile_runner_settings",
        lambda **_kwargs: {
            "active_profile_id": focus_app.STUDY5_PROFILE_ID,
            "active_output_folder": str(tmp_path),
            "participant_id": "P001",
        },
    )
    monkeypatch.setattr(
        focus_app,
        "load_runner_settings",
        lambda *args, **kwargs: {
            "last_experiment_name": "Study 5 gate test",
            "last_profile_id": focus_app.STUDY5_PROFILE_ID,
            "last_participant_id": "P001",
        },
    )
    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "current_runner_diary_path", lambda: None)
    monkeypatch.setattr(focus_app, "find_output_diary", lambda _root: None)
    monkeypatch.setattr(focus_app, "remember_runner_context", lambda **_kwargs: {})
    monkeypatch.setattr(focus_app, "update_profile_runner_settings", lambda **_kwargs: {})
    monkeypatch.setattr(focus_app, "_append_output_diary_event", lambda *args, **kwargs: None)

    def fake_environment_operations_window(**kwargs):
        calls.append(kwargs)
        return 58

    monkeypatch.setattr(focus_app, "_run_environment_operations_window", fake_environment_operations_window)

    resume_attempts = {"count": 0}

    def reject_if_still_open() -> None:
        if calls or errors:
            return
        errors.append(AssertionError("Launcher resume shortcut test timed out before the dialog closed."))
        for widget in app.topLevelWidgets():
            if widget.windowTitle() == "PPS Experiment Runner":
                widget.reject()

    def click_resume() -> None:
        try:
            dialogs = [
                widget
                for widget in app.topLevelWidgets()
                if widget.windowTitle() == "PPS Experiment Runner"
                and widget.isVisible()
                and widget.findChild(q["QPushButton"], "resumeExperimentButton") is not None
            ]
            if not dialogs and resume_attempts["count"] < 20:
                resume_attempts["count"] += 1
                q["QTimer"].singleShot(50, click_resume)
                return
            assert dialogs
            dialog = dialogs[0]
            assert dialog.findChild(q["QComboBox"], "participantCombo") is None
            resume = dialog.findChild(q["QPushButton"], "resumeExperimentButton")
            assert resume is not None
            assert resume.isEnabled()
            resume_shortcuts = [
                shortcut
                for shortcut in dialog.findChildren(q["QShortcut"])
                if shortcut.key().toString() == "1"
            ]
            assert resume_shortcuts
            assert resume_shortcuts[0].isEnabled()
            resume_shortcuts[0].activated.emit()
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, click_resume)
    q["QTimer"].singleShot(3000, reject_if_still_open)
    exit_code = focus_app.run_launcher_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert exit_code == 58
    assert errors == []
    assert len(calls) == 1
    assert calls[0]["participant_id"] == "P001"


def test_launcher_pick_empty_folder_unlocks_required_fields_and_initiate(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image, ImageStat
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []
    remembered = tmp_path / "remembered"
    remembered.mkdir()
    new_parent = tmp_path / "fresh_parent"
    new_parent.mkdir()

    monkeypatch.setattr(
        focus_app,
        "load_profile_runner_settings",
        lambda **_kwargs: {
            "active_profile_id": focus_app.STUDY5_PROFILE_ID,
            "active_output_folder": str(remembered),
            "participant_id": "P001",
        },
    )
    monkeypatch.setattr(
        focus_app,
        "load_runner_settings",
        lambda *args, **kwargs: {
            "last_experiment_name": "Remembered Study",
            "last_profile_id": focus_app.STUDY5_PROFILE_ID,
            "last_participant_id": "P001",
        },
    )
    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "current_runner_diary_path", lambda: None)
    monkeypatch.setattr(q["QFileDialog"], "getExistingDirectory", lambda *args, **kwargs: str(new_parent))

    def pick_folder_and_inspect() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.windowTitle() == "PPS Experiment Runner"]
            assert dialogs
            dialog = dialogs[0]
            initial_choose_button = dialog.findChild(q["QPushButton"], "chooseOutputFolderButton")
            assert initial_choose_button is not None
            QTest.mouseClick(initial_choose_button, q["Qt"].MouseButton.LeftButton)
            app.processEvents()

            output_field = dialog.findChild(q["QLineEdit"], "outputFolderField")
            profile_combo = dialog.findChild(q["QComboBox"], "environmentProfileCombo")
            session_field = dialog.findChild(q["QLineEdit"], "sessionNameField")
            initiate_button = dialog.findChild(q["QPushButton"], "initiateEnvironmentButton")
            resume_button = dialog.findChild(q["QPushButton"], "resumeExperimentButton")
            choose_button = dialog.findChild(q["QPushButton"], "chooseOutputFolderButton")
            assert output_field is not None
            assert profile_combo is not None
            assert session_field is not None
            assert initiate_button is not None
            assert resume_button is not None
            assert choose_button is not None

            assert Path(output_field.text()) == new_parent
            assert not output_field.isReadOnly()
            assert profile_combo.isEnabled()
            assert not session_field.isReadOnly()
            assert output_field.property("gateState") == "complete"
            assert profile_combo.property("gateState") == "needed"
            assert session_field.property("gateState") == "needed"
            assert not resume_button.isEnabled()
            assert not initiate_button.isEnabled()
            assert initiate_button.property("attention") == "locked"
            assert choose_button.property("attention") == "complete"

            screenshot = Path.cwd() / ".pytest_cache" / "launcher_gate_new_parent_required.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            assert dialog.grab().save(str(screenshot))
            image = Image.open(screenshot).convert("RGB")
            assert image.width >= 760
            assert image.height >= 480
            assert max(ImageStat.Stat(image).stddev) > 0.0

            profile_index = profile_combo.findData(focus_app.STUDY5_PROFILE_ID)
            assert profile_index >= 0
            profile_combo.setCurrentIndex(profile_index)
            session_field.setText("Salience Pilot")
            app.processEvents()
            assert profile_combo.property("gateState") == "complete"
            assert session_field.property("gateState") == "complete"
            assert initiate_button.isEnabled()
            assert initiate_button.property("attention") == "go"
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
        finally:
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, pick_folder_and_inspect)
    exit_code = focus_app.run_launcher_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert exit_code == 1
    assert errors == []


def test_launcher_existing_folder_keeps_fields_locked_and_resumes_selected_environment(tmp_path: Path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PIL import Image, ImageStat
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []
    calls: list[dict[str, object]] = []
    remembered = tmp_path / "remembered"
    remembered.mkdir()
    existing_env = tmp_path / "existing_environment"
    existing_env.mkdir()
    (existing_env / focus_app.BRIDGE_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "schema": "pps-dashboard-runner-bridge-manifest.v1",
                "profile_id": focus_app.STUDY5_PROFILE_ID,
                "display_name": "Existing Salience Study",
                "participant_id": "P009",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (existing_env / focus_app.OUTPUT_DIARY_FILENAME).write_text(
        json.dumps(
            {
                "schema": "pps-output-diary-event.v1",
                "event_type": "data_collection_environment_initiated",
                "profile_id": focus_app.STUDY5_PROFILE_ID,
                "participant_id": "P009",
                "session_name": "Output Diary Study",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        focus_app,
        "load_profile_runner_settings",
        lambda **_kwargs: {
            "active_profile_id": focus_app.STUDY5_PROFILE_ID,
            "active_output_folder": str(remembered),
            "participant_id": "P001",
        },
    )
    monkeypatch.setattr(
        focus_app,
        "load_runner_settings",
        lambda *args, **kwargs: {
            "last_experiment_name": "Remembered Study",
            "last_profile_id": focus_app.STUDY5_PROFILE_ID,
            "last_participant_id": "P001",
        },
    )
    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "current_runner_diary_path", lambda: None)
    monkeypatch.setattr(q["QFileDialog"], "getExistingDirectory", lambda *args, **kwargs: str(existing_env))
    monkeypatch.setattr(focus_app, "remember_runner_context", lambda **_kwargs: {})
    monkeypatch.setattr(focus_app, "update_profile_runner_settings", lambda **_kwargs: {})
    monkeypatch.setattr(focus_app, "_append_output_diary_event", lambda *args, **kwargs: None)

    def fake_environment_operations_window(**kwargs):
        calls.append(kwargs)
        return 59

    monkeypatch.setattr(focus_app, "_run_environment_operations_window", fake_environment_operations_window)

    def pick_existing_and_resume() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.windowTitle() == "PPS Experiment Runner"]
            assert dialogs
            dialog = dialogs[0]
            choose_button = dialog.findChild(q["QPushButton"], "chooseOutputFolderButton")
            assert choose_button is not None
            QTest.mouseClick(choose_button, q["Qt"].MouseButton.LeftButton)
            app.processEvents()

            output_field = dialog.findChild(q["QLineEdit"], "outputFolderField")
            profile_combo = dialog.findChild(q["QComboBox"], "environmentProfileCombo")
            session_field = dialog.findChild(q["QLineEdit"], "sessionNameField")
            resume_button = dialog.findChild(q["QPushButton"], "resumeExperimentButton")
            initiate_button = dialog.findChild(q["QPushButton"], "initiateEnvironmentButton")
            message_label = dialog.findChild(q["QLabel"], "gateStatusLabel")
            assert output_field is not None
            assert profile_combo is not None
            assert session_field is not None
            assert resume_button is not None
            assert initiate_button is not None
            assert message_label is not None

            assert Path(output_field.text()) == existing_env
            assert output_field.isReadOnly()
            assert not profile_combo.isEnabled()
            assert session_field.isReadOnly()
            assert output_field.property("gateState") == "locked"
            assert profile_combo.property("gateState") == "locked"
            assert session_field.property("gateState") == "locked"
            assert profile_combo.currentData() == focus_app.STUDY5_PROFILE_ID
            assert session_field.text() == "Existing Salience Study"
            assert "Existing experiment environment found" in message_label.text()
            assert resume_button.isEnabled()
            assert resume_button.property("attention") == "current"
            assert not initiate_button.isEnabled()

            screenshot = Path.cwd() / ".pytest_cache" / "launcher_gate_existing_environment.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            assert dialog.grab().save(str(screenshot))
            image = Image.open(screenshot).convert("RGB")
            assert image.width >= 760
            assert image.height >= 480
            assert max(ImageStat.Stat(image).stddev) > 0.0

            dialog.activateWindow()
            dialog.setFocus(q["Qt"].FocusReason.ShortcutFocusReason)
            QTest.keyClick(dialog, q["Qt"].Key.Key_1)
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, pick_existing_and_resume)
    exit_code = focus_app.run_launcher_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
    )
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()

    assert exit_code == 59
    assert errors == []
    assert len(calls) == 1
    assert calls[0]["participant_id"] == "P009"


def test_main_no_args_opens_resume_environment_gate(monkeypatch):
    from peripersonal_space_toolkit import focus_app

    calls: list[dict[str, object]] = []
    released: list[bool] = []

    def fake_launcher(**kwargs):
        calls.append(kwargs)
        return 37

    class FakeSingleInstance:
        acquired = True
        message = ""

        def release(self):
            released.append(True)

    monkeypatch.setattr(focus_app, "_acquire_runner_single_instance", lambda: FakeSingleInstance())
    monkeypatch.setattr(focus_app, "run_launcher_window", fake_launcher)
    monkeypatch.setattr(
        focus_app,
        "prepare_last_or_latest_focus_session",
        lambda *_args, **_kwargs: pytest.fail("no-argument launch must not auto-resume"),
    )
    monkeypatch.setattr(
        focus_app,
        "run_focus_window",
        lambda *_args, **_kwargs: pytest.fail("no-argument launch must not open Focus Mode directly"),
    )

    assert focus_app.main([]) == 37
    assert len(calls) == 1
    assert calls[0]["participant_id"] == ""
    assert released == [True]


def test_main_blocks_when_experiment_runner_already_open(monkeypatch):
    from peripersonal_space_toolkit import focus_app

    notices: list[str] = []

    monkeypatch.setattr(
        focus_app,
        "_acquire_runner_single_instance",
        lambda: focus_app._RunnerSingleInstance(acquired=False, message="runner already open"),
    )
    monkeypatch.setattr(focus_app, "_show_runner_single_instance_notice", notices.append)
    monkeypatch.setattr(
        focus_app,
        "run_launcher_window",
        lambda **_kwargs: pytest.fail("second runner launch must not open the launcher"),
    )
    monkeypatch.setattr(
        focus_app,
        "run_focus_window",
        lambda *_args, **_kwargs: pytest.fail("second runner launch must not open Focus Mode"),
    )

    assert focus_app.main([]) == focus_app.SINGLE_INSTANCE_EXIT_CODE
    assert notices == ["runner already open"]


def test_main_last_experiment_flag_keeps_explicit_direct_resume(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    manifest = tmp_path / "session_manifest.json"
    calls: dict[str, object] = {}
    released: list[bool] = []

    class FakeSingleInstance:
        acquired = True
        message = ""

        def release(self):
            released.append(True)

    def fake_prepare(participant_id=None, **kwargs):
        calls["participant_id"] = participant_id
        calls["prepare_kwargs"] = kwargs
        return manifest

    def fake_focus_window(path, **kwargs):
        calls["focus_path"] = path
        calls["focus_kwargs"] = kwargs
        return 41

    monkeypatch.setattr(focus_app, "prepare_last_or_latest_focus_session", fake_prepare)
    monkeypatch.setattr(focus_app, "run_focus_window", fake_focus_window)
    monkeypatch.setattr(focus_app, "_acquire_runner_single_instance", lambda: FakeSingleInstance())
    monkeypatch.setattr(
        focus_app,
        "run_launcher_window",
        lambda **_kwargs: pytest.fail("--last-experiment should remain an explicit gate bypass"),
    )

    assert focus_app.main(["--last-experiment", "--participant-id", "P007", "--manual-start"]) == 41
    assert calls["participant_id"] == "P007"
    assert calls["focus_path"] == manifest
    assert calls["focus_kwargs"]["manual_start"] is True
    assert released == [True]


def test_audio_dependency_dialog_retry_accepts_after_asio_detected(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.audio_routing import AudioRuntimeReadiness
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []

    missing = AudioRuntimeReadiness(
        ready=False,
        publication_ready=False,
        severity="error",
        summary="Audio preflight: Komplete Audio ASIO is missing.",
        details=("ASIO is visible, but no output exposes at least three synchronized channels.",),
        actions=(),
        sounddevice_available=True,
        sounddevice_version="0.4.7",
        asio_hostapi_present=True,
        preferred_devices=(),
        fallback_devices=(),
    )
    ready = AudioRuntimeReadiness(
        ready=True,
        publication_ready=True,
        severity="ok",
        summary="Audio preflight: validated Komplete multichannel ASIO output is visible.",
        details=("[3] Komplete Audio ASIO Driver (ASIO, 6 out)",),
        actions=(),
        sounddevice_available=True,
        sounddevice_version="0.4.7",
        asio_hostapi_present=True,
        preferred_devices=("[3] Komplete Audio ASIO Driver (ASIO, 6 out)",),
        fallback_devices=(),
    )
    monkeypatch.setattr(focus_app, "assess_audio_runtime_readiness", lambda: ready)

    def click_retry() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.objectName() == "audioDependencyDialog"]
            assert dialogs
            dialog = dialogs[0]
            labels = _collect_widget_texts(dialog, q["QLabel"])
            assert any("Komplete Audio ASIO driver required" in label for label in labels)
            assert any("Retry Audio Detection" in label for label in labels)
            retry = dialog.findChild(q["QPushButton"], "retryAudioDetectionButton")
            assert retry is not None
            QTest.mouseClick(retry, q["Qt"].MouseButton.LeftButton)
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.objectName() == "audioDependencyDialog":
                    widget.reject()

    q["QTimer"].singleShot(50, click_retry)
    assert focus_app._show_audio_dependency_dialog(q, readiness=missing) is True
    assert errors == []


def test_unvalidated_audio_route_confirmation_window_accepts_continue(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    errors: list[BaseException] = []
    display_device = "Speakers (Nahimic Easy Surround)"

    def click_confirmation() -> None:
        try:
            confirms = [widget for widget in app.topLevelWidgets() if widget.objectName() == "unvalidatedAudioRouteConfirmDialog"]
            assert confirms
            confirm = confirms[0]
            assert "not calibrated" in confirm.informativeText()
            assert display_device in confirm.informativeText()
            assert "[44]" not in confirm.informativeText()
            assert "left=Output 4, right=Output 4, tactile=Output 6" in confirm.informativeText()
            buttons = confirm.findChildren(q["QPushButton"])
            continue_button = next(button for button in buttons if button.text() == "Continue Without Komplete Interface")
            QTest.mouseClick(continue_button, q["Qt"].MouseButton.LeftButton)
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.objectName() == "unvalidatedAudioRouteConfirmDialog":
                    widget.reject()

    parent = q["QDialog"]()
    parent.setObjectName("unvalidatedConfirmParent")
    q["QTimer"].singleShot(50, click_confirmation)
    assert focus_app._confirm_unvalidated_audio_route(q, parent=parent, label=display_device, channels=(4, 4, 6)) is True
    parent.close()
    parent.deleteLater()
    app.processEvents()
    assert errors == []


def test_audio_dependency_dialog_user_selected_system_route_sets_audio_env_after_confirmation(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.delenv("PPS_AUDIO_DEVICE_INDEX", raising=False)
    monkeypatch.delenv("PPS_AUDIO_OUTPUT_CHANNELS", raising=False)
    monkeypatch.delenv("PPS_AUDIO_UNVALIDATED_ROUTE_FROM_DIALOG", raising=False)
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
        from peripersonal_space_toolkit.audio_routing import AudioRuntimeReadiness
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    for widget in app.topLevelWidgets():
        if widget.objectName() in {"audioDependencyDialog", "unvalidatedAudioRouteConfirmDialog", "unvalidatedConfirmParent"}:
            widget.close()
            widget.deleteLater()
    app.processEvents()
    errors: list[BaseException] = []
    fallback = (
        "[44] Speakers (Nahimic Easy Surround) "
        "(Windows WDM-KS, 8 out; outputs 1-8 available; PPS uses 1=L, 2=R, 3=tactile)"
    )
    confirm_calls: list[str] = []
    missing_with_fallback = AudioRuntimeReadiness(
        ready=False,
        publication_ready=False,
        severity="error",
        summary=(
            "Audio preflight: Komplete Audio ASIO driver is installed, but the Komplete Audio 6 MK2 interface "
            "is not exposing a 3+ channel ASIO output."
        ),
        details=(
            "Komplete Audio ASIO Driver is installed/registered in Windows, but the Komplete Audio 6 MK2 interface "
            "is not connected or not ready as a usable 3+ channel ASIO device.",
            f"Non-ASIO multichannel output is visible, but not valid for PPS timing claims: {fallback}",
        ),
        actions=(),
        sounddevice_available=True,
        sounddevice_version="0.5.5",
        asio_hostapi_present=True,
        preferred_devices=(),
        fallback_devices=(fallback,),
        komplete_asio_driver_registered=True,
        unvalidated_output_devices=(fallback,),
    )

    def fake_confirm(q_arg, *, parent, label, channels):
        assert q_arg is q
        assert parent.objectName() == "audioDependencyDialog"
        confirm_calls.append(f"{label}|{channels}")
        return True

    monkeypatch.setattr(focus_app, "_confirm_unvalidated_audio_route", fake_confirm)

    def click_unvalidated_route() -> None:
        try:
            dialogs = [widget for widget in app.topLevelWidgets() if widget.objectName() == "audioDependencyDialog"]
            assert dialogs
            dialog = dialogs[0]
            labels = _collect_widget_texts(dialog, q["QLabel"])
            assert any("Komplete Audio 6 MK2 interface not detected" in label for label in labels)
            assert any("Unvalidated pretest route" in label for label in labels)
            assert any("Left (default 1)" in label for label in labels)
            assert any("Right (default 2)" in label for label in labels)
            assert any("Tactile (default 3)" in label for label in labels)
            assert dialog.findChild(q["QComboBox"], "unvalidatedAudioDeviceCombo") is None
            left = dialog.findChild(q["QComboBox"], "unvalidatedLeftChannelCombo")
            right = dialog.findChild(q["QComboBox"], "unvalidatedRightChannelCombo")
            tactile = dialog.findChild(q["QComboBox"], "unvalidatedTactileChannelCombo")
            assert left is not None and right is not None and tactile is not None
            assert left.count() == 8
            assert right.count() == 8
            assert tactile.count() == 8
            assert left.itemText(0) == "Speakers (Nahimic Easy Surround) - Output 1"
            assert right.itemText(1) == "Speakers (Nahimic Easy Surround) - Output 2"
            assert tactile.itemText(2) == "Speakers (Nahimic Easy Surround) - Output 3"
            assert left.itemData(0)[:2] == (44, 1)
            assert right.itemData(1)[:2] == (44, 2)
            assert tactile.itemData(2)[:2] == (44, 3)
            left.setCurrentIndex(next(index for index in range(left.count()) if left.itemData(index)[:2] == (44, 4)))
            right.setCurrentIndex(next(index for index in range(right.count()) if right.itemData(index)[:2] == (44, 4)))
            tactile.setCurrentIndex(next(index for index in range(tactile.count()) if tactile.itemData(index)[:2] == (44, 6)))
            button = dialog.findChild(q["QPushButton"], "useUnvalidatedAudioRouteButton")
            assert button is not None
            assert button.text() == "Accept Pretest Settings"
            QTest.mouseClick(button, q["Qt"].MouseButton.LeftButton)
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.objectName() == "audioDependencyDialog":
                    widget.reject()

    q["QTimer"].singleShot(50, click_unvalidated_route)
    assert focus_app._show_audio_dependency_dialog(q, readiness=missing_with_fallback) is True
    assert confirm_calls == [f"Speakers (Nahimic Easy Surround)|{(4, 4, 6)}"]
    assert os.environ["PPS_AUDIO_DEVICE_INDEX"] == "44"
    assert os.environ["PPS_AUDIO_OUTPUT_CHANNELS"] == "4,4,6"
    assert os.environ["PPS_AUDIO_UNVALIDATED_ROUTE_FROM_DIALOG"] == "1"
    assert errors == []


def test_launcher_generate_range_button_prepares_requested_range(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from peripersonal_space_toolkit import focus_app
    except Exception as exc:  # pragma: no cover - depends on optional GUI deps
        pytest.skip(f"Optional GUI dependencies unavailable: {exc}")

    q = focus_app._require_qt()
    app = QApplication.instance() or QApplication([])
    participants = ["P001", "P002", "P003"]
    calls: list[tuple[str, list[str]]] = []
    errors: list[BaseException] = []

    monkeypatch.setattr(focus_app, "finished_profile_options", lambda: [(focus_app.STUDY5_PROFILE_ID, "Study 5")])
    monkeypatch.setattr(focus_app, "profile_participant_ids", lambda _profile: participants)
    monkeypatch.setattr(
        focus_app,
        "profile_participant_asset_statuses",
        lambda _profile, **_kwargs: {
            participant: {
                "participant_id": participant,
                "generated": participant != "P003",
                "status": "generated" if participant != "P003" else "not_generated",
                "data_collected": False,
            }
            for participant in participants
        },
    )

    def fake_prepare_profile_audio_assets(profile_id, participant_ids, *, session_root=None, progress_callback=None):
        calls.append((profile_id, list(participant_ids)))
        if progress_callback is not None:
            progress_callback({"message": "Fake range generation", "current": len(participant_ids), "total": len(participant_ids)})
        return {
            "profile_id": profile_id,
            "participant_count": len(participant_ids),
            "prepared_count": 1,
            "reused_count": 2,
            "results": [],
        }

    monkeypatch.setattr(focus_app, "prepare_profile_audio_assets", fake_prepare_profile_audio_assets)

    def inspect_launcher() -> None:
        try:
            dialogs = [
                widget
                for widget in app.topLevelWidgets()
                if widget.windowTitle() == "PPS Experiment Runner" and widget.findChild(q["QComboBox"], "participantCombo") is not None
            ]
            assert dialogs
            dialog = dialogs[0]
            range_inputs = [line for line in dialog.findChildren(q["QLineEdit"]) if line.placeholderText() == "1-10"]
            assert range_inputs
            range_buttons = [button for button in dialog.findChildren(q["QPushButton"]) if button.text() == "Generate Range"]
            assert range_buttons
            range_inputs[0].setText("1-3")
            QTest.mouseClick(range_buttons[0], q["Qt"].MouseButton.LeftButton)

            def verify_and_close() -> None:
                try:
                    assert calls == [(focus_app.STUDY5_PROFILE_ID, participants)]
                    labels = _collect_widget_texts(dialog, q["QLabel"])
                    assert any("Audio assets ready: 1 generated, 2 already available" in label for label in labels)
                except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
                    errors.append(exc)
                finally:
                    dialog.reject()

            q["QTimer"].singleShot(600, verify_and_close)
        except BaseException as exc:  # noqa: BLE001 - surfaced after the modal exits
            errors.append(exc)
            for widget in app.topLevelWidgets():
                if widget.windowTitle() == "PPS Experiment Runner":
                    widget.reject()

    q["QTimer"].singleShot(50, inspect_launcher)
    exit_code = focus_app._run_environment_operations_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
        initial_message="inspection",
    )

    assert exit_code == 1
    assert errors == []


def test_prepare_profile_focus_session_uses_finished_profile_gate(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    manifest = tmp_path / "sessions" / "P123_run" / "session_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    run_setup = tmp_path / "profile" / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    run_setup.parent.mkdir(parents=True)
    run_setup.write_text("{}", encoding="utf-8")
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        focus_app,
        "_materialize_profile_run_setup",
        lambda profile_id, progress_callback=None: (
            SimpleNamespace(design_path=tmp_path / "design.json"),
            SimpleNamespace(),
            run_setup,
        ),
    )
    monkeypatch.setattr(focus_app, "claim_prepared_session", lambda *_args, **_kwargs: None)

    def fake_prepare_segment_run_package(run_setup_path, participant_id, **kwargs):
        calls["run_setup_path"] = run_setup_path
        calls["participant_id"] = participant_id
        calls["prepare_kwargs"] = dict(kwargs)
        return SimpleNamespace(
            manifest_path=manifest,
            source_run_setup_manifest_path=run_setup,
            session_dir=manifest.parent,
            blocks=[object()],
        )

    monkeypatch.setattr(focus_app, "prepare_segment_run_package", fake_prepare_segment_run_package)
    monkeypatch.setattr(focus_app, "record_prepared_session_queue", lambda **kwargs: calls.setdefault("queue", kwargs))
    monkeypatch.setattr(focus_app, "record_experiment_activity", lambda *args, **kwargs: calls.setdefault("activity", (args, kwargs)))
    monkeypatch.setattr(
        focus_app,
        "resolve_profile_entry",
        lambda *_args, **_kwargs: {"kind": "bundled", "dashboard_project_id": "profile_study5_box_breathing_pps"},
    )
    monkeypatch.setattr(focus_app, "update_profile_runner_settings", lambda **kwargs: calls.setdefault("settings", kwargs))

    assert (
        focus_app.prepare_profile_focus_session(
            "study5_box_breathing_pps",
            "P123",
            session_root=tmp_path / "isolated_output",
        )
        == manifest
    )
    assert calls["run_setup_path"] == run_setup
    assert calls["participant_id"] == "P123"
    assert calls["queue"]["participant_id"] == "P123"
    assert calls["settings"]["profile_id"] == "study5_box_breathing_pps"


def test_runner_output_project_setting_creates_timestamped_folder(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    state_root = tmp_path / "state"
    parent = tmp_path / "operator_outputs"
    monkeypatch.setattr(focus_app.time, "strftime", lambda _fmt: "20260617_151500")

    project = focus_app.create_runner_output_project(
        parent,
        state_root=state_root,
        experiment_identifier="Study 5 PPS box-breathing profile",
        profile_id="study5_box_breathing_pps",
        participant_id="P001",
        capture_options={"enable_lsl": True},
    )

    assert project == parent / "study_5_pps_box_breathing_profile_20260617_151500"
    assert project.is_dir()
    assert focus_app.current_runner_session_root(state_root) == project
    settings = focus_app.load_runner_settings(state_root)
    assert settings["schema"] == "pps-focus-runner-settings.v1"
    assert settings["session_root"] == str(project)
    assert settings["current_output_project_root"] == str(project)
    assert settings["diary_path"].endswith("_LOG-DIARY_DO_NOT_DELETE.txt")
    assert settings["last_profile_id"] == "study5_box_breathing_pps"
    assert settings["last_participant_id"] == "P001"
    assert settings["last_capture_options"]["enable_lsl"] is True


def test_timestamped_output_environment_uses_parent_and_collision_suffix(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    parent = tmp_path / "operator_outputs"
    parent.mkdir()
    monkeypatch.setattr(focus_app.time, "strftime", lambda _fmt: "20260618_091011")
    first = parent / "my_lab_pilot_20260618_091011"
    first.mkdir()

    root, diary, slug = focus_app.create_timestamped_output_environment(parent, "My Lab Pilot ä/ß")

    assert slug == "my_lab_pilot"
    assert root == parent / "my_lab_pilot_20260618_091011_2"
    assert root.is_dir()
    assert diary.parent == output_runner_logs_dir(root)
    assert diary.name.endswith("_LOG-DIARY_DO_NOT_DELETE.txt")
    assert not (root / diary.name).exists()


def test_initiate_data_collection_environment_groups_snapshot_metadata(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app
    from peripersonal_space_toolkit.profile_memory import _path_exists

    state_root = tmp_path / "state"
    parent = tmp_path / "operator_outputs"
    parent.mkdir()
    source_project = tmp_path / "source_profile"
    run_setup = source_project / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    run_setup.parent.mkdir(parents=True)
    run_csv = run_setup.parent / "experiment_block_order.csv"
    run_csv.write_text("participant_id\nP001\n", encoding="utf-8")
    run_setup.write_text(
        json.dumps(
            {
                "schema": "pps-experiment-run-setup.v1",
                "prepared": True,
                "csv_path": str(run_csv),
                "participant_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (source_project / "0_profile").mkdir(parents=True)
    (source_project / "0_profile" / "active_design.json").write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(focus_app, "DEFAULT_DASHBOARD_STATE_ROOT", state_root)
    monkeypatch.setattr(focus_app.time, "strftime", lambda fmt: "20260618_205901" if "%Y%m%d" in fmt else "2026-06-18T20:59:01")
    monkeypatch.setattr(
        focus_app,
        "_materialize_profile_run_setup",
        lambda profile, progress_callback=None: (SimpleNamespace(), SimpleNamespace(), run_setup),
    )
    monkeypatch.setattr(
        focus_app,
        "resolve_profile_entry",
        lambda *_args, **_kwargs: {
            "profile_id": focus_app.STUDY5_PROFILE_ID,
            "display_name": "Study 5",
            "kind": "bundled",
            "dashboard_project_id": "profile_study5_box_breathing_pps",
            "project_dir": str(source_project),
            "participant_count": 1,
            "participant_ids": ["P001"],
        },
    )
    monkeypatch.setattr(
        focus_app,
        "prepare_profile_audio_assets",
        lambda *_args, **_kwargs: {"prepared_count": 0, "reused_count": 1, "results": []},
    )

    result = focus_app.initiate_data_collection_environment(
        parent_folder=parent,
        profile_id=focus_app.STUDY5_PROFILE_ID,
        session_name="Study5",
        participant_id="P001",
        capture_options={"enable_lsl": False},
    )

    environment_root = Path(result["environment_root"])
    metadata_dir = output_metadata_dir(environment_root)
    project_state_dir = output_project_state_dir(environment_root)
    profile_snapshot_dir = output_profile_snapshot_dir(environment_root)
    assert environment_root == parent / "study5_20260618_205901"
    assert metadata_dir.is_dir()
    assert Path(result["diary_path"]).parent == output_runner_logs_dir(environment_root)
    assert (project_state_dir / "output_diary.v1.jsonl").is_file()
    assert (project_state_dir / "dashboard_runner_bridge_manifest.v1.json").is_file()
    copied_run_setup = profile_snapshot_dir / focus_app.STUDY5_PROFILE_ID / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    assert _path_exists(copied_run_setup)
    assert not (environment_root / "output_diary.v1.jsonl").exists()
    assert not (environment_root / "dashboard_runner_bridge_manifest.v1.json").exists()
    assert not (environment_root / "study_profile_snapshot").exists()

    bridge = json.loads((project_state_dir / "dashboard_runner_bridge_manifest.v1.json").read_text(encoding="utf-8"))
    assert bridge["environment_metadata_dir"] == str(metadata_dir)
    assert bridge["acquisition_profile_snapshot_dir"] == str(profile_snapshot_dir / focus_app.STUDY5_PROFILE_ID)
    settings = focus_app.load_runner_settings(state_root)
    assert settings["current_output_project_root"] == str(environment_root)
    assert str(settings["diary_path"]).replace("\\\\?\\", "") == result["diary_path"]


def test_prepare_profile_audio_assets_reuses_scanned_generated_packages(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    run_setup_manifest = tmp_path / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    run_setup_manifest.parent.mkdir(parents=True)
    run_setup_manifest.write_text("{}", encoding="utf-8")
    existing_manifest = tmp_path / "sessions" / "P001_existing" / "session_manifest.json"
    existing_manifest.parent.mkdir(parents=True)
    existing_manifest.write_text("{}", encoding="utf-8")
    generated_manifest = tmp_path / "sessions" / "P002_generated" / "session_manifest.json"
    generated_manifest.parent.mkdir(parents=True)

    prepared_participants: list[str] = []
    queue_records: list[dict[str, object]] = []
    activity_records: list[tuple[tuple[object, ...], dict[str, object]]] = []
    output_root = tmp_path / "operator_selected_output"

    monkeypatch.setattr(
        focus_app,
        "_materialize_profile_run_setup",
        lambda profile, progress_callback=None: (
            SimpleNamespace(design_path=tmp_path / "design.json"),
            SimpleNamespace(),
            run_setup_manifest,
        ),
    )

    def fake_asset_status(run_setup_path, participant_id, **_kwargs):
        assert run_setup_path == run_setup_manifest
        assert Path(_kwargs["session_root"]) == output_root
        if participant_id == "P001":
            return {
                "participant_id": "P001",
                "generated": True,
                "status": "generated",
                "source": "session_scan",
                "session_manifest_path": str(existing_manifest),
                "message": "Prepared local audio package is available.",
                "data_collected": False,
            }
        return {
            "participant_id": participant_id,
            "generated": False,
            "status": "not_generated",
            "source": "",
            "session_manifest_path": "",
            "message": "No prepared local audio package found.",
            "data_collected": False,
        }

    def fake_prepare_segment_run_package(run_setup_path, participant_id, **_kwargs):
        assert run_setup_path == run_setup_manifest
        assert Path(_kwargs["session_root"]) == output_root
        prepared_participants.append(participant_id)
        return SimpleNamespace(
            manifest_path=generated_manifest,
            session_dir=generated_manifest.parent,
            blocks=[object(), object()],
        )

    monkeypatch.setattr(focus_app, "prepared_session_asset_status", fake_asset_status)
    monkeypatch.setattr(focus_app, "prepare_segment_run_package", fake_prepare_segment_run_package)
    monkeypatch.setattr(focus_app, "record_prepared_session_queue", lambda **kwargs: queue_records.append(kwargs))
    monkeypatch.setattr(focus_app, "update_profile_runner_settings", lambda **_kwargs: {})
    monkeypatch.setattr(
        focus_app,
        "record_experiment_activity",
        lambda *args, **kwargs: activity_records.append((args, kwargs)),
    )

    result = focus_app.prepare_profile_audio_assets(
        "study5_box_breathing_pps",
        ["P001", "P002"],
        session_root=output_root,
    )

    assert prepared_participants == ["P002"]
    assert result["prepared_count"] == 1
    assert result["reused_count"] == 1
    assert [row["status"] for row in result["results"]] == ["already_ready", "generated"]
    assert queue_records[0]["participant_id"] == "P001"
    assert queue_records[0]["status"] == "ready"
    assert queue_records[0]["session_manifest_path"] == existing_manifest
    assert [record["status"] for record in queue_records if record["participant_id"] == "P002"] == ["preparing", "ready"]
    assert activity_records


def test_prepare_profile_focus_session_rejects_unfinished_profile(monkeypatch):
    from peripersonal_space_toolkit import dashboard_app, focus_app

    class FakeController:
        def __init__(self, **_kwargs):
            self.current_run_package = None

        def preload_inventory_payload(self):
            return {
                "profiles": [
                    {
                        "template_id": "canzoneri_2012_dynamic_sounds",
                        "finished_profile": False,
                        "segment_6_launchable": False,
                        "profile_completion_status": "unfinished_preload",
                    }
                ]
            }

    monkeypatch.setattr(dashboard_app, "DashboardController", FakeController)

    with pytest.raises(ValueError, match="not a finished Segment 6 launchable profile"):
        focus_app.prepare_profile_focus_session("canzoneri_2012_dynamic_sounds", "P001")


def test_prepare_last_or_latest_focus_session_skips_non_launchable_pointer(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    empty_manifest = _write_minimal_session_manifest(tmp_path)
    fallback_manifest = tmp_path / "fallback" / "session_manifest.json"
    fallback_manifest.parent.mkdir(parents=True)

    monkeypatch.setattr(
        focus_app,
        "load_last_experiment_pointer",
        lambda: {"session_manifest_path": str(empty_manifest), "participant_id": "P001"},
    )
    monkeypatch.setattr(
        focus_app,
        "prepare_latest_focus_session",
        lambda participant_id=None, session_root=None, progress_callback=None: fallback_manifest,
    )

    assert focus_app.prepare_last_or_latest_focus_session("P001") == fallback_manifest


def test_prepare_last_or_latest_focus_session_skips_pointer_outside_output_root(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import focus_app

    old_root = tmp_path / "old_output"
    old_root.mkdir()
    old_manifest = _write_focus_preview_session_manifest(old_root)
    new_root = tmp_path / "new_output"
    fallback_manifest = new_root / "P001_fallback" / "session_manifest.json"
    fallback_manifest.parent.mkdir(parents=True)
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        focus_app,
        "load_last_experiment_pointer",
        lambda: {"session_manifest_path": str(old_manifest), "participant_id": "P001"},
    )

    def fake_prepare_latest(participant_id=None, session_root=None, progress_callback=None):
        calls["participant_id"] = participant_id
        calls["session_root"] = session_root
        return fallback_manifest

    monkeypatch.setattr(focus_app, "prepare_latest_focus_session", fake_prepare_latest)

    assert focus_app.prepare_last_or_latest_focus_session("P001", session_root=new_root) == fallback_manifest
    assert calls["participant_id"] == "P001"
    assert calls["session_root"] == new_root
