"""Persistence helpers for participant tactile calibration artifacts."""

from __future__ import annotations

import csv
from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any

from ..output_layout import _filesystem_path
from .schema import (
    LATEST_CALIBRATION_SCHEMA,
    LATEST_FILENAME,
    REPORT_FILENAME,
    TRIAL_FIELDNAMES,
    TRIALS_FILENAME,
)


def sanitize_participant_id(value: str | None) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    text = text.strip("._-")
    return text or "participant"


def participant_calibration_dir(output_root: Path | str, participant_id: str | None) -> Path:
    participant = sanitize_participant_id(participant_id)
    return Path(output_root).expanduser() / participant / f"{participant}_tactile-calibration"


def latest_calibration_path(output_root: Path | str, participant_id: str | None) -> Path:
    return participant_calibration_dir(output_root, participant_id) / LATEST_FILENAME


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    os.makedirs(_filesystem_path(path.parent), exist_ok=True)
    with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_trials_csv(path: Path, trials: list[dict[str, Any]]) -> None:
    os.makedirs(_filesystem_path(path.parent), exist_ok=True)
    with open(_filesystem_path(path), "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRIAL_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for trial in trials:
            writer.writerow({key: trial.get(key, "") for key in TRIAL_FIELDNAMES})


def _latest_payload(report: dict[str, Any], *, report_path: Path, trials_path: Path) -> dict[str, Any]:
    recommended_percent = report.get("recommended_output_34_percent", report.get("final_output_34_percent", ""))
    threshold_percent = report.get("detection_threshold_output_34_percent", recommended_percent)
    staircase_summary = dict(report.get("staircase_summary") or {})
    legacy_source = report.get("confirmation_summary") or ({} if staircase_summary else report.get("validation_summary"))
    legacy_summary = dict(legacy_source or {})
    summary = staircase_summary or legacy_summary
    return {
        "schema": LATEST_CALIBRATION_SCHEMA,
        "participant_id": str(report.get("participant_id") or ""),
        "accepted": bool(report.get("accepted")),
        "status": str(report.get("status") or ""),
        "created_at": str(report.get("created_at") or ""),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "protocol": str(report.get("protocol") or ""),
        "threshold_method": str(report.get("threshold_method") or ""),
        "threshold_definition": str(report.get("threshold_definition") or ""),
        "final_output_34_percent": recommended_percent,
        "detection_threshold_output_34_percent": threshold_percent,
        "recommended_output_34_percent": recommended_percent,
        "confirmation_level_output_34_percent": report.get("confirmation_level_output_34_percent", threshold_percent),
        "staircase_target_detection_rate": staircase_summary.get(
            "target_detection_rate",
            dict(report.get("adaptive_staircase") or {}).get("target_detection_rate", ""),
        ),
        "staircase_reversals": staircase_summary.get("reversals", ""),
        "staircase_reversal_levels_percent": list(staircase_summary.get("reversal_levels_percent") or []),
        "staircase_reversal_levels_used_percent": list(staircase_summary.get("reversal_levels_used_percent") or []),
        "staircase_signal_trials": staircase_summary.get("signal_trials", ""),
        "staircase_hits": staircase_summary.get("hits", ""),
        "staircase_misses": staircase_summary.get("misses", ""),
        "staircase_hit_rate": report.get("staircase_hit_rate", staircase_summary.get("hit_rate", "")),
        "staircase_false_alarm_rate": report.get(
            "staircase_false_alarm_rate",
            staircase_summary.get("false_alarm_rate", ""),
        ),
        "adaptive_staircase": dict(report.get("adaptive_staircase") or {}),
        "confirmation_hits": legacy_summary.get("hits", ""),
        "confirmation_signal_trials": legacy_summary.get("signal_trials", ""),
        "catch_false_alarms": summary.get("false_alarms", ""),
        "catch_trials": summary.get("catch_trials", ""),
        "confirmation_hit_rate": report.get("confirmation_hit_rate", report.get("validation_hit_rate", "")),
        "confirmation_false_alarm_rate": report.get(
            "confirmation_false_alarm_rate",
            report.get("validation_false_alarm_rate", ""),
        ),
        "validation_hit_rate": report.get("validation_hit_rate", ""),
        "validation_false_alarm_rate": report.get("validation_false_alarm_rate", ""),
        "trial_count": report.get("trial_count", ""),
        "timing": dict(report.get("timing") or {}),
        "confirmation_criteria": dict(report.get("confirmation_criteria") or {}),
        "staircase_criteria": dict(report.get("adaptive_staircase") or {}),
        "report_path": str(report_path),
        "trials_csv_path": str(trials_path),
        "run_setup_manifest_path": str(report.get("run_setup_manifest_path") or ""),
        "session_group_id": str(report.get("session_group_id") or ""),
        "part_session_id": str(report.get("part_session_id") or ""),
    }


def save_calibration_attempt(
    *,
    output_root: Path | str,
    participant_id: str | None,
    report: dict[str, Any],
    trials: list[dict[str, Any]],
    timestamp: str | None = None,
) -> dict[str, Path]:
    participant = sanitize_participant_id(participant_id)
    root = participant_calibration_dir(output_root, participant)
    attempt_dir = root / str(timestamp or _timestamp())
    report_path = attempt_dir / REPORT_FILENAME
    trials_path = attempt_dir / TRIALS_FILENAME
    payload = dict(report)
    payload["participant_id"] = participant
    payload["report_path"] = str(report_path)
    payload["trials_csv_path"] = str(trials_path)
    _write_json(report_path, payload)
    _write_trials_csv(trials_path, trials)
    latest_path = root / LATEST_FILENAME
    if bool(payload.get("accepted")):
        _write_json(latest_path, _latest_payload(payload, report_path=report_path, trials_path=trials_path))
    return {"attempt_dir": attempt_dir, "report_path": report_path, "trials_csv_path": trials_path, "latest_path": latest_path}


def load_latest_calibration(output_root: Path | str, participant_id: str | None) -> dict[str, Any] | None:
    path = latest_calibration_path(output_root, participant_id)
    if not os.path.isfile(_filesystem_path(path)):
        return None
    try:
        with open(_filesystem_path(path), "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return None
    if not bool(payload.get("accepted")):
        return None
    try:
        percent = float(payload.get("recommended_output_34_percent", payload.get("final_output_34_percent")))
    except (TypeError, ValueError):
        return None
    if percent < 0.0 or percent > 100.0:
        return None
    payload["final_output_34_percent"] = percent
    payload["recommended_output_34_percent"] = percent
    try:
        payload["detection_threshold_output_34_percent"] = float(
            payload.get("detection_threshold_output_34_percent", percent)
        )
    except (TypeError, ValueError):
        payload["detection_threshold_output_34_percent"] = percent
    payload["latest_path"] = str(path)
    return payload
