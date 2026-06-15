from __future__ import annotations

import csv
import sys
import types
from pathlib import Path

import pytest

from peripersonal_space_toolkit.session_events import SessionEventLogger
from peripersonal_space_toolkit.timing_events import LSL_STREAM_NAME, LSL_NUMERIC_STREAM_NAME, TimingEventHub
from peripersonal_space_toolkit.timing_schedule import BlockEventSchedule, ScheduledBlockEvent


class _FakeDesc:
    def append_child_value(self, _key, _value):
        return self

    def append_child(self, _key):
        return self


class _FakeStreamInfo:
    def __init__(self, *args):
        self.args = args
        self._desc = _FakeDesc()

    def desc(self):
        return self._desc


class _FakeStreamOutlet:
    instances = []

    def __init__(self, info):
        self.info = info
        self.samples = []
        _FakeStreamOutlet.instances.append(self)

    def push_sample(self, sample, timestamp=0.0):
        self.samples.append((sample, timestamp))


def _fake_pylsl():
    return types.SimpleNamespace(
        StreamInfo=_FakeStreamInfo,
        StreamOutlet=_FakeStreamOutlet,
        local_clock=lambda: 1000.0,
    )


def test_timing_event_hub_fans_out_to_logger_and_dual_lsl(monkeypatch):
    _FakeStreamOutlet.instances.clear()
    monkeypatch.setitem(sys.modules, "pylsl", _fake_pylsl())
    logger = SessionEventLogger("P001")
    hub = TimingEventHub(logger, enable_lsl=True, session_id="S001", participant_id="P001")

    event = hub.log("mouse_click", x=10, y=20)

    assert hub.lsl_status.enabled
    assert logger.events == [event]
    assert len(_FakeStreamOutlet.instances) == 2
    rich, numeric = _FakeStreamOutlet.instances
    assert rich.info.args[0] == LSL_STREAM_NAME
    assert numeric.info.args[0] == LSL_NUMERIC_STREAM_NAME
    assert rich.samples[0][0][2] == "mouse_click"
    assert rich.samples[0][0][3] == "30"
    assert rich.samples[0][0][10] == "software_log"
    assert numeric.samples[0][0] == [30]
    assert rich.samples[0][1] == pytest.approx(1000.0)


def test_timing_event_hub_can_defer_lsl_push_until_after_latency_sensitive_work(monkeypatch):
    _FakeStreamOutlet.instances.clear()
    monkeypatch.setitem(sys.modules, "pylsl", _fake_pylsl())
    logger = SessionEventLogger("P001")
    hub = TimingEventHub(logger, enable_lsl=True, session_id="S001", participant_id="P001")

    event = hub.log("mouse_click", x=10, y=20, push_lsl=False)

    assert not _FakeStreamOutlet.instances[0].samples
    assert hub.marker_records[0]["pushed_to_lsl"] is False

    hub.push_deferred_event_marker(event)

    rich, numeric = _FakeStreamOutlet.instances
    assert rich.samples[0][0][1] == str(event.event_id)
    assert rich.samples[0][0][2] == "mouse_click"
    assert numeric.samples[0][0] == [30]
    assert hub.marker_records[0]["pushed_to_lsl"] is True


def test_timing_event_hub_keeps_running_without_pylsl(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "pylsl", None)
    logger = SessionEventLogger("P001")
    hub = TimingEventHub(logger, enable_lsl=True, session_id="S001", participant_id="P001")

    event = hub.log("session_start")
    marker_csv = hub.write_lsl_markers_csv(tmp_path / "lsl_markers.csv")

    assert not hub.lsl_status.enabled
    assert logger.events == [event]
    rows = list(csv.DictReader(marker_csv.open(encoding="utf-8")))
    assert rows[0]["event_type"] == "session_start"
    assert rows[0]["pushed_to_lsl"] == "False"


def test_timing_event_hub_writes_local_lsl_marker_xdf(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "pylsl", None)
    logger = SessionEventLogger("P001")
    hub = TimingEventHub(logger, enable_lsl=True, session_id="S001", participant_id="P001")

    hub.log("trial_start", block_index=1, trial_uid="T001", sample_index=100, lsl_timestamp=123.5)
    hub.log("tactile_onset", block_index=1, trial_uid="T001", sample_index=150, lsl_timestamp=123.55)
    marker_xdf = hub.write_lsl_markers_xdf(tmp_path / "lsl_markers.xdf")

    assert marker_xdf.exists()
    assert marker_xdf.read_bytes().startswith(b"XDF:")
    try:
        import pyxdf  # type: ignore
    except Exception:
        return
    streams, _header = pyxdf.load_xdf(str(marker_xdf))
    names = sorted(str((stream.get("info") or {}).get("name", [""])[0]) for stream in streams)
    assert names == sorted([LSL_NUMERIC_STREAM_NAME, LSL_STREAM_NAME])


def test_timing_event_hub_writes_stream_metadata_to_local_xdf(monkeypatch, tmp_path: Path):
    monkeypatch.setitem(sys.modules, "pylsl", None)
    logger = SessionEventLogger("P001")
    hub = TimingEventHub(
        logger,
        enable_lsl=True,
        session_id="S001",
        participant_id="P001",
        stream_metadata={"participant": {"lsl_identity": "PPS-ABC"}},
    )

    hub.log("session_start", lsl_timestamp=1.0)
    marker_xdf = hub.write_lsl_markers_xdf(tmp_path / "lsl_markers.xdf")

    assert b"session_metadata_json" in marker_xdf.read_bytes()
    assert b"PPS-ABC" in marker_xdf.read_bytes()


def test_callback_event_uses_dac_time_for_sample_exact_timestamp(monkeypatch):
    monkeypatch.setitem(sys.modules, "pylsl", _fake_pylsl())
    logger = SessionEventLogger("P001")
    hub = TimingEventHub(logger, enable_lsl=True, session_id="S001", participant_id="P001")

    hub.enqueue_callback_event(
        {
            "event_type": "tactile_onset",
            "sample_rate": 1000,
            "sample_offset_in_buffer": 10,
            "callback_perf_counter": 100.0,
            "stream_current_time": 50.0,
            "stream_output_buffer_dac_time": 50.1,
            "block_index": 1,
            "trial_uid": "P001_single_B01_T001",
            "trigger_key": "trial:01:001:P001_single_B01_T001:tactile_onset",
        }
    )
    hub.flush_callback_events()

    event = logger.events[0]
    assert event.event_type == "tactile_onset"
    assert event.monotonic_time == pytest.approx(100.11)
    assert event.payload["timestamp_quality"] == "dac_time_sample_exact"
    assert hub.marker_records[0]["timestamp_quality"] == "dac_time_sample_exact"


def test_callback_events_after_audio_zero_use_sample_anchor(monkeypatch):
    monkeypatch.setitem(sys.modules, "pylsl", _fake_pylsl())
    logger = SessionEventLogger("P001")
    hub = TimingEventHub(logger, enable_lsl=True, session_id="S001", participant_id="P001")

    hub.enqueue_callback_event(
        {
            "event_type": "audio_sample_zero",
            "sample_index": 0,
            "sample_rate": 1000,
            "sample_offset_in_buffer": 0,
            "callback_perf_counter": 100.0,
            "stream_current_time": 50.0,
            "stream_output_buffer_dac_time": 50.1,
            "block_index": 1,
        }
    )
    hub.enqueue_callback_event(
        {
            "event_type": "tactile_onset",
            "sample_index": 10000,
            "sample_rate": 1000,
            "sample_offset_in_buffer": 10,
            "callback_perf_counter": 110.0,
            "stream_current_time": 60.0,
            "stream_output_buffer_dac_time": 60.5,
            "block_index": 1,
            "trial_uid": "P001_single_B01_T001",
            "trigger_key": "trial:01:001:P001_single_B01_T001:tactile_onset",
        }
    )
    hub.flush_callback_events()

    zero, tactile = logger.events
    assert tactile.monotonic_time - zero.monotonic_time == pytest.approx(10.0)
    assert tactile.payload["lsl_timestamp"] - zero.payload["lsl_timestamp"] == pytest.approx(10.0)
    assert tactile.payload["timestamp_anchor"] == "audio_sample_zero"


def test_callback_event_timestamp_fallback_quality(monkeypatch):
    monkeypatch.setitem(sys.modules, "pylsl", None)
    logger = SessionEventLogger("P001")
    hub = TimingEventHub(logger, enable_lsl=True, session_id="S001", participant_id="P001")

    hub.enqueue_callback_event(
        {
            "event_type": "looming_onset",
            "sample_rate": 1000,
            "sample_offset_in_buffer": 10,
            "callback_perf_counter": 100.0,
            "stream_current_time": 50.0,
        }
    )
    hub.enqueue_callback_event(
        {
            "event_type": "trial_end",
            "sample_rate": 1000,
            "sample_offset_in_buffer": 20,
            "callback_perf_counter": 200.0,
        }
    )
    hub.flush_callback_events()

    assert logger.events[0].monotonic_time == pytest.approx(100.01)
    assert logger.events[0].payload["timestamp_quality"] == "callback_stream_time_estimated"
    assert logger.events[1].monotonic_time == pytest.approx(200.02)
    assert logger.events[1].payload["timestamp_quality"] == "callback_perf_fallback"


def test_block_event_schedule_reads_sample_columns(tmp_path: Path):
    manifest = tmp_path / "block.csv"
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Trial_Number",
                "Trial_UID",
                "Trial_Type",
                "Family",
                "Row_Label",
                "SOA_ms",
                "Trial_Start_Sample",
                "Looming_Onset_Sample",
                "Tactile_Onset_Sample",
                "Response_Window_Onset_Sample",
                "Trial_End_Sample",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Trial_Number": 1,
                "Trial_UID": "P001_single_B01_T001",
                "Trial_Type": "Audio-Tactile",
                "Family": "audio_tactile",
                "Row_Label": "Inhale",
                "SOA_ms": 10,
                "Trial_Start_Sample": 0,
                "Looming_Onset_Sample": 400,
                "Tactile_Onset_Sample": 410,
                "Response_Window_Onset_Sample": 400,
                "Trial_End_Sample": 800,
            }
        )

    schedule = BlockEventSchedule.from_block_manifest(
        manifest,
        block_index=1,
        block_label="Block 01",
        participant_id="P001",
        session_id="S001",
        sample_rate=100,
    )

    assert [event.event_type for event in schedule.events[:3]] == ["audio_sample_zero", "trial_start", "looming_onset"]
    assert [event.sample_index for event in schedule.consume_buffer(0, 401)] == [0, 0, 400, 400]
    assert schedule.consume_buffer(401, 10)[0].event_type == "tactile_onset"


def test_block_event_schedule_can_flush_final_boundary_event():
    schedule = BlockEventSchedule(
        [
            ScheduledBlockEvent("trial_end", 100, "trial:boundary:end"),
        ]
    )

    assert schedule.consume_buffer(0, 100) == []
    due = schedule.consume_buffer(100, 1)

    assert len(due) == 1
    assert due[0].event_type == "trial_end"
