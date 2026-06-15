"""Launch helpers for the native PPS Focus Mode runner."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKAGED_FOCUS_RUNNER = REPO_ROOT / "dist" / "PPSExperimentRunner" / "PPSExperimentRunner.exe"
FOCUS_RUNNER_ENV_VAR = "PPS_FOCUS_RUNNER_EXE"


@dataclass(frozen=True)
class FocusRunnerCommand:
    command: list[str]
    packaged_runner: bool
    runner_binary: str


def resolve_packaged_focus_runner(env: Mapping[str, str] | None = None) -> Path | None:
    """Return the configured packaged Focus Mode executable when it exists."""
    env_map = env if env is not None else os.environ
    candidates: list[Path] = []
    override = str(env_map.get(FOCUS_RUNNER_ENV_VAR) or "").strip()
    if override:
        candidates.append(Path(override))
    candidates.append(DEFAULT_PACKAGED_FOCUS_RUNNER)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def build_focus_runner_command(
    session_manifest: str | Path,
    *,
    capture_options: Mapping[str, Any] | None = None,
    enable_missed_trial_topup: bool = False,
    manual_start: bool = False,
    env: Mapping[str, str] | None = None,
) -> FocusRunnerCommand:
    """Build the command for launching the active packaged experiment runner."""
    runner_exe = resolve_packaged_focus_runner(env)
    if runner_exe is None:
        raise FileNotFoundError(
            "The active experiment runner is the packaged PPSExperimentRunner.exe, but no runner exe was found. "
            f"Build it with windows\\Build_Experiment_Runner_Exe.ps1 or set {FOCUS_RUNNER_ENV_VAR} to the exe path."
        )

    command = [str(runner_exe)]
    packaged = True
    runner_binary = str(runner_exe)

    command.extend(["--session-manifest", str(session_manifest)])
    options = dict(capture_options or {})
    if not bool(options.get("enable_lsl", True)):
        command.append("--no-lsl")
    if not bool(options.get("write_internal_xdf", True)):
        command.append("--no-internal-xdf")
    if not bool(options.get("write_analysis_csvs", True)):
        command.append("--no-analysis-csv")
    if not bool(options.get("start_backup_recording", True)):
        command.append("--no-backup-recording")
    if enable_missed_trial_topup or bool(options.get("enable_missed_trial_topup", False)):
        command.append("--enable-missed-trial-topup")
    if manual_start:
        command.append("--manual-start")
    return FocusRunnerCommand(command=command, packaged_runner=packaged, runner_binary=runner_binary)
