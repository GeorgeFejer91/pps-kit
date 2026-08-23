from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from peripersonal_space_toolkit.mobile_pps_replication import (
    INPUT_KIND_ANALYSIS_READY,
    INPUT_KIND_OSF_MASTER,
    ReplicationOptions,
    analyze_csv,
    discover_input_csvs,
    write_outputs,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _criterion_status(result, criterion: str) -> str:
    return next(row["status"] for row in result.criteria_rows if row["criterion"] == criterion)


def _osf_rows(*, flat: bool = False, bad_integrity: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    soas = [300, 800, 1500, 2200, 2700]
    for participant_index in range(1, 9):
        participant = f"P{participant_index:02d}"
        baseline = 520.0 + participant_index
        for soa in soas:
            for repeat in range(2):
                rows.append(
                    {
                        "participant_id": participant,
                        "trial_type": "Baseline",
                        "SOA_ms": soa,
                        "condition": "Mobile",
                        "phase": "All",
                        "reaction_time_ms": baseline + repeat,
                        "response_detected_bool": not bad_integrity,
                    }
                )
                facilitation = -40.0 if flat else -15.0 - (soa / 100.0)
                rows.append(
                    {
                        "participant_id": participant,
                        "trial_type": "Audio-Tactile",
                        "SOA_ms": soa,
                        "condition": "Mobile",
                        "phase": "All",
                        "reaction_time_ms": baseline + facilitation + repeat,
                        "response_detected_bool": not bad_integrity,
                    }
                )
        for catch_index in range(4):
            rows.append(
                {
                    "participant_id": participant,
                    "trial_type": "Catch",
                    "SOA_ms": "",
                    "condition": "Mobile",
                    "phase": "All",
                    "reaction_time_ms": "",
                    "response_detected_bool": bad_integrity and catch_index < 3,
                }
            )
    return rows


def _analysis_ready_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for soa in [300, 800, 1500, 2200, 2700]:
        rows.append(
            {
                "participant_id": "P001",
                "trial_type": "Baseline",
                "soa_ms": soa,
                "condition": "Mobile",
                "respiratory_phase": "All",
                "rt_ms": 500,
                "hit": True,
                "primary_analysis_included": True,
            }
        )
        rows.append(
            {
                "participant_id": "P001",
                "trial_type": "Audio-Tactile",
                "soa_ms": soa,
                "condition": "Mobile",
                "respiratory_phase": "All",
                "rt_ms": 470 - soa / 100,
                "hit": True,
                "primary_analysis_included": True,
            }
        )
    rows.append(
        {
            "participant_id": "P001",
            "trial_type": "Catch",
            "soa_ms": "",
            "condition": "Mobile",
            "respiratory_phase": "All",
            "rt_ms": "",
            "hit": True,
            "primary_analysis_included": True,
        }
    )
    return rows


def test_osf_style_data_passes_basic_mobile_pps_replication(tmp_path: Path) -> None:
    input_csv = tmp_path / "master_successful_participants.csv"
    _write_csv(input_csv, _osf_rows())

    result = analyze_csv(input_csv, options=ReplicationOptions(input_kind=INPUT_KIND_OSF_MASTER))

    assert result.input_kind == INPUT_KIND_OSF_MASTER
    assert result.sample["participants"] == 8
    assert _criterion_status(result, "performance_integrity") == "PASS"
    assert _criterion_status(result, "multisensory_facilitation_overall") == "PASS"
    assert _criterion_status(result, "multisensory_facilitation_by_soa") == "PASS"
    assert _criterion_status(result, "approach_gradient") == "SIGNAL"

    outputs = write_outputs(result, tmp_path / "reports")
    assert outputs["summary_json"].exists()
    assert outputs["report_md"].exists()
    summary = json.loads(outputs["summary_json"].read_text(encoding="utf-8"))
    assert summary["summary"]["basic_facilitation_replicated"] is True


def test_flat_facilitation_passes_overall_but_not_approach_gradient(tmp_path: Path) -> None:
    input_csv = tmp_path / "master_successful_participants.csv"
    _write_csv(input_csv, _osf_rows(flat=True))

    result = analyze_csv(input_csv, options=ReplicationOptions(input_kind=INPUT_KIND_OSF_MASTER))

    assert _criterion_status(result, "multisensory_facilitation_overall") == "PASS"
    assert _criterion_status(result, "multisensory_facilitation_by_soa") == "PASS"
    assert _criterion_status(result, "approach_gradient") == "NO_SIGNAL"


def test_bad_response_integrity_fails_integrity_and_clean_inventory(tmp_path: Path) -> None:
    input_csv = tmp_path / "master_successful_participants.csv"
    _write_csv(input_csv, _osf_rows(bad_integrity=True))

    result = analyze_csv(input_csv, options=ReplicationOptions(input_kind=INPUT_KIND_OSF_MASTER))

    assert _criterion_status(result, "performance_integrity") == "FAIL"
    assert _criterion_status(result, "catch_false_alarm_control") == "FAIL"
    assert _criterion_status(result, "clean_trial_inventory") == "FAIL"


def test_analysis_ready_schema_normalizes_catch_success_as_no_false_alarm(tmp_path: Path) -> None:
    input_csv = tmp_path / "P001_analysis_ready_trials.csv"
    _write_csv(input_csv, _analysis_ready_rows())

    result = analyze_csv(input_csv, options=ReplicationOptions(input_kind=INPUT_KIND_ANALYSIS_READY))

    assert result.input_kind == INPUT_KIND_ANALYSIS_READY
    assert result.participant_qc_rows[0]["catch_false_alarms"] == 0
    assert _criterion_status(result, "multisensory_facilitation_overall") == "NO_SIGNAL"
    assert _criterion_status(result, "clean_trial_inventory") == "PASS"


def test_cli_scans_folder_and_writes_index(tmp_path: Path) -> None:
    input_root = tmp_path / "data"
    _write_csv(input_root / "Study 5 OSF" / "4. DataAnalysis" / "Input" / "master_successful_participants.csv", _osf_rows())
    _write_csv(input_root / "local" / "P001_analysis_ready_trials.csv", _analysis_ready_rows())

    discovered = discover_input_csvs(input_root)
    assert len(discovered) == 2

    script = Path("For-AI/engineering/validation") / "scripts" / "analyze_mobile_pps_replication.py"
    output_dir = tmp_path / "out"
    completed = subprocess.run(
        [sys.executable, str(script), "--input", str(input_root), "--output-dir", str(output_dir)],
        cwd=Path(__file__).resolve().parents[3],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    index_path = output_dir / "mobile_pps_replication_index.csv"
    assert index_path.exists()
    rows = list(csv.DictReader(index_path.open(encoding="utf-8")))
    assert len(rows) == 2
    assert all(not row["error"] for row in rows)
