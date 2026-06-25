"""Validate OS mouse-click delivery into the visible Tk runner.

This internal harness opens the real Tk experiment runner surface, replaces the
hardware audio engine with a deterministic fake engine, starts a one-block test
session, and sends armed OS mouse clicks to the runner's click target. It is
intended to fill the gap between controller-level click-path tests and real
participant hardware sessions without playing any signal through the audio
interface.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.design import ProtocolSpec, default_design  # noqa: E402
from peripersonal_space_toolkit.session_runner import RESPONSE_MARKER_GAIN, prepare_run_package  # noqa: E402


SCHEMA = "pps-visible-runner-os-click-stress.v1"


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"visible_runner_os_click_stress_{stamp}"


def _compact_design() -> Any:
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
        random_seed=20260612,
    )
    return design


def _prepare_render_dir(output_dir: Path, *, sample_rate: int) -> Path:
    render_dir = output_dir / "rendered_input"
    render_dir.mkdir(parents=True, exist_ok=True)
    wav_path = render_dir / "visible_runner_click_validation.wav"
    frames = max(1, int(round(sample_rate * 0.050)))
    data = np.zeros((frames, 3), dtype=np.float32)
    sf.write(wav_path, data, sample_rate)
    (render_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "schema": "pps-render-manifest.v1",
                "status": "rendered_reference",
                "wav_outputs": [{"path": str(wav_path), "sha256": "validation-visible-runner-click"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return render_dir


def _sleep_with_tk(root: Any, duration_s: float) -> None:
    deadline = time.perf_counter() + max(0.0, duration_s)
    while time.perf_counter() < deadline:
        try:
            root.update()
        except Exception:
            return
        time.sleep(0.005)


class FakeVisibleRunnerAudioEngine:
    """Deterministic stand-in for runner.AudioEngine that never touches hardware."""

    def __init__(self, *, sample_rate: int, planned_marker_delay_ms: float, block_hold_s: float):
        self.sample_rate = int(sample_rate)
        self.planned_marker_delay_ms = float(planned_marker_delay_ms)
        self.block_hold_s = float(block_hold_s)
        self.max_output_channels = 3
        self.runtime_output_channels = 3
        self.tactile_output_channel = 2
        self.audio_volume = 0.5
        self.tactile_volume = 0.5
        self.elapsed_time = 0.0
        self.stop_flag = False
        self.playback_started = threading.Event()
        self.playback_finished = threading.Event()
        self.trigger_records: list[dict[str, Any]] = []
        self._audio_event_callback = None
        self._play_start_perf = 0.0

    def load_click_sound(self, path: str) -> bool:
        return True

    def preload_audio(self, paths: list[str]) -> None:
        return None

    def play_instruction(self, path: str, on_complete=None) -> bool:
        if on_complete is not None:
            on_complete(True)
        return True

    def start_background_music(self, path: str, volume: float):
        return None

    def set_background_volume(self, volume: float) -> None:
        return None

    def set_main_volume(self, volume: float) -> None:
        self.audio_volume = float(volume)

    def start_recording(self, output_path: str) -> bool:
        return False

    def is_recording(self) -> bool:
        return False

    def stop_recording(self, output_path: str, interrupted: bool = False) -> None:
        return None

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self._audio_event_callback = audio_event_callback
        self._play_start_perf = time.perf_counter()
        self.elapsed_time = 0.0
        self.stop_flag = False
        if audio_event_callback and block_event_schedule is not None:
            block_event_schedule.reset()
            for event in block_event_schedule.consume_buffer(0, self.sample_rate * 60):
                now = time.perf_counter()
                payload = dict(event.payload)
                payload.update(
                    {
                        "event_type": event.event_type,
                        "sample_index": event.sample_index,
                        "buffer_start_sample": 0,
                        "sample_offset_in_buffer": event.sample_index,
                        "sample_rate": self.sample_rate,
                        "trigger_key": event.trigger_key,
                        "callback_perf_counter": now,
                        "stream_current_time": now,
                        "stream_output_buffer_dac_time": now,
                    }
                )
                audio_event_callback(payload)
        elif audio_event_callback is not None:
            now = time.perf_counter()
            audio_event_callback(
                {
                    "event_type": "audio_sample_zero",
                    "sample_index": 0,
                    "buffer_start_sample": 0,
                    "sample_offset_in_buffer": 0,
                    "sample_rate": self.sample_rate,
                    "callback_perf_counter": now,
                    "stream_current_time": now,
                    "stream_output_buffer_dac_time": now,
                }
            )
        self.playback_started.set()
        deadline = time.perf_counter() + max(0.1, self.block_hold_s)
        while time.perf_counter() < deadline and not self.stop_flag:
            self.elapsed_time = time.perf_counter() - self._play_start_perf
            if progress_callback is not None:
                progress_callback(self.elapsed_time)
            time.sleep(0.005)
        self.elapsed_time = time.perf_counter() - self._play_start_perf
        if progress_callback is not None:
            progress_callback(self.elapsed_time)
        self.playback_finished.set()
        return not self.stop_flag

    def trigger_click(self, metadata=None, marker_gain=None) -> None:
        now = time.perf_counter()
        delay_s = max(0.0, self.planned_marker_delay_ms / 1000.0)
        sample_offset = int(round(delay_s * self.sample_rate))
        elapsed_samples = int(round((now - self._play_start_perf) * self.sample_rate))
        payload = {
            "event_type": "response_marker_start",
            "sample_index": elapsed_samples + sample_offset,
            "buffer_start_sample": elapsed_samples,
            "sample_offset_in_buffer": sample_offset,
            "sample_rate": self.sample_rate,
            "callback_perf_counter": now,
            "stream_current_time": now,
            "stream_output_buffer_dac_time": now,
            "marker_channel": 2,
            "marker_gain": marker_gain if marker_gain is not None else RESPONSE_MARKER_GAIN,
            **dict(metadata or {}),
        }
        self.trigger_records.append(payload)
        if self._audio_event_callback is not None:
            self._audio_event_callback(payload)

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None

    def stop(self) -> None:
        self.stop_flag = True

    def shutdown(self) -> None:
        self.stop()


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean_ms": None, "sd_ms": None, "median_ms": None, "p95_ms": None, "max_ms": None, "min_ms": None}
    ordered = sorted(float(value) for value in values)
    p95_index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return {
        "count": len(ordered),
        "mean_ms": statistics.fmean(ordered),
        "sd_ms": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[p95_index],
        "max_ms": max(ordered),
        "min_ms": min(ordered),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Visible Runner OS Click Stress",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Armed OS clicks: `{report['armed']}`",
        f"- Requested clicks: `{report['requested_click_count']}`",
        f"- Mouse clicks logged: `{report['mouse_click_count']}`",
        f"- Response markers logged: `{report['response_marker_start_count']}`",
        f"- Linked pairs: `{report['linked_pair_count']}`",
        f"- In-target mouse clicks: `{report['in_target_mouse_click_count']}`",
        f"- During-playback mouse clicks: `{report['during_playback_mouse_click_count']}`",
        f"- Marker-minus-mouse: `{json.dumps(report['marker_minus_mouse_ms'], sort_keys=True)}`",
        f"- Screenshot: `{report.get('screenshot_path') or 'not captured'}`",
        "",
        "This validates OS mouse-click delivery into the visible Tk runner using a fake audio engine. It does not play audio, measure physical loopback, or measure Woojer mechanical onset.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _capture_window_screenshot(root: Any, path: Path) -> str:
    try:
        from PIL import ImageGrab

        root.update_idletasks()
        x = int(root.winfo_rootx())
        y = int(root.winfo_rooty())
        width = int(root.winfo_width())
        height = int(root.winfo_height())
        if width <= 0 or height <= 0:
            return ""
        path.parent.mkdir(parents=True, exist_ok=True)
        image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
        image.save(path)
        return str(path)
    except Exception:
        return ""


def _event_payload(event: Any) -> dict[str, Any]:
    return dict(getattr(event, "payload", {}) or {})


def _build_pair_rows(events: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    mouse_events = [event for event in events if getattr(event, "event_type", "") == "mouse_click"]
    markers = [event for event in events if getattr(event, "event_type", "") == "response_marker_start"]
    mouse_by_id = {int(getattr(event, "event_id")): event for event in mouse_events}
    pair_rows: list[dict[str, Any]] = []
    delays: list[float] = []
    missing_mouse_ids: list[int] = []
    duplicate_mouse_ids: list[int] = []
    seen_mouse_ids: set[int] = set()
    qualities: dict[str, int] = {}

    for marker in markers:
        marker_payload = _event_payload(marker)
        mouse_event_id = int(marker_payload.get("mouse_event_id") or 0)
        if mouse_event_id in seen_mouse_ids:
            duplicate_mouse_ids.append(mouse_event_id)
        seen_mouse_ids.add(mouse_event_id)
        quality = str(marker_payload.get("timestamp_quality") or "")
        qualities[quality] = qualities.get(quality, 0) + 1
        mouse = mouse_by_id.get(mouse_event_id)
        if mouse is None:
            missing_mouse_ids.append(mouse_event_id)
            continue
        mouse_payload = _event_payload(mouse)
        delta_ms = (float(getattr(marker, "monotonic_time")) - float(getattr(mouse, "monotonic_time"))) * 1000.0
        delays.append(delta_ms)
        pair_rows.append(
            {
                "mouse_event_id": mouse_event_id,
                "response_marker_event_id": getattr(marker, "event_id"),
                "mouse_x": mouse_payload.get("x", ""),
                "mouse_y": mouse_payload.get("y", ""),
                "in_target": mouse_payload.get("in_target", ""),
                "during_playback": mouse_payload.get("during_playback", ""),
                "mouse_monotonic_time": f"{float(getattr(mouse, 'monotonic_time')):.9f}",
                "response_marker_monotonic_time": f"{float(getattr(marker, 'monotonic_time')):.9f}",
                "marker_minus_mouse_ms": f"{delta_ms:.6f}",
                "timestamp_quality": quality,
                "marker_channel": marker_payload.get("marker_channel", ""),
                "marker_gain": marker_payload.get("marker_gain", ""),
            }
        )

    return pair_rows, {
        "mouse_events": mouse_events,
        "markers": markers,
        "missing_mouse_ids_for_markers": missing_mouse_ids,
        "duplicate_response_markers_for_mouse_event_ids": duplicate_mouse_ids,
        "missing_response_marker_for_mouse_event_ids": sorted(set(mouse_by_id) - seen_mouse_ids),
        "response_timestamp_quality_counts": qualities,
        "marker_minus_mouse_ms": _summary(delays),
    }


def run_stress(
    *,
    output_dir: Path,
    count: int,
    interval_s: float,
    start_delay_s: float,
    planned_marker_delay_ms: float,
    sample_rate: int,
    armed: bool,
    block_hold_s: float | None = None,
) -> dict[str, Any]:
    if not armed:
        raise RuntimeError("This validation requires --armed so the visible runner receives real OS clicks.")

    try:
        import tkinter as tk
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(f"Tkinter is required for visible runner validation: {exc}") from exc
    try:
        from pynput.mouse import Button, Controller
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(f"pynput is required to send OS mouse clicks: {exc}") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    render_dir = _prepare_render_dir(output_dir, sample_rate=sample_rate)
    package = prepare_run_package(
        _compact_design(),
        "P001",
        render_dir=render_dir,
        session_root=output_dir / "sessions",
        created_at=datetime.now(),
    )
    hold_s = (
        block_hold_s
        if block_hold_s is not None
        else max(3.0, start_delay_s + max(0, count) * (max(0.0, interval_s) + 0.75) + 1.0)
    )
    engine = FakeVisibleRunnerAudioEngine(
        sample_rate=sample_rate,
        planned_marker_delay_ms=planned_marker_delay_ms,
        block_hold_s=hold_s,
    )

    from peripersonal_space_toolkit import runner as runner_mod

    old_audio_engine = runner_mod.AudioEngine
    old_find_output_device = runner_mod.find_output_device
    old_pyaudio = runner_mod.PYAUDIOWPATCH_AVAILABLE
    old_loopback = runner_mod.ENABLE_LOOPBACK_RECORDING
    old_setup_keyboard = runner_mod.PPSExperimentApp._setup_keyboard_listener
    old_paths = {
        "POST_BLOCK_INSTRUCTIONS": runner_mod.POST_BLOCK_INSTRUCTIONS,
        "FINISH_MESSAGE": runner_mod.FINISH_MESSAGE,
        "INTERIM_MESSAGE": runner_mod.INTERIM_MESSAGE,
        "PRE_BLOCK_INSTRUCTIONS": runner_mod.PRE_BLOCK_INSTRUCTIONS,
    }
    root = None
    app = None
    click_rows: list[dict[str, Any]] = []
    try:
        runner_mod.AudioEngine = lambda _device_idx: engine
        runner_mod.find_output_device = lambda: (999, "Validation fake audio engine", True)
        runner_mod.PYAUDIOWPATCH_AVAILABLE = False
        runner_mod.ENABLE_LOOPBACK_RECORDING = False
        runner_mod.PPSExperimentApp._setup_keyboard_listener = lambda self: None
        missing_audio = str(output_dir / "missing_instruction.wav")
        runner_mod.POST_BLOCK_INSTRUCTIONS = missing_audio
        runner_mod.FINISH_MESSAGE = missing_audio
        runner_mod.INTERIM_MESSAGE = missing_audio
        runner_mod.PRE_BLOCK_INSTRUCTIONS = missing_audio

        root = tk.Tk()
        root.title("PPS Validation Runner - OS Click Stress")
        app = runner_mod.PPSExperimentApp(root)
        app.current_run_package = package
        app.participant_id = package.participant_id
        app.participant_folder = str(package.session_dir)
        app._run_block_by_path = {str(block.wav_path.resolve()): block for block in package.blocks}
        app._initialize_segment_event_logging()
        app.current_part = 1
        app.current_block = 0
        app.part1_files = [str(block.wav_path) for block in package.blocks]
        app.part2_files = []
        app.block_files = app.part1_files
        app.demographics_completed = True
        app.status_label.config(text=f"OK {package.participant_id} validation", foreground="green")
        app._update_block_display()
        app._update_part_display()
        app._enable_all_experiment_controls()
        app._start_mouse_listener()
        root.update_idletasks()
        root.lift()
        root.attributes("-topmost", True)
        root.after(250, lambda: root.attributes("-topmost", False))
        root.update()
        screenshot_path = _capture_window_screenshot(root, output_dir / "visible_runner_window.png")
        controller = Controller()
        target_x, target_y = app.click_target.get_center_coords()
        state: dict[str, Any] = {
            "started_at_perf": time.perf_counter(),
            "error": "",
            "clicks_sent": 0,
        }

        def _send_click(index: int = 1) -> None:
            if not engine.playback_started.is_set():
                if time.perf_counter() - state["started_at_perf"] > 5.0:
                    state["error"] = "Visible runner fake playback did not start in time."
                    root.quit()
                    return
                root.after(10, lambda: _send_click(index))
                return
            scheduled_perf = time.perf_counter()
            controller.position = (target_x, target_y)
            before_perf = time.perf_counter()
            before_unix = time.time()
            controller.click(Button.left)
            after_perf = time.perf_counter()
            click_rows.append(
                {
                    "click_index": index,
                    "target_x": target_x,
                    "target_y": target_y,
                    "before_click_perf_counter": f"{before_perf:.9f}",
                    "after_click_perf_counter": f"{after_perf:.9f}",
                    "before_click_unix_time": f"{before_unix:.9f}",
                    "dispatch_duration_ms": f"{(after_perf - before_perf) * 1000.0:.3f}",
                    "scheduled_perf_counter": f"{scheduled_perf:.9f}",
                    "button": "left",
                }
            )
            state["clicks_sent"] = index
            if index < max(0, count):
                root.after(max(1, int(round(interval_s * 1000.0))), lambda: _send_click(index + 1))

        def _finish_when_ready() -> None:
            if app._session_outputs_written:
                root.quit()
                return
            if time.perf_counter() - state["started_at_perf"] > max(5.0, hold_s + 3.0):
                app._write_segment_event_outputs(completed=True, interrupted=False)
                root.quit()
                return
            root.after(10, _finish_when_ready)

        root.after(0, lambda: app._start_actual_block_playback(app.block_files[0], 1))
        root.after(max(1, int(round(start_delay_s * 1000.0))), _send_click)
        root.after(10, _finish_when_ready)
        root.mainloop()
        if state["error"]:
            raise RuntimeError(str(state["error"]))
        if not app._session_outputs_written:
            app._write_segment_event_outputs(completed=True, interrupted=False)
        if app.run_events is not None:
            app.run_events.flush_callback_events()

        events = list(app.run_event_logger.events if app.run_event_logger is not None else [])
        pair_rows, metrics = _build_pair_rows(events)
        mouse_events = metrics["mouse_events"]
        markers = metrics["markers"]
        in_target_count = sum(1 for event in mouse_events if bool(_event_payload(event).get("in_target")))
        during_playback_count = sum(1 for event in mouse_events if bool(_event_payload(event).get("during_playback")))
        timing = metrics["marker_minus_mouse_ms"]
        median_delay = timing.get("median_ms")
        timing_ok = median_delay is not None and abs(float(median_delay) - planned_marker_delay_ms) <= 2.0
        qualities = metrics["response_timestamp_quality_counts"]
        passed = bool(
            len(mouse_events) == count
            and len(markers) == count
            and len(pair_rows) == count
            and in_target_count == count
            and during_playback_count == count
            and not metrics["missing_mouse_ids_for_markers"]
            and not metrics["missing_response_marker_for_mouse_event_ids"]
            and not metrics["duplicate_response_markers_for_mouse_event_ids"]
            and qualities.get("dac_time_sample_exact", 0) == count
            and timing_ok
            and app._session_outputs_written
        )

        _write_csv(
            output_dir / "visible_runner_os_click_dispatch.csv",
            click_rows,
            [
                "click_index",
                "target_x",
                "target_y",
                "before_click_perf_counter",
                "after_click_perf_counter",
                "before_click_unix_time",
                "dispatch_duration_ms",
                "scheduled_perf_counter",
                "button",
            ],
        )
        _write_csv(
            output_dir / "visible_runner_os_click_pairs.csv",
            pair_rows,
            [
                "mouse_event_id",
                "response_marker_event_id",
                "mouse_x",
                "mouse_y",
                "in_target",
                "during_playback",
                "mouse_monotonic_time",
                "response_marker_monotonic_time",
                "marker_minus_mouse_ms",
                "timestamp_quality",
                "marker_channel",
                "marker_gain",
            ],
        )
        report = {
            "schema": SCHEMA,
            "passed": passed,
            "armed": bool(armed),
            "requested_click_count": count,
            "mouse_click_count": len(mouse_events),
            "response_marker_start_count": len(markers),
            "linked_pair_count": len(pair_rows),
            "in_target_mouse_click_count": in_target_count,
            "during_playback_mouse_click_count": during_playback_count,
            "missing_mouse_ids_for_markers": metrics["missing_mouse_ids_for_markers"],
            "missing_response_marker_for_mouse_event_ids": metrics["missing_response_marker_for_mouse_event_ids"],
            "duplicate_response_markers_for_mouse_event_ids": metrics["duplicate_response_markers_for_mouse_event_ids"],
            "response_timestamp_quality_counts": qualities,
            "marker_minus_mouse_ms": timing,
            "planned_marker_delay_ms": planned_marker_delay_ms,
            "timing_tolerance_ms": 2.0,
            "session_outputs_written": bool(app._session_outputs_written),
            "session_dir": str(package.session_dir),
            "events_csv": str(package.session_dir / "events.csv"),
            "timing_qc_csv": str(package.session_dir / "analysis" / f"{package.session_id}_timing_qc.csv"),
            "lsl_markers_csv": str(package.session_dir / "lsl_markers.csv"),
            "trigger_dictionary_json": str(package.session_dir / "trigger_dictionary.json"),
            "fake_audio_engine": True,
            "hardware_audio_touched": False,
            "click_dispatch_method": "pynput.mouse.Controller.click",
            "screenshot_path": screenshot_path,
            "limitations": [
                "This validates OS click delivery into the visible Tk runner mouse listener and click target using a fake audio engine.",
                "It does not play audio through the Komplete Audio 6 and does not measure physical response-marker loopback.",
                "It does not measure Woojer mechanical vibration onset.",
            ],
        }
        (output_dir / "visible_runner_os_click_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        _write_markdown_report(report, output_dir / "visible_runner_os_click_report.md")
        return report
    finally:
        if app is not None:
            try:
                if app.mouse_listener:
                    app.mouse_listener.stop()
            except Exception:
                pass
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        runner_mod.AudioEngine = old_audio_engine
        runner_mod.find_output_device = old_find_output_device
        runner_mod.PYAUDIOWPATCH_AVAILABLE = old_pyaudio
        runner_mod.ENABLE_LOOPBACK_RECORDING = old_loopback
        runner_mod.PPSExperimentApp._setup_keyboard_listener = old_setup_keyboard
        for key, value in old_paths.items():
            setattr(runner_mod, key, value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run visible Tk-runner OS mouse-click validation.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval-s", type=float, default=0.05)
    parser.add_argument("--start-delay-s", type=float, default=0.10)
    parser.add_argument("--planned-marker-delay-ms", type=float, default=8.0)
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--armed", action="store_true", help="Actually send OS mouse clicks to the validation runner window.")
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    try:
        report = run_stress(
            output_dir=output_dir,
            count=args.count,
            interval_s=args.interval_s,
            start_delay_s=args.start_delay_s,
            planned_marker_delay_ms=args.planned_marker_delay_ms,
            sample_rate=args.sample_rate,
            armed=args.armed,
        )
    except Exception as exc:
        output_dir.mkdir(parents=True, exist_ok=True)
        failure = {
            "schema": SCHEMA,
            "passed": False,
            "armed": bool(args.armed),
            "error": str(exc),
        }
        (output_dir / "visible_runner_os_click_report.json").write_text(json.dumps(failure, indent=2), encoding="utf-8")
        print(f"Visible runner OS-click stress failed: {exc}", file=sys.stderr)
        print(f"Wrote failure report: {output_dir / 'visible_runner_os_click_report.json'}")
        return 1
    print(f"Wrote visible runner OS-click report: {output_dir / 'visible_runner_os_click_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
