"""Audit WAV peak and RMS levels for loudness-calibration exploration.

The script intentionally reports digital dBFS only. It does not estimate dB SPL
unless a measured calibration profile is supplied elsewhere.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


DEFAULT_PATTERNS = (
    "assets/preloads/study5_box_breathing_pps/*.wav",
    "assets/preloads/study5_box_breathing_pps/02_looming_stimuli/*.wav",
    "assets/breathing/**/*.wav",
)


def dbfs(value: float) -> float | None:
    if not math.isfinite(value) or value <= 0:
        return None
    return 20.0 * math.log10(value)


def fmt_db(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.3f}"


def rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def window_samples(data: np.ndarray, sample_rate: int, seconds: float, start: str) -> np.ndarray:
    count = min(len(data), max(1, int(round(seconds * sample_rate))))
    if start == "first":
        return data[:count]
    if start == "last":
        return data[-count:]
    raise ValueError(f"unknown window start {start!r}")


def classify(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    if "study5_box_breathing_pps" in parts and "looming" in name:
        return "study5_looming"
    if "breathing" in parts:
        return "breathing_instruction"
    if "looming" in name:
        return "other_looming"
    return "other"


def channel_dbfs(data: np.ndarray) -> str:
    values = [fmt_db(dbfs(rms(data[:, idx]))) for idx in range(data.shape[1])]
    return ";".join(values)


def audit_file(path: Path, root: Path) -> dict[str, Any]:
    data, sample_rate = sf.read(path, always_2d=True, dtype="float64")
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    full_rms = rms(data)
    first_rms = rms(window_samples(data, sample_rate, 0.5, "first"))
    last_rms = rms(window_samples(data, sample_rate, 0.5, "last"))
    duration = float(len(data) / sample_rate) if sample_rate else 0.0
    notes: list[str] = []
    if peak >= 1.0:
        notes.append("clips_or_full_scale")
    elif peak >= 0.99:
        notes.append("near_full_scale")
    if full_rms == 0.0:
        notes.append("silent")

    return {
        "path": path.relative_to(root).as_posix(),
        "category": classify(path),
        "sample_rate_hz": sample_rate,
        "channels": data.shape[1],
        "duration_s": round(duration, 6),
        "peak": round(peak, 9),
        "peak_dbfs": dbfs(peak),
        "rms": round(full_rms, 9),
        "rms_dbfs": dbfs(full_rms),
        "first_500ms_rms_dbfs": dbfs(first_rms),
        "last_500ms_rms_dbfs": dbfs(last_rms),
        "per_channel_rms_dbfs": channel_dbfs(data),
        "notes": ",".join(notes),
    }


def discover(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    found: dict[Path, Path] = {}
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                found[path.resolve()] = path
    return [found[key] for key in sorted(found)]


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["category"]].append(record)

    summary: dict[str, Any] = {}
    for category, items in grouped.items():
        numeric_keys = ("peak_dbfs", "rms_dbfs", "first_500ms_rms_dbfs", "last_500ms_rms_dbfs")
        entry: dict[str, Any] = {"count": len(items)}
        for key in numeric_keys:
            values = [item[key] for item in items if item[key] is not None]
            if values:
                entry[f"{key}_min"] = min(values)
                entry[f"{key}_max"] = max(values)
        summary[category] = entry
    return summary


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fields = (
        "path",
        "category",
        "sample_rate_hz",
        "channels",
        "duration_s",
        "peak",
        "peak_dbfs",
        "rms",
        "rms_dbfs",
        "first_500ms_rms_dbfs",
        "last_500ms_rms_dbfs",
        "per_channel_rms_dbfs",
        "notes",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = dict(record)
            for key in ("peak_dbfs", "rms_dbfs", "first_500ms_rms_dbfs", "last_500ms_rms_dbfs"):
                row[key] = fmt_db(row[key])
            writer.writerow(row)


def write_json(path: Path, _root: Path, records: list[dict[str, Any]]) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": ".",
        "patterns": list(DEFAULT_PATTERNS),
        "summary": summarize(records),
        "records": records,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("exploratory/loudness-calibration"),
        help="directory for stimulus_level_audit.csv/json",
    )
    parser.add_argument(
        "--pattern",
        action="append",
        dest="patterns",
        help="glob pattern relative to root; repeat to override defaults",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    patterns = tuple(args.patterns) if args.patterns else DEFAULT_PATTERNS
    files = discover(root, patterns)
    records = [audit_file(path, root) for path in files]

    out_dir = (root / args.out_dir).resolve() if not args.out_dir.is_absolute() else args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "stimulus_level_audit.csv", records)
    write_json(out_dir / "stimulus_level_audit.json", root, records)

    print(f"Audited {len(records)} WAV files.")
    for category, entry in sorted(summarize(records).items()):
        print(f"{category}: {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
