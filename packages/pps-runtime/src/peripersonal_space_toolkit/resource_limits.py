"""Shared local generation limits; reject oversized work without truncating it."""
from __future__ import annotations

import csv
import math
import shutil
from itertools import islice
from pathlib import Path

MAX_PLAN_ROWS = 100_000
MAX_BLOCKS = 1024
MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_WAV_BYTES = 768 * 1024 * 1024
MAX_WORKING_AUDIO_BYTES = 1024 * 1024 * 1024


class ResourceLimit(ValueError):
    code = "resource_limit"


def require_plan_size(count: int, label: str, *, limit: int = MAX_PLAN_ROWS) -> None:
    if count < 0 or count > limit:
        raise ResourceLimit(f"{label} requires {count:,} entries; the local limit is {limit:,}. Reduce the plan and retry.")


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    if path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ResourceLimit("An assembly CSV exceeds the 8 MiB limit.")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(islice(csv.DictReader(handle), MAX_PLAN_ROWS + 1))
    require_plan_size(len(rows), "Assembly CSV")
    return rows


def audio_generation_preflight(
    output_dir: str | Path, *, duration_s: float, sample_rate: int, channels: int,
    file_count: int = 1, source_bytes: int = 0,
) -> dict[str, int | float]:
    """Conservative PCM16 output/scratch and three float32 working buffers."""
    if not math.isfinite(duration_s) or duration_s < 0 or sample_rate <= 0 or not 1 <= channels <= 32:
        raise ResourceLimit("Audio duration, sample rate, and channel count must be finite and supported.")
    require_plan_size(file_count, "Generated audio files")
    samples = math.ceil(duration_s * sample_rate)
    wav_bytes = 44 + samples * channels * 2
    working_bytes = samples * channels * 4 * 3
    if wav_bytes > MAX_WAV_BYTES or working_bytes > MAX_WORKING_AUDIO_BYTES:
        raise ResourceLimit("Audio generation exceeds the per-file or working-memory limit. Shorten the stimulus or block.")
    output_bytes = max(wav_bytes * file_count, source_bytes)
    required_bytes = output_bytes * 3 + 8 * 1024 * 1024
    existing = Path(output_dir).resolve()
    while not existing.exists():
        existing = existing.parent
    free_bytes = shutil.disk_usage(existing).free
    if free_bytes < required_bytes:
        raise ResourceLimit(f"Generation needs approximately {math.ceil(required_bytes / 1024**2):,} MiB free; "
                            f"{free_bytes // 1024**2:,} MiB is available. Free space and retry.")
    return {"duration_s": duration_s, "sample_rate": sample_rate, "channels": channels,
            "file_count": file_count, "output_bytes": output_bytes,
            "working_bytes": working_bytes, "required_free_bytes": required_bytes, "free_bytes": free_bytes}
