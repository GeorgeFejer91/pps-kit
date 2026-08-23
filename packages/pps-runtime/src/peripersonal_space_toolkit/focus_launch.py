"""Launch helpers for the native PPS Focus Mode runner."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .session_runner import (
    WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY,
    WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
    normalize_wired_loopback_mode,
)
from .runtime_paths import product_root


REPO_ROOT = product_root()
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
            "Build it with For-AI\\engineering\\build\\windows\\Build_Experiment_Runner_Exe.ps1 "
            f"or set {FOCUS_RUNNER_ENV_VAR} to the exe path."
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
    external_labrecorder = options.get("start_external_labrecorder")
    if external_labrecorder is False:
        command.append("--no-external-labrecorder")
    elif external_labrecorder is True:
        command.append("--external-labrecorder")
        labrecorder_cli = str(options.get("external_labrecorder_cli") or "").strip()
        if labrecorder_cli:
            command.extend(["--labrecorder-cli", labrecorder_cli])
        for option_key, flag in (
            ("external_labrecorder_stream_timeout_s", "--labrecorder-stream-timeout-s"),
            ("external_labrecorder_startup_s", "--labrecorder-startup-s"),
            ("external_labrecorder_stop_timeout_s", "--labrecorder-stop-timeout-s"),
        ):
            if option_key in options:
                command.extend([flag, str(options[option_key])])
    if "wired_loopback_mode" in options:
        wired_mode = normalize_wired_loopback_mode(options.get("wired_loopback_mode"))
        command.extend(
            [
                "--wired-loopback",
                WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY if wired_mode == WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY else "off",
            ]
        )
    elif normalize_wired_loopback_mode(options.get("wired_loopback_mode")) == WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY:
        command.extend(["--wired-loopback", WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY])
    if enable_missed_trial_topup or options.get("enable_missed_trial_topup") is True:
        command.append("--enable-missed-trial-topup")
    elif options.get("enable_missed_trial_topup") is False:
        command.append("--no-missed-trial-topup")
    if manual_start:
        command.append("--manual-start")
    return FocusRunnerCommand(command=command, packaged_runner=packaged, runner_binary=runner_binary)
