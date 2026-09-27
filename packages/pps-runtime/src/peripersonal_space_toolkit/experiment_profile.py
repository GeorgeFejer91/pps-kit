"""Local JSON handoff: approved assembly rows and hash-verified ingredients.

The existing Segment 5/6 owners choose trial and block order. This module freezes
their result; it does not introduce another scheduler or copy audio into JSON.
"""

from __future__ import annotations

import csv
import json
from itertools import islice
from pathlib import Path
from typing import Any

from .design import StimulusDesign, audio_file_summary, design_from_dict, design_to_dict
from .designer_segments.registry import manifest_sha256

PROFILE_SCHEMA = "pps-experiment-profile.v1"
MAX_PROFILE_BYTES = 8 * 1024 * 1024
MAX_PLAN_ROWS = 100_000


def _path(value: str | Path, base: Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base / path).resolve(strict=True)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if path.stat().st_size > MAX_PROFILE_BYTES:
        raise ValueError("An assembly CSV exceeds the 8 MiB profile limit.")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(islice(csv.DictReader(handle), MAX_PLAN_ROWS + 1))
    if not rows or len(rows) > MAX_PLAN_ROWS:
        raise ValueError("An assembly CSV must contain 1–100,000 rows.")
    return rows


def create_experiment_profile(
    design: StimulusDesign, run_setup_path: Path, *, source_revision: int
) -> dict[str, Any]:
    """Freeze the already validated local plan; callers retain review gates."""
    run_setup_path = Path(run_setup_path).resolve(strict=True)
    files: dict[str, dict[str, Any]] = {}

    def record(path: Path, *, audio: bool = False) -> dict[str, Any]:
        path = path.resolve(strict=True)
        key = str(path)
        if key not in files:
            before = path.stat()
            value = {"path": key, "bytes": before.st_size, "sha256": manifest_sha256(path)}
            if audio:
                value["audio"] = audio_file_summary(path)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("An ingredient changed while the profile was being exported.")
            files[key] = value
        return files[key]

    record(run_setup_path)
    if run_setup_path.stat().st_size > MAX_PROFILE_BYTES:
        raise ValueError("Run setup exceeds the 8 MiB profile limit.")
    run_setup = json.loads(run_setup_path.read_text(encoding="utf-8-sig"))
    if run_setup.get("schema") != "pps-experiment-run-setup.v1" or not run_setup.get("prepared"):
        raise ValueError("Export requires a prepared Segment 6 assembly plan.")
    source_manifest = record(_path(run_setup["source_segment5_manifest"], run_setup_path.parent))
    if source_manifest["sha256"] != run_setup.get("source_segment5_manifest_sha256"):
        raise ValueError("The accepted block plan changed; review it before exporting.")
    order_path = _path(run_setup["csv_path"], run_setup_path.parent)
    record(order_path)
    order_rows = _read_csv(order_path)
    blocks: dict[str, dict[str, Any]] = {}
    for order in order_rows:
        source_csv = _path(order["block_csv_path"], order_path.parent)
        key = str(source_csv)
        if key in blocks:
            continue
        record(source_csv)
        rows = _read_csv(source_csv)
        for row in rows:
            value = row.get("trial_file_path") or row.get("Trial_File_Path")
            if not value:
                raise ValueError("An approved trial has no local audio ingredient.")
            record(_path(value, source_csv.parent), audio=True)
        blocks[key] = {"source_csv_path": key, "label": order["block_label"], "rows": rows}
    for slot in run_setup.get("instruction_profile", {}).get("slots", []):
        if slot.get("enabled") and slot.get("path"):
            record(_path(slot["path"], run_setup_path.parent), audio=True)
    # Bind the captured rows to the inventoried bytes, even if another process
    # rewrote a source between hashing it and reading its contents.
    verify_profile_files(list(files.values()))
    return {
        "schema": PROFILE_SCHEMA,
        "profile_id": design.study_profile_id,
        "display_name": design.name,
        "source_revision": int(source_revision),
        "design": design_to_dict(design),
        "run_setup_path": str(run_setup_path),
        "assembly": {"run_setup": run_setup, "block_order": order_rows, "blocks": list(blocks.values())},
        "files": list(files.values()),
    }


def experiment_profile_bytes(profile: dict[str, Any]) -> bytes:
    content = (json.dumps(profile, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(content) > MAX_PROFILE_BYTES:
        raise ValueError("Experiment profile exceeds the 8 MiB limit. Reduce the plan size.")
    return content


def verify_profile_files(files: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for item in files:
        path = Path(item["path"])
        if not path.is_absolute() or str(path) in seen:
            raise ValueError("Profile ingredients require unique absolute local paths.")
        seen.add(str(path))
        if path.stat().st_size != item["bytes"] or manifest_sha256(path) != item["sha256"]:
            raise ValueError(f"Profile ingredient changed or is missing: {path.name}")


def read_experiment_profile(path: Path) -> dict[str, Any]:
    path = Path(path)
    if path.stat().st_size > MAX_PROFILE_BYTES:
        raise ValueError("Experiment profile exceeds the 8 MiB limit.")
    profile = json.loads(path.read_text(encoding="utf-8-sig"))
    if profile.get("schema") != PROFILE_SCHEMA:
        raise ValueError("Unsupported experiment profile schema.")
    files = profile.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Experiment profile has no verified local ingredients.")
    verify_profile_files(files)
    if str(profile.get("run_setup_path")) not in {item["path"] for item in files}:
        raise ValueError("The assembly plan is not in the verified file inventory.")
    return profile


def prepare_experiment_profile(path: Path, participant_id: str, **options: Any) -> Any:
    """Compatibility adapter; assembly remains in the existing Runner owner."""
    from .session_runner import prepare_segment_run_package

    profile = read_experiment_profile(path)
    return prepare_segment_run_package(
        Path(profile["run_setup_path"]), participant_id,
        design=design_from_dict(profile["design"]), **options,
    )
