from __future__ import annotations

import os
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


def _write_minimal_session_manifest(tmp_path: Path) -> Path:
    session_dir = tmp_path / "P001_20260613_120000"
    session_dir.mkdir()
    manifest_path = session_dir / "session_manifest.json"
    manifest_path.write_text(
        """{
  "schema": "%s",
  "participant_id": "P001",
  "session_id": "P001_20260613_120000",
  "created_at": "2026-06-13T12:00:00",
  "design_path": "design.json",
  "protocol_path": "protocol_schedule.csv",
  "render_manifest_path": "",
  "execution_mode": "participant_block_wavs",
  "blocks": []
}
"""
        % RUN_PACKAGE_SCHEMA,
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
    assert constrained.button_min_height >= 32
    assert constrained.target_min_height >= 138
    assert constrained.right_stack_mode == "tabs"
    assert compact.right_stack_mode == "tabs"
    assert standard.right_stack_mode == "resizable"
    assert constrained.recording_chip_columns == 2
    assert standard.recording_chip_columns == 3
    assert standard.target_min_height > constrained.target_min_height

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
    assert "Live Tactile Timeline" in joined
    assert "Next tactile" in joined
    assert "Instruction clips" in joined
    assert "No preloaded clips" in joined
    assert "Include name in LSL/session markers" in joined
    assert "events.csv on" in joined
    assert "LSL/event protocol off" in joined
    assert "Backup WAV (Belts and Suspenders)" in joined
    assert "Top up missed tactile trials at part end" in joined
    assert "CLICK" in joined

    screenshot = tmp_path / "focus_mode_shell.png"
    assert window.dialog.grab().save(str(screenshot))
    image = Image.open(screenshot).convert("RGB")
    stat = ImageStat.Stat(image)
    assert image.width >= 900
    assert image.height >= 600
    assert min(stat.stddev) > 2.0
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
    assert window.target_button.minimumHeight() >= profile.target_min_height
    assert window.output_summary.minimumHeight() == profile.output_min_height

    for widget in (
        window.target_button,
        window.start_button,
        window.pause_button,
        window.stop_button,
        window.close_button,
        window.output_summary,
        window.tactile_timeline_widget,
    ):
        _assert_widget_inside_dialog(widget, window.dialog)

    assert window.target_button.geometry().height() >= profile.target_min_height
    assert window.start_button.geometry().height() >= profile.button_min_height
    assert window.output_summary.geometry().height() >= profile.output_min_height
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
