"""Stress-test audio output devices for PPS binaural+tactile playback.

The rendered PPS trajectory files need one synchronized output stream:

- output 1: binaural left
- output 2: binaural right
- output 3: tactile

On Windows, the Komplete WDM/WASAPI endpoints often appear as separate stereo
pairs. Those are not acceptable for synchronized binaural+tactile playback. The
Komplete ASIO endpoint exposes the interface as one multichannel device.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np

# Must be set before importing sounddevice.
os.environ.setdefault("SD_ENABLE_ASIO", "1")

import sounddevice as sd


def _hostapi_name(device_info: dict) -> str:
    try:
        return sd.query_hostapis()[int(device_info["hostapi"])]["name"]
    except Exception:
        return ""


def _extra_settings(device_idx: int | None, channels: int):
    if device_idx is None:
        return None
    try:
        dev = sd.query_devices(device_idx)
        if _hostapi_name(dev).lower() == "asio" and hasattr(sd, "AsioSettings"):
            return sd.AsioSettings(channel_selectors=list(range(channels)))
    except Exception:
        return None
    return None


def _latency_sort_value(value: str) -> float:
    if value == "low":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 999.0


def _actual_latency_sort_value(row: dict) -> float:
    try:
        value = str(row.get("actual_latency", "")).split("/", 1)[0]
        return float(value)
    except Exception:
        return _latency_sort_value(str(row.get("requested_latency", "")))


def _sounddevice_latency(value: str):
    if value in {"low", "high"}:
        return value
    return float(value)


def _actual_latency(stream) -> str:
    latency = getattr(stream, "latency", "")
    if isinstance(latency, tuple):
        return "/".join(f"{float(x):.6f}" for x in latency)
    try:
        return f"{float(latency):.6f}"
    except Exception:
        return str(latency)


def _candidate_devices(device: int | None, device_query: str | None) -> list[tuple[int, dict]]:
    devices = sd.query_devices()
    rows: list[tuple[int, dict]] = []
    for idx, dev in enumerate(devices):
        if int(dev["max_output_channels"]) < 2:
            continue
        if device is not None and idx != device:
            continue
        if device_query and device_query.lower() not in dev["name"].lower():
            continue
        rows.append((idx, dev))
    return rows


def _try_configuration(
    *,
    device_idx: int,
    device_info: dict,
    channels: int,
    sample_rate: int,
    latency: str,
    blocksize: int,
    duration_s: float,
    dry_run: bool,
    mode: str,
    iteration: int,
) -> dict:
    row = {
        "device_index": device_idx,
        "device_name": device_info["name"],
        "hostapi": _hostapi_name(device_info),
        "max_output_channels": int(device_info["max_output_channels"]),
        "default_samplerate": float(device_info.get("default_samplerate", 0.0)),
        "requested_samplerate": sample_rate,
        "requested_channels": channels,
        "requested_latency": latency,
        "requested_blocksize": blocksize,
        "mode": mode,
        "iteration": iteration,
        "check_ok": False,
        "open_ok": False,
        "actual_latency": "",
        "cpu_load": "",
        "callback_count": 0,
        "status_count": 0,
        "status_messages": "",
        "frames_requested": 0,
        "frames_written": 0,
        "elapsed_ms": "",
        "error": "",
    }

    if channels > row["max_output_channels"]:
        row["error"] = "device has fewer output channels than requested"
        return row

    stream = None
    start = time.perf_counter()
    try:
        sd.check_output_settings(
            device=device_idx,
            channels=channels,
            dtype="float32",
            samplerate=sample_rate,
            extra_settings=_extra_settings(device_idx, channels),
        )
        row["check_ok"] = True
        if dry_run:
            row["open_ok"] = True
            return row

        frames = max(int(sample_rate * duration_s), blocksize)
        row["frames_requested"] = frames

        if mode == "write":
            silence = np.zeros((frames, channels), dtype=np.float32)
            stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="float32",
                device=device_idx,
                latency=_sounddevice_latency(latency),
                blocksize=blocksize,
                extra_settings=_extra_settings(device_idx, channels),
            )
            stream.start()
            stream.write(silence)
            row["frames_written"] = frames
        elif mode == "callback":
            state = {
                "frames_written": 0,
                "callbacks": 0,
                "statuses": [],
            }
            finished = False

            def callback(outdata, callback_frames, time_info, status):
                nonlocal finished
                outdata.fill(0)
                state["callbacks"] += 1
                if status:
                    state["statuses"].append(str(status))
                remaining = frames - state["frames_written"]
                if remaining <= 0:
                    finished = True
                    raise sd.CallbackStop
                n = min(callback_frames, remaining)
                if n < callback_frames:
                    outdata[n:].fill(0)
                    finished = True
                state["frames_written"] += n
                if finished:
                    raise sd.CallbackStop

            stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype="float32",
                device=device_idx,
                latency=_sounddevice_latency(latency),
                blocksize=blocksize,
                extra_settings=_extra_settings(device_idx, channels),
                callback=callback,
            )
            stream.start()
            deadline = time.perf_counter() + duration_s + 5.0
            while stream.active and time.perf_counter() < deadline:
                time.sleep(0.005)
            row["frames_written"] = int(state["frames_written"])
            row["callback_count"] = int(state["callbacks"])
            row["status_count"] = len(state["statuses"])
            row["status_messages"] = " | ".join(sorted(set(state["statuses"])))
            if stream.active:
                row["error"] = "callback stream did not finish before timeout"
        else:
            raise ValueError(f"Unknown stress mode: {mode}")
        row["open_ok"] = True
        row["actual_latency"] = _actual_latency(stream)
        row["cpu_load"] = f"{float(getattr(stream, 'cpu_load', 0.0)):.6f}"
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        row["elapsed_ms"] = f"{(time.perf_counter() - start) * 1000.0:.2f}"

    return row


def _recommend(rows: list[dict]) -> dict:
    successes = [
        row
        for row in rows
        if row["open_ok"]
        and not row["error"]
        and int(row["requested_channels"]) >= 3
        and int(row.get("status_count", 0)) == 0
    ]
    if not successes:
        legacy = [row for row in rows if row["open_ok"] and int(row["requested_channels"]) == 2 and not row["error"]]
        return {
            "status": "legacy_only" if legacy else "no_working_output",
            "message": (
                "No synchronized 3+ channel output stream passed. New binaural+tactile renders "
                "cannot be played safely on this configuration."
            ),
            "row": legacy[0] if legacy else None,
        }

    def key(row: dict):
        name_score = 0 if "komplete" in row["device_name"].lower() else 1
        host_score = 0 if row["hostapi"].lower() == "asio" else 1
        channel_score = 0 if int(row["requested_channels"]) == 3 else 1
        return (
            name_score,
            host_score,
            channel_score,
            _actual_latency_sort_value(row),
            int(row["requested_blocksize"]),
            _latency_sort_value(str(row["requested_latency"])),
        )

    best = sorted(successes, key=key)[0]
    return {
        "status": "spatial_ready",
        "message": (
            "Use this device as one synchronized output stream. Route outputs 1/2 to headphones "
            "and output 3 to the tactile transducer."
        ),
        "row": best,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stress-test PPS audio output routing.")
    parser.add_argument("--device", type=int, help="Specific sounddevice device index.")
    parser.add_argument("--device-query", help="Only test devices whose name contains this text.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/audio_device_stress"))
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--channels", type=int, nargs="+", default=[3, 4, 2])
    parser.add_argument("--latencies", nargs="+", default=["low", "0.003", "0.005", "0.010", "0.020", "0.050"])
    parser.add_argument("--blocksizes", type=int, nargs="+", default=[64, 128, 256, 512, 1024, 2048])
    parser.add_argument("--duration-s", type=float, default=0.05)
    parser.add_argument("--mode", choices=["write", "callback", "both"], default="write")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true", help="Only call check_output_settings; do not open streams.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    candidates = _candidate_devices(args.device, args.device_query)
    if not candidates:
        print("No matching output devices found.")
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rows: list[dict] = []
    for device_idx, dev in candidates:
        print(
            f"Testing [{device_idx}] {dev['name']} | {_hostapi_name(dev)} | "
            f"max_out={dev['max_output_channels']}"
        )
        for channels in args.channels:
            for latency in args.latencies:
                for blocksize in args.blocksizes:
                    modes = ["write", "callback"] if args.mode == "both" else [args.mode]
                    for mode in modes:
                        for iteration in range(1, max(1, int(args.iterations)) + 1):
                            row = _try_configuration(
                                device_idx=device_idx,
                                device_info=dev,
                                channels=channels,
                                sample_rate=args.sample_rate,
                                latency=str(latency),
                                blocksize=int(blocksize),
                                duration_s=float(args.duration_s),
                                dry_run=bool(args.dry_run),
                                mode=mode,
                                iteration=iteration,
                            )
                            rows.append(row)
                            marker = "ok" if row["open_ok"] and not row["error"] and not row["status_messages"] else "fail"
                            detail = f" ({row['error'] or row['status_messages']})" if row["error"] or row["status_messages"] else ""
                            print(
                                f"  {marker}: {mode}#{iteration} ch={channels}, "
                                f"latency={latency}, block={blocksize}, actual={row['actual_latency']}"
                                + detail
                            )

    recommendation = _recommend(rows)
    csv_path = args.output_dir / f"audio_device_stress_{timestamp}.csv"
    json_path = args.output_dir / f"audio_device_stress_{timestamp}.json"

    fieldnames = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "timestamp": timestamp,
        "sounddevice_version": getattr(sd, "__version__", ""),
        "portaudio_version": sd.get_portaudio_version(),
        "arguments": {
            "device": args.device,
            "device_query": args.device_query,
            "sample_rate": args.sample_rate,
            "channels": args.channels,
            "latencies": args.latencies,
            "blocksizes": args.blocksizes,
            "duration_s": args.duration_s,
            "mode": args.mode,
            "iterations": args.iterations,
            "dry_run": args.dry_run,
        },
        "recommendation": recommendation,
        "rows": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\nRecommendation:")
    print(f"  status: {recommendation['status']}")
    print(f"  {recommendation['message']}")
    if recommendation["row"]:
        row = recommendation["row"]
        print(
            f"  device [{row['device_index']}] {row['device_name']} | {row['hostapi']} | "
            f"channels={row['requested_channels']} latency={row['requested_latency']} "
            f"blocksize={row['requested_blocksize']} actual_latency={row['actual_latency']}"
        )
    print(f"\nWrote {csv_path}")
    print(f"Wrote {json_path}")
    return 0 if recommendation["status"] == "spatial_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
