from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

from peripersonal_space_toolkit import focus_app


def _write_events(path: Path, *, standard_blocks: int, standard_trials: int, topup_blocks: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["event_type", "payload_json"])
        writer.writeheader()
        for _index in range(standard_blocks):
            writer.writerow({"event_type": "block_end", "payload_json": "{}"})
        for _index in range(standard_trials):
            writer.writerow({"event_type": "trial_start", "payload_json": "{}"})
            writer.writerow({"event_type": "trial_end", "payload_json": "{}"})
        for _index in range(topup_blocks):
            writer.writerow({"event_type": "block_end", "payload_json": json.dumps({"is_topup": True})})


def _write_split_part(tmp_path: Path, group_id: str, part_number: int, *, completed: bool, standard_trials: int, topup_blocks: int = 0) -> dict[str, Path]:
    part_name = f"part_{part_number:02d}"
    session_dir = tmp_path / group_id / part_name
    manifest_path = tmp_path / "Experiment_context_folder_DO_NOT_DELETE" / "runner_logs" / group_id / part_name / "session_manifest.json"
    events_path = tmp_path / "Experiment_context_folder_DO_NOT_DELETE" / "verbose_events" / group_id / part_name / "events.csv"
    analysis_dir = tmp_path / "Data_Analytics" / group_id / part_name
    status_path = tmp_path / "Experiment_context_folder_DO_NOT_DELETE" / "runner_logs" / group_id / part_name / "part_completion_status.json"
    group_manifest = tmp_path / "Experiment_context_folder_DO_NOT_DELETE" / "runner_logs" / group_id / "session_group_manifest.json"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    _write_events(events_path, standard_blocks=6, standard_trials=standard_trials, topup_blocks=topup_blocks)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(
            {
                "schema": "pps-runner-part-completion-status.v1",
                "completed": completed,
                "interrupted": False,
                "analysis_outputs": {
                    "topup_ledger_json": str(status_path.parent / "topup" / "topup_ledger.json"),
                },
            }
        ),
        encoding="utf-8",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "pps-run-session.v1",
                "participant_id": "P999",
                "session_id": f"{group_id}_{part_name}",
                "session_group_id": group_id,
                "part_number": part_number,
                "part_session_id": f"{group_id}_{part_name}",
                "part_folder_name": part_name,
                "part_split_schema": "pps-runner-part-split.v1",
                "session_dir": str(session_dir),
                "blocks": [{"index": index, "duration_s": 1.0} for index in range(1, 7)],
                "outputs": {
                    "verbose_events_csv": str(events_path),
                    "analysis_dir": str(analysis_dir),
                    "part_completion_status_json": str(status_path),
                    "session_group_manifest_json": str(group_manifest),
                },
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return {
        "manifest": manifest_path,
        "session_dir": session_dir,
        "events": events_path,
        "analysis_dir": analysis_dir,
        "status": status_path,
        "group_manifest": group_manifest,
    }


def test_validation_focus_report_aggregates_split_session_group(tmp_path: Path) -> None:
    group_id = "P999_20260624_120000"
    part1 = _write_split_part(tmp_path, group_id, 1, completed=True, standard_trials=204, topup_blocks=1)
    part2 = _write_split_part(tmp_path, group_id, 2, completed=True, standard_trials=204)
    group_manifest = part1["group_manifest"]
    group_manifest.write_text(
        json.dumps(
            {
                "schema": "pps-run-session-group.v1",
                "session_group_id": group_id,
                "participant_id": "P999",
                "parts_per_participant": 2,
                "parts": [
                    {
                        "part_number": 1,
                        "part_session_id": f"{group_id}_part_01",
                        "part_folder_name": "part_01",
                        "session_manifest_path": str(part1["manifest"]),
                        "session_dir": str(part1["session_dir"]),
                        "block_count": 6,
                        "completed": True,
                        "part_completion_status_path": str(part1["status"]),
                    },
                    {
                        "part_number": 2,
                        "part_session_id": f"{group_id}_part_02",
                        "part_folder_name": "part_02",
                        "session_manifest_path": str(part2["manifest"]),
                        "session_dir": str(part2["session_dir"]),
                        "block_count": 6,
                        "completed": True,
                        "part_completion_status_path": str(part2["status"]),
                    },
                ],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    package = SimpleNamespace(
        manifest_path=part2["manifest"],
        session_dir=part2["session_dir"],
        session_group_id=group_id,
        part_session_id=f"{group_id}_part_02",
        session_id=f"{group_id}_part_02",
        sibling_part_manifest_paths=[part1["manifest"]],
    )
    window = SimpleNamespace(
        package=package,
        result=SimpleNamespace(completed=True, analysis_outputs={}),
        validation_topup_approval_records=[],
        validation_part_snapshots=[
            {"part_session_id": f"{group_id}_part_01", "planned_tactile_cue_count": 204, "cursor_recenter_count": 204, "cursor_recenter_records": [{}] * 204},
            {"part_session_id": f"{group_id}_part_02", "planned_tactile_cue_count": 204, "cursor_recenter_count": 204, "cursor_recenter_records": [{}] * 204},
        ],
        planned_tactile_cue_count=204,
        recenter_records=[{}] * 204,
    )
    engine = SimpleNamespace(
        played_blocks=[str(index) for index in range(12)],
        played_block_durations_s=[1.0] * 12,
        played_instructions=[str(index) for index in range(5)],
        played_instruction_durations_s=[1.0] * 5,
        realtime=True,
    )
    report_path = tmp_path / "focus_validation_report.json"

    focus_app._write_validation_focus_report(
        report_path,
        session_manifest=part2["manifest"],
        package=package,
        exit_code=0,
        window=window,
        validation_clicks=[{"label": "Start Part 01"}, {"label": "Start Part 02"}],
        engine=engine,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    standard = report["scoped_event_counts"]["standard"]
    topup = report["scoped_event_counts"]["topup"]
    assert report["completed"]
    assert report["all_parts_completed"]
    assert report["completed_part_count"] == 2
    assert report["block_count"] == 12
    assert standard["block_end"] == 12
    assert standard["trial_start"] == 408
    assert standard["trial_end"] == 408
    assert topup["block_end"] == 1
    assert report["planned_tactile_cue_count"] == 408
    assert report["cursor_recenter_count"] == 408
    assert [part["completed"] for part in report["parts"]] == [True, True]
