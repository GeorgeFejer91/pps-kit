from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from peripersonal_space_toolkit import focus_app, focus_launch


def test_focus_runner_command_prefers_packaged_exe(tmp_path: Path, monkeypatch):
    exe = tmp_path / "PPSExperimentRunner.exe"
    exe.write_bytes(b"runner")
    manifest = tmp_path / "session_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(focus_launch.FOCUS_RUNNER_ENV_VAR, str(exe))

    result = focus_launch.build_focus_runner_command(
        manifest,
        capture_options={
            "enable_lsl": False,
            "write_internal_xdf": False,
            "write_analysis_csvs": True,
            "start_backup_recording": False,
            "wired_loopback_mode": "output4_tactile_proxy",
            "enable_missed_trial_topup": True,
        },
        manual_start=True,
    )

    assert result.packaged_runner is True
    assert result.runner_binary == str(exe)
    assert result.command[0] == str(exe)
    assert "-m" not in result.command
    assert "--session-manifest" in result.command
    assert str(manifest) in result.command
    assert "--no-lsl" in result.command
    assert "--no-internal-xdf" in result.command
    assert "--no-analysis-csv" not in result.command
    assert "--no-backup-recording" in result.command
    assert "--wired-loopback" in result.command
    assert "output4-tactile-proxy" in result.command
    assert "--enable-missed-trial-topup" in result.command
    assert "--manual-start" in result.command


def test_focus_runner_command_requires_packaged_exe(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "session_manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.delenv(focus_launch.FOCUS_RUNNER_ENV_VAR, raising=False)
    monkeypatch.setattr(focus_launch, "DEFAULT_PACKAGED_FOCUS_RUNNER", tmp_path / "missing.exe")

    try:
        focus_launch.build_focus_runner_command(manifest)
    except FileNotFoundError as exc:
        message = str(exc)
    else:
        raise AssertionError("Missing packaged runner exe should fail instead of falling back to Python.")

    assert "PPSExperimentRunner.exe" in message
    assert "Build_Experiment_Runner_Exe.ps1" in message


def test_focus_app_direct_module_launch_is_retired():
    result = subprocess.run(
        [sys.executable, "-m", "peripersonal_space_toolkit.focus_app", "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )

    message = result.stdout + result.stderr
    assert result.returncode == 2
    assert "Direct Python module launch of Focus Mode is retired" in message
    assert "PPSExperimentRunner.exe" in message
    assert "Build_Experiment_Runner_Exe.ps1" in message


def test_participant_range_parser_requires_explicit_bounded_ranges():
    assert focus_app.parse_participant_range("1-3", max_participant=50) == ["P001", "P002", "P003"]
    assert focus_app.parse_participant_range("P002, 4-5", max_participant=50) == ["P002", "P004", "P005"]

    with pytest.raises(ValueError, match="outside"):
        focus_app.parse_participant_range("49-51", max_participant=50)

    with pytest.raises(ValueError, match="low to high"):
        focus_app.parse_participant_range("10-1", max_participant=50)


def test_study5_launcher_participant_dropdown_source_lists_50_participants():
    participants = focus_app.profile_participant_ids(focus_app.STUDY5_PROFILE_ID)

    assert participants[0] == "P001"
    assert participants[-1] == "P050"
    assert len(participants) == 50


def test_participant_dropdown_marks_collected_data_and_defaults_to_ready_uncollected():
    participants = ["P001", "P002", "P003"]
    statuses = {
        "P001": {"generated": True, "status": "ready", "data_collected": True},
        "P002": {"generated": True, "status": "ready", "data_collected": False},
        "P003": {"generated": False, "status": "not_generated", "data_collected": False},
    }

    collected_label = focus_app.profile_participant_dropdown_label("P001", statuses["P001"])
    ready_label = focus_app.profile_participant_dropdown_label("P002", statuses["P002"])

    assert focus_app.DATA_COLLECTED_MARK in collected_label
    assert "data collected" in collected_label
    assert "data not collected" in ready_label
    assert focus_app.default_profile_participant(participants, statuses, preferred="P001") == "P002"
    assert focus_app.default_profile_participant(participants, statuses, preferred="P002") == "P002"
