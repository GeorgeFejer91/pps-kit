"""Event fan-out for local logs, callback-derived timing, and LSL v2 markers."""

from __future__ import annotations

import csv
import json
import os
import queue
import struct
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .session_events import SessionEvent, SessionEventLogger


MARKER_VERSION = "2.0"
LSL_STREAM_NAME = "PPSMarkersV2"
LSL_NUMERIC_STREAM_NAME = "PPSTriggerCodes"
LSL_STREAM_TYPE = "Markers"
LSL_NUMERIC_STREAM_TYPE = "TriggerCodes"
LSL_SOURCE_ID_PREFIX = "pps-markers-v2"
LSL_NUMERIC_SOURCE_ID_PREFIX = "pps-trigger-codes"
LSL_MARKER_CHANNELS = [
    "marker_version",
    "event_id",
    "event_type",
    "event_code",
    "trigger_key",
    "marker_name",
    "session_id",
    "participant_id",
    "session_group_id",
    "part_session_id",
    "part_number",
    "part_label",
    "block_index",
    "trial_uid",
    "sample_index",
    "timestamp_quality",
    "payload_json",
]
RESERVED_TRIGGER_CODES = {
    "session_start": 1,
    "session_end": 2,
    "session_error": 3,
    "block_schedule_loaded": 9,
    "block_start": 10,
    "block_end": 11,
    "recording_start": 12,
    "recording_end": 13,
    "audio_sample_zero": 20,
    "mouse_click": 30,
    "response_marker_start": 31,
    "response_marker_end": 32,
    "operator_stop": 40,
    "operator_pause": 41,
    "operator_resume": 42,
    "test_marker": 50,
    "timing_anchor_fallback": 90,
}


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if sys.platform == "win32" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _mkdir(path: str | Path) -> None:
    os.makedirs(_filesystem_path(path), exist_ok=True)


@dataclass(frozen=True)
class LSLStatus:
    available: bool
    enabled: bool
    stream_name: str = LSL_STREAM_NAME
    numeric_stream_name: str = LSL_NUMERIC_STREAM_NAME
    message: str = ""


@dataclass
class TriggerDictionary:
    """Deterministic trigger-code mapping for one participant session."""

    codes: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    _next_dynamic_code: int = 500
    _next_trial_code: int = 1000
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @classmethod
    def from_schedules(cls, schedules: Iterable[Any]) -> "TriggerDictionary":
        dictionary = cls()
        for event_type, code in RESERVED_TRIGGER_CODES.items():
            key = f"control:{event_type}"
            dictionary.codes[key] = code
            dictionary.metadata[key] = {"event_type": event_type, "reserved": True}

        trial_records: dict[str, dict[str, Any]] = {}
        for schedule in schedules:
            for event in getattr(schedule, "events", []):
                trigger_key = str(getattr(event, "trigger_key", "") or "")
                if not trigger_key.startswith("trial:"):
                    continue
                payload = dict(getattr(event, "payload", {}) or {})
                trial_records[trigger_key] = {
                    "event_type": getattr(event, "event_type", ""),
                    "session_group_id": payload.get("session_group_id", ""),
                    "part_session_id": payload.get("part_session_id", ""),
                    "part_number": payload.get("part_number", ""),
                    "part_label": payload.get("part_label", ""),
                    "block_index": payload.get("block_index", payload.get("block_number", "")),
                    "trial_index": payload.get("trial_index", payload.get("trial_number", "")),
                    "trial_uid": payload.get("trial_uid", payload.get("Trial_UID", "")),
                    "trial_type": payload.get("trial_type", payload.get("Trial_Type", "")),
                    "family": payload.get("family", payload.get("Family", "")),
                    "row_label": payload.get("row_label", payload.get("Row_Label", "")),
                    "soa_ms": payload.get("soa_ms", payload.get("SOA_ms", "")),
                    "expected_response": payload.get("expected_response", payload.get("Expected_Response", "")),
                    "response_rule": payload.get("response_rule", payload.get("Response_Rule", "")),
                    "target_role": payload.get("target_role", payload.get("Target_Role", "")),
                    "response_mode": payload.get("response_mode", payload.get("Response_Mode", "")),
                    "response_choice_set": payload.get(
                        "response_choice_set",
                        payload.get("Response_Choice_Set", ""),
                    ),
                    "correct_response": payload.get("correct_response", payload.get("Correct_Response", "")),
                    "response_scoring_policy": payload.get(
                        "response_scoring_policy",
                        payload.get("Response_Scoring_Policy", ""),
                    ),
                    "response_capture_device": payload.get(
                        "response_capture_device",
                        payload.get("Response_Capture_Device", ""),
                    ),
                    "response_input_modality": payload.get(
                        "response_input_modality",
                        payload.get("Response_Input_Modality", ""),
                    ),
                    "voice_key_enabled": payload.get(
                        "voice_key_enabled",
                        payload.get("Voice_Key_Enabled", ""),
                    ),
                    "voice_key_response_label": payload.get(
                        "voice_key_response_label",
                        payload.get("Voice_Key_Response_Label", ""),
                    ),
                    "voice_key_threshold": payload.get(
                        "voice_key_threshold",
                        payload.get("Voice_Key_Threshold", ""),
                    ),
                    "voice_key_latency_correction_ms": payload.get(
                        "voice_key_latency_correction_ms",
                        payload.get("Voice_Key_Latency_Correction_ms", ""),
                    ),
                    "tactile_stimulation_modality": payload.get(
                        "tactile_stimulation_modality",
                        payload.get("Tactile_Stimulation_Modality", ""),
                    ),
                    "tactile_calibration_method": payload.get(
                        "tactile_calibration_method",
                        payload.get("Tactile_Calibration_Method", ""),
                    ),
                    "tactile_threshold_reference": payload.get(
                        "tactile_threshold_reference",
                        payload.get("Tactile_Threshold_Reference", ""),
                    ),
                    "tactile_intensity": payload.get(
                        "tactile_intensity",
                        payload.get("Tactile_Intensity", ""),
                    ),
                    "tactile_intensity_unit": payload.get(
                        "tactile_intensity_unit",
                        payload.get("Tactile_Intensity_Unit", ""),
                    ),
                    "tactile_pulse_duration_ms": payload.get(
                        "tactile_pulse_duration_ms",
                        payload.get("Tactile_Pulse_Duration_ms", ""),
                    ),
                    "electrical_stimulator_model": payload.get(
                        "electrical_stimulator_model",
                        payload.get("Electrical_Stimulator_Model", ""),
                    ),
                    "electrical_electrode_site": payload.get(
                        "electrical_electrode_site",
                        payload.get("Electrical_Electrode_Site", ""),
                    ),
                    "spatial_coordinate_frame": payload.get(
                        "spatial_coordinate_frame",
                        payload.get("Spatial_Coordinate_Frame", ""),
                    ),
                    "body_anchor": payload.get("body_anchor", payload.get("Body_Anchor", "")),
                    "body_part": payload.get("body_part", payload.get("Body_Part", "")),
                    "body_side": payload.get("body_side", payload.get("Body_Side", "")),
                    "spatial_hemifield": payload.get(
                        "spatial_hemifield",
                        payload.get("Spatial_Hemifield", ""),
                    ),
                    "body_relative_axis": payload.get(
                        "body_relative_axis",
                        payload.get("Body_Relative_Axis", ""),
                    ),
                    "external_trigger_required": payload.get(
                        "external_trigger_required",
                        payload.get("External_Trigger_Required", ""),
                    ),
                    "external_trigger_modality": payload.get(
                        "external_trigger_modality",
                        payload.get("External_Trigger_Modality", ""),
                    ),
                    "external_trigger_role": payload.get(
                        "external_trigger_role",
                        payload.get("External_Trigger_Role", ""),
                    ),
                    "external_trigger_code": payload.get(
                        "external_trigger_code",
                        payload.get("External_Trigger_Code", ""),
                    ),
                    "external_trigger_tolerance_ms": payload.get(
                        "external_trigger_tolerance_ms",
                        payload.get("External_Trigger_Tolerance_ms", ""),
                    ),
                    "external_trigger_channel": payload.get(
                        "external_trigger_channel",
                        payload.get("External_Trigger_Channel", ""),
                    ),
                    "iti_policy": payload.get("iti_policy", payload.get("ITI_Policy", "")),
                    "iti_ms": payload.get(
                        "iti_ms",
                        payload.get("ITI_ms", payload.get("Intertrial_Interval_ms", "")),
                    ),
                    "foreperiod_ms": payload.get("foreperiod_ms", payload.get("Foreperiod_ms", "")),
                    "hazard_control_policy": payload.get(
                        "hazard_control_policy",
                        payload.get("Hazard_Control_Policy", ""),
                    ),
                    "expectancy_control_role": payload.get(
                        "expectancy_control_role",
                        payload.get("Expectancy_Control_Role", ""),
                    ),
                    "sample_index": getattr(event, "sample_index", ""),
                }

        for offset, trigger_key in enumerate(sorted(trial_records), start=0):
            dictionary.codes[trigger_key] = 1000 + offset
            dictionary.metadata[trigger_key] = trial_records[trigger_key]
        dictionary._next_trial_code = 1000 + len(trial_records)
        return dictionary

    def code_for(self, event_type: str, payload: dict[str, Any] | None = None, trigger_key: str | None = None) -> tuple[str, int]:
        payload = payload or {}
        key = str(trigger_key or payload.get("trigger_key") or "").strip() or f"control:{event_type}"
        with self._lock:
            if key in self.codes:
                return key, int(self.codes[key])
            if event_type in RESERVED_TRIGGER_CODES:
                code = int(RESERVED_TRIGGER_CODES[event_type])
            elif key.startswith("trial:"):
                code = self._next_trial_code
                self._next_trial_code += 1
            else:
                code = self._next_dynamic_code
                self._next_dynamic_code += 1
            self.codes[key] = code
            self.metadata[key] = {
                "event_type": event_type,
                "session_group_id": payload.get("session_group_id", ""),
                "part_session_id": payload.get("part_session_id", ""),
                "part_number": payload.get("part_number", ""),
                "part_label": payload.get("part_label", ""),
                "block_index": payload.get("block_index", payload.get("block_number", "")),
                "trial_index": payload.get("trial_index", payload.get("trial_number", "")),
                "trial_uid": payload.get("trial_uid", payload.get("Trial_UID", "")),
                "expected_response": payload.get("expected_response", payload.get("Expected_Response", "")),
                "response_rule": payload.get("response_rule", payload.get("Response_Rule", "")),
                "target_role": payload.get("target_role", payload.get("Target_Role", "")),
                "response_mode": payload.get("response_mode", payload.get("Response_Mode", "")),
                "response_choice_set": payload.get(
                    "response_choice_set",
                    payload.get("Response_Choice_Set", ""),
                ),
                "correct_response": payload.get("correct_response", payload.get("Correct_Response", "")),
                "response_scoring_policy": payload.get(
                    "response_scoring_policy",
                    payload.get("Response_Scoring_Policy", ""),
                ),
                "response_capture_device": payload.get(
                    "response_capture_device",
                    payload.get("Response_Capture_Device", ""),
                ),
                "response_input_modality": payload.get(
                    "response_input_modality",
                    payload.get("Response_Input_Modality", ""),
                ),
                "voice_key_enabled": payload.get(
                    "voice_key_enabled",
                    payload.get("Voice_Key_Enabled", ""),
                ),
                "voice_key_response_label": payload.get(
                    "voice_key_response_label",
                    payload.get("Voice_Key_Response_Label", ""),
                ),
                "voice_key_threshold": payload.get(
                    "voice_key_threshold",
                    payload.get("Voice_Key_Threshold", ""),
                ),
                "voice_key_latency_correction_ms": payload.get(
                    "voice_key_latency_correction_ms",
                    payload.get("Voice_Key_Latency_Correction_ms", ""),
                ),
                "tactile_stimulation_modality": payload.get(
                    "tactile_stimulation_modality",
                    payload.get("Tactile_Stimulation_Modality", ""),
                ),
                "tactile_calibration_method": payload.get(
                    "tactile_calibration_method",
                    payload.get("Tactile_Calibration_Method", ""),
                ),
                "tactile_threshold_reference": payload.get(
                    "tactile_threshold_reference",
                    payload.get("Tactile_Threshold_Reference", ""),
                ),
                "tactile_intensity": payload.get(
                    "tactile_intensity",
                    payload.get("Tactile_Intensity", ""),
                ),
                "tactile_intensity_unit": payload.get(
                    "tactile_intensity_unit",
                    payload.get("Tactile_Intensity_Unit", ""),
                ),
                "tactile_pulse_duration_ms": payload.get(
                    "tactile_pulse_duration_ms",
                    payload.get("Tactile_Pulse_Duration_ms", ""),
                ),
                "electrical_stimulator_model": payload.get(
                    "electrical_stimulator_model",
                    payload.get("Electrical_Stimulator_Model", ""),
                ),
                "electrical_electrode_site": payload.get(
                    "electrical_electrode_site",
                    payload.get("Electrical_Electrode_Site", ""),
                ),
                "spatial_coordinate_frame": payload.get(
                    "spatial_coordinate_frame",
                    payload.get("Spatial_Coordinate_Frame", ""),
                ),
                "body_anchor": payload.get("body_anchor", payload.get("Body_Anchor", "")),
                "body_part": payload.get("body_part", payload.get("Body_Part", "")),
                "body_side": payload.get("body_side", payload.get("Body_Side", "")),
                "spatial_hemifield": payload.get(
                    "spatial_hemifield",
                    payload.get("Spatial_Hemifield", ""),
                ),
                "body_relative_axis": payload.get(
                    "body_relative_axis",
                    payload.get("Body_Relative_Axis", ""),
                ),
                "external_trigger_required": payload.get(
                    "external_trigger_required",
                    payload.get("External_Trigger_Required", ""),
                ),
                "external_trigger_modality": payload.get(
                    "external_trigger_modality",
                    payload.get("External_Trigger_Modality", ""),
                ),
                "external_trigger_role": payload.get(
                    "external_trigger_role",
                    payload.get("External_Trigger_Role", ""),
                ),
                "external_trigger_code": payload.get(
                    "external_trigger_code",
                    payload.get("External_Trigger_Code", ""),
                ),
                "external_trigger_tolerance_ms": payload.get(
                    "external_trigger_tolerance_ms",
                    payload.get("External_Trigger_Tolerance_ms", ""),
                ),
                "external_trigger_channel": payload.get(
                    "external_trigger_channel",
                    payload.get("External_Trigger_Channel", ""),
                ),
                "iti_policy": payload.get("iti_policy", payload.get("ITI_Policy", "")),
                "iti_ms": payload.get(
                    "iti_ms",
                    payload.get("ITI_ms", payload.get("Intertrial_Interval_ms", "")),
                ),
                "foreperiod_ms": payload.get("foreperiod_ms", payload.get("Foreperiod_ms", "")),
                "hazard_control_policy": payload.get(
                    "hazard_control_policy",
                    payload.get("Hazard_Control_Policy", ""),
                ),
                "expectancy_control_role": payload.get(
                    "expectancy_control_role",
                    payload.get("Expectancy_Control_Role", ""),
                ),
                "sample_index": payload.get("sample_index", ""),
                "dynamic": True,
            }
            return key, code

    def write_json(
        self,
        path: str | Path,
        *,
        session_id: str = "",
        participant_id: str = "",
        session_group_id: str = "",
        part_session_id: str = "",
        part_number: str | int = "",
        part_label: str = "",
    ) -> Path:
        path = Path(path)
        payload = {
            "schema": "pps-trigger-dictionary.v1",
            "marker_version": MARKER_VERSION,
            "session_id": session_id,
            "participant_id": participant_id,
            "session_group_id": session_group_id,
            "part_session_id": part_session_id,
            "part_number": part_number,
            "part_label": part_label,
            "reserved_codes": dict(sorted(RESERVED_TRIGGER_CODES.items(), key=lambda item: item[1])),
            "triggers": [
                {
                    "trigger_key": key,
                    "event_code": int(self.codes[key]),
                    **self.metadata.get(key, {}),
                }
                for key in sorted(self.codes, key=lambda item: (self.codes[item], item))
            ],
        }
        _mkdir(path.parent)
        with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return path


class LSLMarkerOutlet:
    """Optional pylsl marker outlets with rich and numeric trigger streams."""

    def __init__(self, *, session_id: str, participant_id: str, stream_metadata: dict[str, Any] | None = None):
        self.session_id = session_id
        self.participant_id = participant_id
        self.stream_metadata = dict(stream_metadata or {})
        self.status = LSLStatus(available=False, enabled=False, message="pylsl is not installed.")
        self._outlet = None
        self._numeric_outlet = None
        self._local_clock = time.perf_counter
        try:
            from pylsl import StreamInfo, StreamOutlet, local_clock  # type: ignore
        except Exception as exc:
            self.status = LSLStatus(available=False, enabled=False, message=f"pylsl unavailable: {exc}")
            return

        try:
            self._local_clock = local_clock
            info = StreamInfo(
                LSL_STREAM_NAME,
                LSL_STREAM_TYPE,
                len(LSL_MARKER_CHANNELS),
                0,
                "string",
                f"{LSL_SOURCE_ID_PREFIX}-{session_id}",
            )
            desc = info.desc()
            desc.append_child_value("marker_version", MARKER_VERSION)
            desc.append_child_value("session_id", session_id)
            desc.append_child_value("participant_id", participant_id)
            if self.stream_metadata:
                desc.append_child_value("session_metadata_json", json.dumps(self.stream_metadata, sort_keys=True, ensure_ascii=False))
            channels = desc.append_child("channels")
            for label in LSL_MARKER_CHANNELS:
                channel = channels.append_child("channel")
                channel.append_child_value("label", label)
                channel.append_child_value("type", "Marker")
            self._outlet = StreamOutlet(info)

            numeric_info = StreamInfo(
                LSL_NUMERIC_STREAM_NAME,
                LSL_NUMERIC_STREAM_TYPE,
                1,
                0,
                "int32",
                f"{LSL_NUMERIC_SOURCE_ID_PREFIX}-{session_id}",
            )
            numeric_desc = numeric_info.desc()
            numeric_desc.append_child_value("marker_version", MARKER_VERSION)
            numeric_desc.append_child_value("session_id", session_id)
            numeric_desc.append_child_value("participant_id", participant_id)
            if self.stream_metadata:
                numeric_desc.append_child_value("session_metadata_json", json.dumps(self.stream_metadata, sort_keys=True, ensure_ascii=False))
            numeric_channels = numeric_desc.append_child("channels")
            numeric_channel = numeric_channels.append_child("channel")
            numeric_channel.append_child_value("label", "event_code")
            numeric_channel.append_child_value("type", "Trigger")
            self._numeric_outlet = StreamOutlet(numeric_info)
            self.status = LSLStatus(available=True, enabled=True, message="LSL v2 marker and trigger-code outlets active.")
        except Exception as exc:
            self.status = LSLStatus(available=True, enabled=False, message=f"Could not create LSL outlet: {exc}")

    def local_clock(self) -> float:
        try:
            return float(self._local_clock())
        except Exception:
            return time.perf_counter()

    def push(self, event: SessionEvent, marker: dict[str, Any], *, timestamp: float) -> None:
        if self._outlet is None:
            return
        payload_json = json.dumps(event.payload, sort_keys=True, ensure_ascii=False)
        sample = [
            MARKER_VERSION,
            str(event.event_id),
            event.event_type,
            str(marker.get("event_code", "")),
            str(marker.get("trigger_key", "")),
            str(marker.get("marker_name", "")),
            str(marker.get("session_id", "")),
            str(marker.get("participant_id", "")),
            str(marker.get("session_group_id", "")),
            str(marker.get("part_session_id", "")),
            str(marker.get("part_number", "")),
            str(marker.get("part_label", "")),
            str(marker.get("block_index", "")),
            str(marker.get("trial_uid", "")),
            str(marker.get("sample_index", "")),
            str(marker.get("timestamp_quality", "")),
            payload_json,
        ]
        _push_sample(self._outlet, sample, timestamp)
        if self._numeric_outlet is not None:
            _push_sample(self._numeric_outlet, [int(marker.get("event_code") or 0)], timestamp)


class TimingEventHub:
    """Fan out timing events to local logs, LSL v2 streams, and marker CSV rows."""

    def __init__(
        self,
        logger: SessionEventLogger,
        *,
        enable_lsl: bool,
        session_id: str,
        participant_id: str,
        lsl_stream_session_id: str | None = None,
        lsl_outlet: LSLMarkerOutlet | None = None,
        trigger_dictionary: TriggerDictionary | None = None,
        event_callback: Callable[[SessionEvent], None] | None = None,
        stream_metadata: dict[str, Any] | None = None,
        default_payload: dict[str, Any] | None = None,
    ):
        self.logger = logger
        self.session_id = session_id
        self.participant_id = participant_id
        self.lsl_stream_session_id = str(lsl_stream_session_id or session_id)
        self.trigger_dictionary = trigger_dictionary or TriggerDictionary.from_schedules([])
        self._event_callback = event_callback
        self.stream_metadata = dict(stream_metadata or {})
        self.default_payload = dict(default_payload or {})
        if lsl_outlet is not None:
            self.lsl = lsl_outlet
        elif enable_lsl:
            self.lsl = LSLMarkerOutlet(
                session_id=self.lsl_stream_session_id,
                participant_id=participant_id,
                stream_metadata=self.stream_metadata,
            )
        else:
            self.lsl = None
        self._marker_records: list[dict[str, Any]] = []
        self._marker_lock = threading.Lock()
        self._callback_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=4096)
        self._dropped_callback_events = 0
        self._anchor_lock = threading.Lock()
        self._sample_time_anchors: dict[str, dict[str, float]] = {}
        self._worker = threading.Thread(target=self._callback_worker, name=f"pps-marker-worker-{session_id}", daemon=True)
        self._worker.start()

    @property
    def lsl_status(self) -> LSLStatus:
        if self.lsl is None:
            return LSLStatus(available=False, enabled=False, message="LSL disabled for this run.")
        return self.lsl.status

    @property
    def marker_records(self) -> list[dict[str, Any]]:
        with self._marker_lock:
            return list(self._marker_records)

    def log(
        self,
        event_type: str,
        *,
        unix_time: float | None = None,
        monotonic_time: float | None = None,
        push_lsl: bool = True,
        **payload: Any,
    ) -> SessionEvent:
        if unix_time is None:
            unix_time = time.time()
        if monotonic_time is None:
            monotonic_time = time.perf_counter()
        for key, value in self.default_payload.items():
            payload.setdefault(key, value)
        payload.setdefault("session_id", self.session_id)
        payload.setdefault("participant_id", self.participant_id)
        lsl_timestamp = _as_float(payload.get("lsl_timestamp"), default=None)
        timestamp_quality = str(payload.get("timestamp_quality") or "software_log")
        trigger_key, event_code = self.trigger_dictionary.code_for(event_type, payload)
        payload.setdefault("trigger_key", trigger_key)
        payload.setdefault("event_code", event_code)
        payload.setdefault("marker_version", MARKER_VERSION)
        payload.setdefault("marker_name", _self_describing_marker_name(event_type, payload))
        event = self.logger.log(event_type, unix_time=unix_time, monotonic_time=monotonic_time, **payload)
        marker = self._marker_from_event(
            event,
            trigger_key=trigger_key,
            event_code=event_code,
            lsl_timestamp=lsl_timestamp,
            timestamp_quality=timestamp_quality,
        )
        if push_lsl:
            self._push_marker(event, marker)
        else:
            marker["pushed_to_lsl"] = False
        self._append_marker(marker)
        self._notify_event(event)
        return event

    def enqueue_callback_event(self, payload: dict[str, Any]) -> bool:
        """Queue one callback-derived event without doing expensive work in the callback."""

        try:
            self._callback_queue.put_nowait(dict(payload))
            return True
        except queue.Full:
            self._dropped_callback_events += 1
            return False

    def flush_callback_events(self, timeout_s: float = 2.0) -> None:
        deadline = time.time() + max(0.0, timeout_s)
        while self._callback_queue.unfinished_tasks and time.time() < deadline:
            time.sleep(0.005)

    def close(self) -> None:
        try:
            self._callback_queue.put_nowait(None)
        except queue.Full:
            pass

    def write_lsl_markers_csv(self, path: str | Path) -> Path:
        self.flush_callback_events()
        path = Path(path)
        _mkdir(path.parent)
        fieldnames = [
            "event_id",
            "event_type",
            "event_code",
            "trigger_key",
            "marker_name",
            "session_id",
            "participant_id",
            "session_group_id",
            "part_session_id",
            "part_number",
            "part_label",
            "lsl_timestamp",
            "timestamp_quality",
            "sample_index",
            "block_index",
            "trial_uid",
            "pushed_to_lsl",
            "payload_json",
        ]
        with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for marker in self.marker_records:
                writer.writerow({key: marker.get(key, "") for key in fieldnames})
        return path

    def write_lsl_markers_xdf(self, path: str | Path) -> Path:
        self.flush_callback_events()
        return write_lsl_marker_xdf(
            path,
            self.marker_records,
            session_id=self.session_id,
            participant_id=self.participant_id,
            stream_metadata=self.stream_metadata,
        )

    def write_trigger_dictionary(self, path: str | Path) -> Path:
        return self.trigger_dictionary.write_json(
            path,
            session_id=self.session_id,
            participant_id=self.participant_id,
            session_group_id=str(self.default_payload.get("session_group_id") or ""),
            part_session_id=str(self.default_payload.get("part_session_id") or ""),
            part_number=self.default_payload.get("part_number", ""),
            part_label=str(self.default_payload.get("part_label") or ""),
        )

    def push_deferred_event_marker(self, event: SessionEvent) -> None:
        """Push an already logged event marker after latency-sensitive work.

        ``log(..., push_lsl=False)`` still appends the marker record with the
        timestamp computed at log time. This method finds that record and pushes
        it later so callers can avoid placing network/LSL work in front of a
        physical response marker.
        """

        marker_index = None
        marker: dict[str, Any] | None = None
        with self._marker_lock:
            for index, record in enumerate(self._marker_records):
                if str(record.get("event_id")) == str(event.event_id):
                    marker_index = index
                    marker = dict(record)
                    break
        if marker is None:
            trigger_key, event_code = self.trigger_dictionary.code_for(event.event_type, event.payload)
            marker = self._marker_from_event(
                event,
                trigger_key=trigger_key,
                event_code=event_code,
                lsl_timestamp=_as_float((event.payload or {}).get("lsl_timestamp"), default=None),
                timestamp_quality=str((event.payload or {}).get("timestamp_quality") or "software_log"),
            )
        if marker.get("pushed_to_lsl"):
            return
        self._push_marker(event, marker)
        with self._marker_lock:
            if marker_index is None:
                self._marker_records.append(dict(marker))
            else:
                self._marker_records[marker_index] = dict(marker)

    def _callback_worker(self) -> None:
        while True:
            payload = self._callback_queue.get()
            try:
                if payload is None:
                    return
                self._process_callback_payload(payload)
            finally:
                self._callback_queue.task_done()

    def _process_callback_payload(self, payload: dict[str, Any]) -> None:
        event_type = str(payload.pop("event_type", "audio_event"))
        timestamp_info = self._callback_timestamp_info(event_type, payload)
        payload.update(timestamp_info["payload"])
        self.log(
            event_type,
            unix_time=timestamp_info["unix_time"],
            monotonic_time=timestamp_info["monotonic_time"],
            **payload,
        )

    def _callback_timestamp_info(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        sample_rate = _as_float(payload.get("sample_rate"), default=0.0) or 0.0
        sample_offset = _as_float(payload.get("sample_offset_in_buffer"), default=0.0) or 0.0
        sample_index = _as_float(payload.get("sample_index", payload.get("planned_sample_index")), default=None)
        offset_s = sample_offset / sample_rate if sample_rate > 0 else 0.0
        callback_perf = _as_float(payload.get("callback_perf_counter"), default=time.perf_counter()) or time.perf_counter()
        current_perf = time.perf_counter()
        current_unix = time.time()
        current_lsl = self._local_lsl_clock()
        perf_to_lsl_offset = current_lsl - current_perf
        stream_current = _positive_float(payload.get("stream_current_time"))
        stream_dac = _positive_float(payload.get("stream_output_buffer_dac_time"))
        if stream_dac is not None and stream_current is not None:
            event_stream_time = stream_dac + offset_s
            event_perf = event_stream_time + (callback_perf - stream_current)
            quality = "dac_time_sample_exact"
        elif stream_current is not None:
            event_stream_time = stream_current + offset_s
            event_perf = event_stream_time + (callback_perf - stream_current)
            quality = "callback_stream_time_estimated"
        else:
            event_perf = callback_perf + offset_s
            quality = "callback_perf_fallback"
        timestamp_info = {
            "unix_time": current_unix + (event_perf - current_perf),
            "monotonic_time": event_perf,
            "payload": {
                "lsl_timestamp": event_perf + perf_to_lsl_offset,
                "timestamp_quality": quality,
                "callback_sample_offset_s": offset_s,
            },
        }
        anchor_key = self._anchor_key(payload)
        if event_type == "audio_sample_zero" and sample_rate > 0:
            with self._anchor_lock:
                self._sample_time_anchors[anchor_key] = {
                    "sample_index": float(sample_index if sample_index is not None else 0.0),
                    "sample_rate": float(sample_rate),
                    "unix_time": float(timestamp_info["unix_time"]),
                    "monotonic_time": float(timestamp_info["monotonic_time"]),
                    "lsl_timestamp": float(timestamp_info["payload"]["lsl_timestamp"]),
                }
            timestamp_info["payload"]["timestamp_anchor"] = "audio_sample_zero"
            return timestamp_info

        with self._anchor_lock:
            anchor = dict(self._sample_time_anchors.get(anchor_key) or {})
        anchor_rate = float(anchor.get("sample_rate") or sample_rate or 0.0)
        if anchor and sample_index is not None and anchor_rate > 0:
            anchor_sample = float(anchor.get("sample_index") or 0.0)
            delta_s = (float(sample_index) - anchor_sample) / anchor_rate
            timestamp_info = {
                "unix_time": float(anchor["unix_time"]) + delta_s,
                "monotonic_time": float(anchor["monotonic_time"]) + delta_s,
                "payload": {
                    **timestamp_info["payload"],
                    "lsl_timestamp": float(anchor["lsl_timestamp"]) + delta_s,
                    "timestamp_quality": quality,
                    "timestamp_anchor": "audio_sample_zero",
                    "timestamp_anchor_sample_index": anchor_sample,
                    "timestamp_anchor_sample_rate": anchor_rate,
                },
            }
        return timestamp_info

    def _anchor_key(self, payload: dict[str, Any]) -> str:
        block = payload.get("block_index", payload.get("block_number", ""))
        return str(block or "default")

    def _local_lsl_clock(self) -> float:
        if self.lsl is not None:
            return self.lsl.local_clock()
        return time.perf_counter()

    def _marker_from_event(
        self,
        event: SessionEvent,
        *,
        trigger_key: str,
        event_code: int,
        lsl_timestamp: float | None,
        timestamp_quality: str,
    ) -> dict[str, Any]:
        payload = dict(event.payload or {})
        if lsl_timestamp is None:
            lsl_timestamp = self._local_lsl_clock()
        block_index = payload.get("block_index", payload.get("block_number", ""))
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "event_code": int(event_code),
            "trigger_key": trigger_key,
            "marker_name": payload.get("marker_name", ""),
            "session_id": self.session_id,
            "participant_id": self.participant_id,
            "session_group_id": payload.get("session_group_id", ""),
            "part_session_id": payload.get("part_session_id", ""),
            "part_number": payload.get("part_number", ""),
            "part_label": payload.get("part_label", ""),
            "block_index": block_index,
            "trial_uid": payload.get("trial_uid", payload.get("Trial_UID", "")),
            "sample_index": payload.get("sample_index", payload.get("planned_sample_index", "")),
            "lsl_timestamp": f"{float(lsl_timestamp):.9f}",
            "timestamp_quality": timestamp_quality,
            "payload_json": json.dumps(payload, sort_keys=True, ensure_ascii=False),
            "pushed_to_lsl": False,
        }

    def _push_marker(self, event: SessionEvent, marker: dict[str, Any]) -> None:
        if self.lsl is None or not self.lsl_status.enabled:
            marker["pushed_to_lsl"] = False
            return
        try:
            self.lsl.push(event, marker, timestamp=float(marker["lsl_timestamp"]))
            marker["pushed_to_lsl"] = True
        except Exception as exc:
            marker["pushed_to_lsl"] = False
            marker["lsl_error"] = str(exc)

    def _append_marker(self, marker: dict[str, Any]) -> None:
        with self._marker_lock:
            self._marker_records.append(dict(marker))

    def _notify_event(self, event: SessionEvent) -> None:
        if self._event_callback is None:
            return
        try:
            self._event_callback(event)
        except Exception:
            # Event listeners are observers; logging/LSL fan-out must remain the
            # primary runner contract even if an optional observer fails.
            return


def _push_sample(outlet: Any, sample: list[Any], timestamp: float) -> None:
    try:
        outlet.push_sample(sample, timestamp=timestamp)
    except TypeError:
        try:
            outlet.push_sample(sample, timestamp)
        except TypeError:
            outlet.push_sample(sample)


def _self_describing_marker_name(event_type: str, payload: dict[str, Any]) -> str:
    participant = _marker_token(payload.get("participant_id", "PXX"))
    block = _as_int(payload.get("block_index", payload.get("block_number")), default=0)
    block_label = f"block{block:02d}" if block > 0 else "blockXX"
    phase = _marker_token(
        _row_value(payload, "respiratory_phase", "Respiratory_Phase", "row_label", "Row_Label", "Row", default="")
    )
    trial_type = str(_row_value(payload, "trial_type", "Trial_Type", default="")).strip()
    family = str(_row_value(payload, "family", "Family", default="")).strip()
    modality = _marker_modality(trial_type, family)
    catch = _marker_is_catch(trial_type, family)
    noise = _marker_token(_row_value(payload, "noise_type", "Noise_Type", "noise_label", "Noise_Label", default=""))
    soa = str(_row_value(payload, "soa_ms", "SOA_ms", default="")).strip()
    suffix = {
        "trial_start": "trial_start",
        "looming_onset": "audio_start",
        "tactile_onset": "tactile_start",
        "response_window_onset": "response_window",
        "stimulus_window_onset": "start",
        "mouse_click": "response",
        "trial_end": "trial_end",
    }.get(str(event_type or ""), str(event_type or "event"))
    parts = [participant, block_label]
    if phase:
        parts.append(phase)
    if modality:
        parts.append(modality)
    if catch and "catch" not in modality:
        parts.append("catch")
    if noise:
        parts.append(noise)
    if soa and soa.lower() not in {"nan", "none"} and modality != "audio":
        parts.append(f"SOA{_marker_token(soa)}")
    parts.append(_marker_token(suffix))
    return "_".join(part for part in parts if part)


def _marker_modality(trial_type: str, family: str) -> str:
    text = f"{trial_type} {family}".strip().lower()
    if "audio" in text and "tactile" in text:
        return "audiotactile"
    if "baseline" in text or ("tactile" in text and "audio" not in text):
        return "tactile"
    if "audio" in text or "catch" in text:
        return "audio"
    return ""


def _marker_is_catch(trial_type: str, family: str) -> bool:
    text = f"{trial_type} {family}".strip().lower()
    return "catch" in text or "audio_only" in text or "audio-only" in text


def _row_value(row: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def _marker_token(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("+", "plus")
    return "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def write_lsl_marker_xdf(
    path: str | Path,
    marker_records: Iterable[dict[str, Any]],
    *,
    session_id: str = "",
    participant_id: str = "",
    stream_metadata: dict[str, Any] | None = None,
) -> Path:
    """Write local XDF streams with the same records as the PPS LSL outlets."""

    path = Path(path)
    _mkdir(path.parent)
    markers = [dict(record) for record in marker_records]
    rich_stream_id = 1
    numeric_stream_id = 2
    with open(_filesystem_path(path), "wb") as handle:
        handle.write(b"XDF:")
        _write_xdf_chunk(handle, 1, _xdf_file_header_xml())
        _write_xdf_chunk(
            handle,
            2,
            struct.pack("<I", rich_stream_id)
            + _xdf_stream_header_xml(
                name=LSL_STREAM_NAME,
                stream_type=LSL_STREAM_TYPE,
                channel_count=len(LSL_MARKER_CHANNELS),
                channel_format="string",
                source_id=f"{LSL_SOURCE_ID_PREFIX}-{session_id}",
                session_id=session_id,
                participant_id=participant_id,
                channel_labels=LSL_MARKER_CHANNELS,
                stream_metadata=stream_metadata,
            ),
        )
        _write_xdf_chunk(
            handle,
            2,
            struct.pack("<I", numeric_stream_id)
            + _xdf_stream_header_xml(
                name=LSL_NUMERIC_STREAM_NAME,
                stream_type=LSL_NUMERIC_STREAM_TYPE,
                channel_count=1,
                channel_format="int32",
                source_id=f"{LSL_NUMERIC_SOURCE_ID_PREFIX}-{session_id}",
                session_id=session_id,
                participant_id=participant_id,
                channel_labels=["event_code"],
                stream_metadata=stream_metadata,
            ),
        )
        if markers:
            _write_xdf_chunk(handle, 3, _rich_marker_samples_chunk(rich_stream_id, markers))
            _write_xdf_chunk(handle, 3, _numeric_marker_samples_chunk(numeric_stream_id, markers))
        _write_xdf_chunk(handle, 6, struct.pack("<I", rich_stream_id) + _xdf_stream_footer_xml(markers))
        _write_xdf_chunk(handle, 6, struct.pack("<I", numeric_stream_id) + _xdf_stream_footer_xml(markers))
    return path


def _xdf_file_header_xml() -> bytes:
    root = ET.Element("info")
    ET.SubElement(root, "version").text = "1.0"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _xdf_stream_header_xml(
    *,
    name: str,
    stream_type: str,
    channel_count: int,
    channel_format: str,
    source_id: str,
    session_id: str,
    participant_id: str,
    channel_labels: list[str],
    stream_metadata: dict[str, Any] | None = None,
) -> bytes:
    root = ET.Element("info")
    ET.SubElement(root, "name").text = name
    ET.SubElement(root, "type").text = stream_type
    ET.SubElement(root, "channel_count").text = str(channel_count)
    ET.SubElement(root, "nominal_srate").text = "0"
    ET.SubElement(root, "channel_format").text = channel_format
    ET.SubElement(root, "source_id").text = source_id
    ET.SubElement(root, "version").text = MARKER_VERSION
    ET.SubElement(root, "created_at").text = f"{time.time():.9f}"
    ET.SubElement(root, "uid").text = source_id
    ET.SubElement(root, "session_id").text = session_id
    desc = ET.SubElement(root, "desc")
    ET.SubElement(desc, "participant_id").text = participant_id
    ET.SubElement(desc, "marker_version").text = MARKER_VERSION
    ET.SubElement(desc, "local_recording_schema").text = "pps-local-lsl-marker-xdf.v1"
    if stream_metadata:
        ET.SubElement(desc, "session_metadata_json").text = json.dumps(stream_metadata, sort_keys=True, ensure_ascii=False)
    channels = ET.SubElement(desc, "channels")
    for label in channel_labels:
        channel = ET.SubElement(channels, "channel")
        ET.SubElement(channel, "label").text = label
        ET.SubElement(channel, "type").text = "Marker" if channel_format == "string" else "Trigger"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _xdf_stream_footer_xml(markers: list[dict[str, Any]]) -> bytes:
    root = ET.Element("info")
    timestamps = [_as_float(marker.get("lsl_timestamp"), default=None) for marker in markers]
    timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    if timestamps:
        ET.SubElement(root, "first_timestamp").text = f"{min(timestamps):.9f}"
        ET.SubElement(root, "last_timestamp").text = f"{max(timestamps):.9f}"
    ET.SubElement(root, "sample_count").text = str(len(markers))
    ET.SubElement(root, "measured_srate").text = "0"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rich_marker_samples_chunk(stream_id: int, markers: list[dict[str, Any]]) -> bytes:
    content = bytearray(struct.pack("<I", stream_id))
    content.extend(_xdf_varlen_int(len(markers)))
    for marker in markers:
        content.extend(b"\x08")
        content.extend(struct.pack("<d", _as_float(marker.get("lsl_timestamp"), default=0.0) or 0.0))
        payload_json = str(marker.get("payload_json", "") or "")
        values = [
            MARKER_VERSION,
            str(marker.get("event_id", "")),
            str(marker.get("event_type", "")),
            str(marker.get("event_code", "")),
            str(marker.get("trigger_key", "")),
            str(marker.get("marker_name", "")),
            str(marker.get("session_id", "")),
            str(marker.get("participant_id", "")),
            str(marker.get("session_group_id", "")),
            str(marker.get("part_session_id", "")),
            str(marker.get("part_number", "")),
            str(marker.get("part_label", "")),
            str(marker.get("block_index", "")),
            str(marker.get("trial_uid", "")),
            str(marker.get("sample_index", "")),
            str(marker.get("timestamp_quality", "")),
            payload_json,
        ]
        for value in values:
            content.extend(_xdf_varlen_bytes(value.encode("utf-8")))
    return bytes(content)


def _numeric_marker_samples_chunk(stream_id: int, markers: list[dict[str, Any]]) -> bytes:
    content = bytearray(struct.pack("<I", stream_id))
    content.extend(_xdf_varlen_int(len(markers)))
    for marker in markers:
        content.extend(b"\x08")
        content.extend(struct.pack("<d", _as_float(marker.get("lsl_timestamp"), default=0.0) or 0.0))
        content.extend(struct.pack("<i", int(_as_float(marker.get("event_code"), default=0.0) or 0)))
    return bytes(content)


def _write_xdf_chunk(handle: Any, tag: int, content: bytes) -> None:
    body_length = 2 + len(content)
    handle.write(_xdf_varlen_int(body_length))
    handle.write(struct.pack("<H", tag))
    handle.write(content)


def _xdf_varlen_int(value: int) -> bytes:
    if value < 0:
        raise ValueError("XDF variable-length integers cannot be negative")
    if value <= 0xFF:
        return b"\x01" + struct.pack("<B", value)
    if value <= 0xFFFFFFFF:
        return b"\x04" + struct.pack("<I", value)
    return b"\x08" + struct.pack("<Q", value)


def _xdf_varlen_bytes(data: bytes) -> bytes:
    return _xdf_varlen_int(len(data)) + data


def _positive_float(value: Any) -> float | None:
    result = _as_float(value, default=None)
    if result is None or result <= 0:
        return None
    return result


def _as_float(value: Any, *, default: float | None) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default
