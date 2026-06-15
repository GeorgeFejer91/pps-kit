"""Run one-output-at-a-time dummy route sweeps for Komplete channel mapping."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from compare_dummy_pulse_recordings import MIN_PEAK, MIN_SHAPE_CORRELATION, _channel_threshold, _normalized_correlation  # noqa: E402
from diagnose_dummy_channel_route import _detect_expected_starts  # noqa: E402
from make_dummy_pulse_stimulus import (  # noqa: E402
    CHANNEL_CODES,
    build_dummy_pulse_stimulus,
    parse_channel_amplitudes,
    parse_intervals_ms,
    write_dummy_pulse_files,
)


SAFE_HARDWARE_AMPLITUDE_DEFAULT = 0.05
SAFE_HARDWARE_AMPLITUDE_MAX = 0.10


def _default_output_dir() -> Path:
    return Path("artifacts") / "validation_runs" / f"dummy_output_route_sweep_{time.strftime('%Y%m%d_%H%M%S')}"


def _median(values: list[float]) -> float:
    return float(np.median(np.asarray(values, dtype=np.float64))) if values else math.nan


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    flat_rows = []
    for row in rows:
        flat = dict(row)
        flat["per_pulse_latencies_ms"] = json.dumps(flat["per_pulse_latencies_ms"], sort_keys=True)
        flat_rows.append(flat)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0].keys()))
        writer.writeheader()
        writer.writerows(flat_rows)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Dummy Single-Output Route Sweep",
        "",
        f"- Run dir: `{report['run_dir']}`",
        f"- Expected identity route passed: `{report['expected_identity_route_passed']}`",
        "",
        "## Output Mapping",
        "",
    ]
    for output in report["outputs"]:
        lines.append(
            "- Output {out}: detected input(s) {inputs}; expected input {expected}; "
            "identity_ok={ok}; median latency ms={lat}".format(
                out=output["output_channel_1based"],
                inputs=output["detected_inputs_1based"],
                expected=output["expected_input_1based"],
                ok=output["identity_ok"],
                lat=output["primary_median_latency_ms"],
            )
        )
    lines.extend(["", "## Input Details", ""])
    for row in report["input_rows"]:
        lines.append(
            "- Output {out} -> input {inp}: detected={det}/{exp}, peak={peak:.6f}, "
            "corr={corr:.3f}, median latency={lat} ms, accepted={accepted}".format(
                out=row["output_channel_1based"],
                inp=row["input_channel_1based"],
                det=row["detected_count"],
                exp=row["expected_count"],
                peak=float(row["peak"]),
                corr=float(row["median_shape_correlation"]) if math.isfinite(float(row["median_shape_correlation"])) else math.nan,
                lat=row["median_latency_ms"],
                accepted=row["accepted_detection"],
            )
        )
    lines.extend(["", "## Limitations", ""])
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _capture_stimulus(
    stimulus: np.ndarray,
    *,
    output_dir: Path,
    active_output: int,
    device: int | None,
    device_query: str,
    sample_rate: int,
    input_channels: int,
    output_channels: int,
    latency_s: float,
    blocksize: int,
    allow_non_asio: bool,
    capture_tail_s: float,
) -> tuple[np.ndarray, dict[str, Any]]:
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

    total_frames = stimulus.shape[0] + int(round(capture_tail_s * sample_rate))
    state: dict[str, Any] = {
        "pos": 0,
        "callbacks": 0,
        "statuses": [],
        "input_chunks": [],
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
            outdata[:n, active_output] = stimulus[start : start + n, active_output]
        state["input_chunks"].append(np.array(indata[:, :input_channels], dtype=np.float32, copy=True))
        state["pos"] = stop
        if stop >= total_frames:
            raise sd.CallbackStop

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

    capture = np.concatenate(state["input_chunks"], axis=0)[:total_frames] if state["input_chunks"] else np.zeros((0, input_channels), dtype=np.float32)
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
    route["active_output_channel_1based"] = active_output + 1
    return capture, {
        "route": route,
        "actual_latency": lv._latency_string(actual_latency),
        "cpu_load": f"{cpu_load:.6f}",
        "callback_count": state["callbacks"],
        "status_count": len(state["statuses"]),
        "status_messages": " | ".join(sorted(set(state["statuses"]))),
        "active_after_deadline": active_after_deadline,
        "elapsed_ms": (time.perf_counter() - start_time) * 1000.0,
    }


def run_sweep(
    *,
    output_dir: Path,
    device: int | None,
    device_query: str,
    sample_rate: int,
    intervals_ms: list[int],
    pre_roll_s: float,
    post_roll_s: float,
    amplitude: float,
    input_channels: int,
    output_channels: int,
    sweep_output_count: int,
    latency_s: float,
    blocksize: int,
    allow_non_asio: bool,
    capture_tail_s: float,
    search_pre_ms: float,
    search_post_ms: float,
    channel_amplitudes: dict[int, float] | None = None,
) -> dict[str, Any]:
    if output_channels < 3:
        raise ValueError("output_channels must be at least 3")
    if sweep_output_count < 1:
        raise ValueError("sweep_output_count must be at least 1")
    if sweep_output_count > output_channels:
        raise ValueError("sweep_output_count cannot exceed output_channels")
    if amplitude <= 0:
        raise ValueError("amplitude must be positive")
    if amplitude > SAFE_HARDWARE_AMPLITUDE_MAX:
        raise ValueError(
            f"Refusing hardware playback amplitude {amplitude}; "
            f"internal validation caps direct-loopback playback at {SAFE_HARDWARE_AMPLITUDE_MAX}. "
            "Fix routing/input gain rather than raising the digital test level."
        )
    if channel_amplitudes and max(channel_amplitudes.values()) > SAFE_HARDWARE_AMPLITUDE_MAX:
        raise ValueError(
            f"Refusing channel amplitude above {SAFE_HARDWARE_AMPLITUDE_MAX}; "
            "internal validation caps direct-loopback playback to protect the hardware."
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    stimulus, planned_rows, manifest = build_dummy_pulse_stimulus(
        sample_rate=sample_rate,
        intervals_ms=intervals_ms,
        pre_roll_s=pre_roll_s,
        post_roll_s=post_roll_s,
        amplitude=amplitude,
        channel_amplitudes=channel_amplitudes,
    )
    manifest.update(
        {
            "schema": "pps-dummy-output-route-sweep.v1",
            "run_id": output_dir.name,
            "validation_type": "single_output_route_sweep",
            "input_channels": input_channels,
            "output_channels": output_channels,
            "sweep_output_count": sweep_output_count,
            "search_window_ms": {"pre": search_pre_ms, "post": search_post_ms},
        }
    )
    write_dummy_pulse_files(output_dir, stimulus=stimulus, planned_rows=planned_rows, manifest=manifest)

    input_rows: list[dict[str, Any]] = []
    output_summaries: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []

    for active_output in range(sweep_output_count):
        probe_source_channel = active_output if active_output < stimulus.shape[1] else 0
        expected_samples = sorted(
            {int(row["expected_sample_index"]) for row in planned_rows if int(row["channel"]) == probe_source_channel}
        )
        single = np.zeros((stimulus.shape[0], output_channels), dtype=np.float32)
        single[:, active_output] = stimulus[:, probe_source_channel]
        capture, io_status = _capture_stimulus(
            single,
            output_dir=output_dir,
            active_output=active_output,
            device=device,
            device_query=device_query,
            sample_rate=sample_rate,
            input_channels=input_channels,
            output_channels=output_channels,
            latency_s=latency_s,
            blocksize=blocksize,
            allow_non_asio=allow_non_asio,
            capture_tail_s=capture_tail_s,
        )
        capture_path = output_dir / f"output_{active_output + 1}_capture.wav"
        sf.write(capture_path, capture, sample_rate)
        captures.append({"output_channel_1based": active_output + 1, "capture_path": str(capture_path), **io_status})

        template = single[:, active_output]
        pulse_span = np.flatnonzero(np.abs(template) > 0)
        if pulse_span.size:
            pulse_template = template[pulse_span[0] : pulse_span[0] + max(1, int(round(0.035 * sample_rate)))]
        else:
            pulse_template = template
        accepted_inputs: list[int] = []
        accepted_latencies: list[float] = []
        for input_channel in range(capture.shape[1]):
            signal = capture[:, input_channel]
            detected, profile = _detect_expected_starts(
                signal,
                expected_samples,
                sample_rate=sample_rate,
                search_pre_ms=search_pre_ms,
                search_post_ms=search_post_ms,
            )
            latencies_ms = [
                (detected[idx] - expected_samples[idx]) / float(sample_rate) * 1000.0
                for idx in range(min(len(detected), len(expected_samples)))
            ]
            correlations = []
            for detected_sample in detected:
                segment = signal[detected_sample : detected_sample + len(pulse_template)]
                correlations.append(abs(_normalized_correlation(segment, pulse_template)))
            detection_rate = len(detected) / float(len(expected_samples) or 1)
            median_corr = _median(correlations)
            accepted = (
                detection_rate >= 0.95
                and math.isfinite(median_corr)
                and median_corr >= MIN_SHAPE_CORRELATION
                and float(profile["peak"]) >= MIN_PEAK
            )
            if accepted:
                accepted_inputs.append(input_channel + 1)
                accepted_latencies.extend(latencies_ms)
            input_rows.append(
                {
                    "output_channel_1based": active_output + 1,
                    "probe_source_channel_1based": probe_source_channel + 1,
                    "input_channel_1based": input_channel + 1,
                    "detected_count": len(detected),
                    "expected_count": len(expected_samples),
                    "detection_rate": detection_rate,
                    "median_latency_ms": _median(latencies_ms),
                    "median_shape_correlation": median_corr,
                    "peak": float(profile["peak"]),
                    "threshold": float(profile["threshold"]),
                    "low_signal": bool(profile["low_signal"]),
                    "clipped": bool(profile["clipped"]),
                    "accepted_detection": accepted,
                    "per_pulse_latencies_ms": latencies_ms,
                }
            )
        expected_input = active_output + 1
        output_summaries.append(
            {
                "output_channel_1based": active_output + 1,
                "probe_source_channel_1based": probe_source_channel + 1,
                "expected_input_1based": expected_input,
                "detected_inputs_1based": accepted_inputs,
                "identity_ok": accepted_inputs == [expected_input],
                "primary_median_latency_ms": _median(accepted_latencies),
            }
        )

    expected_identity = all(row["identity_ok"] for row in output_summaries)
    report = {
        "schema": "pps-dummy-output-route-sweep-report.v1",
        "run_dir": str(output_dir),
        "sample_rate": sample_rate,
        "amplitude": amplitude,
        "channel_amplitudes": manifest.get("channel_amplitudes"),
        "input_channels": input_channels,
        "output_channels": output_channels,
        "sweep_output_count": sweep_output_count,
        "expected_identity_route_passed": expected_identity,
        "outputs": output_summaries,
        "input_rows": input_rows,
        "captures": captures,
        "limitations": [
            "This measures electrical route identity and crosstalk, not Woojer mechanical onset.",
            "Accepted detections on multiple inputs for one output indicate crosstalk, duplicate routing, or a patching/driver issue that must be investigated before participant timing claims.",
        ],
    }
    (output_dir / "dummy_output_route_sweep_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_csv(output_dir / "dummy_output_route_sweep_inputs.csv", input_rows)
    _write_markdown(output_dir / "dummy_output_route_sweep_report.md", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run single-output dummy pulse route sweeps.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--device-query", default="Komplete")
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
    parser.add_argument("--input-channels", type=int, default=6)
    parser.add_argument("--output-channels", type=int, default=3)
    parser.add_argument("--sweep-output-count", type=int, default=3)
    parser.add_argument("--latency", type=float, default=0.010)
    parser.add_argument("--blocksize", type=int, default=256)
    parser.add_argument("--allow-non-asio", action="store_true")
    parser.add_argument("--capture-tail-s", type=float, default=0.5)
    parser.add_argument("--search-pre-ms", type=float, default=25.0)
    parser.add_argument("--search-post-ms", type=float, default=200.0)
    args = parser.parse_args(argv)

    report = run_sweep(
        output_dir=args.output_dir or _default_output_dir(),
        device=args.device,
        device_query=args.device_query,
        sample_rate=args.sample_rate,
        intervals_ms=parse_intervals_ms(args.intervals_ms),
        pre_roll_s=args.pre_roll_s,
        post_roll_s=args.post_roll_s,
        amplitude=args.amplitude,
        channel_amplitudes=parse_channel_amplitudes(
            args.channel_amplitudes,
            default_amplitude=args.amplitude,
            channel_count=len(CHANNEL_CODES),
        ),
        input_channels=args.input_channels,
        output_channels=args.output_channels,
        sweep_output_count=args.sweep_output_count,
        latency_s=args.latency,
        blocksize=args.blocksize,
        allow_non_asio=args.allow_non_asio,
        capture_tail_s=args.capture_tail_s,
        search_pre_ms=args.search_pre_ms,
        search_post_ms=args.search_post_ms,
    )
    print(f"Wrote {Path(report['run_dir']) / 'dummy_output_route_sweep_report.json'}")
    return 0 if report["expected_identity_route_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
