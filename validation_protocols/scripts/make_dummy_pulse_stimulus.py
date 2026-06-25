"""Generate a coded 3-channel dummy pulse WAV for internal timing validation."""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


SCHEMA = "pps-dummy-3ch-pulse-stimulus.v1"
DEFAULT_INTERVALS_MS = [300, 800, 1500, 2200]


@dataclass(frozen=True)
class ChannelCode:
    channel: int
    channel_number: int
    channel_label: str
    physical_target: str
    code: str
    duration_ms: float
    pattern: tuple[float, ...]


CHANNEL_CODES = [
    ChannelCode(
        channel=0,
        channel_number=1,
        channel_label="left_audio",
        physical_target="left Sennheiser headphone path",
        code="biphasic_positive_first",
        duration_ms=20.0,
        pattern=(1.0, -1.0),
    ),
    ChannelCode(
        channel=1,
        channel_number=2,
        channel_label="right_audio",
        physical_target="right Sennheiser headphone path",
        code="quad_alternating_positive_first",
        duration_ms=24.0,
        pattern=(1.0, -1.0, 1.0, -1.0),
    ),
    ChannelCode(
        channel=2,
        channel_number=3,
        channel_label="tactile_drive",
        physical_target="Woojer/tactile output path",
        code="quad_alternating_negative_first",
        duration_ms=28.0,
        pattern=(-1.0, 1.0, -1.0, 1.0),
    ),
]


def parse_intervals_ms(text: str | None) -> list[float]:
    if not text:
        return [float(value) for value in DEFAULT_INTERVALS_MS]
    values = []
    for chunk in text.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        values.append(float(chunk))
    if not values:
        raise ValueError("at least one interval is required")
    if any(value <= 0 for value in values):
        raise ValueError("intervals must be positive")
    return values


def parse_channel_amplitudes(text: str | None, *, default_amplitude: float, channel_count: int = 3) -> dict[int, float] | None:
    """Parse optional per-channel amplitudes into zero-based channel keys.

    Accepts either a comma-separated list, e.g. ``0.0005,0.02,0.02``, or
    one-based key/value pairs, e.g. ``1:0.0005,2:0.02,3:0.02``.
    """

    if not text:
        return None
    chunks = [chunk.strip() for chunk in text.replace(";", ",").split(",") if chunk.strip()]
    if not chunks:
        return None
    amplitudes = {channel: float(default_amplitude) for channel in range(channel_count)}
    if all(":" not in chunk for chunk in chunks):
        if len(chunks) != channel_count:
            raise ValueError(f"expected {channel_count} comma-separated channel amplitudes")
        for channel, chunk in enumerate(chunks):
            amplitudes[channel] = float(chunk)
    else:
        for chunk in chunks:
            if ":" not in chunk:
                raise ValueError("channel amplitude entries must all use channel:value when any entry does")
            channel_text, value_text = chunk.split(":", 1)
            channel_number = int(channel_text.strip())
            if not (1 <= channel_number <= channel_count):
                raise ValueError(f"channel number must be in 1..{channel_count}")
            amplitudes[channel_number - 1] = float(value_text.strip())
    if any(value <= 0 for value in amplitudes.values()):
        raise ValueError("channel amplitudes must be positive")
    return amplitudes


def channel_amplitude_for(manifest: dict[str, Any], channel: int) -> float:
    amplitudes = manifest.get("channel_amplitudes")
    if isinstance(amplitudes, dict):
        for key in (str(channel + 1), str(channel)):
            if key in amplitudes:
                return float(amplitudes[key])
    return float(manifest["amplitude"])


def channel_template(code: ChannelCode, *, sample_rate: int, amplitude: float) -> np.ndarray:
    samples = max(len(code.pattern), int(round((code.duration_ms / 1000.0) * sample_rate)))
    pulse = np.zeros(samples, dtype=np.float32)
    for indices, sign in zip(np.array_split(np.arange(samples), len(code.pattern)), code.pattern):
        pulse[indices] = float(sign) * float(amplitude)
    return pulse


def build_dummy_pulse_stimulus(
    *,
    sample_rate: int = 44100,
    intervals_ms: list[float] | None = None,
    pre_roll_s: float = 1.0,
    post_roll_s: float = 1.0,
    amplitude: float = 0.20,
    channel_amplitudes: dict[int, float] | None = None,
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if pre_roll_s < 0 or post_roll_s < 0:
        raise ValueError("pre_roll_s and post_roll_s must be non-negative")
    if not (0.0 < amplitude <= 0.95):
        raise ValueError("amplitude must be in the range (0, 0.95]")
    if channel_amplitudes is not None:
        for channel, value in channel_amplitudes.items():
            if channel not in {code.channel for code in CHANNEL_CODES}:
                raise ValueError(f"unknown zero-based channel {channel}")
            if not (0.0 < float(value) <= 0.95):
                raise ValueError("channel amplitudes must be in the range (0, 0.95]")

    intervals_ms = list(intervals_ms if intervals_ms is not None else DEFAULT_INTERVALS_MS)
    if any(value <= 0 for value in intervals_ms):
        raise ValueError("intervals must be positive")

    pulse_count = len(intervals_ms) + 1
    first_sample = int(round(pre_roll_s * sample_rate))
    onset_samples = [first_sample]
    cursor = first_sample
    for interval_ms in intervals_ms:
        cursor += int(round((interval_ms / 1000.0) * sample_rate))
        onset_samples.append(cursor)

    amplitude_by_channel = {
        code.channel: float(channel_amplitudes.get(code.channel, amplitude)) if channel_amplitudes else float(amplitude)
        for code in CHANNEL_CODES
    }
    templates = {
        code.channel: channel_template(code, sample_rate=sample_rate, amplitude=amplitude_by_channel[code.channel])
        for code in CHANNEL_CODES
    }
    max_template_samples = max(len(template) for template in templates.values())
    frames = onset_samples[-1] + max_template_samples + int(round(post_roll_s * sample_rate))
    data = np.zeros((frames, len(CHANNEL_CODES)), dtype=np.float32)
    planned_rows: list[dict[str, Any]] = []

    for pulse_index, sample_index in enumerate(onset_samples, start=1):
        previous_interval_s = "" if pulse_index == 1 else f"{intervals_ms[pulse_index - 2] / 1000.0:.9f}"
        for code in CHANNEL_CODES:
            template = templates[code.channel]
            data[sample_index : sample_index + len(template), code.channel] += template
            planned_rows.append(
                {
                    "pulse_index": pulse_index,
                    "channel": code.channel,
                    "channel_number": code.channel_number,
                    "channel_label": code.channel_label,
                    "physical_target": code.physical_target,
                    "code": code.code,
                    "nominal_sample_index": sample_index,
                    "expected_sample_index": sample_index,
                    "expected_time_s": f"{sample_index / float(sample_rate):.9f}",
                    "pulse_duration_samples": len(template),
                    "pulse_duration_s": f"{len(template) / float(sample_rate):.9f}",
                    "amplitude": amplitude_by_channel[code.channel],
                    "previous_interval_s": previous_interval_s,
                }
            )

    manifest = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "purpose": "Internal 3-channel channel-routing and latency validation dataset.",
        "sample_rate": sample_rate,
        "channels": len(CHANNEL_CODES),
        "pulse_count": pulse_count,
        "pre_roll_s": pre_roll_s,
        "post_roll_s": post_roll_s,
        "intervals_ms": intervals_ms,
        "amplitude": amplitude,
        "channel_amplitudes": {str(code.channel_number): amplitude_by_channel[code.channel] for code in CHANNEL_CODES},
        "channel_codes": [asdict(code) for code in CHANNEL_CODES],
        "channel_mapping_under_test": {
            "channel_1": "left Sennheiser headphone path",
            "channel_2": "right Sennheiser headphone path",
            "channel_3": "Woojer/tactile output path",
        },
        "not_measured": [
            "Woojer mechanical vibration onset without an external sensor",
            "human response latency",
        ],
    }
    return data, planned_rows, manifest


def write_dummy_pulse_files(output_dir: Path, *, stimulus: np.ndarray, planned_rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / "dummy_3ch_pulses.wav"
    planned_csv = output_dir / "planned_pulses.csv"
    planned_json = output_dir / "planned_pulses.json"
    manifest_path = output_dir / "dummy_pulse_manifest.json"

    sf.write(wav_path, stimulus, int(manifest["sample_rate"]), subtype="PCM_24")
    with planned_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(planned_rows[0].keys()))
        writer.writeheader()
        writer.writerows(planned_rows)
    planned_json.write_text(json.dumps(planned_rows, indent=2), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "wav": wav_path,
        "planned_csv": planned_csv,
        "planned_json": planned_json,
        "manifest": manifest_path,
    }


def _default_output_dir() -> Path:
    return Path("artifacts") / "validation_runs" / f"dummy_pulse_{time.strftime('%Y%m%d_%H%M%S')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a coded 3-channel dummy pulse validation WAV.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--intervals-ms", default=",".join(str(value) for value in DEFAULT_INTERVALS_MS))
    parser.add_argument("--pre-roll-s", type=float, default=1.0)
    parser.add_argument("--post-roll-s", type=float, default=1.0)
    parser.add_argument("--amplitude", type=float, default=0.20)
    parser.add_argument(
        "--channel-amplitudes",
        default=None,
        help="Optional per-channel amplitudes as '0.0005,0.02,0.02' or '1:0.0005,2:0.02,3:0.02'.",
    )
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    stimulus, planned_rows, manifest = build_dummy_pulse_stimulus(
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
    )
    paths = write_dummy_pulse_files(output_dir, stimulus=stimulus, planned_rows=planned_rows, manifest=manifest)
    print(f"Wrote dummy stimulus: {paths['wav']}")
    print(f"Wrote planned pulse table: {paths['planned_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
