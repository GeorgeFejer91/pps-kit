"""Run-local adaptive tactile threshold adjustment."""

from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .output_layout import _filesystem_path as _output_filesystem_path
from .tactile_calibration.schema import CONFIRMATION_LEVEL_INCREMENT_PERCENT, TACTILE_OUTPUT_34_MAX_PERCENT


ADAPTIVE_TACTILE_THRESHOLD_SCHEMA = "pps-adaptive-tactile-threshold.v1"
DEFAULT_MISSES_PER_ADJUSTMENT = 2
DEFAULT_MISS_SCOPE = "all_tactile_misses_including_topup"
SUMMARY_FILENAME = "adaptive_tactile_threshold_summary.json"
ADJUSTMENTS_FILENAME = "adaptive_tactile_threshold_adjustments.csv"


@dataclass(frozen=True)
class AdaptiveTactileThresholdAdjustment:
    adjustment_index: int
    old_output_34_percent: float
    new_output_34_percent: float
    increment_output_34_percent: float
    triggering_miss_count: int
    triggering_ledger_id: str
    triggering_trial_uid: str
    triggering_block_number: str
    triggering_trial_number: str
    triggering_is_topup: bool
    triggering_miss_reason: str

    def as_row(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_TACTILE_THRESHOLD_SCHEMA,
            "adjustment_index": self.adjustment_index,
            "old_output_34_percent": self.old_output_34_percent,
            "new_output_34_percent": self.new_output_34_percent,
            "increment_output_34_percent": self.increment_output_34_percent,
            "triggering_miss_count": self.triggering_miss_count,
            "triggering_ledger_id": self.triggering_ledger_id,
            "triggering_trial_uid": self.triggering_trial_uid,
            "triggering_block_number": self.triggering_block_number,
            "triggering_trial_number": self.triggering_trial_number,
            "triggering_is_topup": self.triggering_is_topup,
            "triggering_miss_reason": self.triggering_miss_reason,
        }


class AdaptiveTactileThresholdController:
    """Raise run-local Output 3/4 after missed tactile trials accumulate."""

    def __init__(
        self,
        *,
        initial_output_34_percent: Any,
        enabled: bool = True,
        misses_per_adjustment: int = DEFAULT_MISSES_PER_ADJUSTMENT,
        increment_output_34_percent: float = CONFIRMATION_LEVEL_INCREMENT_PERCENT,
        max_output_34_percent: float = TACTILE_OUTPUT_34_MAX_PERCENT,
        miss_scope: str = DEFAULT_MISS_SCOPE,
    ):
        self.enabled = bool(enabled)
        self.initial_output_34_percent = _coerce_output_34_percent(initial_output_34_percent, maximum=max_output_34_percent)
        self.current_output_34_percent = self.initial_output_34_percent
        self.misses_per_adjustment = max(1, int(misses_per_adjustment or DEFAULT_MISSES_PER_ADJUSTMENT))
        self.increment_output_34_percent = max(0.0, float(increment_output_34_percent or 0.0))
        self.max_output_34_percent = max(0.0, float(max_output_34_percent or 0.0))
        self.miss_scope = str(miss_scope or DEFAULT_MISS_SCOPE)
        self.total_misses = 0
        self.misses_since_last_adjustment = 0
        self.tracked_tactile_trials = 0
        self.current_hit_count = 0
        self.current_miss_count = 0
        self.current_pending_count = 0
        self.adjustments: list[AdaptiveTactileThresholdAdjustment] = []
        self.suppressed_at_cap_count = 0
        self._observed_miss_keys: set[str] = set()

    def policy_payload(self) -> dict[str, Any]:
        return {
            "schema": ADAPTIVE_TACTILE_THRESHOLD_SCHEMA,
            "enabled": self.enabled,
            "rule": "raise_output_34_after_n_misses",
            "miss_scope": self.miss_scope,
            "misses_per_adjustment": self.misses_per_adjustment,
            "increment_output_34_percent": self.increment_output_34_percent,
            "max_output_34_percent": self.max_output_34_percent,
            "initial_output_34_percent": self.initial_output_34_percent,
        }

    def observe_missed_entries(self, entries: Iterable[Any]) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        emitted: list[dict[str, Any]] = []
        for entry in sorted(list(entries), key=_entry_sort_key):
            key = _entry_key(entry)
            if not key or key in self._observed_miss_keys:
                continue
            self._observed_miss_keys.add(key)
            self.total_misses += 1
            self.misses_since_last_adjustment += 1
            if self.misses_since_last_adjustment < self.misses_per_adjustment:
                continue
            self.misses_since_last_adjustment = 0
            next_percent = _coerce_output_34_percent(
                self.current_output_34_percent + self.increment_output_34_percent,
                maximum=self.max_output_34_percent,
            )
            if next_percent <= self.current_output_34_percent:
                self.suppressed_at_cap_count += 1
                continue
            adjustment = AdaptiveTactileThresholdAdjustment(
                adjustment_index=len(self.adjustments) + 1,
                old_output_34_percent=self.current_output_34_percent,
                new_output_34_percent=next_percent,
                increment_output_34_percent=round(next_percent - self.current_output_34_percent, 3),
                triggering_miss_count=self.total_misses,
                triggering_ledger_id=str(getattr(entry, "ledger_id", "")),
                triggering_trial_uid=str(getattr(entry, "trial_uid", "")),
                triggering_block_number=str(getattr(entry, "block_number", "")),
                triggering_trial_number=str(getattr(entry, "trial_number", "")),
                triggering_is_topup=bool(getattr(entry, "is_topup", False)),
                triggering_miss_reason=str(getattr(entry, "miss_reason", "")),
            )
            self.current_output_34_percent = next_percent
            self.adjustments.append(adjustment)
            emitted.append(adjustment.as_row())
        return emitted

    def update_counts_from_entries(self, entries: Iterable[Any]) -> None:
        rows = list(entries)
        self.tracked_tactile_trials = len(rows)
        self.current_hit_count = sum(1 for entry in rows if str(getattr(entry, "status", "") or "") == "hit")
        self.current_miss_count = sum(
            1 for entry in rows if str(getattr(entry, "status", "") or "") == "missed_needs_topup"
        )
        self.current_pending_count = sum(1 for entry in rows if str(getattr(entry, "status", "") or "") == "pending")

    def summary(self) -> dict[str, Any]:
        payload = self.policy_payload()
        miss_rate = self.current_miss_count / self.tracked_tactile_trials if self.tracked_tactile_trials else None
        payload.update(
            {
                "tracked_tactile_trials": self.tracked_tactile_trials,
                "current_hit_count": self.current_hit_count,
                "current_miss_count": self.current_miss_count,
                "current_pending_count": self.current_pending_count,
                "current_miss_rate": miss_rate,
                "total_misses": self.total_misses,
                "misses_since_last_adjustment": self.misses_since_last_adjustment,
                "adjustment_count": len(self.adjustments),
                "suppressed_at_cap_count": self.suppressed_at_cap_count,
                "final_output_34_percent": self.current_output_34_percent,
                "capped_at_max": self.current_output_34_percent >= self.max_output_34_percent,
                "adjustments": [item.as_row() for item in self.adjustments],
            }
        )
        return payload

    def write_outputs(self, output_dir: str | Path) -> dict[str, Path]:
        root = Path(output_dir)
        os.makedirs(_output_filesystem_path(root), exist_ok=True)
        summary_path = root / SUMMARY_FILENAME
        csv_path = root / ADJUSTMENTS_FILENAME
        with open(_output_filesystem_path(summary_path), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(self.summary(), indent=2, sort_keys=True) + "\n")
        fieldnames = [
            "schema",
            "adjustment_index",
            "old_output_34_percent",
            "new_output_34_percent",
            "increment_output_34_percent",
            "triggering_miss_count",
            "triggering_ledger_id",
            "triggering_trial_uid",
            "triggering_block_number",
            "triggering_trial_number",
            "triggering_is_topup",
            "triggering_miss_reason",
        ]
        with open(_output_filesystem_path(csv_path), "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(item.as_row() for item in self.adjustments)
        return {
            "adaptive_tactile_threshold_summary": summary_path,
            "adaptive_tactile_threshold_adjustments": csv_path,
        }


def adaptive_threshold_initial_output_34_percent(runner_metadata: dict[str, Any] | None) -> float:
    raw = dict(runner_metadata or {})
    playback = raw.get("playback_output_levels")
    if isinstance(playback, dict) and playback.get("output_3_4_percent") not in (None, ""):
        return _coerce_output_34_percent(playback.get("output_3_4_percent"))
    calibration = raw.get("tactile_calibration")
    if isinstance(calibration, dict):
        for key in ("recommended_output_34_percent", "final_output_34_percent", "detection_threshold_output_34_percent"):
            if calibration.get(key) not in (None, ""):
                return _coerce_output_34_percent(calibration.get(key))
    return _coerce_output_34_percent(TACTILE_OUTPUT_34_MAX_PERCENT)


def _coerce_output_34_percent(value: Any, *, maximum: float = TACTILE_OUTPUT_34_MAX_PERCENT) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(maximum)
    if not math.isfinite(number):
        number = float(maximum)
    return round(max(0.0, min(float(maximum), number)), 3)


def _entry_key(entry: Any) -> str:
    ledger_id = str(getattr(entry, "ledger_id", "") or "").strip()
    if ledger_id:
        return f"ledger:{ledger_id}"
    trial_uid = str(getattr(entry, "trial_uid", "") or "").strip()
    tactile_event_id = str(getattr(entry, "tactile_event_id", "") or "").strip()
    if trial_uid or tactile_event_id:
        return f"trial:{trial_uid}:{tactile_event_id}"
    return ""


def _entry_sort_key(entry: Any) -> tuple[float, int, str]:
    try:
        tactile_time = float(getattr(entry, "tactile_unix_time", 0.0) or 0.0)
    except (TypeError, ValueError):
        tactile_time = 0.0
    try:
        ledger_id = int(getattr(entry, "ledger_id", 0) or 0)
    except (TypeError, ValueError):
        ledger_id = 0
    return tactile_time, ledger_id, str(getattr(entry, "trial_uid", "") or "")
