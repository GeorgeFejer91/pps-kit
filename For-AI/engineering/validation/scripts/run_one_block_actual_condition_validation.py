"""Run one actual Segment 5/6 block through the runner under validation controls.

This is an internal hardware-validation harness. It keeps the package runtime as
the system under test, but adds lab-only safeguards around the run:

- exactly one prepared participant block is allowed
- Komplete ASIO or another single multichannel device is required by default
- playback gains default to a conservative validation level
- direct electrical input capture is attempted through the same ASIO device
- deterministic simulated clicks can be injected after tactile onsets

The script writes normal runner outputs plus a validation report. It is not a
participant-facing entry point.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


os.environ.setdefault("SD_ENABLE_ASIO", "1")

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    SessionRunnerController,
    load_run_package,
    prepare_segment_run_package,
)
from peripersonal_space_toolkit import runner as runtime_runner  # noqa: E402
from validate_one_block_actual_condition_run import validate_session  # noqa: E402


SCHEMA = "pps-one-block-actual-condition-run.v1"
SAFE_PLAYBACK_GAIN_DEFAULT = 0.05
SAFE_PLAYBACK_GAIN_MAX = 0.10
DEFAULT_OUTPUT_DIR = Path("artifacts") / "validation_runs" / "one_block_actual_condition_current"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    validation = report.get("actual_condition_audit") or {}
    capture = report.get("direct_capture") or {}
    digital = report.get("digital_output_evidence") or {}
    run_result = report.get("runner_result") or {}
    levels = report.get("signal_levels") or {}
    lines = [
        "# One-Block Actual-Condition Run",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Session dir: `{report.get('session_dir')}`",
        f"- Block duration s: `{report.get('block', {}).get('duration_s')}`",
        f"- Trial count: `{report.get('block', {}).get('trial_count')}`",
        f"- Simulated clicks: `{len(report.get('click_schedule') or [])}`",
        f"- Runner completed: `{run_result.get('completed')}`",
        f"- Actual-condition audit passed: `{validation.get('passed')}`",
        f"- Direct capture started: `{capture.get('started')}`",
        f"- Direct capture path: `{capture.get('path')}`",
        f"- Direct capture clipped channels: `{(capture.get('metadata') or {}).get('clipped_channels_1based')}`",
        f"- Digital output evidence path: `{digital.get('path')}`",
        f"- Digital output evidence dropped buffers: `{(digital.get('metadata') or {}).get('dropped_buffer_count')}`",
        f"- Source peaks: `{levels.get('source_peak_by_channel')}`",
        f"- Effective peaks after validation gain: `{levels.get('effective_peak_by_channel')}`",
        "",
        "## Device",
        "",
        f"- Device index: `{report.get('device', {}).get('index')}`",
        f"- Device name: `{report.get('device', {}).get('name')}`",
        f"- Host API: `{report.get('device', {}).get('hostapi')}`",
        f"- Input/output channels: `{report.get('device', {}).get('max_input_channels')}` / `{report.get('device', {}).get('max_output_channels')}`",
        "",
        "## Outputs",
        "",
    ]
    for key, value in (report.get("outputs") or {}).items():
        lines.append(f"- {key}: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _float(value: Any, default: float = math.nan) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _signal_levels(path: Path, *, audio_gain: float, tactile_gain: float) -> dict[str, Any]:
    samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    peaks = np.max(np.abs(samples), axis=0).astype(float).tolist() if samples.size else []
    rms = np.sqrt(np.mean(np.square(samples.astype(np.float64)), axis=0)).astype(float).tolist() if samples.size else []
    gains = [audio_gain, audio_gain, tactile_gain]
    effective = [float(peak) * gains[min(index, len(gains) - 1)] for index, peak in enumerate(peaks)]
    return {
        "sample_rate": int(sample_rate),
        "channels": int(samples.shape[1]),
        "frames": int(samples.shape[0]),
        "duration_s": float(samples.shape[0] / sample_rate),
        "source_peak_by_channel": peaks,
        "source_rms_by_channel": rms,
        "audio_gain": float(audio_gain),
        "tactile_gain": float(tactile_gain),
        "effective_peak_by_channel": effective,
        "effective_global_peak": max(effective, default=0.0),
    }


def _device_snapshot(sd_module: Any, device_idx: int) -> dict[str, Any]:
    info = sd_module.query_devices(device_idx)
    hostapi = sd_module.query_hostapis(int(info["hostapi"]))["name"]
    return {
        "index": int(device_idx),
        "name": str(info.get("name", "")),
        "hostapi": hostapi,
        "max_input_channels": int(info.get("max_input_channels", 0)),
        "max_output_channels": int(info.get("max_output_channels", 0)),
        "default_samplerate": float(info.get("default_samplerate", 0.0)),
    }


def _asio_settings_for_input(sd_module: Any, channels: int) -> Any:
    if hasattr(sd_module, "AsioSettings"):
        return sd_module.AsioSettings(channel_selectors=list(range(int(channels))))
    return None


class DirectInputCaptureAudioEngine(runtime_runner.AudioEngine):
    """AudioEngine plus validation-only direct input capture."""

    def __init__(
        self,
        device_idx: int,
        *,
        capture_channels: int,
        capture_sample_rate: int,
        capture_latency_s: float,
        capture_blocksize: int,
        capture_enabled: bool = True,
    ):
        runtime_runner.ENABLE_LOOPBACK_RECORDING = False
        super().__init__(device_idx)
        self.capture_channels = int(capture_channels)
        self.capture_sample_rate = int(capture_sample_rate)
        self.capture_latency_s = float(capture_latency_s)
        self.capture_blocksize = int(capture_blocksize)
        self.capture_enabled = bool(capture_enabled)
        self.direct_capture_started = False
        self.direct_capture_path: Path | None = None
        self.direct_capture_metadata: dict[str, Any] = {}
        self.digital_evidence_metadata: dict[str, Any] = {}
        self._direct_capture_stream = None
        self._direct_capture_active = False
        self._direct_capture_chunks: list[np.ndarray] = []
        self._direct_capture_statuses: list[str] = []
        self._direct_capture_lock = threading.Lock()
        self.audio_started = threading.Event()
        self.audio_zero_perf_counter: float | None = None

    def _emit_audio_event(self, event_type, time_info=None, **payload):  # type: ignore[override]
        if event_type == "audio_sample_zero" and self.audio_zero_perf_counter is None:
            self.audio_zero_perf_counter = time.perf_counter()
            self.audio_started.set()
        return super()._emit_audio_event(event_type, time_info, **payload)

    def _capture_indata(self, indata, status) -> None:
        if not self._direct_capture_active:
            return
        if status:
            self._direct_capture_statuses.append(str(status))
        with self._direct_capture_lock:
            self._direct_capture_chunks.append(np.array(indata[:, : self.capture_channels], dtype=np.float32, copy=True))

    def _init_click_stream(self):  # type: ignore[override]
        """Initialize the persistent output path as one full-duplex ASIO stream."""

        if self._click_data is None:
            print("DEBUG: _init_click_stream - no click data loaded")
            return
        try:
            print(
                "DEBUG: Initializing full-duplex validation click stream "
                f"on device {self.device_idx}, sr={self._click_sr}, latency={runtime_runner.CLICK_LATENCY}"
            )
            sd = runtime_runner.sd
            input_settings = _asio_settings_for_input(sd, self.capture_channels)
            output_settings = runtime_runner.output_extra_settings_for_device(self.device_idx, self.runtime_output_channels)

            def duplex_callback(indata, outdata, frames, time_info, status):
                self._capture_indata(indata, status)
                self._click_callback(outdata, frames, time_info, status)

            self._click_stream = sd.Stream(
                samplerate=self._click_sr,
                device=(self.device_idx, self.device_idx),
                channels=(self.capture_channels, self.runtime_output_channels),
                dtype="float32",
                latency=(self.capture_latency_s, runtime_runner.CLICK_LATENCY),
                blocksize=runtime_runner.CLICK_BLOCKSIZE,
                extra_settings=(input_settings, output_settings),
                callback=duplex_callback,
            )
            self._click_stream.start()
            print(f"DEBUG: Full-duplex validation click stream started, active={self._click_stream.active}")
        except Exception as exc:
            print(f"ERROR: Failed to initialize full-duplex validation click stream: {exc}")
            self._click_stream = None

    def start_recording(self, output_path=None) -> bool:  # type: ignore[override]
        digital_path = Path(output_path) if output_path else None
        digital_started = bool(super().start_recording(str(digital_path))) if digital_path is not None else False
        if not self.capture_enabled:
            self.direct_capture_metadata = {"enabled": False, "message": "direct capture disabled by caller"}
            return digital_started
        if digital_path is not None:
            physical_name = digital_path.name.replace("_audio_evidence.wav", "_physical_loopback.wav")
            if physical_name == digital_path.name:
                physical_name = digital_path.stem + "_physical_loopback.wav"
            self.direct_capture_path = digital_path.with_name(physical_name)
        else:
            self.direct_capture_path = None
        self._direct_capture_chunks = []
        self._direct_capture_statuses = []
        if self._click_stream is None and self._click_data is not None:
            self._init_click_stream()
        if self._click_stream is None or not self._click_stream.active:
            self.direct_capture_metadata = {
                "enabled": True,
                "started": False,
                "message": "full-duplex persistent ASIO stream is unavailable",
            }
            return digital_started

        self._direct_capture_active = True
        self.direct_capture_started = True
        self.direct_capture_metadata = {
            "enabled": True,
            "started": True,
            "sample_rate": self.capture_sample_rate,
            "channels": self.capture_channels,
            "latency_s": self.capture_latency_s,
            "blocksize": self.capture_blocksize,
            "path": str(self.direct_capture_path or ""),
            "mode": "physical_loopback_validation_reference",
        }
        return True

    def stop_recording(self, output_path=None, interrupted=False):  # type: ignore[override]
        try:
            super().stop_recording(output_path, interrupted=interrupted)
            self.digital_evidence_metadata = dict(getattr(self, "_output_evidence_summary", {}) or {})
        except Exception as exc:
            self.digital_evidence_metadata = {"started": False, "error": str(exc)}
        if not self._direct_capture_active and not self._direct_capture_chunks:
            return None
        self._direct_capture_active = False

        with self._direct_capture_lock:
            chunks = list(self._direct_capture_chunks)
            self._direct_capture_chunks = []
        capture = np.concatenate(chunks, axis=0) if chunks else np.zeros((0, self.capture_channels), dtype=np.float32)
        target = self.direct_capture_path
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            sf.write(target, capture, self.capture_sample_rate)

        peaks = np.max(np.abs(capture), axis=0).astype(float).tolist() if capture.size else []
        rms = np.sqrt(np.mean(np.square(capture.astype(np.float64)), axis=0)).astype(float).tolist() if capture.size else []
        self.direct_capture_metadata.update(
            {
                "started": True,
                "path": str(target or ""),
                "frames": int(capture.shape[0]),
                "duration_s": float(capture.shape[0] / self.capture_sample_rate) if self.capture_sample_rate else 0.0,
                "peak_by_channel": peaks,
                "rms_by_channel": rms,
                "clipped_channels_1based": [index + 1 for index, peak in enumerate(peaks) if peak >= 0.98],
                "status_messages": sorted(set(self._direct_capture_statuses)),
                "interrupted": bool(interrupted),
            }
        )
        if target is not None:
            _write_json(target.with_suffix(".direct_capture_metadata.json"), self.direct_capture_metadata)
        return capture

    def shutdown(self):  # type: ignore[override]
        if self._direct_capture_stream is not None:
            self.stop_recording(self.direct_capture_path, interrupted=True)
        return super().shutdown()


def _build_click_schedule(block_csv: Path, *, delay_s: float, jitter_s: float, seed: int) -> list[dict[str, Any]]:
    rows = _read_csv(block_csv)
    rng = random.Random(seed)
    schedule: list[dict[str, Any]] = []
    for fallback_index, row in enumerate(rows, start=1):
        tactile_sample = str(row.get("Tactile_Onset_Sample") or row.get("tactile_onset_sample") or "").strip()
        tactile_time = _float(row.get("Tactile_Onset_S") or row.get("tactile_onset_s"), default=math.nan)
        if not tactile_sample and not math.isfinite(tactile_time):
            continue
        trial_start = _float(row.get("Trial_Start_S") or row.get("trial_start_s"), default=0.0)
        trial_end = _float(row.get("Trial_End_S") or row.get("trial_end_s"), default=math.nan)
        if math.isfinite(_float(tactile_sample, default=math.nan)):
            sample_rate = _float(row.get("Sample_Rate_Hz") or row.get("sample_rate_hz"), default=44100.0)
            tactile_abs_s = _float(tactile_sample, default=0.0) / sample_rate
        else:
            tactile_abs_s = trial_start + tactile_time
        jitter = rng.uniform(-jitter_s, jitter_s) if jitter_s > 0 else 0.0
        click_time = tactile_abs_s + max(0.0, delay_s + jitter)
        if math.isfinite(trial_end):
            click_time = min(click_time, max(tactile_abs_s, trial_end - 0.050))
        schedule.append(
            {
                "trial_number": int(_float(row.get("Trial_Number") or fallback_index, default=fallback_index)),
                "trial_uid": row.get("Trial_UID") or row.get("trial_uid") or "",
                "family": row.get("Family") or row.get("family") or "",
                "tactile_onset_s": tactile_abs_s,
                "click_time_s": click_time,
                "delay_after_tactile_s": click_time - tactile_abs_s,
            }
        )
    return schedule


def _run_click_worker(controller: SessionRunnerController, engine: DirectInputCaptureAudioEngine, schedule: list[dict[str, Any]]) -> None:
    if not schedule:
        return
    if not engine.audio_started.wait(timeout=30.0):
        return
    zero = engine.audio_zero_perf_counter or time.perf_counter()
    for item in schedule:
        target = zero + float(item["click_time_s"])
        while True:
            remaining = target - time.perf_counter()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.010))
        controller.log_click(x=320, y=240, in_target=True)
        item["actual_click_perf_counter"] = time.perf_counter()


def _write_progress_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames: list[str] = []
    for preferred in ("monotonic_time", "ui_event", "block_index", "block_label", "elapsed_s", "duration_s", "session_id"):
        if any(preferred in row for row in rows):
            fieldnames.append(preferred)
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_validation(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.audio_gain is None:
        args.audio_gain = args.playback_gain
    if args.tactile_gain is None:
        args.tactile_gain = args.playback_gain
    for gain_name in ("playback_gain", "audio_gain", "tactile_gain"):
        gain_value = float(getattr(args, gain_name))
        if gain_value < 0.0:
            raise ValueError(f"--{gain_name.replace('_', '-')} must be >= 0.0.")
        if gain_value > SAFE_PLAYBACK_GAIN_MAX:
            raise ValueError(f"--{gain_name.replace('_', '-')} must be <= {SAFE_PLAYBACK_GAIN_MAX} for hardware safety.")

    if args.session_manifest:
        package = load_run_package(Path(args.session_manifest))
    elif args.run_setup_manifest:
        package = prepare_segment_run_package(
            Path(args.run_setup_manifest),
            args.participant_id,
            session_root=output_dir / "sessions",
        )
    else:
        raise ValueError("--run-setup-manifest or --session-manifest is required.")

    if len(package.blocks) != 1:
        raise ValueError(f"Actual-condition validation must run exactly one block; package has {len(package.blocks)} blocks.")

    block = package.blocks[0]
    levels = _signal_levels(block.wav_path, audio_gain=args.audio_gain, tactile_gain=args.tactile_gain)
    if levels["channels"] < 3:
        raise ValueError(f"Actual-condition validation requires a 3-channel block WAV; found {levels['channels']}.")
    if levels["effective_global_peak"] > SAFE_PLAYBACK_GAIN_MAX:
        raise ValueError(
            f"Effective output peak {levels['effective_global_peak']:.4f} exceeds safe validation ceiling {SAFE_PLAYBACK_GAIN_MAX:.4f}."
        )

    device_idx = args.device
    if device_idx is None:
        device_idx, _name, _preferred = runtime_runner.find_output_device()
    if device_idx is None:
        raise RuntimeError("No output device was found.")
    device = _device_snapshot(runtime_runner.sd, int(device_idx))
    if args.require_asio and str(device["hostapi"]).lower() != "asio":
        raise RuntimeError(f"Refusing actual-condition run on non-ASIO host API: {device}")
    if int(device["max_output_channels"]) < 3 or int(device["max_input_channels"]) < 3:
        raise RuntimeError(f"Refusing actual-condition run without >=3 input and output channels: {device}")

    engine = DirectInputCaptureAudioEngine(
        int(device_idx),
        capture_channels=args.capture_channels,
        capture_sample_rate=int(levels["sample_rate"]),
        capture_latency_s=args.capture_latency_s,
        capture_blocksize=args.capture_blocksize,
        capture_enabled=not args.no_direct_capture,
    )
    engine.audio_volume = float(args.audio_gain)
    engine.tactile_volume = float(args.tactile_gain)
    if runtime_runner.CLICK_SOUND:
        engine.load_click_sound(runtime_runner.CLICK_SOUND)

    capture_options = SessionCaptureOptions(
        enable_lsl=not args.no_lsl,
        write_events_csv=True,
        write_internal_xdf=True,
        write_analysis_csvs=True,
        write_lsl_marker_mirror=True,
        write_trigger_dictionary=True,
        start_backup_recording=not args.no_audio_evidence,
    )
    controller = SessionRunnerController(package, audio_engine=engine, capture_options=capture_options)

    click_schedule = []
    click_thread = None
    if not args.no_simulated_clicks:
        click_schedule = _build_click_schedule(
            block.manifest_path,
            delay_s=args.click_delay_s,
            jitter_s=args.click_jitter_s,
            seed=args.click_seed,
        )
        click_thread = threading.Thread(target=_run_click_worker, args=(controller, engine, click_schedule), daemon=True)
        click_thread.start()

    progress_rows: list[dict[str, Any]] = []

    def progress_callback(payload: dict[str, Any]) -> None:
        progress_rows.append({"monotonic_time": time.perf_counter(), **payload})

    result = controller.run(progress_callback=progress_callback)
    if click_thread is not None:
        click_thread.join(timeout=5.0)

    audit = validate_session(
        package.session_dir,
        output_dir=output_dir / "actual_condition_validation",
        require_xdf=True,
        require_lsl_marker_mirror=True,
        require_trigger_dictionary=True,
        require_response_markers=not args.no_simulated_clicks,
        require_backup_recording=not args.no_audio_evidence,
    )

    progress_csv = output_dir / "runner_progress_samples.csv"
    if progress_rows:
        _write_progress_csv(progress_csv, progress_rows)

    capture_clipped = bool(engine.direct_capture_metadata.get("clipped_channels_1based"))
    capture_started_ok = args.no_direct_capture or bool(engine.direct_capture_metadata.get("started"))
    digital_metadata = dict(engine.digital_evidence_metadata or {})
    digital_failed = bool(digital_metadata.get("clipped_channels_1based")) or int(digital_metadata.get("dropped_buffer_count") or 0) > 0
    report = {
        "schema": SCHEMA,
        "passed": bool(result.completed and audit.get("passed") and capture_started_ok and not capture_clipped and not digital_failed),
        "output_dir": str(output_dir),
        "session_dir": str(package.session_dir),
        "device": device,
        "block": {
            "index": block.index,
            "label": block.label,
            "wav_path": str(block.wav_path),
            "csv_path": str(block.manifest_path),
            "trial_count": block.trial_count,
            "duration_s": block.duration_s,
        },
        "signal_levels": levels,
        "direct_capture": {
            "enabled": not args.no_direct_capture,
            "started": bool(engine.direct_capture_metadata.get("started")),
            "path": engine.direct_capture_metadata.get("path", ""),
            "metadata": engine.direct_capture_metadata,
        },
        "digital_output_evidence": {
            "enabled": not args.no_audio_evidence,
            "started": bool(digital_metadata.get("started")),
            "path": digital_metadata.get("path", ""),
            "metadata": digital_metadata,
        },
        "click_schedule": click_schedule,
        "runner_result": {
            "completed": result.completed,
            "interrupted": result.interrupted,
            "events_csv": str(result.events_csv),
            "events_xdf": str(result.events_xdf),
            "analysis_outputs": {key: str(value) for key, value in result.analysis_outputs.items()},
            "lsl_status": result.lsl_status,
            "recording_paths": [str(path) for path in result.recording_paths],
            "capture_options": result.capture_options,
            "warnings": result.warnings,
        },
        "actual_condition_audit": audit,
        "outputs": {
            "run_report_json": str(output_dir / "one_block_actual_condition_run_report.json"),
            "run_report_md": str(output_dir / "one_block_actual_condition_run_report.md"),
            "progress_csv": str(progress_csv) if progress_rows else "",
            "actual_condition_audit_json": str(output_dir / "actual_condition_validation" / "one_block_actual_condition_validation.json"),
        },
        "safety": {
            "playback_gain_max_allowed": SAFE_PLAYBACK_GAIN_MAX,
            "effective_peak_ceiling": SAFE_PLAYBACK_GAIN_MAX,
            "phantom_power_required": False,
            "woojer_in_loop": False,
            "direct_capture_unclipped": not capture_clipped,
            "direct_capture_started_ok": capture_started_ok,
            "notes": [
                "This validation uses low digital gains for hardware safety.",
                "The Woojer mechanical actuator is not in this loop; channel 3 is electrical timing only.",
            ],
        },
    }
    _write_json(output_dir / "one_block_actual_condition_run_report.json", report)
    _write_markdown(output_dir / "one_block_actual_condition_run_report.md", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one actual-condition Segment 5/6 block through the runner.")
    parser.add_argument("--run-setup-manifest", type=Path, default=None)
    parser.add_argument("--session-manifest", type=Path, default=None)
    parser.add_argument("--participant-id", default="P001")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--require-asio", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--playback-gain", type=float, default=SAFE_PLAYBACK_GAIN_DEFAULT, help="Set both audio and tactile gains.")
    parser.add_argument("--audio-gain", type=float, default=None)
    parser.add_argument("--tactile-gain", type=float, default=None)
    parser.add_argument("--capture-channels", type=int, default=3)
    parser.add_argument("--capture-latency-s", type=float, default=0.010)
    parser.add_argument("--capture-blocksize", type=int, default=256)
    parser.add_argument("--no-direct-capture", action="store_true")
    parser.add_argument("--no-audio-evidence", action="store_true")
    parser.add_argument("--no-lsl", action="store_true")
    parser.add_argument("--no-simulated-clicks", action="store_true")
    parser.add_argument("--click-delay-s", type=float, default=0.250)
    parser.add_argument("--click-jitter-s", type=float, default=0.050)
    parser.add_argument("--click-seed", type=int, default=20260612)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.audio_gain is None:
        args.audio_gain = args.playback_gain
    if args.tactile_gain is None:
        args.tactile_gain = args.playback_gain
    report = run_validation(args)
    print(json.dumps({"passed": report["passed"], "session_dir": report["session_dir"], "report": report["outputs"]["run_report_json"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
