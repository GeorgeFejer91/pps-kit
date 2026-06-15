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
STUDY5_TEMPLATE_ID = "study5_box_breathing_pps"
SCHEMA = "pps-full-realtime-participant-emulation-evaluation.v1"


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
    lines = [
        "# Full Realtime Participant Emulation Evaluation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- UI ready for data collection: `{report.get('ui_ready_for_data_collection')}`",
        f"- Runner exe: `{report.get('runner')}`",
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
        "This is evaluation evidence only, not a public toolkit deliverable. It uses the packaged runner with hidden validation hooks, wall-clock-paced software audio, and PC mouse-event emulation. It does not replace hardware loopback or participant-data collection SOPs.",
    ]
    if report.get("failures"):
        lines.extend(["", "## Failures"])
        lines.extend(f"- {failure}" for failure in report["failures"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _evaluate_focus_report(focus_report_path: Path, *, process_wall_s: float, exit_code: int | None) -> tuple[dict[str, Any], list[str]]:
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
    if exit_code != 0:
        failures.append(f"Packaged runner exited with code {exit_code}.")
    if not focus.get("completed"):
        failures.append("Focus Mode did not report completed=True.")
    if not focus.get("validation_audio_realtime"):
        failures.append("The run did not use the realtime validation audio engine.")
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
    parser.add_argument("--profile", default=STUDY5_TEMPLATE_ID)
    parser.add_argument("--participant-id", default="P001")
    parser.add_argument("--timeout-s", type=float, default=5400.0)
    parser.add_argument("--miss-rate", type=float, default=0.06)
    parser.add_argument("--min-misses", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260615)
    parser.add_argument("--mouse-backend", default="pynput", choices=["pynput", "win32", "pyautogui", "qtest"])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    output_dir = (args.output_dir or _default_output_dir()).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = args.runner.resolve()
    if not runner.is_file():
        raise FileNotFoundError(f"Packaged runner exe was not found: {runner}")
    focus_report_path = output_dir / "full_realtime_focus_report.json"
    if focus_report_path.exists():
        focus_report_path.unlink()

    env = os.environ.copy()
    env.pop("QT_QPA_PLATFORM", None)
    env["PPS_FOCUS_VALIDATION_REALTIME_AUDIO"] = "1"
    env["PPS_FOCUS_VALIDATION_AUDIO_CHUNK_FRAMES"] = "4096"
    env["PPS_FOCUS_VALIDATION_PARTICIPANT_EMULATOR"] = "1"
    env["PPS_FOCUS_VALIDATION_AUTO_APPROVE_TOPUP"] = "1"
    env["PPS_FOCUS_VALIDATION_MOUSE_BACKEND"] = str(args.mouse_backend)
    env["PPS_FOCUS_VALIDATION_PARTICIPANT_SEED"] = str(int(args.seed))
    env["PPS_FOCUS_VALIDATION_PARTICIPANT_MISS_RATE"] = str(float(args.miss_rate))
    env["PPS_FOCUS_VALIDATION_PARTICIPANT_MIN_MISSES"] = str(int(args.min_misses))
    env["PPS_FOCUS_VALIDATION_REPORT"] = str(focus_report_path)
    env["PPS_FOCUS_DISABLE_PREWARM"] = "1"

    command = [
        str(runner),
        "--profile",
        str(args.profile),
        "--participant-id",
        str(args.participant_id),
        "--manual-start",
        "--enable-missed-trial-topup",
        "--no-lsl",
        "--no-internal-xdf",
        "--no-backup-recording",
    ]
    started = time.perf_counter()
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
    )
    failures.extend(evaluation_failures)
    report = {
        "schema": SCHEMA,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "runner": str(runner),
        "command": command,
        "process_exit_code": exit_code,
        "process_wall_s": process_wall_s,
        "evaluation": evaluation,
        "passed": not failures,
        "ui_ready_for_data_collection": not failures,
        "failures": failures,
        "notes": [
            "Evaluation-only protocol, not a toolkit deliverable.",
            "The packaged runner remains the only active experiment runner.",
            "Audio is wall-clock paced through a validation engine; this proves full-duration UI/software survival and top-up behavior, not hardware latency.",
        ],
    }
    _write_json(output_dir / "full_realtime_participant_emulation_report.json", report)
    _write_markdown(output_dir / "full_realtime_participant_emulation_report.md", report)
    print(f"Wrote full realtime participant emulation report: {output_dir / 'full_realtime_participant_emulation_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
