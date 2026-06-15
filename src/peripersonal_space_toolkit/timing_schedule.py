"""Sample-based block event schedules for PPS runner playback."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ScheduledBlockEvent:
    event_type: str
    sample_index: int
    trigger_key: str
    payload: dict[str, Any] = field(default_factory=dict)


class BlockEventSchedule:
    """Runtime cursor over sample-indexed events for one block WAV."""

    def __init__(self, events: Iterable[ScheduledBlockEvent]):
        self.events = sorted(
            list(events),
            key=lambda event: (
                int(event.sample_index),
                _event_priority(event.event_type),
                str(event.trigger_key),
            ),
        )
        self._cursor = 0

    def __len__(self) -> int:
        return len(self.events)

    def reset(self) -> None:
        self._cursor = 0

    def consume_buffer(self, buffer_start_sample: int, frame_count: int) -> list[ScheduledBlockEvent]:
        """Return events in [buffer_start_sample, buffer_start_sample + frame_count)."""

        if frame_count <= 0 or self._cursor >= len(self.events):
            return []
        buffer_start_sample = max(0, int(buffer_start_sample))
        buffer_end_sample = buffer_start_sample + int(frame_count)
        while self._cursor < len(self.events) and self.events[self._cursor].sample_index < buffer_start_sample:
            self._cursor += 1
        due: list[ScheduledBlockEvent] = []
        while self._cursor < len(self.events):
            event = self.events[self._cursor]
            if event.sample_index >= buffer_end_sample:
                break
            due.append(event)
            self._cursor += 1
        return due

    @classmethod
    def from_block_manifest(
        cls,
        manifest_path: str | Path,
        *,
        block_index: int,
        block_label: str = "",
        block_wav_path: str | Path | None = None,
        participant_id: str = "",
        session_id: str = "",
        part_number: int | str = "",
        sample_rate: int = 0,
        block_metadata: dict[str, Any] | None = None,
        trial_duration_s: float = 8.0,
        stimulus_segment_onset_s: float = 4.0,
    ) -> "BlockEventSchedule":
        path = Path(manifest_path)
        rows = _read_rows(path)
        metadata = dict(block_metadata or {})
        events: list[ScheduledBlockEvent] = [
            ScheduledBlockEvent(
                event_type="audio_sample_zero",
                sample_index=0,
                trigger_key="control:audio_sample_zero",
                payload={
                    "participant_id": participant_id,
                    "session_id": session_id,
                    "part_number": part_number,
                    "block_number": block_index,
                    "block_index": block_index,
                    "block_label": block_label,
                    "block_path": str(block_wav_path or ""),
                    "manifest_path": str(path),
                    "scheduled_from": "block_event_schedule",
                    **_block_metadata_payload(metadata),
                },
            )
        ]
        inferred_sample_rate = _infer_sample_rate(rows, sample_rate)
        for fallback_index, row in enumerate(rows, start=1):
            trial_number = _as_int(_row_value(row, "Trial_Number", "trial_number"), default=fallback_index)
            trial_uid = str(_row_value(row, "Trial_UID", "trial_uid", default=f"B{block_index:02d}_T{trial_number:03d}"))
            trial_type = str(_row_value(row, "Trial_Type", "trial_type", default="")).strip()
            soa_ms = _as_float(_row_value(row, "SOA_ms", "soa_ms", default=0), default=0.0)
            trial_start_default = int(round((trial_number - 1) * max(0.0, trial_duration_s) * inferred_sample_rate)) if inferred_sample_rate else None
            trial_start_sample = _sample_index(
                row,
                ("Trial_Start_Sample", "trial_start_sample"),
                ("Trial_Start_S", "trial_start_s"),
                inferred_sample_rate,
                default_sample=trial_start_default,
            )
            trial_end_default = (
                trial_start_sample + int(round(max(0.0, trial_duration_s) * inferred_sample_rate))
                if trial_start_sample is not None and inferred_sample_rate
                else None
            )
            looming_default = (
                trial_start_sample + int(round(max(0.0, stimulus_segment_onset_s) * inferred_sample_rate))
                if trial_start_sample is not None and inferred_sample_rate and trial_type in {"Audio-Tactile", "Catch"}
                else None
            )
            tactile_default = (
                trial_start_sample + int(round((max(0.0, stimulus_segment_onset_s) + (soa_ms / 1000.0)) * inferred_sample_rate))
                if trial_start_sample is not None and inferred_sample_rate and trial_type in {"Audio-Tactile", "Baseline"}
                else None
            )
            response_default = looming_default if trial_type in {"Audio-Tactile", "Catch"} else tactile_default
            common = _trial_payload(
                row,
                participant_id=participant_id,
                session_id=session_id,
                part_number=part_number,
                block_index=block_index,
                block_label=block_label,
                block_wav_path=str(block_wav_path or ""),
                manifest_path=str(path),
                trial_number=trial_number,
                trial_uid=trial_uid,
                metadata=metadata,
            )
            for event_type, sample_keys, second_keys, default_sample in (
                ("trial_start", ("Trial_Start_Sample", "trial_start_sample"), ("Trial_Start_S", "trial_start_s"), trial_start_sample),
                ("looming_onset", ("Looming_Onset_Sample", "looming_onset_sample"), ("Looming_Onset_S", "looming_onset_s"), looming_default),
                ("tactile_onset", ("Tactile_Onset_Sample", "tactile_onset_sample"), ("Tactile_Onset_S", "tactile_onset_s"), tactile_default),
                (
                    "response_window_onset",
                    ("Response_Window_Onset_Sample", "response_window_onset_sample"),
                    ("Response_Window_Onset_S", "response_window_onset_s"),
                    response_default,
                ),
                ("trial_end", ("Trial_End_Sample", "trial_end_sample"), ("Trial_End_S", "trial_end_s"), trial_end_default),
            ):
                sample_index = _sample_index(row, sample_keys, second_keys, inferred_sample_rate, default_sample=default_sample)
                if sample_index is None:
                    continue
                payload = dict(common)
                payload["relative_time_s"] = sample_index / inferred_sample_rate if inferred_sample_rate > 0 else ""
                payload["planned_sample_index"] = sample_index
                payload["stimulus_modality"] = _stimulus_modality(event_type, str(common.get("Trial_Type") or common.get("trial_type") or ""))
                events.append(
                    ScheduledBlockEvent(
                        event_type=event_type,
                        sample_index=sample_index,
                        trigger_key=f"trial:{block_index:02d}:{trial_number:03d}:{trial_uid}:{event_type}",
                        payload=payload,
                    )
                )
        return cls(events)


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _event_priority(event_type: str) -> int:
    order = {
        "audio_sample_zero": 0,
        "trial_start": 10,
        "looming_onset": 20,
        "tactile_onset": 30,
        "response_window_onset": 40,
        "trial_end": 50,
    }
    return order.get(event_type, 100)


def _trial_payload(
    row: dict[str, Any],
    *,
    participant_id: str,
    session_id: str,
    part_number: int | str,
    block_index: int,
    block_label: str,
    block_wav_path: str,
    manifest_path: str,
    trial_number: int,
    trial_uid: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "participant_id": participant_id,
        "session_id": session_id,
        "part_number": part_number,
        "block_number": block_index,
        "block_index": block_index,
        "block_label": block_label,
        "block_path": block_wav_path,
        "manifest_path": manifest_path,
        "trial_number": trial_number,
        "trial_index": trial_number,
        "trial_uid": trial_uid,
        "scheduled_from": "block_event_schedule",
        **_block_metadata_payload(metadata),
    }
    for key, value in row.items():
        payload[key] = value
        normalized = _normalize_key(key)
        if normalized and normalized not in payload:
            payload[normalized] = value
    payload.setdefault("trial_type", payload.get("Trial_Type", ""))
    payload.setdefault("family", payload.get("Family", ""))
    payload.setdefault("row_label", payload.get("Row_Label", payload.get("Row", "")))
    payload.setdefault("soa_ms", payload.get("SOA_ms", ""))
    return payload


def _block_metadata_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        f"block_{key}": value
        for key, value in metadata.items()
        if isinstance(key, str) and key and isinstance(value, (str, int, float, bool))
    }


def _normalize_key(key: str) -> str:
    return str(key).strip().lower().replace(" ", "_")


def _row_value(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def _sample_index(
    row: dict[str, Any],
    sample_keys: tuple[str, ...],
    second_keys: tuple[str, ...],
    sample_rate: int,
    *,
    default_sample: int | None = None,
) -> int | None:
    sample_value = _row_value(row, *sample_keys, default="")
    if sample_value not in (None, ""):
        sample = _as_int(sample_value, default=-1)
        return sample if sample >= 0 else None
    seconds_value = _row_value(row, *second_keys, default="")
    if seconds_value in (None, "") or sample_rate <= 0:
        return default_sample
    seconds = _as_float(seconds_value, default=math.nan)
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return int(round(seconds * sample_rate))


def _infer_sample_rate(rows: list[dict[str, Any]], fallback: int) -> int:
    if fallback > 0:
        return int(fallback)
    for row in rows:
        value = _as_int(_row_value(row, "Sample_Rate_Hz", "sample_rate_hz"), default=0)
        if value > 0:
            return value
    return 0


def _stimulus_modality(event_type: str, trial_type: str) -> str:
    if event_type == "looming_onset":
        return "audio"
    if event_type == "tactile_onset":
        return "tactile"
    if event_type in {"response_window_onset", "trial_start", "trial_end"}:
        text = trial_type.strip().lower()
        return "audio+tactile" if text == "audio-tactile" else text
    return ""


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, *, default: float) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default
