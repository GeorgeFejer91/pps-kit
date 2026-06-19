"""Evaluation-only full realtime participant emulation for the packaged runner.

This script is not a toolkit feature. It launches the packaged
PPSExperimentRunner.exe with hidden validation hooks, paces audio on the full
wall-clock schedule, emulates a participant with randomized tactile misses and
delayed responses, auto-approves top-up blocks, and writes an evidence report.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from audit_protocol11_study5_readiness import audit_readiness  # noqa: E402


STUDY5_TEMPLATE_ID = "study5_box_breathing_pps"
SCHEMA = "pps-full-realtime-participant-emulation-evaluation.v1"
VALIDATION_LANE_AUTO = "auto"
VALIDATION_LANE_SOFTWARE_ONLY = "software-only"
VALIDATION_LANE_FULL_STACK = "full-stack"
OS_MOUSE_BACKENDS = {"pynput", "win32", "pyautogui"}
WIRED_LOOPBACK_OFF = "off"
WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY = "output4-tactile-proxy"


def _default_output_dir() -> Path:
    return REPO_ROOT / "artifacts" / "validation_runs" / f"full_realtime_participant_emulation_{time.strftime('%Y%m%d_%H%M%S')}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _resolved_validation_lane(args: argparse.Namespace) -> str:
    lane = str(getattr(args, "validation_lane", VALIDATION_LANE_AUTO) or VALIDATION_LANE_AUTO).strip().lower()
    if lane != VALIDATION_LANE_AUTO:
        return lane
    if bool(getattr(args, "strict_study5_readiness", False)) or str(getattr(args, "audio_mode", "")) == "hardware":
        return VALIDATION_LANE_FULL_STACK
    return VALIDATION_LANE_SOFTWARE_ONLY


def _apply_validation_lane_policy(args: argparse.Namespace) -> str:
    lane = _resolved_validation_lane(args)
    if lane == VALIDATION_LANE_SOFTWARE_ONLY:
        if bool(args.strict_study5_readiness):
            raise ValueError("Software-only validation cannot request strict Study 5 readiness; use --validation-lane full-stack --audio-mode hardware.")
        if str(args.audio_mode) != "validation-realtime":
            raise ValueError("Software-only validation requires --audio-mode validation-realtime; use --validation-lane full-stack for hardware audio.")
    elif lane == VALIDATION_LANE_FULL_STACK:
        if str(args.audio_mode) != "hardware":
            raise ValueError("Full-stack validation requires --audio-mode hardware so the normal ASIO/local-recorder path is exercised.")
        if str(args.mouse_backend) not in OS_MOUSE_BACKENDS:
            allowed = ", ".join(sorted(OS_MOUSE_BACKENDS))
            raise ValueError(f"Full-stack validation requires an OS mouse backend ({allowed}); qtest is software-only.")
        if args.no_lsl or args.no_internal_xdf or args.no_backup_recording:
            raise ValueError("Full-stack validation cannot disable LSL, internal XDF, or local audio-evidence recording.")
        args.standard_capture = True
        args.strict_study5_readiness = True
    else:
        raise ValueError(f"Unknown validation lane: {lane}")
    args.validation_lane = lane
    return lane


def _standard_capture_requested(args: argparse.Namespace) -> bool:
    return bool(
        args.standard_capture
        or args.strict_study5_readiness
        or _resolved_validation_lane(args) == VALIDATION_LANE_FULL_STACK
    )


def _build_runner_command(args: argparse.Namespace, *, runner: Path, screenshot_path: Path) -> list[str]:
    if args.runner_mode == "source":
        command = [sys.executable, str(REPO_ROOT / "windows" / "focus_runner_entry.py")]
    else:
        command = [str(runner)]
    command.extend(
        [
        "--profile",
        str(args.profile),
        "--participant-id",
        str(args.participant_id),
        "--manual-start",
        "--enable-missed-trial-topup",
        "--validation-screenshot",
        str(screenshot_path),
        ]
    )
    wired_loopback = str(getattr(args, "wired_loopback", WIRED_LOOPBACK_OFF) or WIRED_LOOPBACK_OFF)
    if wired_loopback != WIRED_LOOPBACK_OFF:
        command.extend(["--wired-loopback", wired_loopback])
    if not _standard_capture_requested(args):
        command.extend(["--no-lsl", "--no-internal-xdf", "--no-backup-recording"])
    else:
        if args.no_lsl:
            command.append("--no-lsl")
        if args.no_internal_xdf:
            command.append("--no-internal-xdf")
        if args.no_backup_recording:
            command.append("--no-backup-recording")
    return command


def _configure_validation_env(args: argparse.Namespace, *, output_dir: Path, focus_report_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    env.setdefault("SD_ENABLE_ASIO", "1")
    if args.runner_mode == "source":
        existing_pythonpath = env.get("PYTHONPATH", "")
        paths = [str(SRC_ROOT)]
        if existing_pythonpath:
            paths.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(paths)
    if args.audio_mode == "validation-realtime":
        env["PPS_FOCUS_VALIDATION_REALTIME_AUDIO"] = "1"
        env["PPS_FOCUS_VALIDATION_AUDIO_CHUNK_FRAMES"] = str(int(args.validation_audio_chunk_frames))
    else:
        env.pop("PPS_FOCUS_VALIDATION_REALTIME_AUDIO", None)
        env.pop("PPS_FOCUS_VALIDATION_FAST_AUDIO", None)
        env.pop("PPS_FOCUS_VALIDATION_AUDIO_CHUNK_FRAMES", None)
    env["PPS_FOCUS_VALIDATION_PARTICIPANT_EMULATOR"] = "1"
    env["PPS_FOCUS_VALIDATION_AUTO_APPROVE_TOPUP"] = "1"
    env["PPS_FOCUS_VALIDATION_MOUSE_BACKEND"] = str(args.mouse_backend)
    env["PPS_FOCUS_VALIDATION_PARTICIPANT_SEED"] = str(int(args.seed))
    env["PPS_FOCUS_VALIDATION_PARTICIPANT_MISS_RATE"] = str(float(args.miss_rate))
    env["PPS_FOCUS_VALIDATION_PARTICIPANT_MIN_MISSES"] = str(int(args.min_misses))
    env["PPS_FOCUS_VALIDATION_REPORT"] = str(focus_report_path)
    env["PPS_FOCUS_DISABLE_PREWARM"] = "1"
    env["PPS_PROTOCOL11_OUTPUT_DIR"] = str(output_dir)
    env["PPS_PROTOCOL11_VALIDATION_LANE"] = _resolved_validation_lane(args)
    env["PPS_PROTOCOL11_WIRED_LOOPBACK"] = str(getattr(args, "wired_loopback", WIRED_LOOPBACK_OFF) or WIRED_LOOPBACK_OFF)
    if args.audio_device_index is not None:
        env["PPS_AUDIO_DEVICE_INDEX"] = str(int(args.audio_device_index))
    return env


def _annotate_focus_report(path: Path, *, args: argparse.Namespace) -> dict[str, Any]:
    focus = _read_json(path)
    if not focus:
        return {}
    focus["protocol11_audio_mode"] = str(args.audio_mode)
    focus["protocol11_validation_lane"] = _resolved_validation_lane(args)
    focus["hardware_audio_realtime"] = bool(args.audio_mode == "hardware")
    focus["standard_capture_requested"] = bool(_standard_capture_requested(args))
    focus["strict_study5_readiness_requested"] = bool(args.strict_study5_readiness)
    focus["final_condition_candidate"] = bool(_resolved_validation_lane(args) == VALIDATION_LANE_FULL_STACK)
    focus["wired_loopback_mode"] = str(getattr(args, "wired_loopback", WIRED_LOOPBACK_OFF) or WIRED_LOOPBACK_OFF)
    _write_json(path, focus)
    return focus


def _write_launch_and_preparation_reports(
    output_dir: Path,
    *,
    args: argparse.Namespace,
    runner: Path,
    command: list[str],
    pid: int | None,
    exit_code: int | None,
    focus_report_path: Path,
    screenshot_path: Path,
    evaluation: dict[str, Any],
    started_at: str,
) -> None:
    _write_json(
        output_dir / "packaged_runner_process_launch.json",
        {
            "schema": "pps-packaged-full-study5-process-launch.v1",
            "pid": pid,
            "exe": str(runner),
            "command": command,
            "profile_id": str(args.profile),
            "participant_id": str(args.participant_id),
            "runner_mode": str(args.runner_mode),
            "audio_mode": str(args.audio_mode),
            "validation_lane": _resolved_validation_lane(args),
            "audio_device_index": args.audio_device_index,
            "wired_loopback_mode": str(getattr(args, "wired_loopback", WIRED_LOOPBACK_OFF) or WIRED_LOOPBACK_OFF),
            "standard_capture_requested": _standard_capture_requested(args),
            "strict_study5_readiness_requested": bool(args.strict_study5_readiness),
            "started_at": started_at,
            "exit_code": exit_code,
            "validation_report": str(focus_report_path),
            "screenshot": str(screenshot_path),
            "mouse_backend": str(args.mouse_backend),
        },
    )
    _write_json(
        output_dir / "preparation_report.json",
        {
            "schema": "pps-full-study5-realtime-validation-prep.v1",
            "profile_id": str(args.profile),
            "participant_id": str(args.participant_id),
            "audio_mode": str(args.audio_mode),
            "validation_lane": _resolved_validation_lane(args),
            "wired_loopback_mode": str(getattr(args, "wired_loopback", WIRED_LOOPBACK_OFF) or WIRED_LOOPBACK_OFF),
            "standard_capture_requested": _standard_capture_requested(args),
            "session_dir": evaluation.get("session_dir", ""),
            "session_manifest": evaluation.get("session_manifest", ""),
            "events_csv": evaluation.get("events_csv", ""),
        },
    )


def _events(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _read_csv(path):
        try:
            payload = json.loads(row.get("payload_json", "") or "{}")
        except json.JSONDecodeError:
            payload = {}
        rows.append({**row, "payload": payload})
    return rows


def _event_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("event_type") or "")
        if event_type:
            counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _session_manifest_duration_s(path: Path) -> float:
    manifest = _read_json(path)
    total = 0.0
    for block in manifest.get("blocks", []) or []:
        try:
            total += float(block.get("duration_s") or 0.0)
        except (TypeError, ValueError):
            pass
    return total


def _latest_analysis_csv(session_dir: Path, suffix: str) -> Path | None:
    matches = sorted((session_dir / "analysis").glob(f"*_{suffix}.csv"))
    return matches[-1] if matches else None


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    evaluation = dict(report.get("evaluation") or {})
    audio_mode = str(report.get("audio_mode") or "")
    validation_lane = str(report.get("validation_lane") or "")
    audio_note = (
        "It is the full-stack lane: packaged Focus Mode, OS mouse clicks, hardware ASIO audio, and local audio-evidence capture."
        if validation_lane == VALIDATION_LANE_FULL_STACK
        else "It is the software-only lane: packaged Focus Mode with wall-clock-paced validation audio and PC mouse-event emulation."
    )
    lines = [
        "# Full Realtime Participant Emulation Evaluation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- UI ready for data collection: `{report.get('ui_ready_for_data_collection')}`",
        f"- Runner exe: `{report.get('runner')}`",
        f"- Runner mode: `{report.get('runner_mode')}`",
        f"- Validation lane: `{validation_lane}`",
        f"- Audio mode: `{audio_mode}`",
        f"- Final-condition ready: `{report.get('final_condition_ready')}`",
        f"- Standard capture requested: `{report.get('standard_capture_requested')}`",
        f"- Strict Study 5 readiness requested: `{report.get('strict_study5_readiness_requested')}`",
        f"- Process exit code: `{report.get('process_exit_code')}`",
        f"- Wall-clock process duration: `{report.get('process_wall_s')}` s",
        f"- Session manifest: `{evaluation.get('session_manifest')}`",
        f"- Events CSV: `{evaluation.get('events_csv')}`",
        f"- Standard tactile cues: `{evaluation.get('standard_tactile_cue_count')}`",
        f"- Planned/observed intentional misses: `{evaluation.get('planned_miss_count')}` / `{evaluation.get('intentional_miss_count')}`",
        f"- Standard/top-up response clicks: `{evaluation.get('standard_response_click_count')}` / `{evaluation.get('topup_response_click_count')}`",
        f"- Top-up approvals: `{evaluation.get('topup_approval_count')}`",
        f"- Top-up rescue rows: `{evaluation.get('topup_rescue_row_count')}`",
        "",
        f"This is evaluation evidence only, not a public toolkit deliverable. {audio_note} It does not replace hardware loopback or participant-data collection SOPs.",
    ]
    if report.get("failures"):
        lines.extend(["", "## Failures"])
        lines.extend(f"- {failure}" for failure in report["failures"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _evaluate_focus_report(
    focus_report_path: Path,
    *,
    process_wall_s: float,
    exit_code: int | None,
    audio_mode: str = "validation-realtime",
    runner_mode: str = "packaged",
    validation_lane: str = VALIDATION_LANE_SOFTWARE_ONLY,
) -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    focus = _read_json(focus_report_path)
    if not focus:
        return {}, ["Packaged Focus Mode did not write its validation focus report."]
    session_manifest = Path(str(focus.get("session_manifest") or ""))
    session_dir = Path(str(focus.get("session_dir") or ""))
    events_csv = Path(str(focus.get("events_csv") or ""))
    events = _events(events_csv)
    counts = _event_counts(events)
    click_records = list(focus.get("validation_mouse_clicks") or [])
    plan = next((record for record in click_records if record.get("label") == "participant_emulator_plan"), {})
    intentional_misses = [
        record
        for record in click_records
        if record.get("label") == "tactile_response_plan" and record.get("action") == "deliberate_miss"
    ]
    standard_clicks = [
        record
        for record in click_records
        if record.get("label") == "tactile_response_click" and record.get("action") == "standard_click"
    ]
    topup_clicks = [
        record
        for record in click_records
        if record.get("label") == "tactile_response_click" and record.get("action") == "topup_click"
    ]
    delay_values = [
        float(record.get("actual_delay_ms") or 0.0)
        for record in standard_clicks
        if str(record.get("actual_delay_ms") or "").strip()
    ]
    approvals = list(focus.get("validation_topup_approvals") or [])
    ledger = _read_json(session_dir / "topup_ledger.json")
    topup_manifest_paths = [
        path
        for path in sorted(session_dir.glob("topup_block*manifest.csv"))
        if "draft" not in path.name.lower()
    ]
    topup_manifest_rows = [row for path in topup_manifest_paths for row in _read_csv(path)]
    rescue_rows = [
        row
        for row in topup_manifest_rows
        if str(row.get("Topup_Role") or row.get("topup_role") or "").lower() == "rescue"
    ]
    final_outcomes = _latest_analysis_csv(session_dir, "final_trial_outcomes")
    final_rows = _read_csv(final_outcomes) if final_outcomes else []
    rescued_final_rows = [
        row
        for row in final_rows
        if str(row.get("final_outcome_source") or "").lower() == "topup_rescue"
        and str(row.get("hit") or "").lower() == "true"
    ]
    expected_duration_s = 0.0
    try:
        expected_duration_s += float(focus.get("played_block_duration_s") or 0.0)
    except (TypeError, ValueError):
        pass
    if expected_duration_s <= 0:
        expected_duration_s = _session_manifest_duration_s(session_manifest)
    try:
        expected_duration_s += float(focus.get("played_instruction_duration_s") or 0.0)
    except (TypeError, ValueError):
        pass

    planned_misses = int(plan.get("planned_miss_count") or 0)
    planned_standard = int(plan.get("standard_tactile_cue_count") or 0)
    runner_label = "packaged runner" if runner_mode == "packaged" else "source runner"
    if exit_code != 0:
        failures.append(f"{runner_label.capitalize()} exited with code {exit_code}.")
    if not focus.get("completed"):
        failures.append("Focus Mode did not report completed=True.")
    hardware_realtime = str(audio_mode) == "hardware"
    full_stack = str(validation_lane) == VALIDATION_LANE_FULL_STACK
    if not hardware_realtime and not focus.get("validation_audio_realtime"):
        failures.append("The run did not use the realtime validation audio engine.")
    if full_stack:
        if not hardware_realtime:
            failures.append("Full-stack validation did not use hardware audio mode.")
        if counts.get("recording_unavailable", 0):
            failures.append(f"Full-stack validation logged recording_unavailable {counts.get('recording_unavailable')} time(s).")
        audio_evidence_wavs = sorted(session_dir.glob("*audio_evidence.wav"))
        audio_evidence_sidecars = sorted(session_dir.glob("*audio_evidence.output_evidence.json"))
        if not audio_evidence_wavs or len(audio_evidence_wavs) != len(audio_evidence_sidecars):
            failures.append(
                f"Full-stack validation requires per-block audio-evidence WAV/sidecar sets; found wavs={len(audio_evidence_wavs)} sidecars={len(audio_evidence_sidecars)}."
            )
        if counts.get("mouse_click", 0) <= 0 or counts.get("response_marker_start", 0) != counts.get("mouse_click", 0):
            failures.append(
                f"Full-stack validation requires one response_marker_start per mouse_click; mouse_click={counts.get('mouse_click', 0)} response_marker_start={counts.get('response_marker_start', 0)}."
            )
    if expected_duration_s > 0 and process_wall_s < expected_duration_s * 0.90:
        failures.append(
            f"Process wall time {process_wall_s:.1f}s was shorter than 90% of expected realtime duration {expected_duration_s:.1f}s."
        )
    if int(counts.get("block_end") or 0) < 12:
        failures.append("Fewer than 12 block_end events were logged.")
    if planned_standard <= 0:
        failures.append("The participant emulator did not see any standard tactile cues.")
    if planned_misses <= 0 or len(intentional_misses) != planned_misses:
        failures.append("Intentional misses were not planned and observed consistently.")
    if not standard_clicks:
        failures.append("No standard tactile response clicks were emitted.")
    if not delay_values or len(set(round(value, 1) for value in delay_values[:20])) < 3:
        failures.append("Standard response delays were not varied enough to look randomized.")
    if not approvals:
        failures.append("No top-up approval request was auto-approved.")
    if not topup_manifest_paths or not rescue_rows:
        failures.append("No top-up rescue manifest rows were written.")
    if len(rescue_rows) < planned_misses:
        failures.append("Top-up rescue row count is lower than the intentional miss count.")
    if len(topup_clicks) < len(rescue_rows):
        failures.append("Top-up response clicks are fewer than rescue rows.")
    if len(rescued_final_rows) < planned_misses:
        failures.append("Final outcomes do not show all intentional misses rescued by top-up.")
    planned_cues = int(focus.get("planned_tactile_cue_count") or 0)
    recentered = int(focus.get("cursor_recenter_count") or 0)
    if planned_cues <= 0 or planned_cues != recentered:
        failures.append(f"Cursor recenter count did not match planned tactile cues ({recentered}/{planned_cues}).")

    evaluation = {
        "focus_report": str(focus_report_path),
        "runner_mode": runner_mode,
        "validation_lane": validation_lane,
        "audio_mode": audio_mode,
        "hardware_audio_realtime": hardware_realtime,
        "final_condition_candidate": full_stack,
        "session_manifest": str(session_manifest),
        "session_dir": str(session_dir),
        "events_csv": str(events_csv),
        "event_counts": counts,
        "expected_realtime_duration_s": expected_duration_s,
        "played_block_duration_s": focus.get("played_block_duration_s"),
        "played_instruction_duration_s": focus.get("played_instruction_duration_s"),
        "standard_tactile_cue_count": planned_standard,
        "planned_miss_count": planned_misses,
        "intentional_miss_count": len(intentional_misses),
        "standard_response_click_count": len(standard_clicks),
        "topup_response_click_count": len(topup_clicks),
        "topup_approval_count": len(approvals),
        "topup_manifest_paths": [str(path) for path in topup_manifest_paths],
        "topup_rescue_row_count": len(rescue_rows),
        "topup_ledger_summary": ledger.get("summary", {}),
        "final_outcomes_csv": str(final_outcomes or ""),
        "final_topup_rescued_hit_count": len(rescued_final_rows),
        "cursor_recenter_count": recentered,
        "planned_tactile_cue_count": planned_cues,
        "delay_ms_min": min(delay_values) if delay_values else None,
        "delay_ms_max": max(delay_values) if delay_values else None,
    }
    return evaluation, failures


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run full realtime packaged runner participant-emulation evaluation.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--runner", type=Path, default=REPO_ROOT / "dist" / "PPSExperimentRunner" / "PPSExperimentRunner.exe")
    parser.add_argument(
        "--runner-mode",
        default="packaged",
        choices=["packaged", "source"],
        help="packaged launches dist/PPSExperimentRunner.exe; source launches windows/focus_runner_entry.py through Python.",
    )
    parser.add_argument("--profile", default=STUDY5_TEMPLATE_ID)
    parser.add_argument("--participant-id", default="P001")
    parser.add_argument("--timeout-s", type=float, default=5400.0)
    parser.add_argument("--miss-rate", type=float, default=0.06)
    parser.add_argument("--min-misses", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260615)
    parser.add_argument("--mouse-backend", default="pynput", choices=["pynput", "win32", "pyautogui", "qtest"])
    parser.add_argument(
        "--validation-lane",
        default=VALIDATION_LANE_AUTO,
        choices=[VALIDATION_LANE_AUTO, VALIDATION_LANE_SOFTWARE_ONLY, VALIDATION_LANE_FULL_STACK],
        help=(
            "auto labels validation-realtime runs as software-only and hardware/strict runs as full-stack; "
            "software-only is development evidence, full-stack is final-condition readiness evidence."
        ),
    )
    parser.add_argument(
        "--audio-mode",
        default="validation-realtime",
        choices=["validation-realtime", "hardware"],
        help="validation-realtime uses wall-clock fake audio; hardware uses the normal ASIO runner engine.",
    )
    parser.add_argument(
        "--validation-audio-chunk-frames",
        type=int,
        default=4096,
        help="Callback chunk size for validation-realtime audio mode.",
    )
    parser.add_argument(
        "--standard-capture",
        action="store_true",
        help="Leave standard LSL, local XDF, trigger dictionary, analysis CSV, and local audio-evidence recording enabled.",
    )
    parser.add_argument(
        "--audio-device-index",
        type=int,
        default=None,
        help="Validation override passed as PPS_AUDIO_DEVICE_INDEX to force a specific sounddevice output index.",
    )
    parser.add_argument(
        "--wired-loopback",
        default=WIRED_LOOPBACK_OFF,
        choices=[WIRED_LOOPBACK_OFF, WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY],
        help="Pass through the optional Focus Mode wired loopback capture mode.",
    )
    parser.add_argument("--no-lsl", action="store_true", help="With --standard-capture, still disable live LSL outlets.")
    parser.add_argument("--no-internal-xdf", action="store_true", help="With --standard-capture, still disable events.xdf.")
    parser.add_argument("--no-backup-recording", action="store_true", help="With --standard-capture, still disable local audio-evidence WAVs.")
    parser.add_argument(
        "--readiness-audit",
        action="store_true",
        help="Run the Protocol 11 Study 5 readiness audit after the full run.",
    )
    parser.add_argument(
        "--strict-study5-readiness",
        action="store_true",
        help="Run the strict final Study 5 readiness gate; implies --standard-capture and requires hardware audio mode.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    validation_lane = _apply_validation_lane_policy(args)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = args.runner.resolve()
    if args.runner_mode == "packaged" and not runner.is_file():
        raise FileNotFoundError(f"Packaged runner exe was not found: {runner}")
    focus_report_path = output_dir / "focus_validation_report.json"
    screenshot_path = output_dir / "focus_screenshot.png"
    if focus_report_path.exists():
        focus_report_path.unlink()
    if screenshot_path.exists():
        screenshot_path.unlink()

    env = _configure_validation_env(args, output_dir=output_dir, focus_report_path=focus_report_path)
    command = _build_runner_command(args, runner=runner, screenshot_path=screenshot_path)
    started = time.perf_counter()
    started_at = datetime.now().isoformat(timespec="seconds")
    process = subprocess.Popen(command, cwd=str(REPO_ROOT), env=env)
    failures: list[str] = []
    try:
        exit_code = process.wait(timeout=float(args.timeout_s))
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            exit_code = process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = process.wait(timeout=10.0)
        failures.append(f"Packaged runner exceeded timeout {args.timeout_s:.1f}s.")
    process_wall_s = time.perf_counter() - started

    evaluation, evaluation_failures = _evaluate_focus_report(
        focus_report_path,
        process_wall_s=process_wall_s,
        exit_code=exit_code,
        audio_mode=str(args.audio_mode),
        runner_mode=str(args.runner_mode),
        validation_lane=validation_lane,
    )
    focus = _annotate_focus_report(focus_report_path, args=args)
    if focus:
        evaluation["protocol11_audio_mode"] = focus.get("protocol11_audio_mode")
        evaluation["protocol11_validation_lane"] = focus.get("protocol11_validation_lane")
        evaluation["hardware_audio_realtime"] = focus.get("hardware_audio_realtime")
        evaluation["final_condition_candidate"] = focus.get("final_condition_candidate")
    _write_launch_and_preparation_reports(
        output_dir,
        args=args,
        runner=runner,
        command=command,
        pid=process.pid,
        exit_code=exit_code,
        focus_report_path=focus_report_path,
        screenshot_path=screenshot_path,
        evaluation=evaluation,
        started_at=started_at,
    )
    failures.extend(evaluation_failures)
    readiness_audit: dict[str, Any] | None = None
    if args.readiness_audit or args.strict_study5_readiness or validation_lane == VALIDATION_LANE_FULL_STACK:
        readiness_audit = audit_readiness(
            output_dir,
            output_dir=output_dir / "protocol11_study5_readiness_audit",
            require_full_study5=bool(args.strict_study5_readiness or validation_lane == VALIDATION_LANE_FULL_STACK),
            require_realtime=bool(args.strict_study5_readiness or validation_lane == VALIDATION_LANE_FULL_STACK),
        )
        if not readiness_audit.get("passed"):
            failures.append("Protocol 11 Study 5 readiness audit failed.")
        if args.strict_study5_readiness and not readiness_audit.get("full_study5_realtime_ready"):
            failures.append("Strict Study 5 readiness was not proven by the audit.")
    report = {
        "schema": SCHEMA,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "runner": str(runner),
        "runner_mode": str(args.runner_mode),
        "validation_lane": validation_lane,
        "command": command,
        "audio_mode": str(args.audio_mode),
        "wired_loopback_mode": str(getattr(args, "wired_loopback", WIRED_LOOPBACK_OFF) or WIRED_LOOPBACK_OFF),
        "standard_capture_requested": _standard_capture_requested(args),
        "audio_device_index": args.audio_device_index,
        "strict_study5_readiness_requested": bool(args.strict_study5_readiness),
        "process_exit_code": exit_code,
        "process_wall_s": process_wall_s,
        "evaluation": evaluation,
        "readiness_audit": readiness_audit or {},
        "passed": not failures,
        "ui_ready_for_data_collection": not failures,
        "final_condition_ready": bool(validation_lane == VALIDATION_LANE_FULL_STACK and not failures),
        "failures": failures,
        "notes": [
            "Evaluation-only protocol, not a toolkit deliverable.",
            "The packaged runner remains the only active experiment runner.",
            (
                "Full-stack lane exercises the normal ASIO/local audio-evidence path and is eligible for final-condition readiness when the strict audit passes."
                if validation_lane == VALIDATION_LANE_FULL_STACK
                else "Software-only lane is wall-clock paced through a validation engine; it proves full-duration UI/software survival and top-up behavior, not hardware readiness."
            ),
        ],
    }
    _write_json(output_dir / "full_realtime_participant_emulation_report.json", report)
    _write_markdown(output_dir / "full_realtime_participant_emulation_report.md", report)
    print(f"Wrote full realtime participant emulation report: {output_dir / 'full_realtime_participant_emulation_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
