"""Internal missed-trial ledger for optional top-up blocks."""

from __future__ import annotations

import csv
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .output_layout import _filesystem_path as _output_filesystem_path
from .response_policy import TACTILE_RESPONSE_MAX_RT_S, TACTILE_RESPONSE_MIN_RT_S
from .session_events import SessionEvent


PENDING = "pending"
HIT = "hit"
MISSED_NEEDS_TOPUP = "missed_needs_topup"
DEFAULT_MIN_RESPONSE_RT_S = TACTILE_RESPONSE_MIN_RT_S
DEFAULT_MAX_RESPONSE_RT_S = TACTILE_RESPONSE_MAX_RT_S


@dataclass
class TopUpLedgerEntry:
    ledger_id: int
    status: str
    participant_id: str
    session_id: str
    part_number: int | str
    phase: str
    phase_label: str
    block_number: int | str
    block_label: str
    trial_number: int | str
    trial_uid: str
    trial_type: str
    family: str
    row_label: str
    respiratory_phase: str
    soa_ms: int | str
    noise_type: str
    sequence_labels: str
    trial_file_path: str
    source_sha256: str
    manifest_path: str
    source_block_index: int | str
    source_block_label: str
    segment5_block_trial_index: int | str
    tactile_event_id: int | str
    tactile_unix_time: float
    tactile_monotonic_time: float
    response_deadline_unix_time: float
    response_deadline_monotonic_time: float
    click_event_id: int | str = ""
    click_unix_time: float | str = ""
    click_monotonic_time: float | str = ""
    rt_ms: float | str = ""
    is_topup: bool = False
    topup_role: str = ""
    source_trial_uid: str = ""
    primary_analysis_included: bool = True
    miss_reason: str = ""
    created_at_unix: float = field(default_factory=time.time)

    def as_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["is_topup"] = str(bool(self.is_topup)).lower()
        row["primary_analysis_included"] = str(bool(self.primary_analysis_included)).lower()
        return row


class TopUpLedger:
    """Track tactile trials live and persist recoverable top-up state."""

    def __init__(
        self,
        session_dir: str | Path,
        *,
        participant_id: str,
        session_id: str,
        min_rt_s: float = DEFAULT_MIN_RESPONSE_RT_S,
        max_rt_s: float = DEFAULT_MAX_RESPONSE_RT_S,
    ):
        self.session_dir = Path(session_dir)
        self.participant_id = participant_id
        self.session_id = session_id
        self.min_rt_s = max(0.0, float(min_rt_s))
        self.max_rt_s = max(self.min_rt_s, float(max_rt_s))
        self.entries: list[TopUpLedgerEntry] = []
        self._unmatched_clicks: list[dict[str, Any]] = []
        self._next_id = 1
        self._lock = threading.RLock()

    @property
    def csv_path(self) -> Path:
        return self.session_dir / "topup_ledger.csv"

    @property
    def json_path(self) -> Path:
        return self.session_dir / "topup_ledger.json"

    def observe_event(self, event: SessionEvent) -> None:
        with self._lock:
            row = _event_row(event)
            event_type = str(row.get("event_type") or "")
            if event_type == "tactile_onset":
                self.expire_due(float(event.unix_time))
                self._add_tactile(event, row)
            elif event_type == "mouse_click":
                self._record_click(event, row)
            elif event_type == "trial_start":
                self.expire_due(float(event.unix_time))
            elif event_type == "trial_end":
                self.expire_due(float(event.unix_time))
            elif event_type in {"block_end", "session_end"}:
                self.expire_due(float(event.unix_time))

    def finalize_open_trials(self, *, part_number: int | str | None = None) -> None:
        with self._lock:
            for entry in self.entries:
                if part_number is not None and _part_key(entry.part_number) != _part_key(part_number):
                    continue
                if entry.status == PENDING:
                    entry.status = MISSED_NEEDS_TOPUP
                    entry.miss_reason = entry.miss_reason or "session_or_block_finished"

    def expire_due(self, unix_time: float) -> None:
        with self._lock:
            for entry in self.entries:
                if entry.status == PENDING and float(entry.response_deadline_unix_time) <= unix_time:
                    entry.status = MISSED_NEEDS_TOPUP
                    entry.miss_reason = entry.miss_reason or "response_deadline_expired"
            self._prune_unmatched_clicks(unix_time)

    def expire_at_trial_boundary(self, unix_time: float, monotonic_time: float) -> None:
        with self._lock:
            self.expire_due(unix_time)
            self._prune_unmatched_clicks(unix_time)

    def missed_entries(self, *, include_topup: bool = False, part_number: int | str | None = None) -> list[TopUpLedgerEntry]:
        with self._lock:
            return [
                entry
                for entry in self.entries
                if entry.status == MISSED_NEEDS_TOPUP and (include_topup or not entry.is_topup)
                and (part_number is None or _part_key(entry.part_number) == _part_key(part_number))
            ]

    def hit_entries(self, *, include_topup: bool = False, part_number: int | str | None = None) -> list[TopUpLedgerEntry]:
        with self._lock:
            return [
                entry
                for entry in self.entries
                if entry.status == HIT and (include_topup or not entry.is_topup)
                and (part_number is None or _part_key(entry.part_number) == _part_key(part_number))
            ]

    def pending_entries(self) -> list[TopUpLedgerEntry]:
        with self._lock:
            return [entry for entry in self.entries if entry.status == PENDING]

    def summary(self) -> dict[str, Any]:
        with self._lock:
            rows = self.entries
            return {
                "participant_id": self.participant_id,
                "session_id": self.session_id,
                "tracked_tactile_trials": len(rows),
                "pending": sum(1 for entry in rows if entry.status == PENDING),
                "hit": sum(1 for entry in rows if entry.status == HIT),
                "missed_needs_topup": sum(1 for entry in rows if entry.status == MISSED_NEEDS_TOPUP and not entry.is_topup),
                "topup_attempts": sum(1 for entry in rows if entry.is_topup),
                "parts": sorted({_part_key(entry.part_number) for entry in rows if _part_key(entry.part_number)}),
            }

    def write_outputs(self) -> dict[str, Path]:
        with self._lock:
            os.makedirs(_output_filesystem_path(self.session_dir), exist_ok=True)
            rows = [entry.as_row() for entry in self.entries]
            fieldnames = _fieldnames(rows)
            with open(_output_filesystem_path(self.csv_path), "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            with open(_output_filesystem_path(self.json_path), "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps({"schema": "pps-topup-ledger.v1", "summary": self.summary(), "entries": rows}, indent=2)
                )
        return {"topup_ledger_csv": self.csv_path, "topup_ledger_json": self.json_path}

    def _add_tactile(self, event: SessionEvent, row: dict[str, Any]) -> None:
        if not _is_tactile_trial(row):
            return
        if not _tactile_trial_requires_response(row):
            return
        trial_uid = str(_field(row, "trial_uid", "Trial_UID") or "")
        if trial_uid and any(entry.trial_uid == trial_uid and str(entry.tactile_event_id) == str(event.event_id) for entry in self.entries):
            return
        is_topup = _truthy(_field(row, "is_topup", "Is_Topup"))
        topup_role = str(_field(row, "topup_role", "Topup_Role") or "").strip().lower()
        source_primary = _field(row, "primary_analysis_included", "Primary_Analysis_Included")
        primary_included = _truthy(source_primary) if source_primary not in (None, "") else True
        primary_included = primary_included and not (is_topup and topup_role == "filler")
        entry = TopUpLedgerEntry(
            ledger_id=self._next_id,
            status=PENDING,
            participant_id=str(_field(row, "participant_id", "Participant_ID") or self.participant_id),
            session_id=str(_field(row, "session_id", "Session_ID") or self.session_id),
            part_number=_field(row, "part_number", "Part_Number"),
            phase=str(_field(row, "phase", "Phase") or ""),
            phase_label=str(_field(row, "phase_label", "Phase_Label") or ""),
            block_number=_field(row, "block_number", "Block_Number"),
            block_label=str(_field(row, "block_label", "Block_Label") or ""),
            trial_number=_field(row, "trial_number", "Trial_Number"),
            trial_uid=trial_uid,
            trial_type=str(_field(row, "trial_type", "Trial_Type") or ""),
            family=str(_field(row, "family", "Family") or ""),
            row_label=str(_field(row, "row_label", "Row_Label", "Row") or ""),
            respiratory_phase=str(_field(row, "respiratory_phase", "Respiratory_Phase") or _field(row, "row_label", "Row_Label", "Row") or ""),
            soa_ms=_field(row, "soa_ms", "SOA_ms"),
            noise_type=str(_field(row, "noise_type", "Noise_Type") or ""),
            sequence_labels=str(_field(row, "sequence_labels", "Sequence_Labels") or ""),
            trial_file_path=str(_field(row, "trial_file_path", "Trial_File_Path") or ""),
            source_sha256=str(_field(row, "source_sha256", "Source_SHA256") or ""),
            manifest_path=str(_field(row, "manifest_path", "Manifest_Path") or ""),
            source_block_index=_field(row, "source_block_index", "Source_Block_Index"),
            source_block_label=str(_field(row, "source_block_label", "Source_Block_Label") or ""),
            segment5_block_trial_index=_field(row, "segment5_block_trial_index", "Segment5_Block_Trial_Index"),
            tactile_event_id=event.event_id,
            tactile_unix_time=float(event.unix_time),
            tactile_monotonic_time=float(event.monotonic_time),
            response_deadline_unix_time=float(event.unix_time) + self.max_rt_s,
            response_deadline_monotonic_time=float(event.monotonic_time) + self.max_rt_s,
            is_topup=is_topup,
            topup_role=topup_role,
            source_trial_uid=str(_field(row, "source_trial_uid", "Source_Trial_UID", "Original_Trial_UID") or ""),
            primary_analysis_included=primary_included,
        )
        self._next_id += 1
        self.entries.append(entry)
        self._try_resolve_from_unmatched(entry)

    def _record_click(self, event: SessionEvent, row: dict[str, Any]) -> None:
        raw_is_topup = _field(row, "is_topup", "Is_Topup")
        click = {
            "event_id": event.event_id,
            "unix_time": float(event.unix_time),
            "monotonic_time": float(event.monotonic_time),
            "in_target": _truthy(row.get("in_target", True)),
            "during_playback": _truthy(row.get("during_playback", True)),
            "block_number": _field(row, "block_number", "Block_Number"),
            "part_number": _field(row, "part_number", "Part_Number"),
            "is_topup": _truthy(raw_is_topup) if raw_is_topup not in (None, "") else None,
        }
        if not click["in_target"] or not click["during_playback"]:
            return
        if self._try_resolve_click(click):
            return
        self._unmatched_clicks.append(click)
        self._prune_unmatched_clicks(float(event.unix_time))

    def _try_resolve_from_unmatched(self, entry: TopUpLedgerEntry) -> None:
        for click in list(self._unmatched_clicks):
            if entry.status != PENDING:
                break
            if self._click_matches(entry, click):
                self._resolve_entry(entry, click)
                self._unmatched_clicks.remove(click)
                break

    def _try_resolve_click(self, click: dict[str, Any]) -> bool:
        candidates = [
            entry
            for entry in self.entries
            if entry.status in {PENDING, MISSED_NEEDS_TOPUP}
        ]
        for entry in sorted(candidates, key=lambda item: (float(item.tactile_unix_time), int(item.ledger_id))):
            if self._click_matches(entry, click):
                self._resolve_entry(entry, click)
                return True
        return False

    def _click_matches(self, entry: TopUpLedgerEntry, click: dict[str, Any]) -> bool:
        click_time = float(click["unix_time"])
        if not _same_click_context(entry, click):
            return False
        return (float(entry.tactile_unix_time) + self.min_rt_s) <= click_time <= float(entry.response_deadline_unix_time)

    def _resolve_entry(self, entry: TopUpLedgerEntry, click: dict[str, Any]) -> None:
        entry.status = HIT
        entry.click_event_id = click["event_id"]
        entry.click_unix_time = float(click["unix_time"])
        entry.click_monotonic_time = float(click["monotonic_time"])
        entry.rt_ms = (float(click["unix_time"]) - float(entry.tactile_unix_time)) * 1000.0
        entry.miss_reason = ""

    def _prune_unmatched_clicks(self, now_unix: float) -> None:
        keep_after = now_unix - (self.max_rt_s + 5.0)
        self._unmatched_clicks = [click for click in self._unmatched_clicks if float(click["unix_time"]) >= keep_after]


def write_topup_draft_manifest(session_dir: str | Path, ledger: TopUpLedger, *, part_number: int | str | None = None) -> Path:
    suffix = "" if part_number is None else f"_part{_part_key(part_number)}"
    path = Path(session_dir) / f"topup_block_manifest{suffix}_draft.json"
    payload = {
        "schema": "pps-topup-block-draft.v1",
        "part_number": "" if part_number is None else _part_key(part_number),
        "summary": ledger.summary(),
        "missed_trials": [entry.as_row() for entry in ledger.missed_entries(include_topup=False, part_number=part_number)],
    }
    os.makedirs(_output_filesystem_path(path.parent), exist_ok=True)
    with open(_output_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2))
    return path


def _event_row(event: SessionEvent) -> dict[str, Any]:
    row = event.as_flat_dict()
    row.setdefault("event_type", event.event_type)
    return row


def _field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return ""


def _is_tactile_trial(row: dict[str, Any]) -> bool:
    trial_type = str(_field(row, "trial_type", "Trial_Type") or "").strip().lower()
    family = str(_field(row, "family", "Family") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if family in {"audio_tactile", "baseline"}:
        return True
    if trial_type in {"audio-tactile", "baseline"}:
        return True
    tactile_sample = _field(row, "tactile_onset_sample", "Tactile_Onset_Sample")
    if tactile_sample not in (None, ""):
        return True
    return False


def _tactile_trial_requires_response(row: dict[str, Any]) -> bool:
    expected = _field(
        row,
        "expected_response",
        "Expected_Response",
        "response_expected",
        "Response_Expected",
        "required_response",
        "Required_Response",
        "correct_response",
        "Correct_Response",
    )
    decision = _response_expectation_decision(expected)
    if decision is not None:
        return decision
    for value in (
        _field(
            row,
            "target_role",
            "Target_Role",
            "go_nogo_role",
            "Go_NoGo_Role",
            "stimulus_role",
            "Stimulus_Role",
            "tactile_role",
            "Tactile_Role",
        ),
        _field(
            row,
            "response_rule",
            "Response_Rule",
            "response_mapping",
            "Response_Mapping",
            "task_response_rule",
            "Task_Response_Rule",
        ),
        _field(row, "trial_type", "Trial_Type"),
        _field(row, "family", "Family"),
    ):
        decision = _response_expectation_decision(value)
        if decision is not None:
            return decision
    return True


def _response_expectation_decision(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    token = "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")
    if not token:
        return None
    if token in {
        "0",
        "false",
        "no",
        "none",
        "withhold",
        "withhold_response",
        "no_response",
        "noresponse",
        "no_go",
        "nogo",
        "no_target",
        "not_target",
        "non_target",
        "nontarget",
        "strong",
        "strong_nontarget",
        "strong_non_target",
        "distractor",
    }:
        return False
    if token in {
        "1",
        "true",
        "yes",
        "respond",
        "response",
        "click",
        "button_press",
        "go",
        "target",
        "weak",
        "weak_target",
        "weak_go",
    }:
        return True
    parts = set(token.split("_"))
    has_no_marker = (
        "no_response" in token
        or "no_target" in token
        or "non_target" in token
        or "nontarget" in token
        or parts.intersection({"withhold", "nogo", "not", "none", "strong", "distractor", "nontarget"})
    )
    strong_response_marker = "respond" in parts or "click" in parts or "go" in parts or "weak" in parts
    has_response_marker = strong_response_marker or ("target" in parts and not has_no_marker)
    if has_no_marker and strong_response_marker:
        return None
    if has_no_marker:
        return False
    if has_response_marker:
        return True
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


def _same_click_context(entry: TopUpLedgerEntry, click: dict[str, Any]) -> bool:
    click_block = click.get("block_number")
    if entry.block_number not in (None, "") and click_block not in (None, ""):
        if _part_key(entry.block_number) != _part_key(click_block):
            return False
    click_part = click.get("part_number")
    if entry.part_number not in (None, "") and click_part not in (None, ""):
        if _part_key(entry.part_number) != _part_key(click_part):
            return False
    click_is_topup = click.get("is_topup")
    if click_is_topup is not None and bool(entry.is_topup) != bool(click_is_topup):
        return False
    return True


def _part_key(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except ValueError:
        return text.lower()


def _fieldnames(rows: Iterable[dict[str, Any]]) -> list[str]:
    keys = sorted({key for row in rows for key in row.keys()})
    return keys or ["empty"]
