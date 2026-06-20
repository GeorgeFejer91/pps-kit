"""Run a full Study 5 mock rehearsal into a fresh Desktop output folder.

This validation orchestrates the normal packaged Focus Mode runner with a
scripted participant, hardware audio, wired loopback, local WAV/CSV/XDF outputs,
and optional continuous external LabRecorder XDF capture.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from collections.abc import Iterator
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_full_realtime_participant_emulation as emulator  # noqa: E402
from run_labrecorder_lsl_xdf_stress import (  # noqa: E402
    _find_labrecorder_cli,
    _load_xdf_streams,
    _stats,
    _stop_labrecorder,
    _write_csv,
    compare_xdf_to_local,
)
from peripersonal_space_toolkit.focus_app import initiate_data_collection_environment  # noqa: E402
from peripersonal_space_toolkit.output_layout import output_validation_reports_dir  # noqa: E402
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY,
    WIRED_LOOPBACK_OFF,
    normalize_wired_loopback_mode,
)
from peripersonal_space_toolkit.timing_events import LSL_MARKER_CHANNELS  # noqa: E402


SCHEMA = "pps-desktop-full-mock-rehearsal.v1"


def _default_desktop_output_parent() -> Path:
    home = Path(os.environ.get("USERPROFILE") or Path.home()).expanduser()
    desktop = home / "Desktop"
    return desktop if desktop.exists() else home


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
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


def _resolve_path(value: Any, *, base: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return Path()
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _audio_route_preflight() -> dict[str, Any]:
    os.environ.setdefault("SD_ENABLE_ASIO", "1")
    try:
        import sounddevice as sd  # type: ignore
    except Exception as exc:
        return {"checked": True, "komplete_asio_4x4_ready": False, "error": str(exc), "candidates": []}
    try:
        hostapis = sd.query_hostapis()
        devices = sd.query_devices()
    except Exception as exc:
        return {"checked": True, "komplete_asio_4x4_ready": False, "error": str(exc), "candidates": []}
    candidates: list[dict[str, Any]] = []
    for index, device in enumerate(devices):
        hostapi_index = int(device.get("hostapi", -1))
        hostapi_name = str(hostapis[hostapi_index].get("name", "")) if 0 <= hostapi_index < len(hostapis) else ""
        name = str(device.get("name", ""))
        candidate = {
            "index": index,
            "name": name,
            "hostapi": hostapi_name,
            "max_input_channels": int(device.get("max_input_channels", 0)),
            "max_output_channels": int(device.get("max_output_channels", 0)),
        }
        if "komplete" in name.lower() or "komplete" in hostapi_name.lower():
            candidates.append(candidate)
    ready = any(
        "asio" in row["hostapi"].lower()
        and row["max_input_channels"] >= 4
        and row["max_output_channels"] >= 4
        for row in candidates
    )
    return {"checked": True, "komplete_asio_4x4_ready": bool(ready), "error": "", "candidates": candidates}


def build_emulator_argv(args: argparse.Namespace, *, output_dir: Path) -> list[str]:
    argv = [
        "--output-dir",
        str(output_dir),
        "--runner",
        str(args.runner),
        "--runner-mode",
        str(args.runner_mode),
        "--profile",
        str(args.profile),
        "--participant-id",
        str(args.participant_id),
        "--timeout-s",
        str(float(args.timeout_s)),
        "--miss-rate",
        str(float(args.miss_rate)),
        "--min-misses",
        str(int(args.min_misses)),
        "--seed",
        str(int(args.seed)),
        "--mouse-backend",
        str(args.mouse_backend),
        "--validation-lane",
        str(args.validation_lane),
        "--audio-mode",
        str(args.audio_mode),
        "--validation-audio-chunk-frames",
        str(int(args.validation_audio_chunk_frames)),
        "--wired-loopback",
        str(args.wired_loopback),
    ]
    if args.audio_device_index is not None:
        argv.extend(["--audio-device-index", str(int(args.audio_device_index))])
    if bool(args.strict_study5_readiness):
        argv.append("--strict-study5-readiness")
    return argv


def _create_rehearsal_environment(args: argparse.Namespace) -> dict[str, Any]:
    capture_options = SessionCaptureOptions(
        wired_loopback_mode=normalize_wired_loopback_mode(args.wired_loopback),
    )
    return initiate_data_collection_environment(
        parent_folder=Path(args.desktop_output_parent).expanduser(),
        profile_id=str(args.profile),
        session_name=str(args.session_name),
        participant_id=str(args.participant_id),
        capture_options=capture_options,
    )


def _start_labrecorder_session(
    *,
    labrecorder_cli: Path,
    xdf_path: Path,
    startup_s: float,
) -> tuple[subprocess.Popen, list[str]]:
    xdf_path.parent.mkdir(parents=True, exist_ok=True)
    predicates = ["name='PPSMarkersV2'", "name='PPSTriggerCodes'"]
    command = [str(labrecorder_cli), str(xdf_path), *predicates]
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )
    time.sleep(max(0.0, startup_s))
    if process.poll() is not None:
        stdout, stderr = process.communicate(timeout=2.0)
        raise RuntimeError(
            "LabRecorderCLI exited before the rehearsal started. "
            f"returncode={process.returncode} stdout={stdout!r} stderr={stderr!r}"
        )
    return process, command


def _session_output_paths(validation_dir: Path) -> dict[str, Path]:
    focus_report = _read_json(validation_dir / "focus_validation_report.json")
    session_manifest = _resolve_path(focus_report.get("session_manifest"), base=validation_dir)
    manifest = _read_json(session_manifest)
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    manifest_base = session_manifest.parent if session_manifest.parent != Path() else validation_dir
    session_dir = _resolve_path(focus_report.get("session_dir"), base=validation_dir)
    events_csv = _resolve_path(focus_report.get("events_csv") or outputs.get("verbose_events_csv"), base=manifest_base)
    lsl_markers_csv = _resolve_path(outputs.get("lsl_markers_csv"), base=manifest_base)
    return {
        "session_dir": session_dir,
        "session_manifest": session_manifest,
        "events_csv": events_csv,
        "lsl_markers_csv": lsl_markers_csv,
    }


def reconcile_external_labrecorder_xdf(
    *,
    validation_dir: Path,
    xdf_path: Path,
    labrecorder_cli: Path | None,
    labrecorder_command: list[str],
    labrecorder_returncode: int | None,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
    output_dir = validation_dir / "external_labrecorder_reconciliation"
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _session_output_paths(validation_dir)
    if not xdf_path.is_file() or xdf_path.stat().st_size == 0:
        report = {
            "schema": "pps-desktop-rehearsal-external-labrecorder.v1",
            "passed": False,
            "xdf_path": str(xdf_path),
            "labrecorder_cli": str(labrecorder_cli or ""),
            "labrecorder_command": labrecorder_command,
            "labrecorder_returncode": labrecorder_returncode,
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "error": "External LabRecorder did not produce a non-empty XDF file.",
        }
        _write_json(output_dir / "external_labrecorder_reconciliation_report.json", report)
        _write_markdown_report(output_dir / "external_labrecorder_reconciliation_report.md", report)
        return report

    rich_rows, numeric_rows, _header = _load_xdf_streams(xdf_path)
    _write_csv(output_dir / "external_labrecorder_rich_xdf_samples.csv", rich_rows, [*LSL_MARKER_CHANNELS, "sample_lsl_timestamp"])
    _write_csv(output_dir / "external_labrecorder_numeric_xdf_samples.csv", numeric_rows, ["event_code", "sample_lsl_timestamp"])
    marker_rows = _read_csv(paths["lsl_markers_csv"])
    comparison = compare_xdf_to_local(rich_rows=rich_rows, numeric_rows=numeric_rows, marker_rows=marker_rows)
    event_type_counts = comparison.get("event_type_counts_xdf") or {}
    block_indices = sorted(
        {
            str(row.get("block_index", "")).strip()
            for row in rich_rows
            if str(row.get("block_index", "")).strip()
        }
    )
    timestamp_deltas = [
        (float(rich["sample_lsl_timestamp"]) - float(marker["lsl_timestamp"])) * 1000.0
        for rich, marker in zip(rich_rows, marker_rows)
        if str(rich.get("sample_lsl_timestamp", "")).strip() and str(marker.get("lsl_timestamp", "")).strip()
    ]
    report = {
        "schema": "pps-desktop-rehearsal-external-labrecorder.v1",
        "passed": bool(comparison.get("passed")),
        "xdf_path": str(xdf_path),
        "labrecorder_cli": str(labrecorder_cli or ""),
        "labrecorder_command": labrecorder_command,
        "labrecorder_returncode": labrecorder_returncode,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "session_dir": str(paths["session_dir"]),
        "session_manifest": str(paths["session_manifest"]),
        "events_csv": str(paths["events_csv"]),
        "lsl_markers_csv": str(paths["lsl_markers_csv"]),
        "rich_xdf_samples_csv": str(output_dir / "external_labrecorder_rich_xdf_samples.csv"),
        "numeric_xdf_samples_csv": str(output_dir / "external_labrecorder_numeric_xdf_samples.csv"),
        "block_indices_observed": block_indices,
        "event_type_counts_xdf": event_type_counts,
        "timestamp_delta_xdf_minus_local_marker_ms": _stats(timestamp_deltas),
        "comparison": comparison,
        "limitations": [
            "This is one continuous external XDF for the whole rehearsal; block identity is preserved by LSL marker fields.",
            "This validates external LSL/XDF capture and metadata reconciliation, not tactile perception or Woojer mechanical onset.",
        ],
    }
    _write_json(output_dir / "external_labrecorder_reconciliation_report.json", report)
    _write_markdown_report(output_dir / "external_labrecorder_reconciliation_report.md", report)
    return report


def _write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Desktop Full Mock Rehearsal",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Output root: `{report.get('environment_root', '')}`",
        f"- Validation dir: `{report.get('validation_dir', report.get('output_dir', ''))}`",
        f"- External XDF: `{report.get('xdf_path', '')}`",
        f"- Error: `{report.get('error', '')}`" if report.get("error") else "",
    ]
    comparison = report.get("comparison") if isinstance(report.get("comparison"), dict) else {}
    if comparison:
        lines.extend(
            [
                "",
                "## External XDF",
                "",
                f"- Expected markers: `{comparison.get('expected_marker_count')}`",
                f"- Rich XDF samples: `{comparison.get('rich_xdf_sample_count')}`",
                f"- Numeric XDF samples: `{comparison.get('numeric_xdf_sample_count')}`",
                f"- Missing event IDs: `{comparison.get('missing_event_ids') or []}`",
                f"- Field mismatches: `{comparison.get('field_mismatches') or []}`",
            ]
        )
    limitations = report.get("limitations") or []
    if limitations:
        lines.extend(["", "## Limitations", ""])
        for limitation in limitations:
            lines.append(f"- {limitation}")
    path.write_text("\n".join(line for line in lines if line != "") + "\n", encoding="utf-8")


@contextmanager
def _temporary_env(updates: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_rehearsal(args: argparse.Namespace) -> dict[str, Any]:
    parent = Path(args.desktop_output_parent).expanduser()
    if not parent.is_dir():
        raise ValueError(f"Desktop output parent does not exist: {parent}")
    runner = Path(args.runner).expanduser()
    if args.runner_mode == "packaged" and not runner.is_file():
        raise FileNotFoundError(f"Packaged runner exe was not found: {runner}")
    if args.wired_loopback != WIRED_LOOPBACK_OFF and args.audio_mode != "hardware":
        raise ValueError("Wired loopback rehearsal requires --audio-mode hardware.")
    audio_preflight = _audio_route_preflight() if not args.skip_audio_preflight else {"checked": False}
    if (
        not args.skip_audio_preflight
        and args.validation_lane == emulator.VALIDATION_LANE_FULL_STACK
        and not audio_preflight.get("komplete_asio_4x4_ready")
    ):
        raise RuntimeError("Komplete Audio ASIO 4-input/4-output route was not found; inspect the audio_preflight field.")

    environment = _create_rehearsal_environment(args)
    environment_root = Path(environment["environment_root"]).resolve()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    validation_dir = output_validation_reports_dir(environment_root) / f"mock_rehearsal_{stamp}"
    validation_dir.mkdir(parents=True, exist_ok=True)
    start_ready_file = validation_dir / "external_labrecorder.ready"
    if start_ready_file.exists():
        start_ready_file.unlink()

    labrecorder_process: subprocess.Popen | None = None
    labrecorder_cli: Path | None = None
    labrecorder_command: list[str] = []
    labrecorder_returncode: int | None = None
    stdout_path = validation_dir / "external_labrecorder_stdout.txt"
    stderr_path = validation_dir / "external_labrecorder_stderr.txt"
    external_report: dict[str, Any] = {"checked": False, "passed": True}
    xdf_path = validation_dir / "session_external_labrecorder.xdf"

    _write_json(
        validation_dir / "desktop_full_mock_rehearsal_preflight.json",
        {
            "schema": SCHEMA + ".preflight",
            "environment": environment,
            "audio_preflight": audio_preflight,
            "external_labrecorder_requested": bool(args.external_labrecorder),
            "wired_loopback": str(args.wired_loopback),
        },
    )

    if args.external_labrecorder:
        labrecorder_cli = _find_labrecorder_cli(args.labrecorder_cli)
        labrecorder_process, labrecorder_command = _start_labrecorder_session(
            labrecorder_cli=labrecorder_cli,
            xdf_path=xdf_path,
            startup_s=float(args.labrecorder_startup_s),
        )
        start_ready_file.write_text(
            json.dumps({"labrecorder_pid": labrecorder_process.pid, "xdf_path": str(xdf_path)}, indent=2) + "\n",
            encoding="utf-8",
        )

    env_updates: dict[str, str] = {}
    if args.external_labrecorder:
        env_updates = {
            "PPS_FOCUS_VALIDATION_START_READY_FILE": str(start_ready_file),
            "PPS_FOCUS_VALIDATION_START_READY_TIMEOUT_S": str(float(args.start_ready_timeout_s)),
        }
    emulator_argv = build_emulator_argv(args, output_dir=validation_dir)
    harness_exit_code = 1
    harness_error = ""
    try:
        with _temporary_env(env_updates):
            harness_exit_code = int(emulator.main(emulator_argv))
    except Exception as exc:
        harness_error = str(exc)
    finally:
        if labrecorder_process is not None:
            labrecorder_returncode, stdout, stderr = _stop_labrecorder(
                labrecorder_process,
                timeout_s=float(args.labrecorder_stop_timeout_s),
            )
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")

    if args.external_labrecorder:
        external_report = reconcile_external_labrecorder_xdf(
            validation_dir=validation_dir,
            xdf_path=xdf_path,
            labrecorder_cli=labrecorder_cli,
            labrecorder_command=labrecorder_command,
            labrecorder_returncode=labrecorder_returncode,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        external_report["checked"] = True

    harness_report = _read_json(validation_dir / "full_realtime_participant_emulation_report.json")
    focus_report = _read_json(validation_dir / "focus_validation_report.json")
    passed = harness_exit_code == 0 and bool(harness_report.get("passed")) and bool(external_report.get("passed", True)) and not harness_error
    report = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "passed": bool(passed),
        "full_mock_rehearsal_ready": bool(passed),
        "environment_root": str(environment_root),
        "validation_dir": str(validation_dir),
        "profile_id": str(args.profile),
        "participant_id": str(args.participant_id),
        "session_name": str(args.session_name),
        "runner": str(runner),
        "runner_mode": str(args.runner_mode),
        "audio_mode": str(args.audio_mode),
        "validation_lane": str(args.validation_lane),
        "mouse_backend": str(args.mouse_backend),
        "wired_loopback": str(args.wired_loopback),
        "external_labrecorder_requested": bool(args.external_labrecorder),
        "audio_preflight": audio_preflight,
        "emulator_argv": emulator_argv,
        "harness_exit_code": harness_exit_code,
        "harness_error": harness_error,
        "harness_report": str(validation_dir / "full_realtime_participant_emulation_report.json"),
        "focus_report": str(validation_dir / "focus_validation_report.json"),
        "session_dir": str(focus_report.get("session_dir") or ""),
        "external_labrecorder": external_report,
        "limitations": [
            "Emulated participant responses prove operational data-shape and capture behavior, not human perception or fatigue.",
            "The wired loopback records an analog duplicate tactile proxy from Output 4 to Input 4, not Woojer mechanical onset.",
        ],
    }
    _write_json(validation_dir / "desktop_full_mock_rehearsal_report.json", report)
    _write_markdown_report(validation_dir / "desktop_full_mock_rehearsal_report.md", report)
    print(f"Wrote desktop full mock rehearsal report: {validation_dir / 'desktop_full_mock_rehearsal_report.json'}")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a full Desktop Study 5 mock rehearsal with emulated participant responses.")
    parser.add_argument("--desktop-output-parent", type=Path, default=_default_desktop_output_parent())
    parser.add_argument("--session-name", default="study_5_full_mock_rehearsal")
    parser.add_argument("--profile", default=emulator.STUDY5_TEMPLATE_ID)
    parser.add_argument("--participant-id", default="P050")
    parser.add_argument("--runner", type=Path, default=REPO_ROOT / "dist" / "PPSExperimentRunner" / "PPSExperimentRunner.exe")
    parser.add_argument("--runner-mode", default="packaged", choices=["packaged", "source"])
    parser.add_argument("--timeout-s", type=float, default=7200.0)
    parser.add_argument("--miss-rate", type=float, default=0.06)
    parser.add_argument("--min-misses", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260615)
    parser.add_argument("--mouse-backend", default="pynput", choices=["pynput", "win32", "pyautogui", "qtest"])
    parser.add_argument(
        "--validation-lane",
        default=emulator.VALIDATION_LANE_FULL_STACK,
        choices=[emulator.VALIDATION_LANE_SOFTWARE_ONLY, emulator.VALIDATION_LANE_FULL_STACK],
    )
    parser.add_argument("--audio-mode", default="hardware", choices=["validation-realtime", "hardware"])
    parser.add_argument("--validation-audio-chunk-frames", type=int, default=4096)
    parser.add_argument("--audio-device-index", type=int, default=None)
    parser.add_argument(
        "--wired-loopback",
        default=WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY,
        choices=[WIRED_LOOPBACK_OFF, WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY],
    )
    parser.add_argument("--external-labrecorder", action="store_true")
    parser.add_argument("--labrecorder-cli", type=Path, default=None)
    parser.add_argument("--labrecorder-startup-s", type=float, default=2.5)
    parser.add_argument("--labrecorder-stop-timeout-s", type=float, default=8.0)
    parser.add_argument("--start-ready-timeout-s", type=float, default=60.0)
    parser.add_argument("--strict-study5-readiness", dest="strict_study5_readiness", action="store_true", default=True)
    parser.add_argument("--no-strict-study5-readiness", dest="strict_study5_readiness", action="store_false")
    parser.add_argument("--skip-audio-preflight", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_rehearsal(args)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
