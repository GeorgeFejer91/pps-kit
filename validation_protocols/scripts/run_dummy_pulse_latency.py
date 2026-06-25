"""Run the internal dummy 3-channel pulse latency validation stimulus."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from make_dummy_pulse_stimulus import (  # noqa: E402
    CHANNEL_CODES,
    build_dummy_pulse_stimulus,
    parse_channel_amplitudes,
    parse_intervals_ms,
    write_dummy_pulse_files,
)


SAFE_HARDWARE_AMPLITUDE_DEFAULT = 0.05
SAFE_HARDWARE_AMPLITUDE_MAX = 0.10


def _stream_time_value(time_info: Any, name: str) -> float | None:
    if time_info is None:
        return None
    try:
        value = getattr(time_info, name)
    except Exception:
        try:
            value = time_info.get(name)
        except Exception:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class WasapiLoopbackRecorder:
    def __init__(self, *, device_query: str = "Komplete", output_path: Path):
        self.device_query = device_query.lower()
        self.output_path = output_path
        self.available = False
        self.status = "not_started"
        self.sample_rate = 0
        self.channels = 0
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._pyaudio = None
        self._stream = None
        self._device_info = None
        try:
            import pyaudiowpatch as pyaudio_wp  # type: ignore
        except Exception as exc:
            self.status = f"pyaudiowpatch unavailable: {exc}"
            self._pyaudio_wp = None
            return
        self._pyaudio_wp = pyaudio_wp
        try:
            self._pyaudio = pyaudio_wp.PyAudio()
            candidates = list(self._pyaudio.get_loopback_device_info_generator())
            selected = None
            for candidate in candidates:
                name = str(candidate.get("name", "")).lower()
                if self.device_query in name and "output 1/2" in name:
                    selected = candidate
                    break
            if selected is None:
                for candidate in candidates:
                    name = str(candidate.get("name", "")).lower()
                    if self.device_query in name:
                        selected = candidate
                        break
            if selected is None:
                self.status = "no matching WASAPI loopback device"
                return
            self._device_info = selected
            self.sample_rate = int(selected["defaultSampleRate"])
            self.channels = int(selected["maxInputChannels"])
            self.available = True
            self.status = "available"
        except Exception as exc:
            self.status = f"WASAPI init failed: {exc}"

    def start(self) -> bool:
        if not self.available or self._pyaudio is None or self._pyaudio_wp is None or self._device_info is None:
            return False
        with self._lock:
            self._chunks.clear()

        def callback(in_data, frame_count, time_info, status):
            data = np.frombuffer(in_data, dtype=np.float32).copy()
            with self._lock:
                self._chunks.append(data)
            return (None, self._pyaudio_wp.paContinue)

        self._stream = self._pyaudio.open(
            format=self._pyaudio_wp.paFloat32,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            input_device_index=self._device_info["index"],
            frames_per_buffer=2048,
            stream_callback=callback,
        )
        self._stream.start_stream()
        self.status = "recording"
        return True

    def stop(self) -> dict[str, Any]:
        if not self.available and self._stream is None:
            return {"status": self.status, "path": "", "frames": 0, "sample_rate": self.sample_rate, "channels": self.channels}
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        with self._lock:
            chunks = list(self._chunks)
            self._chunks.clear()
        if not chunks:
            self.status = "no_data"
            return {"status": self.status, "path": "", "frames": 0, "sample_rate": self.sample_rate, "channels": self.channels}
        data = np.concatenate(chunks)
        if self.channels > 1:
            data = data.reshape(-1, self.channels)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(self.output_path, data, self.sample_rate)
        self.status = "saved"
        return {
            "status": self.status,
            "path": str(self.output_path),
            "frames": int(data.shape[0]),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }

    def close(self) -> None:
        if self._pyaudio is not None:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
            self._pyaudio = None


def _make_lsl_outlet(stream_name: str, run_id: str):
    try:
        from pylsl import StreamInfo, StreamOutlet, local_clock  # type: ignore
    except Exception as exc:
        return None, None, f"pylsl unavailable: {exc}"
    try:
        info = StreamInfo(stream_name, "Markers", 3, 0, "string", f"pps-dummy-pulse-{run_id}")
        desc = info.desc()
        desc.append_child_value("run_id", run_id)
        desc.append_child_value("schema", "pps-dummy-pulse-lsl.v1")
        channels = desc.append_child("channels")
        for label in ("event_type", "event_id", "payload_json"):
            channel = channels.append_child("channel")
            channel.append_child_value("label", label)
            channel.append_child_value("type", "Marker")
        return StreamOutlet(info), local_clock, "active"
    except Exception as exc:
        return None, None, f"LSL outlet creation failed: {exc}"


def _write_marker_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "event_id",
        "event_type",
        "pulse_index",
        "nominal_sample_index",
        "expected_time_s",
        "callback_perf_counter",
        "lsl_timestamp",
        "stream_output_buffer_dac_time",
        "stream_current_time",
        "payload_json",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _run_full_duplex_capture(
    stimulus: np.ndarray,
    planned_rows: list[dict[str, Any]],
    *,
    output_dir: Path,
    device: int | None,
    device_query: str,
    sample_rate: int,
    input_channels: int,
    output_channels: int,
    latency_s: float,
    blocksize: int,
    allow_non_asio: bool,
    capture_tail_s: float,
    emit_lsl: bool,
    lsl_stream_name: str,
    run_id: str,
    wasapi_recorder: WasapiLoopbackRecorder | None = None,
) -> dict[str, Any]:
    from peripersonal_space_toolkit import latency_validation as lv

    sd = lv._load_sounddevice()
    device_idx, device_info, hostapi = lv._select_device(
        sd,
        device=device,
        device_query=device_query,
        require_asio=not allow_non_asio,
    )
    input_selectors = list(range(input_channels))
    output_selectors = list(range(output_channels))
    extra_settings = None
    if hostapi.lower() == "asio":
        extra_settings = (lv._asio_settings(sd, input_selectors), lv._asio_settings(sd, output_selectors))

    planned_by_pulse: dict[int, dict[str, Any]] = {}
    for row in planned_rows:
        planned_by_pulse.setdefault(int(row["pulse_index"]), row)
    pulse_markers = [
        {
            "pulse_index": int(row["pulse_index"]),
            "nominal_sample_index": int(row["nominal_sample_index"]),
            "expected_time_s": float(row["expected_time_s"]),
            "payload": {
                "schema": "pps-dummy-pulse-marker.v1",
                "run_id": run_id,
                "pulse_index": int(row["pulse_index"]),
                "nominal_sample_index": int(row["nominal_sample_index"]),
                "expected_time_s": float(row["expected_time_s"]),
                "channels": [1, 2, 3],
                "channel_targets": {
                    "1": "left Sennheiser headphone path",
                    "2": "right Sennheiser headphone path",
                    "3": "Woojer/tactile output path",
                },
            },
        }
        for row in planned_by_pulse.values()
    ]
    pulse_markers.sort(key=lambda item: item["nominal_sample_index"])

    outlet = None
    local_clock = None
    lsl_status = "disabled"
    if emit_lsl:
        outlet, local_clock, lsl_status = _make_lsl_outlet(lsl_stream_name, run_id)

    total_frames = stimulus.shape[0] + int(round(capture_tail_s * sample_rate))
    state: dict[str, Any] = {
        "pos": 0,
        "callbacks": 0,
        "statuses": [],
        "input_chunks": [],
        "emitted_pulse_indices": set(),
        "marker_rows": [],
    }

    def callback(indata, outdata, frames, time_info, status):
        if status:
            state["statuses"].append(str(status))
        state["callbacks"] += 1
        start = int(state["pos"])
        stop = start + frames
        outdata.fill(0)
        if start < stimulus.shape[0]:
            n = min(frames, stimulus.shape[0] - start)
            output_columns = min(stimulus.shape[1], output_channels)
            outdata[:n, :output_columns] = stimulus[start : start + n, :output_columns]
        state["input_chunks"].append(np.array(indata[:, :input_channels], dtype=np.float32, copy=True))

        for marker in pulse_markers:
            pulse_index = int(marker["pulse_index"])
            nominal = int(marker["nominal_sample_index"])
            if pulse_index in state["emitted_pulse_indices"]:
                continue
            if start <= nominal < stop:
                state["emitted_pulse_indices"].add(pulse_index)
                event_id = f"{run_id}_pulse_{pulse_index:03d}"
                payload = dict(marker["payload"])
                payload.update(
                    {
                        "buffer_start_sample": start,
                        "buffer_end_sample": stop,
                        "sample_offset_in_buffer": nominal - start,
                        "stream_output_buffer_dac_time": _stream_time_value(time_info, "outputBufferDacTime"),
                        "stream_current_time": _stream_time_value(time_info, "currentTime"),
                    }
                )
                lsl_timestamp = ""
                if outlet is not None and local_clock is not None:
                    lsl_timestamp = float(local_clock())
                    outlet.push_sample(["dummy_pulse", event_id, json.dumps(payload, sort_keys=True)], timestamp=lsl_timestamp)
                state["marker_rows"].append(
                    {
                        "event_id": event_id,
                        "event_type": "dummy_pulse",
                        "pulse_index": pulse_index,
                        "nominal_sample_index": nominal,
                        "expected_time_s": f"{float(marker['expected_time_s']):.9f}",
                        "callback_perf_counter": f"{time.perf_counter():.9f}",
                        "lsl_timestamp": "" if lsl_timestamp == "" else f"{float(lsl_timestamp):.9f}",
                        "stream_output_buffer_dac_time": payload["stream_output_buffer_dac_time"],
                        "stream_current_time": payload["stream_current_time"],
                        "payload_json": json.dumps(payload, sort_keys=True),
                    }
                )
        state["pos"] = stop
        if stop >= total_frames:
            raise sd.CallbackStop

    wasapi_started = False
    if wasapi_recorder is not None:
        wasapi_started = wasapi_recorder.start()
        time.sleep(0.2)

    stream = sd.Stream(
        samplerate=sample_rate,
        blocksize=blocksize,
        dtype="float32",
        device=(device_idx, device_idx),
        channels=(input_channels, output_channels),
        latency=(latency_s, latency_s),
        extra_settings=extra_settings,
        callback=callback,
    )
    start_time = time.perf_counter()
    stream.start()
    deadline = start_time + (total_frames / float(sample_rate)) + 5.0
    while stream.active and time.perf_counter() < deadline:
        time.sleep(0.005)
    active_after_deadline = bool(stream.active)
    actual_latency = getattr(stream, "latency", "")
    cpu_load = float(getattr(stream, "cpu_load", 0.0))
    stream.stop()
    stream.close()

    if wasapi_started:
        time.sleep(0.2)

    capture = np.concatenate(state["input_chunks"], axis=0)[:total_frames] if state["input_chunks"] else np.zeros((0, input_channels), dtype=np.float32)
    capture_path = output_dir / "direct_loopback_capture.wav"
    sf.write(capture_path, capture, sample_rate)
    marker_path = output_dir / "lsl_emitted_markers.csv"
    _write_marker_rows(marker_path, state["marker_rows"])

    route = lv.build_route_snapshot(
        device_name=str(device_info.get("name", "")),
        hostapi=hostapi,
        sample_rate=sample_rate,
        channels=output_channels,
        latency_s=latency_s,
        blocksize=blocksize,
        input_selectors=input_selectors,
        output_selectors=output_selectors,
        local_device_info=lv._jsonable_device_info(device_info, device_idx=device_idx, hostapi=hostapi),
    )
    route["input_channels"] = input_channels
    route["output_channels"] = output_channels
    route["stimulus_channels"] = int(stimulus.shape[1])
    return {
        "status": "complete",
        "capture_path": str(capture_path),
        "marker_path": str(marker_path),
        "route": route,
        "actual_latency": lv._latency_string(actual_latency),
        "cpu_load": f"{cpu_load:.6f}",
        "callback_count": state["callbacks"],
        "status_count": len(state["statuses"]),
        "status_messages": " | ".join(sorted(set(state["statuses"]))),
        "active_after_deadline": active_after_deadline,
        "elapsed_ms": (time.perf_counter() - start_time) * 1000.0,
        "lsl_status": lsl_status,
        "emitted_marker_count": len(state["marker_rows"]),
        "wasapi_started": wasapi_started,
    }


def _default_output_dir() -> Path:
    return Path("artifacts") / "validation_runs" / f"dummy_pulse_{time.strftime('%Y%m%d_%H%M%S')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the dummy 3-channel pulse validation stimulus.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--intervals-ms", default="300,800,1500,2200")
    parser.add_argument("--pre-roll-s", type=float, default=1.0)
    parser.add_argument("--post-roll-s", type=float, default=1.0)
    parser.add_argument("--amplitude", type=float, default=SAFE_HARDWARE_AMPLITUDE_DEFAULT)
    parser.add_argument(
        "--channel-amplitudes",
        default=None,
        help="Optional per-channel amplitudes as '0.0005,0.02,0.02' or '1:0.0005,2:0.02,3:0.02'.",
    )
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--device-query", default="Komplete")
    parser.add_argument("--input-channels", type=int, default=3)
    parser.add_argument("--output-channels", type=int, default=3)
    parser.add_argument("--latency", type=float, default=0.010)
    parser.add_argument("--blocksize", type=int, default=256)
    parser.add_argument("--allow-non-asio", action="store_true")
    parser.add_argument("--record-asio-loopback", action="store_true")
    parser.add_argument("--record-wasapi", action="store_true")
    parser.add_argument("--capture-tail-s", type=float, default=0.5)
    parser.add_argument("--emit-lsl", action="store_true")
    parser.add_argument("--lsl-stream-name", default="PPSDummyPulseMarkers")
    args = parser.parse_args(argv)

    if args.output_channels < 3:
        print("--output-channels must be at least 3 for the dummy 3-channel stimulus.", file=sys.stderr)
        return 2
    if args.input_channels < 1:
        print("--input-channels must be at least 1.", file=sys.stderr)
        return 2
    if args.amplitude <= 0:
        print("--amplitude must be positive.", file=sys.stderr)
        return 2
    if args.amplitude > SAFE_HARDWARE_AMPLITUDE_MAX:
        print(
            f"Refusing hardware playback amplitude {args.amplitude}; "
            f"internal validation caps direct-loopback playback at {SAFE_HARDWARE_AMPLITUDE_MAX}. "
            "Fix routing/input gain rather than raising the digital test level.",
            file=sys.stderr,
        )
        return 2
    try:
        channel_amplitudes = parse_channel_amplitudes(
            args.channel_amplitudes,
            default_amplitude=args.amplitude,
            channel_count=len(CHANNEL_CODES),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if channel_amplitudes and max(channel_amplitudes.values()) > SAFE_HARDWARE_AMPLITUDE_MAX:
        print(
            f"Refusing channel amplitude above {SAFE_HARDWARE_AMPLITUDE_MAX}; "
            "internal validation caps direct-loopback playback to protect the hardware.",
            file=sys.stderr,
        )
        return 2

    output_dir = args.output_dir or _default_output_dir()
    run_id = output_dir.name
    stimulus, planned_rows, manifest = build_dummy_pulse_stimulus(
        sample_rate=args.sample_rate,
        intervals_ms=parse_intervals_ms(args.intervals_ms),
        pre_roll_s=args.pre_roll_s,
        post_roll_s=args.post_roll_s,
        amplitude=args.amplitude,
        channel_amplitudes=channel_amplitudes,
    )
    manifest.update(
        {
            "run_id": run_id,
            "output_dir": str(output_dir),
            "record_asio_loopback": bool(args.record_asio_loopback),
            "record_wasapi": bool(args.record_wasapi),
            "emit_lsl": bool(args.emit_lsl),
            "lsl_stream_name": args.lsl_stream_name,
        }
    )
    write_dummy_pulse_files(output_dir, stimulus=stimulus, planned_rows=planned_rows, manifest=manifest)

    run_report: dict[str, Any] = {
        "schema": "pps-dummy-pulse-run.v1",
        "run_id": run_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stimulus_manifest": str(output_dir / "dummy_pulse_manifest.json"),
        "recording": {},
        "limitations": [
            "Direct electrical loopback measures interface/channel timing, not Woojer mechanical onset.",
            "WASAPI loopback is diagnostic and may not capture ASIO multichannel playback.",
            "LSL marker timing validates data collection reliability, not physical signal arrival.",
        ],
    }

    if args.record_wasapi and not args.record_asio_loopback:
        print("--record-wasapi requires playback; add --record-asio-loopback for this first-run protocol.", file=sys.stderr)
        return 2

    wasapi_recorder = None
    if args.record_wasapi:
        wasapi_recorder = WasapiLoopbackRecorder(device_query=args.device_query, output_path=output_dir / "wasapi_loopback_capture.wav")
        run_report["recording"]["wasapi_init_status"] = wasapi_recorder.status

    if args.record_asio_loopback:
        result = _run_full_duplex_capture(
            stimulus,
            planned_rows,
            output_dir=output_dir,
            device=args.device,
            device_query=args.device_query,
            sample_rate=args.sample_rate,
            input_channels=args.input_channels,
            output_channels=args.output_channels,
            latency_s=args.latency,
            blocksize=args.blocksize,
            allow_non_asio=args.allow_non_asio,
            capture_tail_s=args.capture_tail_s,
            emit_lsl=args.emit_lsl,
            lsl_stream_name=args.lsl_stream_name,
            run_id=run_id,
            wasapi_recorder=wasapi_recorder,
        )
        run_report["recording"]["direct_loopback"] = result
    else:
        run_report["recording"]["direct_loopback"] = {"status": "not_requested"}

    if wasapi_recorder is not None:
        try:
            run_report["recording"]["wasapi"] = wasapi_recorder.stop()
        finally:
            wasapi_recorder.close()

    report_path = output_dir / "dummy_pulse_run_report.json"
    report_path.write_text(json.dumps(run_report, indent=2), encoding="utf-8")
    print(f"Wrote dummy pulse validation run to {output_dir}")
    print(f"Wrote run report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
