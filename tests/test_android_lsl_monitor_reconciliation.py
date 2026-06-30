from __future__ import annotations

import csv
import importlib.util
import json
import sys
import types
from pathlib import Path

from peripersonal_space_toolkit import android_lsl_monitor as monitor
from peripersonal_space_toolkit.lsl_command_ack import LSLCommandAck, LSLCommandSignal, ack_to_sample, command_to_sample
from peripersonal_space_toolkit.timing_events import LSL_MARKER_CHANNELS, MARKER_VERSION


SCRIPT_PATH = Path("validation_protocols/scripts/reconcile_android_lsl_monitor_with_phone_run.py")
spec = importlib.util.spec_from_file_location("reconcile_android_lsl_monitor_with_phone_run", SCRIPT_PATH)
assert spec and spec.loader
reconciler = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reconciler
spec.loader.exec_module(reconciler)


def test_reconcile_android_lsl_monitor_accepts_matching_marker_and_trigger_rows():
    phone_markers = [
        _phone_marker(event_id="1", event_type="session_metadata", event_code="8"),
        _phone_marker(event_id="2", event_type="block_start", event_code="10"),
    ]
    monitor_rows = [
        _monitor_rich_row(phone_markers[0], timestamp=1.0),
        _monitor_numeric_row(8, timestamp=1.0),
        _monitor_rich_row(phone_markers[1], timestamp=2.0),
        _monitor_numeric_row(10, timestamp=2.0),
        _monitor_ack_row(command_id="cmd-1"),
    ]

    result = reconciler.reconcile_android_lsl_monitor(
        phone_markers,
        monitor_rows,
        expect_numeric_triggers=True,
        expect_command_acks=True,
    )

    assert result.ok is True
    assert result.report["compared_event_count"] == 2
    assert result.report["numeric_trigger_summary"]["sequence_matches_phone_markers"] is True
    assert result.report["command_ack_summary"]["ack_count"] == 1


def test_reconcile_android_lsl_monitor_reports_missing_rich_marker():
    phone_markers = [
        _phone_marker(event_id="1", event_type="session_metadata", event_code="8"),
        _phone_marker(event_id="2", event_type="block_start", event_code="10"),
    ]
    monitor_rows = [_monitor_rich_row(phone_markers[0], timestamp=1.0)]

    result = reconciler.reconcile_android_lsl_monitor(phone_markers, monitor_rows)

    assert result.ok is False
    assert result.report["missing_event_ids"] == ["2"]
    assert "missing 1 phone marker" in "\n".join(result.report["failures"])


def test_reconcile_android_lsl_monitor_reports_numeric_sequence_drift():
    phone_markers = [
        _phone_marker(event_id="1", event_type="session_metadata", event_code="8"),
        _phone_marker(event_id="2", event_type="block_start", event_code="10"),
    ]
    monitor_rows = [
        _monitor_rich_row(phone_markers[0], timestamp=1.0),
        _monitor_rich_row(phone_markers[1], timestamp=2.0),
        _monitor_numeric_row(8, timestamp=1.0),
        _monitor_numeric_row(11, timestamp=2.0),
    ]

    result = reconciler.reconcile_android_lsl_monitor(
        phone_markers,
        monitor_rows,
        expect_numeric_triggers=True,
    )

    assert result.ok is False
    assert result.report["numeric_trigger_summary"]["first_mismatch_index"] == 2
    assert "numeric trigger sequence" in "\n".join(result.report["failures"])


def test_reconcile_android_lsl_monitor_accepts_semantically_matching_payload_json():
    phone_markers = [
        _phone_marker(
            event_id="1",
            event_type="session_metadata",
            event_code="8",
            payload={
                "type": "session_metadata",
                "participant_metadata": {"handedness": "right", "age_years": 29},
            },
        ),
    ]
    monitor_row = _monitor_rich_row(phone_markers[0], timestamp=1.0)
    monitor_row["payload_json"] = json.dumps(
        {
            "participant_metadata": {"age_years": 29, "handedness": "right"},
            "type": "session_metadata",
        }
    )

    result = reconciler.reconcile_android_lsl_monitor(phone_markers, [monitor_row])

    assert result.ok is True
    assert result.report["field_mismatch_count"] == 0


def test_reconcile_android_lsl_monitor_reports_payload_json_drift():
    phone_markers = [
        _phone_marker(
            event_id="1",
            event_type="session_metadata",
            event_code="8",
            payload={
                "type": "session_metadata",
                "participant_metadata": {"handedness": "right", "age_years": 29},
            },
        ),
    ]
    monitor_row = _monitor_rich_row(phone_markers[0], timestamp=1.0)
    monitor_row["payload_json"] = json.dumps(
        {
            "type": "session_metadata",
            "participant_metadata": {"handedness": "left", "age_years": 29},
        }
    )

    result = reconciler.reconcile_android_lsl_monitor(phone_markers, [monitor_row])

    assert result.ok is False
    assert result.report["field_mismatch_count"] == 1
    assert result.report["field_mismatches"][0]["field"] == "payload_json"
    assert "rich markers have 1 field mismatches" in "\n".join(result.report["failures"])


def test_reconcile_android_lsl_monitor_accepts_matching_command_ack_pair():
    phone_markers = [_phone_marker(event_id="1", event_type="session_metadata", event_code="8")]
    monitor_rows = [
        _monitor_rich_row(phone_markers[0], timestamp=1.0),
        _monitor_command_row(command_id="cmd-1", command="pause"),
        _monitor_ack_row(
            command_id="cmd-1",
            payload={"command": "pause", **_target_identity_payload(), "run_id": "phone-run-001"},
        ),
    ]

    result = reconciler.reconcile_android_lsl_monitor(
        phone_markers,
        monitor_rows,
        expect_command_acks=True,
    )

    assert result.ok is True
    assert result.report["monitor_command_signal_count"] == 1
    assert result.report["command_ack_pair_summary"]["command_ids_without_ack"] == []
    assert result.report["command_ack_pair_summary"]["mismatch_count"] == 0


def test_reconcile_android_lsl_monitor_reports_command_without_ack():
    phone_markers = [_phone_marker(event_id="1", event_type="session_metadata", event_code="8")]
    monitor_rows = [
        _monitor_rich_row(phone_markers[0], timestamp=1.0),
        _monitor_command_row(command_id="cmd-missing", command="resume"),
    ]

    result = reconciler.reconcile_android_lsl_monitor(
        phone_markers,
        monitor_rows,
        expect_command_acks=True,
    )

    assert result.ok is False
    assert result.report["command_ack_pair_summary"]["command_ids_without_ack"] == ["cmd-missing"]
    assert "command signals are missing matching ack ids" in "\n".join(result.report["failures"])


def test_reconcile_android_lsl_monitor_reports_command_ack_payload_drift():
    phone_markers = [_phone_marker(event_id="1", event_type="session_metadata", event_code="8")]
    monitor_rows = [
        _monitor_rich_row(phone_markers[0], timestamp=1.0),
        _monitor_command_row(
            command_id="cmd-2",
            command="stop_after_block",
            payload={"token": "secret", "package_id": "pkg-001"},
        ),
        _monitor_ack_row(
            command_id="cmd-2",
            payload={"command": "pause", "package_id": "pkg-other"},
        ),
    ]

    result = reconciler.reconcile_android_lsl_monitor(
        phone_markers,
        monitor_rows,
        expect_command_acks=True,
    )

    assert result.ok is False
    summary = result.report["command_ack_pair_summary"]
    assert summary["mismatch_count"] == 2
    assert {item["field"] for item in summary["mismatches"]} == {"payload.command", "payload.package_id"}
    assert "command/ack pairs have 2 mismatches" in "\n".join(result.report["failures"])


def test_reconcile_android_lsl_monitor_reports_command_ack_target_identity_drift():
    phone_markers = [_phone_marker(event_id="1", event_type="session_metadata", event_code="8")]
    ack_payload = {"command": "start_experiment", **_target_identity_payload()}
    ack_payload["target_part_session_id"] = "part-999"
    monitor_rows = [
        _monitor_rich_row(phone_markers[0], timestamp=1.0),
        _monitor_command_row(command_id="cmd-target", command="start_experiment"),
        _monitor_ack_row(command_id="cmd-target", payload=ack_payload),
    ]

    result = reconciler.reconcile_android_lsl_monitor(
        phone_markers,
        monitor_rows,
        expect_command_acks=True,
    )

    assert result.ok is False
    summary = result.report["command_ack_pair_summary"]
    assert summary["mismatch_count"] == 1
    assert summary["mismatches"][0]["field"] == "payload.target_part_session_id"
    assert summary["mismatches"][0]["expected"] == "part-001"
    assert summary["mismatches"][0]["observed"] == "part-999"


def test_loaders_accept_phone_run_folder_and_monitor_folder(tmp_path: Path):
    phone_dir = tmp_path / "phone-run"
    phone_dir.mkdir()
    phone_markers = [
        _phone_marker(event_id="1", event_type="session_metadata", event_code="8"),
    ]
    _write_marker_csv(phone_dir / "lsl_marker_mirror.csv", phone_markers)
    monitor_dir = tmp_path / "monitor"
    monitor_dir.mkdir()
    monitor_rows = [_monitor_rich_row(phone_markers[0], timestamp=1.0)]
    monitor.write_android_lsl_monitor_artifacts(monitor_dir, monitor_rows)

    result = reconciler.reconcile_android_lsl_monitor(
        reconciler.load_phone_markers(phone_dir),
        reconciler.load_monitor_rows(monitor_dir),
    )

    assert result.ok is True
    assert result.report["phone_marker_count"] == 1
    assert result.report["monitor_rich_marker_count"] == 1


def test_load_monitor_rows_accepts_labrecorder_xdf(monkeypatch):
    phone_markers = [
        _phone_marker(event_id="1", event_type="session_metadata", event_code="8"),
        _phone_marker(event_id="2", event_type="block_start", event_code="10"),
    ]

    def fake_load_xdf(_path: str):
        return (
            [
                {
                    "info": {"name": ["PPSMarkersV2"], "type": ["Markers"], "source_id": ["pps-android-markers-v2-test"]},
                    "time_series": [
                        [phone_markers[0].get(label, "") for label in LSL_MARKER_CHANNELS],
                        [phone_markers[1].get(label, "") for label in LSL_MARKER_CHANNELS],
                    ],
                    "time_stamps": [1.0, 2.0],
                },
                {
                    "info": {"name": ["PPSTriggerCodes"], "type": ["Markers"], "source_id": ["pps-android-trigger-codes-test"]},
                    "time_series": [[8], [10]],
                    "time_stamps": [1.0, 2.0],
                },
            ],
            {},
        )

    monkeypatch.setitem(sys.modules, "pyxdf", types.SimpleNamespace(load_xdf=fake_load_xdf))

    monitor_rows = reconciler.load_monitor_rows(Path("android_capture.xdf"))
    result = reconciler.reconcile_android_lsl_monitor(
        phone_markers,
        monitor_rows,
        expect_numeric_triggers=True,
    )

    assert result.ok is True
    assert result.report["monitor_rich_marker_count"] == 2
    assert result.report["monitor_numeric_trigger_count"] == 2
    assert result.report["numeric_trigger_summary"]["sequence_matches_phone_markers"] is True


def _phone_marker(
    *,
    event_id: str,
    event_type: str,
    event_code: str,
    payload: dict | None = None,
) -> dict[str, str]:
    return {
        "marker_version": MARKER_VERSION,
        "event_id": event_id,
        "event_type": event_type,
        "event_code": event_code,
        "trigger_key": f"control:{event_type}",
        "marker_name": f"P001_{event_type}",
        "session_id": "session-001",
        "participant_id": "P001",
        "session_group_id": "group-001",
        "part_session_id": "part-001",
        "part_number": "1",
        "block_index": "1" if event_type == "block_start" else "",
        "trial_uid": "",
        "sample_index": "",
        "timestamp_quality": "android_elapsed_realtime",
        "payload_json": json.dumps(payload or {"type": event_type}, sort_keys=True),
    }


def _monitor_rich_row(marker: dict[str, str], *, timestamp: float) -> dict:
    sample = [marker.get(label, "") for label in LSL_MARKER_CHANNELS]
    return monitor.build_android_lsl_monitor_row(
        stream_key="rich_markers",
        sample=sample,
        lsl_timestamp=timestamp,
    )


def _monitor_numeric_row(code: int, *, timestamp: float) -> dict:
    return monitor.build_android_lsl_monitor_row(
        stream_key="numeric_triggers",
        sample=[code],
        lsl_timestamp=timestamp,
    )


def _target_identity_payload() -> dict[str, str]:
    return {
        "package_id": "pkg-001",
        "participant_id": "P001",
        "target_session_id": "part-001",
        "target_part_session_id": "part-001",
        "target_session_group_id": "group-001",
        "target_part_number": "1",
    }


def _monitor_command_row(*, command_id: str, command: str, payload: dict | None = None) -> dict:
    return monitor.build_android_lsl_monitor_row(
        stream_key="command_signals",
        sample=command_to_sample(
            LSLCommandSignal(
                command_id=command_id,
                session_id="part-001",
                sender_id="pc_runner",
                command=command,
                issued_lsl_time=1.0,
                payload=payload or {"token": "secret", **_target_identity_payload()},
            )
        ),
        lsl_timestamp=1.0,
    )


def _monitor_ack_row(*, command_id: str, payload: dict | None = None) -> dict:
    return monitor.build_android_lsl_monitor_row(
        stream_key="command_acks",
        sample=ack_to_sample(
            LSLCommandAck(
                command_id=command_id,
                session_id="part-001",
                receiver_id="android_runner",
                status="applied",
                reason="ok",
                received_lsl_time=1.0,
                applied_lsl_time=1.1,
                ack_lsl_time=1.2,
                payload=payload or {},
            )
        ),
        lsl_timestamp=1.2,
    )


def _write_marker_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
