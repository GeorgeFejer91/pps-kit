from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

from peripersonal_space_toolkit import android_lsl_monitor as monitor
from peripersonal_space_toolkit.lsl_command_ack import LSLCommandAck, ack_to_sample
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


def _phone_marker(*, event_id: str, event_type: str, event_code: str) -> dict[str, str]:
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
        "payload_json": json.dumps({"type": event_type}, sort_keys=True),
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


def _monitor_ack_row(*, command_id: str) -> dict:
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
                payload={},
            )
        ),
        lsl_timestamp=1.2,
    )


def _write_marker_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
