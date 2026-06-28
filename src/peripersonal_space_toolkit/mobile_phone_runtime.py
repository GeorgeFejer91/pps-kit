"""Mobile phone runtime package export/import helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from .output_layout import _filesystem_path, output_runner_logs_dir


MOBILE_PACKAGE_LIST_SCHEMA = "pps-mobile-run-package-list.v1"
MOBILE_PACKAGE_SCHEMA = "pps-mobile-run-package.v1"
MOBILE_RUN_EVENTS_SCHEMA = "pps-mobile-run-events.v1"
MOBILE_RUN_COMPLETE_SCHEMA = "pps-mobile-run-complete.v1"
MOBILE_RUNTIME_ARTIFACT_SCHEMA = "pps-mobile-runtime-artifact.v1"
MOBILE_RUNTIME_LIMITATIONS = [
    "Phone runtime plays prepared block WAVs locally and records phone touch timestamps.",
    "Phone vibration is driven by Android vibrator timing and is not equivalent to the PC tactile audio output.",
    "Phone runtime does not own LSL, LabRecorder, or hardware loopback evidence.",
]


class MobileRuntimePackageError(RuntimeError):
    """Raised when a prepared runner package cannot be exported for phone runtime."""


def mobile_package_id(package: Any) -> str:
    raw = (
        str(getattr(package, "part_session_id", "") or "").strip()
        or str(getattr(package, "session_id", "") or "").strip()
        or str(getattr(package, "participant_id", "") or "").strip()
        or "active-package"
    )
    part = getattr(package, "part_number", None)
    if part not in (None, "") and f"part{part}" not in raw.lower():
        raw = f"{raw}-part{part}"
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._")
    return clean or "active-package"


def build_mobile_package_list(package: Any | Sequence[Any] | None) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    active_id = ""
    for item in _coerce_packages(package):
        manifest = build_mobile_package_manifest(item, include_trials=False, include_sha256=False)
        if not active_id:
            active_id = str(manifest.get("package_id") or "")
        packages.append(
            {
                "package_id": str(manifest.get("package_id") or ""),
                "participant_id": manifest.get("participant_id", ""),
                "session_id": manifest.get("session_id", ""),
                "part_number": manifest.get("part_number"),
                "part_session_id": manifest.get("part_session_id", ""),
                "title": manifest.get("title", ""),
                "block_count": len(manifest.get("blocks") or []),
                "trial_count": sum(int(block.get("trial_count") or 0) for block in manifest.get("blocks") or []),
                "asset_count": len(manifest.get("assets") or []),
                "total_asset_bytes": sum(int(asset.get("size_bytes") or 0) for asset in manifest.get("assets") or []),
                "mobile_runnable": bool(manifest.get("mobile_runnable")),
                "warnings": list(manifest.get("warnings") or []),
                "runtime_limitations": list(MOBILE_RUNTIME_LIMITATIONS),
            }
        )
    return {
        "schema": MOBILE_PACKAGE_LIST_SCHEMA,
        "generated_at": _utc_now(),
        "active_package_id": active_id,
        "packages": packages,
    }


def _coerce_packages(package: Any | Sequence[Any] | None) -> list[Any]:
    if package is None:
        return []
    if isinstance(package, Sequence) and not isinstance(package, (str, bytes, bytearray)):
        return [item for item in package if item is not None]
    return [package]


def build_mobile_package_manifest(
    package: Any,
    *,
    include_trials: bool = True,
    include_sha256: bool = True,
) -> dict[str, Any]:
    package_id = mobile_package_id(package)
    blocks_payload: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    warnings: list[str] = []
    tactile_cue_count = 0
    for block in list(getattr(package, "blocks", []) or []):
        wav_path = Path(getattr(block, "wav_path", "") or "")
        asset_id = f"block-{int(getattr(block, 'index', len(blocks_payload) + 1)):02d}-audio"
        asset = _asset_payload(asset_id, wav_path, include_sha256=include_sha256)
        if not bool(asset.get("available")):
            warnings.append(f"Missing audio asset for block {getattr(block, 'index', '?')}: {wav_path}")
        assets.append(asset)

        trials, cues = _block_trial_payloads(block) if include_trials else ([], [])
        tactile_cue_count += len(cues)
        block_payload = {
            "block_id": f"block-{int(getattr(block, 'index', len(blocks_payload) + 1)):02d}",
            "index": int(getattr(block, "index", len(blocks_payload) + 1) or len(blocks_payload) + 1),
            "label": str(getattr(block, "label", "") or f"Block {len(blocks_payload) + 1:02d}"),
            "duration_s": _float(getattr(block, "duration_s", 0.0)),
            "trial_count": int(getattr(block, "trial_count", 0) or len(trials)),
            "audio_asset_id": asset_id,
            "manifest_filename": Path(getattr(block, "manifest_path", "") or "").name,
            "trials": trials,
            "tactile_cues": cues,
            "metadata": dict(getattr(block, "metadata", {}) or {}),
        }
        blocks_payload.append(block_payload)

    if not blocks_payload:
        warnings.append("No prepared block WAVs are available for phone runtime.")
    if include_trials and tactile_cue_count <= 0:
        warnings.append("No phone-vibration tactile cues were found in the block manifests.")

    return {
        "schema": MOBILE_PACKAGE_SCHEMA,
        "package_id": package_id,
        "generated_at": _utc_now(),
        "title": _package_title(package),
        "participant_id": str(getattr(package, "participant_id", "") or ""),
        "session_id": str(getattr(package, "session_id", "") or ""),
        "session_group_id": str(getattr(package, "session_group_id", "") or ""),
        "part_number": getattr(package, "part_number", None),
        "part_session_id": str(getattr(package, "part_session_id", "") or ""),
        "execution_mode": str(getattr(package, "execution_mode", "") or ""),
        "manifest_path": str(getattr(package, "manifest_path", "") or ""),
        "design_path": str(getattr(package, "design_path", "") or ""),
        "blocks": blocks_payload,
        "assets": assets,
        "mobile_runnable": bool(blocks_payload and all(bool(asset.get("available")) for asset in assets)),
        "warnings": warnings,
        "runtime": {
            "mode": "mobile_phone_runtime",
            "response_input": "touch",
            "tactile_output": "android_vibrator",
            "clock": "android_elapsed_realtime",
            "limitations": list(MOBILE_RUNTIME_LIMITATIONS),
        },
    }


def mobile_asset_path(package: Any, package_id: str, asset_id: str) -> Path:
    expected_package_id = mobile_package_id(package)
    if str(package_id) != expected_package_id:
        raise MobileRuntimePackageError("Unknown mobile package.")
    for block in list(getattr(package, "blocks", []) or []):
        candidate_id = f"block-{int(getattr(block, 'index', 0) or 0):02d}-audio"
        if str(asset_id) == candidate_id:
            path = Path(getattr(block, "wav_path", "") or "")
            if not path.is_file():
                raise MobileRuntimePackageError("Mobile package asset is missing.")
            return path
    raise MobileRuntimePackageError("Unknown mobile package asset.")


def write_mobile_runtime_events(
    package: Any,
    *,
    output_root: Path,
    run_id: str,
    payload: dict[str, Any],
    complete: bool,
) -> dict[str, Any]:
    package_id = str(payload.get("package_id") or mobile_package_id(package))
    if package_id != mobile_package_id(package):
        raise MobileRuntimePackageError("Uploaded events target a different mobile package.")
    clean_run_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(run_id or "phone-run")).strip("-._") or "phone-run"
    out_dir = (
        output_runner_logs_dir(output_root)
        / "mobile_phone_runtime"
        / str(getattr(package, "participant_id", "") or "participant")
        / package_id
        / clean_run_id
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    accepted_at = _utc_now()
    events = [dict(item) for item in list(payload.get("events") or []) if isinstance(item, dict)]
    event_path = out_dir / "events.jsonl"
    if events:
        with open(_filesystem_path(event_path), "a", encoding="utf-8") as handle:
            for event in events:
                row = dict(event)
                row.setdefault("accepted_at", accepted_at)
                row.setdefault("package_id", package_id)
                row.setdefault("run_id", clean_run_id)
                handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        _write_events_csv(out_dir / "events.csv", events)

    artifact = {
        "schema": MOBILE_RUNTIME_ARTIFACT_SCHEMA,
        "accepted_at": accepted_at,
        "complete": bool(complete),
        "package_id": package_id,
        "run_id": clean_run_id,
        "participant_id": str(getattr(package, "participant_id", "") or ""),
        "session_id": str(getattr(package, "session_id", "") or ""),
        "event_count": len(events),
        "phone_payload": payload,
        "paths": {
            "directory": str(out_dir),
            "events_jsonl": str(event_path),
            "events_csv": str(out_dir / "events.csv"),
        },
    }
    artifact_path = out_dir / ("completion.json" if complete else "latest_events_upload.json")
    with open(_filesystem_path(artifact_path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(artifact, indent=2, sort_keys=True, default=str) + "\n")
    return {
        "schema": MOBILE_RUN_COMPLETE_SCHEMA if complete else MOBILE_RUN_EVENTS_SCHEMA,
        "status": "accepted",
        "accepted_at": accepted_at,
        "package_id": package_id,
        "run_id": clean_run_id,
        "event_count": len(events),
        "artifact_path": str(artifact_path),
        "artifact_dir": str(out_dir),
    }


def _asset_payload(asset_id: str, path: Path, *, include_sha256: bool) -> dict[str, Any]:
    available = path.is_file()
    size = path.stat().st_size if available else 0
    return {
        "asset_id": asset_id,
        "filename": path.name,
        "media_type": "audio/wav",
        "role": "block_audio",
        "size_bytes": int(size),
        "sha256": _sha256(path) if include_sha256 and available else "",
        "available": bool(available),
    }


def _block_trial_payloads(block: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = Path(getattr(block, "manifest_path", "") or "")
    if not manifest_path.is_file():
        return [], []
    rows: list[dict[str, str]] = []
    try:
        with open(_filesystem_path(manifest_path), newline="", encoding="utf-8-sig") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return [], []
    trials: list[dict[str, Any]] = []
    cues: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        trial_number = _int(_first(row, "Trial_Number", "trial_number"), index)
        start_s = _float(_first(row, "Trial_Start_S", "start_s", "trial_start_s"))
        duration_s = _float(_first(row, "Trial_Duration_S", "duration_s"))
        end_s = _float(_first(row, "Trial_End_S", "end_s"))
        if end_s <= 0.0 and duration_s > 0.0:
            end_s = start_s + duration_s
        family = _first(row, "Family", "family")
        trial_type = _first(row, "Trial_Type", "trial_type")
        tactile_onset = _optional_float(_first(row, "Tactile_Onset_S", "tactile_onset_s"))
        response_onset = _optional_float(_first(row, "Response_Window_Onset_S", "response_window_onset_s"))
        trial_uid = _first(row, "Trial_UID", "trial_uid") or f"trial-{trial_number:03d}"
        trial_payload = {
            "trial_number": trial_number,
            "trial_uid": trial_uid,
            "trial_type": trial_type,
            "family": family,
            "soa_ms": _first(row, "SOA_ms", "soa_ms"),
            "row_label": _first(row, "Row_Label", "Row", "row_label"),
            "noise_type": _first(row, "Noise_Type", "noise_type"),
            "start_s": start_s,
            "end_s": max(end_s, start_s),
            "duration_s": max(0.0, duration_s if duration_s > 0.0 else end_s - start_s),
            "tactile_onset_s": tactile_onset,
            "response_window_onset_s": response_onset,
        }
        trials.append(trial_payload)
        if tactile_onset is not None and _has_tactile(row, family=family, trial_type=trial_type):
            cues.append(
                {
                    "cue_id": len(cues) + 1,
                    "trial_number": trial_number,
                    "trial_uid": trial_uid,
                    "time_s": max(0.0, start_s + tactile_onset),
                    "trial_relative_time_s": max(0.0, tactile_onset),
                    "soa_ms": trial_payload["soa_ms"],
                    "row_label": trial_payload["row_label"],
                    "noise_type": trial_payload["noise_type"],
                }
            )
    return trials, sorted(cues, key=lambda cue: float(cue.get("time_s") or 0.0))


def _has_tactile(row: dict[str, Any], *, family: str, trial_type: str) -> bool:
    explicit = _first(row, "Tactile_Enabled", "tactile_enabled", "Has_Tactile", "has_tactile").strip().lower()
    if explicit in {"false", "0", "no", "n"}:
        return False
    if explicit in {"true", "1", "yes", "y"}:
        return True
    text = f"{family} {trial_type}".lower()
    return "baseline" in text or "audio_tactile" in text or "tactile" in text


def _write_events_csv(path: Path, events: list[dict[str, Any]]) -> None:
    keys: list[str] = []
    for event in events:
        for key in event:
            if key not in keys and isinstance(event.get(key), (str, int, float, bool, type(None))):
                keys.append(key)
    if not keys:
        return
    existing_rows: list[dict[str, Any]] = []
    if path.is_file():
        try:
            with open(_filesystem_path(path), newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                for key in reader.fieldnames or []:
                    if key not in keys:
                        keys.append(key)
                existing_rows = [dict(row) for row in reader]
        except Exception:
            existing_rows = []
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in existing_rows:
            writer.writerow(row)
        for event in events:
            writer.writerow({key: event.get(key, "") for key in keys})


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(str(value).strip())
    except Exception:
        return default
    if not (number == number):
        return default
    return float(number)


def _optional_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    number = _float(text, default=float("nan"))
    if not (number == number):
        return None
    return float(number)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(_filesystem_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_title(package: Any) -> str:
    part = getattr(package, "part_number", None)
    base = f"Participant {getattr(package, 'participant_id', '')}".strip()
    if part not in (None, ""):
        return f"{base} Part {part}"
    return base


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
