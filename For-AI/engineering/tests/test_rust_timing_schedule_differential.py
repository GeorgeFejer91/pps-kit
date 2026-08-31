from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from peripersonal_space_toolkit.timing_schedule import BlockEventSchedule


def _cargo_executable() -> str:
    if cargo := shutil.which("cargo"):
        return cargo
    rustup_cargo = Path.home() / ".cargo" / "bin" / (
        "cargo.exe" if os.name == "nt" else "cargo"
    )
    assert rustup_cargo.is_file(), "cargo was not found on PATH or in the rustup bin directory"
    return str(rustup_cargo)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _event_row(event: Any) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "sample_index": event.sample_index,
        "trigger_key": event.trigger_key,
        "payload": event.payload,
    }


def _python_result(case: dict[str, Any]) -> dict[str, Any]:
    schedule = BlockEventSchedule.from_block_manifest(
        Path(case["manifest_path"]),
        block_index=case["block_index"],
        block_label=case["block_label"],
        block_wav_path=case["block_wav_path"],
        participant_id=case["participant_id"],
        session_id=case["session_id"],
        part_number=case["part_number"],
        sample_rate=case["sample_rate"],
        block_metadata=case["block_metadata"],
        trial_duration_s=case["trial_duration_s"],
        stimulus_segment_onset_s=case["stimulus_segment_onset_s"],
    )
    events = [_event_row(event) for event in schedule.events]
    buffers = [
        [_event_row(event) for event in schedule.consume_buffer(query["start_sample"], query["frame_count"])]
        for query in case["buffers"]
    ]
    return {"id": case["id"], "events": events, "buffers": buffers}


def _case(
    case_id: str,
    manifest_path: Path,
    *,
    sample_rate: int,
    buffers: list[tuple[int, int]],
    block_index: int = 1,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "manifest_path": str(manifest_path),
        "block_index": block_index,
        "block_label": f"Block {block_index:02d}",
        "block_wav_path": f"block_{block_index:02d}.wav",
        "participant_id": "P001",
        "session_id": "S001",
        "part_number": "2",
        "sample_rate": sample_rate,
        "block_metadata": {
            "phase": "part2",
            "sample_rate_hz": sample_rate,
            "capture_enabled": True,
            "nested_value_is_not_projected": {"private": True},
        },
        "trial_duration_s": 8.0,
        "stimulus_segment_onset_s": 4.0,
        "buffers": [
            {"start_sample": start_sample, "frame_count": frame_count}
            for start_sample, frame_count in buffers
        ],
    }


def test_rust_block_event_schedule_matches_python_oracle(tmp_path: Path) -> None:
    modern = tmp_path / "modern.csv"
    modern_fields = [
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
    ]
    _write_csv(
        modern,
        modern_fields,
        [
            {
                "Trial_Number": "1",
                "Trial_UID": "T_AUDIO_TACTILE",
                "Trial_Type": "Audio-Tactile",
                "Family": "audio_tactile",
                "Row_Label": "Inhale",
                "SOA_ms": "300",
                "Trial_Start_Sample": "0",
                "Looming_Onset_Sample": "4000",
                "Tactile_Onset_Sample": "4300",
                "Response_Window_Onset_Sample": "4000",
                "Trial_End_Sample": "8000",
            },
            {
                "Trial_Number": "2",
                "Trial_UID": "T_CATCH",
                "Trial_Type": "Catch",
                "Family": "catch",
                "Row_Label": "Exhale",
                "SOA_ms": "0",
                "Trial_Start_Sample": "8000",
                "Looming_Onset_Sample": "12000",
                "Tactile_Onset_Sample": "",
                "Response_Window_Onset_Sample": "12000",
                "Trial_End_Sample": "16000",
            },
            {
                "Trial_Number": "3",
                "Trial_UID": "T_BASELINE",
                "Trial_Type": "Baseline",
                "Family": "baseline",
                "Row_Label": "Inhale",
                "SOA_ms": "800",
                "Trial_Start_Sample": "16000",
                "Looming_Onset_Sample": "",
                "Tactile_Onset_Sample": "20800",
                "Response_Window_Onset_Sample": "20800",
                "Trial_End_Sample": "24000",
            },
            {
                "Trial_Number": "4",
                "Trial_UID": "T_AUDITORY",
                "Trial_Type": "Auditory-Only",
                "Family": "auditory_only",
                "Row_Label": "Exhale",
                "SOA_ms": "0",
                "Trial_Start_Sample": "24000",
                "Looming_Onset_Sample": "28000",
                "Tactile_Onset_Sample": "",
                "Response_Window_Onset_Sample": "28000",
                "Trial_End_Sample": "32000",
            },
        ],
    )

    legacy = tmp_path / "legacy.csv"
    _write_csv(
        legacy,
        ["Trial_Number", "Trial_Type", "SOA_ms", "Row_Label"],
        [
            {"Trial_Number": "1", "Trial_Type": "Audio-Tactile", "SOA_ms": "300", "Row_Label": "Inhale"},
            {"Trial_Number": "2", "Trial_Type": "Baseline", "SOA_ms": "800", "Row_Label": "Exhale"},
            {"Trial_Number": "3", "Trial_Type": "Catch", "SOA_ms": "0", "Row_Label": "Inhale"},
            {"Trial_Number": "4", "Trial_Type": "Auditory-Only", "SOA_ms": "0", "Row_Label": "Exhale"},
        ],
    )

    seconds = tmp_path / "seconds.csv"
    _write_csv(
        seconds,
        [
            "trial_number",
            "trial_uid",
            "trial_type",
            "family",
            "soa_ms",
            "trial_start_s",
            "looming_onset_s",
            "tactile_onset_s",
            "response_window_onset_s",
            "trial_end_s",
        ],
        [
            {
                "trial_number": "1",
                "trial_uid": "T_SECONDS",
                "trial_type": "audio_tactile",
                "family": "audio_tactile",
                "soa_ms": "0",
                "trial_start_s": "0.005",
                "looming_onset_s": "0.015",
                "tactile_onset_s": "0.025",
                "response_window_onset_s": "0.035",
                "trial_end_s": "0.045",
            }
        ],
    )

    invalid_explicit = tmp_path / "invalid-explicit.csv"
    _write_csv(
        invalid_explicit,
        [
            "Trial_Number",
            "Trial_UID",
            "Trial_Type",
            "Family",
            "Trial_Start_Sample",
            "Trial_Start_S",
            "Looming_Onset_Sample",
            "Looming_Onset_S",
            "Tactile_Onset_Sample",
            "Tactile_Onset_S",
            "Response_Window_Onset_Sample",
            "Response_Window_Onset_S",
            "Trial_End_Sample",
            "Trial_End_S",
        ],
        [
            {
                "Trial_Number": "1",
                "Trial_UID": "T_INVALID_EXPLICIT",
                "Trial_Type": "Audio-Tactile",
                "Family": "audio_tactile",
                "Trial_Start_Sample": "-1",
                "Trial_Start_S": "1.0",
                "Looming_Onset_Sample": "not-a-number",
                "Looming_Onset_S": "1.1",
                "Tactile_Onset_Sample": "120",
                "Tactile_Onset_S": "9.9",
                "Response_Window_Onset_Sample": "",
                "Response_Window_Onset_S": "1.3",
                "Trial_End_Sample": "",
                "Trial_End_S": "-1",
            }
        ],
    )

    cases = [
        _case(
            "modern_sample_columns_and_buffer_boundaries",
            modern,
            sample_rate=1000,
            buffers=[(0, 4000), (4000, 301), (4301, 3699), (8000, 1), (8001, 23999), (32000, 1)],
        ),
        _case("legacy_default_timing", legacy, sample_rate=100, buffers=[(0, 3201)], block_index=3),
        _case("seconds_aliases_and_ties_to_even", seconds, sample_rate=100, buffers=[(0, 5)], block_index=4),
        _case("invalid_explicit_sample_suppresses_seconds_fallback", invalid_explicit, sample_rate=100, buffers=[(0, 131)], block_index=5),
    ]

    python_results = [_python_result(case) for case in cases]
    modern_result, legacy_result, seconds_result, invalid_result = python_results
    assert [(row["event_type"], row["sample_index"]) for row in modern_result["events"]] == [
        ("audio_sample_zero", 0),
        ("trial_start", 0),
        ("looming_onset", 4000),
        ("response_window_onset", 4000),
        ("tactile_onset", 4300),
        ("trial_start", 8000),
        ("trial_end", 8000),
        ("looming_onset", 12000),
        ("response_window_onset", 12000),
        ("trial_start", 16000),
        ("trial_end", 16000),
        ("tactile_onset", 20800),
        ("response_window_onset", 20800),
        ("trial_start", 24000),
        ("trial_end", 24000),
        ("looming_onset", 28000),
        ("response_window_onset", 28000),
        ("trial_end", 32000),
    ]
    assert [row["event_type"] for row in modern_result["buffers"][3]] == ["trial_start", "trial_end"]
    assert [row["event_type"] for row in modern_result["buffers"][-1]] == ["trial_end"]
    assert len(legacy_result["events"]) == 18
    assert [(row["event_type"], row["sample_index"]) for row in seconds_result["events"]] == [
        ("audio_sample_zero", 0),
        ("trial_start", 0),
        ("looming_onset", 2),
        ("tactile_onset", 2),
        ("response_window_onset", 4),
        ("trial_end", 4),
    ]
    assert [(row["event_type"], row["sample_index"]) for row in invalid_result["events"]] == [
        ("audio_sample_zero", 0),
        ("tactile_onset", 120),
        ("response_window_onset", 130),
    ]

    repo_root = Path(__file__).resolve().parents[3]
    completed = subprocess.run(
        [
            _cargo_executable(),
            "run",
            "--quiet",
            "--locked",
            "-p",
            "pps-runner-execution",
            "--example",
            "schedule_probe",
        ],
        cwd=repo_root,
        input=json.dumps({"cases": cases}),
        text=True,
        capture_output=True,
        timeout=120,
        env={**os.environ, "CARGO_TERM_COLOR": "never"},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"cases": python_results}
