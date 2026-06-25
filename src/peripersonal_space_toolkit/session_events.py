"""Session event capture and minimal XDF export for the PPS runner."""

from __future__ import annotations

import csv
import json
import math
import os
import struct
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


TRIAL_DURATION_S = 8.0
STIMULUS_SEGMENT_ONSET_S = 4.0


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if sys.platform == "win32" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _path_exists(path: str | Path) -> bool:
    try:
        return os.path.exists(_filesystem_path(path))
    except OSError:
        return False


def _mkdir(path: str | Path) -> None:
    os.makedirs(_filesystem_path(path), exist_ok=True)


@dataclass(frozen=True)
class SessionEvent:
    """One timestamped event marker."""

    event_id: int
    event_type: str
    unix_time: float
    monotonic_time: float
    payload: dict[str, Any] = field(default_factory=dict)

    def as_flat_dict(self) -> dict[str, Any]:
        row = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "unix_time": self.unix_time,
            "monotonic_time": self.monotonic_time,
        }
        row.update(self.payload)
        return row


class SessionEventLogger:
    """Thread-safe event recorder used by playback and mouse-listener threads."""

    def __init__(self, participant_id: str | None = None):
        self.participant_id = participant_id or ""
        self.session_id = str(uuid.uuid4())
        self.created_unix_time = time.time()
        self._events: list[SessionEvent] = []
        self._lock = threading.Lock()

    @property
    def events(self) -> list[SessionEvent]:
        with self._lock:
            return list(self._events)

    def log(
        self,
        event_type: str,
        *,
        unix_time: float | None = None,
        monotonic_time: float | None = None,
        **payload: Any,
    ) -> SessionEvent:
        if unix_time is None:
            unix_time = time.time()
        if monotonic_time is None:
            monotonic_time = time.perf_counter()
        if self.participant_id and "participant_id" not in payload:
            payload["participant_id"] = self.participant_id
        with self._lock:
            event = SessionEvent(
                event_id=len(self._events) + 1,
                event_type=event_type,
                unix_time=float(unix_time),
                monotonic_time=float(monotonic_time),
                payload=dict(payload),
            )
            self._events.append(event)
            return event

    def extend_planned_block_events(
        self,
        block_path: str | Path,
        *,
        block_start_unix: float,
        block_start_monotonic: float,
        participant_id: str,
        part_number: int,
        block_number: int,
        trial_duration_s: float = TRIAL_DURATION_S,
        stimulus_segment_onset_s: float = STIMULUS_SEGMENT_ONSET_S,
    ) -> int:
        rows = load_block_manifest(block_path)
        if not rows:
            return 0

        block_path = Path(block_path)
        manifest_path = derive_manifest_path(block_path)
        count = 0
        for index, row in enumerate(rows, start=1):
            trial_number = _coerce_int(row.get("Trial_Number"), default=index)
            trial_start_s = _coerce_float(row.get("Trial_Start_S"), default=(trial_number - 1) * trial_duration_s)
            current_trial_duration_s = _coerce_float(row.get("Trial_Duration_S"), default=trial_duration_s)
            trial_end_s = _coerce_float(row.get("Trial_End_S"), default=trial_start_s + current_trial_duration_s)
            common = _trial_payload(
                row,
                participant_id=participant_id,
                part_number=part_number,
                block_number=block_number,
                block_path=block_path,
                manifest_path=manifest_path,
                trial_number=trial_number,
            )
            count += self._log_planned(
                "trial_start",
                block_start_unix,
                block_start_monotonic,
                trial_start_s,
                relative_time_s=trial_start_s,
                **common,
            )

            trial_type = str(row.get("Trial_Type", "")).strip()
            soa_ms = _coerce_float(row.get("SOA_ms"), default=0.0)
            looming_relative_s = _coerce_float(row.get("Looming_Onset_S"), default=stimulus_segment_onset_s)
            tactile_relative_s = _coerce_float(row.get("Tactile_Onset_S"), default=stimulus_segment_onset_s + (soa_ms / 1000.0))
            response_relative_s = _coerce_float(row.get("Response_Window_Onset_S"), default=looming_relative_s)
            if trial_type in {"Audio-Tactile", "Catch"}:
                count += self._log_planned(
                    "looming_onset",
                    block_start_unix,
                    block_start_monotonic,
                    trial_start_s + looming_relative_s,
                    relative_time_s=trial_start_s + looming_relative_s,
                    stimulus_modality="audio",
                    planned_sample_index=row.get("Looming_Onset_Sample", ""),
                    **common,
                )
            if trial_type in {"Audio-Tactile", "Baseline"}:
                tactile_onset_s = trial_start_s + tactile_relative_s
                count += self._log_planned(
                    "tactile_onset",
                    block_start_unix,
                    block_start_monotonic,
                    tactile_onset_s,
                    relative_time_s=tactile_onset_s,
                    stimulus_modality="tactile",
                    planned_sample_index=row.get("Tactile_Onset_Sample", ""),
                    **common,
                )
            count += self._log_planned(
                "stimulus_window_onset",
                block_start_unix,
                block_start_monotonic,
                trial_start_s + response_relative_s,
                relative_time_s=trial_start_s + response_relative_s,
                stimulus_modality=("audio+tactile" if trial_type == "Audio-Tactile" else trial_type.lower()),
                planned_sample_index=row.get("Response_Window_Onset_Sample", ""),
                **common,
            )
            count += self._log_planned(
                "response_window_onset",
                block_start_unix,
                block_start_monotonic,
                trial_start_s + response_relative_s,
                relative_time_s=trial_start_s + response_relative_s,
                planned_sample_index=row.get("Response_Window_Onset_Sample", ""),
                **common,
            )
            count += self._log_planned(
                "trial_end",
                block_start_unix,
                block_start_monotonic,
                trial_end_s,
                relative_time_s=trial_end_s,
                planned_sample_index=row.get("Trial_End_Sample", ""),
                **common,
            )
        return count

    def _log_planned(
        self,
        event_type: str,
        block_start_unix: float,
        block_start_monotonic: float,
        offset_s: float,
        **payload: Any,
    ) -> int:
        self.log(
            event_type,
            unix_time=block_start_unix + offset_s,
            monotonic_time=block_start_monotonic + offset_s,
            planned=True,
            timestamp_quality="block_anchor_fallback",
            **payload,
        )
        return 1

    def write_csv(self, path: str | Path) -> Path:
        path = Path(path)
        _mkdir(path.parent)
        with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["event_id", "event_type", "unix_time", "monotonic_time", "payload_json"],
            )
            writer.writeheader()
            for event in sorted(self.events, key=lambda item: (item.unix_time, item.event_id)):
                writer.writerow(
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "unix_time": f"{event.unix_time:.9f}",
                        "monotonic_time": f"{event.monotonic_time:.9f}",
                        "payload_json": json.dumps(event.payload, sort_keys=True, ensure_ascii=False),
                    }
                )
        return path

    def write_xdf(self, path: str | Path, *, metadata: dict[str, Any] | None = None) -> Path:
        path = Path(path)
        _mkdir(path.parent)
        events = sorted(self.events, key=lambda item: (item.unix_time, item.event_id))
        metadata = dict(metadata or {})
        metadata.setdefault("participant_id", self.participant_id)
        metadata.setdefault("session_id", self.session_id)
        metadata.setdefault("created_unix_time", self.created_unix_time)
        write_event_xdf(path, events, metadata=metadata)
        return path


def derive_manifest_path(block_path: str | Path) -> Path:
    block_path = Path(block_path)
    candidates = []
    if block_path.name.endswith("_concatenated.wav"):
        candidates.append(block_path.with_name(block_path.name.replace("_concatenated.wav", ".csv")))
    candidates.append(block_path.with_suffix(".csv"))
    for candidate in candidates:
        if _path_exists(candidate):
            return candidate
    return candidates[0]


def load_block_manifest(block_path: str | Path) -> list[dict[str, str]]:
    manifest_path = derive_manifest_path(block_path)
    if not _path_exists(manifest_path):
        return []
    with open(_filesystem_path(manifest_path), newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_event_xdf(path: str | Path, events: Iterable[SessionEvent], *, metadata: dict[str, Any] | None = None) -> Path:
    """Write a minimal XDF 1.x file containing one irregular marker stream."""

    path = Path(path)
    events = list(events)
    metadata = dict(metadata or {})
    stream_id = 1
    _mkdir(path.parent)
    with open(_filesystem_path(path), "wb") as f:
        f.write(b"XDF:")
        _write_chunk(f, 1, _file_header_xml())
        _write_chunk(f, 2, struct.pack("<I", stream_id) + _stream_header_xml(metadata))
        if events:
            _write_chunk(f, 3, _samples_chunk_content(stream_id, events))
        _write_chunk(f, 6, struct.pack("<I", stream_id) + _stream_footer_xml(events))
    return path


def _file_header_xml() -> bytes:
    root = ET.Element("info")
    ET.SubElement(root, "version").text = "1.0"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _stream_header_xml(metadata: dict[str, Any]) -> bytes:
    root = ET.Element("info")
    ET.SubElement(root, "name").text = "PPSExperimentEvents"
    ET.SubElement(root, "type").text = "Markers"
    ET.SubElement(root, "channel_count").text = "3"
    ET.SubElement(root, "nominal_srate").text = "0"
    ET.SubElement(root, "channel_format").text = "string"
    ET.SubElement(root, "source_id").text = str(metadata.get("session_id", "pps-session"))
    ET.SubElement(root, "version").text = "1.0"
    ET.SubElement(root, "created_at").text = str(metadata.get("created_unix_time", ""))
    ET.SubElement(root, "uid").text = str(metadata.get("session_id", ""))
    ET.SubElement(root, "session_id").text = str(metadata.get("session_id", ""))
    desc = ET.SubElement(root, "desc")
    ET.SubElement(desc, "participant_id").text = str(metadata.get("participant_id", ""))
    ET.SubElement(desc, "payload_schema").text = "JSON payload with block, trial, stimulus, click, and UI-state fields."
    channels = ET.SubElement(desc, "channels")
    for label in ("event_type", "event_id", "payload_json"):
        channel = ET.SubElement(channels, "channel")
        ET.SubElement(channel, "label").text = label
        ET.SubElement(channel, "type").text = "Marker"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _stream_footer_xml(events: list[SessionEvent]) -> bytes:
    root = ET.Element("info")
    if events:
        ordered = sorted(events, key=lambda item: (item.unix_time, item.event_id))
        ET.SubElement(root, "first_timestamp").text = f"{ordered[0].unix_time:.9f}"
        ET.SubElement(root, "last_timestamp").text = f"{ordered[-1].unix_time:.9f}"
    ET.SubElement(root, "sample_count").text = str(len(events))
    ET.SubElement(root, "measured_srate").text = "0"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _samples_chunk_content(stream_id: int, events: list[SessionEvent]) -> bytes:
    content = bytearray(struct.pack("<I", stream_id))
    content.extend(_varlen_int(len(events)))
    for event in sorted(events, key=lambda item: (item.unix_time, item.event_id)):
        content.extend(b"\x08")
        content.extend(struct.pack("<d", event.unix_time))
        payload_json = json.dumps(event.payload, sort_keys=True, ensure_ascii=False)
        for value in (event.event_type, str(event.event_id), payload_json):
            content.extend(_varlen_bytes(value.encode("utf-8")))
    return bytes(content)


def _write_chunk(handle, tag: int, content: bytes) -> None:
    body_length = 2 + len(content)
    handle.write(_varlen_int(body_length))
    handle.write(struct.pack("<H", tag))
    handle.write(content)


def _varlen_int(value: int) -> bytes:
    if value < 0:
        raise ValueError("XDF variable-length integers cannot be negative")
    if value <= 0xFF:
        return b"\x01" + struct.pack("<B", value)
    if value <= 0xFFFFFFFF:
        return b"\x04" + struct.pack("<I", value)
    return b"\x08" + struct.pack("<Q", value)


def _varlen_bytes(data: bytes) -> bytes:
    return _varlen_int(len(data)) + data


def _trial_payload(
    row: dict[str, Any],
    *,
    participant_id: str,
    part_number: int,
    block_number: int,
    block_path: Path,
    manifest_path: Path,
    trial_number: int,
) -> dict[str, Any]:
    payload = {
        "participant_id": participant_id,
        "part_number": part_number,
        "condition": f"Part {part_number}",
        "block_number": block_number,
        "block_path": str(block_path),
        "manifest_path": str(manifest_path),
        "trial_number": trial_number,
    }
    for key, value in row.items():
        payload[key] = value
        normalized = _normalize_key(key)
        if normalized and normalized not in payload:
            payload[normalized] = value
    return payload


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_")


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, *, default: float) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default
