from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import soundfile as sf

from peripersonal_space_toolkit.focus_layout import (
    focus_palette_contrast_report,
    render_focus_layout_profile,
)
from peripersonal_space_toolkit.session_runner import RUN_PACKAGE_SCHEMA, SessionCaptureOptions, load_run_package


def _write_minimal_session_manifest(
    tmp_path: Path,
    *,
    participant_id: str = "P001",
    source_run_setup_manifest_path: Path | None = None,
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
        "blocks": [],
    }
    if source_run_setup_manifest_path is not None:
        payload["source_run_setup_manifest_path"] = str(source_run_setup_manifest_path)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


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
    assert "8 Block 07" in plan
    assert "13 Block 12" in plan
    assert "14 Top-up if needed" in plan
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
    assert "Recording" in joined
    assert "Experiment Control" in joined
    if window.layout_profile.screen_class != "constrained":
        assert "Block Order" in joined
        assert "Stimulus / Tactile / Click Timeline" in joined
    assert "Next tactile" in joined
    assert "Instruction clips" in joined
    assert "No preloaded clips" in joined
    assert "Include name in LSL/session markers" in joined
    assert "events.csv on" in joined
    assert "LSL/event protocol off" in joined
    assert "Backup WAV (Belts and Suspenders)" in joined
    assert "Top up missed tactile trials at part end" in joined
    assert "CLICK" in joined
    assert window.participant_code_combo.objectName() == "runnerParticipantCombo"
    assert not window.participant_code_combo.isEditable()
    assert window.participant_code_combo.currentData() == "P001"
    placeholders = [line.placeholderText() for line in window.dialog.findChildren(q["QLineEdit"])]
    assert "Participant code" not in placeholders
    assert window.include_name_lsl_checkbox.objectName() == "nameSharingCheckbox"
    assert "(opt-in)" in window.include_name_lsl_checkbox.text()
    assert window.include_name_lsl_checkbox.minimumHeight() >= window.layout_profile.button_min_height + 8
    assert window.response_panel.width() == window.response_panel.height()
    assert window.response_panel.width() == window.layout_profile.response_panel_side
    assert window.output_panel is not window.processing_panel

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
    assert window.response_panel.minimumWidth() == profile.response_panel_side
    assert window.response_panel.minimumHeight() == profile.response_panel_side
    assert window.response_panel.maximumWidth() == profile.response_panel_side
    assert window.response_panel.maximumHeight() == profile.response_panel_side
    assert window.response_panel.geometry().width() == window.response_panel.geometry().height()
    assert window.output_panel is not window.processing_panel
    assert window.processing_splitter.count() == 2
    expected_run_splitter_count = 2 if profile.right_stack_mode == "tabs" else 3
    assert window.run_splitter.count() == expected_run_splitter_count

    for widget in (
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
        window.block_plan_widget,
        window.output_summary,
        window.tactile_timeline_widget,
    ):
        _assert_widget_inside_dialog(widget, window.dialog)

    assert window.target_button.geometry().width() == profile.target_min_height
    assert window.target_button.geometry().height() == profile.target_min_height
    assert window.start_button.geometry().height() >= profile.button_min_height
    assert window.output_summary.geometry().height() >= profile.output_min_height
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


def test_launcher_uses_participant_dropdown_instead_of_text_entry():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
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
            participant_combo = dialog.findChild(q["QComboBox"], "participantCombo")
            assert participant_combo is not None
            assert participant_combo.count() >= 1
            placeholders = [line.placeholderText() for line in dialog.findChildren(q["QLineEdit"])]
            assert "Participant ID" not in placeholders
            assert "1-10" in placeholders
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

    assert exit_code == 1
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
        lambda _profile: {
            participant: {
                "participant_id": participant,
                "generated": participant != "P003",
                "status": "generated" if participant != "P003" else "not_generated",
                "data_collected": False,
            }
            for participant in participants
        },
    )

    def fake_prepare_profile_audio_assets(profile_id, participant_ids, *, progress_callback=None):
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
            dialogs = [widget for widget in app.topLevelWidgets() if widget.windowTitle() == "PPS Experiment Runner"]
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
    exit_code = focus_app.run_launcher_window(
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        participant_id="P001",
        initial_message="inspection",
    )

    assert exit_code == 1
    assert errors == []


def test_prepare_profile_focus_session_uses_finished_profile_gate(tmp_path: Path, monkeypatch):
    from peripersonal_space_toolkit import dashboard_app, focus_app

    manifest = tmp_path / "sessions" / "P123_run" / "session_manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    calls: dict[str, object] = {}

    class FakeController:
        current_run_package = None

        def __init__(self, **kwargs):
            calls["init_kwargs"] = kwargs

        def preload_inventory_payload(self):
            return {
                "profiles": [
                    {
                        "template_id": "study5_box_breathing_pps",
                        "variant_display": "Study 5",
                        "finished_profile": True,
                        "segment_6_launchable": True,
                    }
                ]
            }

        def load_template(self, profile_id, **kwargs):
            calls["profile_id"] = profile_id
            calls["load_template_kwargs"] = dict(kwargs)

        def prepare_session(self, payload, **kwargs):
            calls["payload"] = dict(payload)
            calls["prepare_session_kwargs"] = dict(kwargs)
            self.current_run_package = SimpleNamespace(
                manifest_path=manifest,
                source_run_setup_manifest_path=tmp_path / "run_setup.json",
                session_dir=manifest.parent,
            )
            return {}

    monkeypatch.setattr(dashboard_app, "DashboardController", FakeController)
    monkeypatch.setattr(focus_app, "DEFAULT_FOCUS_PROFILE_DESIGN_PATH", tmp_path / "focus_design.json")

    assert focus_app.prepare_profile_focus_session("study5_box_breathing_pps", "P123") == manifest
    assert calls["profile_id"] == "study5_box_breathing_pps"
    assert calls["load_template_kwargs"] == {"snapshot": False}
    assert calls["payload"] == {"participant_id": "P123"}
    assert calls["prepare_session_kwargs"] == {"progress_callback": None, "snapshot": False}
    assert calls["init_kwargs"]["design_path"] == tmp_path / "focus_design.json"


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
        prepared_participants.append(participant_id)
        return SimpleNamespace(
            manifest_path=generated_manifest,
            session_dir=generated_manifest.parent,
            blocks=[object(), object()],
        )

    monkeypatch.setattr(focus_app, "prepared_session_asset_status", fake_asset_status)
    monkeypatch.setattr(focus_app, "prepare_segment_run_package", fake_prepare_segment_run_package)
    monkeypatch.setattr(focus_app, "record_prepared_session_queue", lambda **kwargs: queue_records.append(kwargs))
    monkeypatch.setattr(
        focus_app,
        "record_experiment_activity",
        lambda *args, **kwargs: activity_records.append((args, kwargs)),
    )

    result = focus_app.prepare_profile_audio_assets("study5_box_breathing_pps", ["P001", "P002"])

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
        lambda participant_id=None, progress_callback=None: fallback_manifest,
    )

    assert focus_app.prepare_last_or_latest_focus_session("P001") == fallback_manifest
