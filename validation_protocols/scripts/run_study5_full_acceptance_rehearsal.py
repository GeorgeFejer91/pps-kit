#!/usr/bin/env python
"""Run the Study 5 pink/white full acceptance rehearsal gate sequence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_ID = "study5_box_breathing_pps"
SCHEMA = "pps-study5-full-acceptance-rehearsal.v1"
DEFAULT_RUNNER = REPO_ROOT / "dist" / "PPSExperimentRunner" / "PPSExperimentRunner.exe"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the full Study 5 acceptance rehearsal campaign.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--profile", default=PROFILE_ID)
    parser.add_argument("--participant-id", default="P050")
    parser.add_argument("--runner", type=Path, default=DEFAULT_RUNNER)
    parser.add_argument("--session-name", default="study5_full_acceptance")
    parser.add_argument("--labrecorder-cli", type=Path, default=None)
    parser.add_argument("--timeout-s", type=float, default=7200.0)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-static", action="store_true")
    parser.add_argument("--skip-ui", action="store_true")
    parser.add_argument("--skip-hardware", action="store_true")
    return parser


def run_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = (
        args.output_dir
        or REPO_ROOT
        / "artifacts"
        / "validation_runs"
        / f"study5_full_acceptance_{time.strftime('%Y%m%d_%H%M%S')}"
    ).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    commands_dir = output_dir / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    gates: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {
        "output_dir": str(output_dir),
        "runner": str(Path(args.runner).resolve()),
        "profile": str(args.profile),
        "participant_id": str(args.participant_id),
    }

    _record_gate(gates, "close_open_runner_windows", "runner_package", _close_open_runners(commands_dir))

    runner = Path(args.runner).resolve()
    before_mtime = runner.stat().st_mtime if runner.is_file() else 0.0
    if args.skip_build:
        _record_gate(gates, "rebuild_packaged_runner", "runner_package", {"passed": True, "skipped": True, "detail": "--skip-build"})
    else:
        build = _run_command(
            "rebuild_packaged_runner",
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "windows" / "Build_Experiment_Runner_Exe.ps1"),
            ],
            commands_dir=commands_dir,
            timeout_s=1800,
        )
        _record_gate(gates, "rebuild_packaged_runner", "runner_package", build)
        if not build["passed"]:
            return _finalize(output_dir, gates, evidence)
        after_mtime = runner.stat().st_mtime if runner.is_file() else 0.0
        fresh = runner.is_file() and after_mtime > before_mtime
        _record_gate(
            gates,
            "rebuilt_runner_is_newer",
            "runner_package",
            {
                "passed": fresh,
                "runner": str(runner),
                "before_mtime": before_mtime,
                "after_mtime": after_mtime,
            },
        )
        if not fresh:
            return _finalize(output_dir, gates, evidence)

    if not args.skip_static:
        static_ok = _run_static_gates(commands_dir, gates)
        if not static_ok:
            return _finalize(output_dir, gates, evidence)
    else:
        _record_gate(gates, "static_profile_truth_gates", "profile_config", {"passed": True, "skipped": True, "detail": "--skip-static"})

    probe = _materialize_package_probe(output_dir=output_dir, args=args)
    _record_gate(gates, "materialize_fresh_p050_package", "generation", probe)
    if not probe["passed"]:
        return _finalize(output_dir, gates, evidence)
    evidence["package_probe"] = probe

    audit_probe = _run_command(
        "gate3_baseline_propagation_audit",
        [
            sys.executable,
            str(SCRIPT_DIR / "audit_study5_baseline_propagation.py"),
            "--profile-dir",
            str(probe["profile_dir"]),
            "--session-manifest",
            str(probe["session_manifest"]),
            "--output-dir",
            str(output_dir / "gate3_baseline_propagation"),
        ],
        commands_dir=commands_dir,
        timeout_s=900,
    )
    _record_gate(gates, "gate3_package_block_consistency", "generation", audit_probe)
    if not audit_probe["passed"]:
        return _finalize(output_dir, gates, evidence)

    if not args.skip_ui:
        ui = _run_command(
            "gate2_study5_ui_mouse_path",
            [
                sys.executable,
                str(SCRIPT_DIR / "run_study5_end_to_end_ui_mouse_validation.py"),
                "--output-dir",
                str(output_dir / "gate2_ui_mouse"),
                "--participant-id",
                str(args.participant_id),
                "--standalone-launcher",
                "--packaged-standalone-app",
                "--packaged-runner",
                str(runner),
            ],
            commands_dir=commands_dir,
            timeout_s=900,
        )
        _record_gate(gates, "gate2_gui_mouse_path", "gui", ui)
        if not ui["passed"]:
            return _finalize(output_dir, gates, evidence)
    else:
        _record_gate(gates, "gate2_gui_mouse_path", "gui", {"passed": True, "skipped": True, "detail": "--skip-ui"})

    if args.skip_hardware:
        _record_gate(gates, "gate4_full_hardware_rehearsal", "audio_hardware", {"passed": True, "skipped": True, "detail": "--skip-hardware"})
        return _finalize(output_dir, gates, evidence)

    desktop_parent = output_dir / "desktop_rehearsals"
    desktop_parent.mkdir(parents=True, exist_ok=True)
    full_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "run_desktop_full_mock_rehearsal.py"),
        "--desktop-output-parent",
        str(desktop_parent),
        "--session-name",
        str(args.session_name),
        "--profile",
        str(args.profile),
        "--participant-id",
        str(args.participant_id),
        "--runner",
        str(runner),
        "--runner-mode",
        "packaged",
        "--audio-mode",
        "hardware",
        "--validation-lane",
        "full-stack",
        "--wired-loopback",
        "output4-tactile-proxy",
        "--external-labrecorder",
        "--strict-study5-readiness",
        "--timeout-s",
        str(float(args.timeout_s)),
    ]
    if args.labrecorder_cli is not None:
        full_cmd.extend(["--labrecorder-cli", str(args.labrecorder_cli)])
    full_rehearsal = _run_command(
        "gate4_full_hardware_rehearsal",
        full_cmd,
        commands_dir=commands_dir,
        timeout_s=float(args.timeout_s) + 600,
    )
    _record_gate(gates, "gate4_full_hardware_rehearsal", "audio_hardware", full_rehearsal)
    if not full_rehearsal["passed"]:
        return _finalize(output_dir, gates, evidence)

    rehearsal_report_path = _latest_report(desktop_parent, "desktop_full_mock_rehearsal_report.json")
    rehearsal_report = _read_json(rehearsal_report_path)
    validation_dir = Path(str(rehearsal_report.get("validation_dir") or "")).resolve()
    environment_root = Path(str(rehearsal_report.get("environment_root") or "")).resolve()
    session_dir = Path(str(rehearsal_report.get("session_dir") or "")).resolve()
    focus_report = _read_json(validation_dir / "focus_validation_report.json")
    session_manifest = _resolve_path(focus_report.get("session_manifest"), base=validation_dir)
    evidence["full_rehearsal"] = {
        "report": str(rehearsal_report_path),
        "environment_root": str(environment_root),
        "validation_dir": str(validation_dir),
        "session_dir": str(session_dir),
        "session_manifest": str(session_manifest),
    }
    _record_gate(
        gates,
        "full_rehearsal_report_discovery",
        "analysis",
        {
            "passed": rehearsal_report_path.is_file()
            and _is_dir(validation_dir)
            and _is_dir(environment_root)
            and _path_exists(session_manifest),
            **evidence["full_rehearsal"],
        },
    )
    if not gates[-1]["passed"]:
        return _finalize(output_dir, gates, evidence)

    protocol11 = _run_command(
        "gate5_protocol11_readiness",
        [
            sys.executable,
            str(SCRIPT_DIR / "audit_protocol11_study5_readiness.py"),
            "--artifact-dir",
            str(validation_dir),
            "--session-dir",
            str(session_dir),
            "--output-dir",
            str(validation_dir / "protocol11_study5_readiness_audit"),
            "--require-full-study5",
            "--require-realtime",
        ],
        commands_dir=commands_dir,
        timeout_s=900,
    )
    _record_gate(gates, "gate5_protocol11_readiness", "analysis", protocol11)
    if not protocol11["passed"]:
        return _finalize(output_dir, gates, evidence)

    drift = _run_command(
        "gate5_wired_lsl_xdf_drift",
        [
            sys.executable,
            str(SCRIPT_DIR / "audit_full_session_wired_lsl_xdf_drift.py"),
            "--rehearsal-root",
            str(environment_root),
            "--validation-dir",
            str(validation_dir),
            "--output-dir",
            str(validation_dir / "wired_lsl_xdf_tactile_drift_gate"),
        ],
        commands_dir=commands_dir,
        timeout_s=900,
    )
    _record_gate(gates, "gate5_wired_lsl_xdf_drift", "wired_loopback", drift)
    if not drift["passed"]:
        return _finalize(output_dir, gates, evidence)

    profile_dir = _profile_dir_from_session_manifest(session_manifest)
    final_baseline = _run_command(
        "gate5_final_session_baseline_propagation_audit",
        [
            sys.executable,
            str(SCRIPT_DIR / "audit_study5_baseline_propagation.py"),
            "--profile-dir",
            str(profile_dir),
            "--session-manifest",
            str(session_manifest),
            "--output-dir",
            str(validation_dir / "study5_baseline_propagation_audit"),
        ],
        commands_dir=commands_dir,
        timeout_s=900,
    )
    _record_gate(gates, "gate5_final_session_baseline_propagation", "analysis", final_baseline)
    return _finalize(output_dir, gates, evidence)


def _run_static_gates(commands_dir: Path, gates: list[dict[str, Any]]) -> bool:
    pytest_gate = _run_command(
        "gate1_targeted_pytest",
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_dashboard_app.py::test_dashboard_validates_full_study5_segment0_to_3_pipeline",
            "tests/test_dashboard_app.py::test_dashboard_study5_profile_preserves_trial_budget_with_two_sources",
            "tests/test_focus_app.py::test_launcher_initiate_button_creates_environment_and_opens_operations",
            "tests/test_validation_protocols.py::test_desktop_full_mock_rehearsal_delegates_to_full_stack_harness",
            "tests/test_validation_protocols.py::test_desktop_full_mock_rehearsal_uses_runner_owned_labrecorder",
            "tests/test_validation_protocols.py::test_study5_baseline_no_looming_metrics_require_instruction_audio",
            "tests/test_validation_protocols.py::test_study5_prepared_block_audit_flags_baseline_silent",
            "-q",
        ],
        commands_dir=commands_dir,
        timeout_s=900,
    )
    _record_gate(gates, "gate1_targeted_pytest", "profile_config", pytest_gate)
    if not pytest_gate["passed"]:
        return False
    parity = _run_command(
        "gate1_static_dashboard_preview_parity",
        [
            sys.executable,
            str(SCRIPT_DIR / "run_static_dashboard_preview_parity_audit.py"),
            "--template",
            PROFILE_ID,
            "--output-dir",
            str(commands_dir.parent / "gate1_static_dashboard_preview_parity"),
        ],
        commands_dir=commands_dir,
        timeout_s=900,
    )
    _record_gate(gates, "gate1_static_dashboard_preview_parity", "profile_config", parity)
    if not parity["passed"]:
        return False
    matrix = _run_command(
        "gate1_profile_recreation_interface_matrix",
        [
            sys.executable,
            str(SCRIPT_DIR / "run_profile_recreation_interface_matrix.py"),
            "--template",
            PROFILE_ID,
            "--skip-blocked-samples",
            "--output-dir",
            str(commands_dir.parent / "gate1_profile_recreation_interface_matrix"),
        ],
        commands_dir=commands_dir,
        timeout_s=1200,
    )
    _record_gate(gates, "gate1_profile_recreation_interface_matrix", "profile_config", matrix)
    return bool(matrix["passed"])


def _materialize_package_probe(*, output_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    try:
        from peripersonal_space_toolkit.focus_app import initiate_data_collection_environment
        from peripersonal_space_toolkit.session_runner import (
            SessionCaptureOptions,
            WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY,
        )

        parent = output_dir / "gate3_package_probe_parent"
        parent.mkdir(parents=True, exist_ok=True)
        capture = SessionCaptureOptions(
            wired_loopback_mode=WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY,
            start_external_labrecorder=True,
            external_labrecorder_cli=str(args.labrecorder_cli or ""),
        )
        result = initiate_data_collection_environment(
            parent_folder=parent,
            profile_id=str(args.profile),
            session_name=f"{args.session_name}_package_probe",
            participant_id=str(args.participant_id),
            capture_options=capture,
        )
        environment_root = Path(str(result.get("environment_root") or "")).resolve()
        profile_dir = Path(str((result.get("bridge") or {}).get("acquisition_profile_snapshot_dir") or "")).resolve()
        session_manifest = _find_nested_session_manifest(result) or _latest_report(environment_root, "session_manifest.json")
        return {
            "passed": _is_dir(environment_root) and _is_dir(profile_dir) and _path_exists(session_manifest),
            "environment_root": str(environment_root),
            "profile_dir": str(profile_dir),
            "session_manifest": str(session_manifest),
            "raw_result_path": str(output_dir / "gate3_package_probe_result.json"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"passed": False, "reason": str(exc), "category": "generation"}


def _find_nested_session_manifest(value: Any) -> Path | None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"manifest_path", "session_manifest", "session_manifest_path"}:
                path = Path(str(item)).expanduser()
                if _path_exists(path) and path.name == "session_manifest.json":
                    return path.resolve()
            found = _find_nested_session_manifest(item)
            if found is not None:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_nested_session_manifest(item)
            if found is not None:
                return found
    return None


def _profile_dir_from_session_manifest(session_manifest: Path) -> Path:
    manifest = _read_json(session_manifest)
    run_setup = _resolve_path(manifest.get("source_run_setup_manifest_path"), base=session_manifest.parent)
    if _path_exists(run_setup):
        return run_setup.resolve().parents[1]
    context_dir = _resolve_path(manifest.get("context_dir"), base=session_manifest.parent)
    candidate = context_dir / "profile_snapshot" / PROFILE_ID
    if _is_dir(candidate):
        return candidate.resolve()
    return DEFAULT_RUNNER.parents[2] / "local_data" / "dashboard_projects" / "0_study_project_registry" / f"profile_{PROFILE_ID}"


def _close_open_runners(commands_dir: Path) -> dict[str, Any]:
    script = (
        "$ErrorActionPreference='SilentlyContinue'; "
        "$procs=Get-Process PPSExperimentRunner; "
        "$ids=@($procs | ForEach-Object { $_.Id }); "
        "$procs | ForEach-Object { if ($_.MainWindowHandle -ne 0) { [void]$_.CloseMainWindow() } }; "
        "Start-Sleep -Milliseconds 800; "
        "$remaining=Get-Process PPSExperimentRunner; "
        "$remaining | Stop-Process -Force; "
        "[pscustomobject]@{closed=($ids -join ','); remaining=(($remaining | ForEach-Object { $_.Id }) -join ',')} | ConvertTo-Json -Compress"
    )
    result = _run_command(
        "close_open_runner_windows",
        ["powershell", "-NoProfile", "-Command", script],
        commands_dir=commands_dir,
        timeout_s=30,
    )
    result["passed"] = True
    return result


def _run_command(
    name: str,
    argv: list[str],
    *,
    commands_dir: Path,
    timeout_s: float,
) -> dict[str, Any]:
    commands_dir.mkdir(parents=True, exist_ok=True)
    slug = _slug(name)
    stdout_path = commands_dir / f"{slug}.stdout.txt"
    stderr_path = commands_dir / f"{slug}.stderr.txt"
    meta_path = commands_dir / f"{slug}.command.json"
    started = time.time()
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout, stderr_path.open(
        "w", encoding="utf-8", errors="replace"
    ) as stderr:
        try:
            proc = subprocess.run(
                [str(item) for item in argv],
                cwd=REPO_ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
                timeout=float(timeout_s),
                check=False,
            )
            returncode: int | None = proc.returncode
            error = ""
        except subprocess.TimeoutExpired as exc:
            returncode = None
            error = f"timeout after {timeout_s}s: {exc}"
    elapsed = time.time() - started
    passed = returncode == 0 and not error
    payload = {
        "name": name,
        "argv": [str(item) for item in argv],
        "returncode": returncode,
        "passed": passed,
        "error": error,
        "elapsed_s": elapsed,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }
    meta_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _record_gate(gates: list[dict[str, Any]], name: str, category: str, result: dict[str, Any]) -> None:
    gates.append(
        {
            "name": name,
            "category": category,
            "passed": bool(result.get("passed")),
            "skipped": bool(result.get("skipped")),
            **result,
        }
    )


def _finalize(output_dir: Path, gates: list[dict[str, Any]], evidence: dict[str, Any]) -> dict[str, Any]:
    required = [gate for gate in gates if not gate.get("skipped")]
    failed = [gate for gate in required if not gate.get("passed")]
    report = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo_root": str(REPO_ROOT),
        "passed": not failed and bool(required),
        "failed_gate": failed[0] if failed else {},
        "gate_count": len(gates),
        "passed_gate_count": sum(1 for gate in gates if gate.get("passed")),
        "gates": gates,
        "evidence": evidence,
        "output_dir": str(output_dir),
        "report_json": str(output_dir / "acceptance_summary.json"),
        "report_md": str(output_dir / "acceptance_summary.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    print(f"Wrote Study 5 acceptance summary: {report['report_json']}")
    return report


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Study 5 Full Acceptance Rehearsal",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Output dir: `{report.get('output_dir')}`",
        f"- Gates: `{report.get('passed_gate_count')}` / `{report.get('gate_count')}`",
        "",
    ]
    failed = report.get("failed_gate") or {}
    if failed:
        lines.extend(
            [
                "## Blocking Gate",
                "",
                f"- Name: `{failed.get('name')}`",
                f"- Category: `{failed.get('category')}`",
                f"- Stdout: `{failed.get('stdout_path', '')}`",
                f"- Stderr: `{failed.get('stderr_path', '')}`",
                f"- Detail: `{failed.get('detail') or failed.get('error') or failed.get('reason') or ''}`",
                "",
            ]
        )
    lines.extend(["## Gate Summary", ""])
    for gate in report.get("gates", []):
        status = "passed" if gate.get("passed") else "failed"
        if gate.get("skipped"):
            status = "skipped"
        lines.append(f"- `{gate.get('name')}` ({gate.get('category')}): `{status}`")
    evidence = report.get("evidence") or {}
    full = evidence.get("full_rehearsal") or {}
    if full:
        lines.extend(
            [
                "",
                "## Full Rehearsal Evidence",
                "",
                f"- Environment root: `{full.get('environment_root', '')}`",
                f"- Validation dir: `{full.get('validation_dir', '')}`",
                f"- Session manifest: `{full.get('session_manifest', '')}`",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _latest_report(root: Path, filename: str) -> Path:
    matches = [path for path in Path(root).rglob(filename) if _path_exists(path)]
    if not matches:
        return Path()
    return max(matches, key=lambda path: os.path.getmtime(_filesystem_path(path))).resolve()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with open(_filesystem_path(path), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


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


def _resolve_path(value: Any, *, base: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return Path()
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if sys.platform == "win32" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _path_exists(path: str | Path) -> bool:
    try:
        return os.path.exists(_filesystem_path(path))
    except OSError:
        return False


def _is_dir(path: str | Path) -> bool:
    try:
        return os.path.isdir(_filesystem_path(path))
    except OSError:
        return False


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_") or "command"


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_acceptance(args)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
