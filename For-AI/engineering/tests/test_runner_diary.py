from __future__ import annotations

from pathlib import Path

from peripersonal_space_toolkit.runner_diary import (
    DIARY_FILENAME_MARKER,
    append_diary_entry,
    diary_filename,
    find_output_diary,
    latest_diary_context,
    read_diary_entries,
    resolve_or_create_output_project,
    slugify_identifier,
)
from peripersonal_space_toolkit.output_layout import output_metadata_dir, output_runner_logs_dir


def test_diary_filename_uses_experiment_identifier():
    filename = diary_filename("Study 5 PPS box-breathing white/pink profile")

    assert filename == f"study_5_pps_box_breathing_white_pink_profile_{DIARY_FILENAME_MARKER}.txt"
    assert slugify_identifier("  Bad / Name ++  ") == "bad_name"


def test_diary_append_and_read_skips_corrupted_lines(tmp_path: Path):
    diary = tmp_path / diary_filename("Study 5")
    diary.write_text("{not json}\n", encoding="utf-8")

    append_diary_entry(
        diary,
        "session_start",
        session_id="P001_20260617_151500",
        participant_id="P001",
        experiment_name="Study 5",
        profile_id="study5_box_breathing_pps",
        capture_options={"enable_lsl": True},
        payload={"events_csv": "events.csv"},
    )

    entries = read_diary_entries(diary)
    assert len(entries) == 1
    assert entries[0]["event_type"] == "session_start"
    assert entries[0]["participant_id"] == "P001"
    assert entries[0]["capture_options"]["enable_lsl"] is True
    assert latest_diary_context(diary)["profile_id"] == "study5_box_breathing_pps"


def test_resolve_output_project_creates_experiment_named_child(tmp_path: Path):
    result = resolve_or_create_output_project(
        tmp_path,
        experiment_identifier="Study 5 PPS box-breathing white/pink profile",
        timestamp="20260617_151500",
    )

    assert result.created is True
    assert result.reused_existing_diary is False
    assert result.root == tmp_path / "study_5_pps_box_breathing_white_pink_profile_20260617_151500"
    assert result.diary_path == output_runner_logs_dir(result.root) / diary_filename(
        "study_5_pps_box_breathing_white_pink_profile"
    )
    assert result.diary_path.parent == output_metadata_dir(result.root) / "runner_logs"
    assert not (result.root / diary_filename("study_5_pps_box_breathing_profile")).exists()
    entries = read_diary_entries(result.diary_path)
    assert entries[0]["event_type"] == "output_project_created"


def test_resolve_output_project_reuses_existing_diary(tmp_path: Path):
    existing = tmp_path / diary_filename("Existing Study")
    append_diary_entry(existing, "diary_created", experiment_name="Existing Study")

    result = resolve_or_create_output_project(
        tmp_path,
        experiment_identifier="Ignored New Study",
        timestamp="20260617_151500",
    )

    assert result.created is False
    assert result.reused_existing_diary is True
    assert result.root == tmp_path
    assert result.diary_path == existing
    assert find_output_diary(tmp_path) == existing
    assert [entry["event_type"] for entry in read_diary_entries(existing)][-1] == "output_project_reused"


def test_missing_diary_reads_as_empty(tmp_path: Path):
    assert read_diary_entries(tmp_path / "missing.txt") == []
    assert latest_diary_context(tmp_path / "missing.txt") == {}
