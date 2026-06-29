"""Validate Android phone-owned LSL runtime status artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.lsl_command_ack import (  # noqa: E402
    ACK_SCHEMA,
    COMMAND_SCHEMA,
    LSL_ACK_CHANNELS,
    LSL_ACK_STREAM_NAME,
    LSL_COMMAND_CHANNELS,
    LSL_COMMAND_STREAM_NAME,
)


ANDROID_LSL_RUNTIME_STATUS_SCHEMA = "pps-android-lsl-runtime-status.v1"
EXPECTED_STREAMS = {
    "rich_markers": "PPSMarkersV2",
    "numeric_triggers": "PPSTriggerCodes",
    "command_signals": LSL_COMMAND_STREAM_NAME,
    "command_acks": LSL_ACK_STREAM_NAME,
}


@dataclass(frozen=True)
class AndroidLslValidationResult:
    ok: bool
    source_path: str
    status: dict[str, Any]
    failures: list[str]
    warnings: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "pps-android-lsl-runtime-artifact-validation.v1",
            "ok": self.ok,
            "source_path": self.source_path,
            "failures": self.failures,
            "warnings": self.warnings,
            "status": self.status,
        }


def validate_runtime_status(
    status: dict[str, Any],
    *,
    source_path: str = "",
    completion: dict[str, Any] | None = None,
    expect_native_transport: bool = False,
) -> AndroidLslValidationResult:
    failures: list[str] = []
    warnings: list[str] = []
    if status.get("schema") != ANDROID_LSL_RUNTIME_STATUS_SCHEMA:
        failures.append("lsl_runtime_status schema mismatch")

    streams = status.get("streams") if isinstance(status.get("streams"), dict) else {}
    for key, expected in EXPECTED_STREAMS.items():
        if streams.get(key) != expected:
            failures.append(f"stream {key} expected {expected!r}, got {streams.get(key)!r}")

    protocol = status.get("command_protocol") if isinstance(status.get("command_protocol"), dict) else {}
    if protocol.get("command_schema") != COMMAND_SCHEMA:
        failures.append("command schema does not match PC runner protocol")
    if protocol.get("ack_schema") != ACK_SCHEMA:
        failures.append("ack schema does not match PC runner protocol")
    if list(protocol.get("command_channels") or []) != list(LSL_COMMAND_CHANNELS):
        failures.append("command channel order does not match PC runner protocol")
    if list(protocol.get("ack_channels") or []) != list(LSL_ACK_CHANNELS):
        failures.append("ack channel order does not match PC runner protocol")
    if protocol.get("token_required") is not True:
        failures.append("command protocol must require the pairing token")

    privacy = status.get("privacy") if isinstance(status.get("privacy"), dict) else {}
    if privacy.get("demographics_in_stream_name") is not False:
        failures.append("participant demographics must not be encoded in discoverable stream names")

    native_available = bool(status.get("native_transport_available"))
    receiver_available = bool(status.get("command_receiver_available"))
    if expect_native_transport:
        if not native_available:
            failures.append("native Android LSL transport was expected but is not available")
        if not receiver_available:
            failures.append("native command receiver was expected but is not available")
    elif native_available:
        warnings.append("native Android LSL transport is marked available; rerun with --expect-native-transport for strict checks")
    elif not str(status.get("reason") or "").strip():
        failures.append("missing reason for unavailable native Android LSL transport")

    if completion:
        embedded = completion.get("lsl_runtime_status")
        if isinstance(embedded, dict):
            if embedded.get("schema") != status.get("schema"):
                failures.append("completion.json embedded LSL status schema differs from lsl_runtime_status.json")
            embedded_streams = embedded.get("streams") if isinstance(embedded.get("streams"), dict) else {}
            if embedded_streams and embedded_streams != streams:
                failures.append("completion.json embedded LSL streams differ from lsl_runtime_status.json")
        else:
            warnings.append("completion/latest-events artifact does not embed lsl_runtime_status")

    return AndroidLslValidationResult(
        ok=not failures,
        source_path=source_path,
        status=status,
        failures=failures,
        warnings=warnings,
    )


def validate_run_artifact(path: Path, *, expect_native_transport: bool = False) -> AndroidLslValidationResult:
    loaded = _load_status_inputs(path)
    return validate_runtime_status(
        loaded["status"],
        source_path=str(path),
        completion=loaded.get("completion"),
        expect_native_transport=expect_native_transport,
    )


def _load_status_inputs(path: Path) -> dict[str, Any]:
    if path.is_dir():
        status_path = path / "lsl_runtime_status.json"
        if not status_path.is_file():
            raise FileNotFoundError(f"Missing {status_path}")
        completion_path = path / "completion.json"
        if not completion_path.is_file():
            completion_path = path / "latest_events.json"
        return {
            "status": _read_json(status_path),
            "completion": _read_json(completion_path) if completion_path.is_file() else None,
        }
    if path.suffix.lower() == ".zip":
        return _load_from_zip(path)
    data = _read_json(path)
    if data.get("schema") == ANDROID_LSL_RUNTIME_STATUS_SCHEMA:
        return {"status": data, "completion": None}
    embedded = data.get("lsl_runtime_status")
    if isinstance(embedded, dict):
        return {"status": embedded, "completion": data}
    raise ValueError(f"{path} is not an Android LSL status or completion artifact")


def _load_from_zip(path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pps-android-lsl-") as temp_dir:
        temp_root = Path(temp_dir)
        with zipfile.ZipFile(path) as archive:
            status_members = [name for name in archive.namelist() if name.endswith("lsl_runtime_status.json")]
            if not status_members:
                raise FileNotFoundError("ZIP does not contain lsl_runtime_status.json")
            status_name = sorted(status_members)[0]
            completion_members = [
                name for name in archive.namelist() if name.endswith("completion.json") or name.endswith("latest_events.json")
            ]
            archive.extract(status_name, temp_root)
            completion = None
            if completion_members:
                completion_name = sorted(completion_members)[0]
                archive.extract(completion_name, temp_root)
                completion = _read_json(temp_root / completion_name)
            return {"status": _read_json(temp_root / status_name), "completion": completion}


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def _write_report(result: AndroidLslValidationResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_json = output_dir / "android_lsl_runtime_artifact_validation.json"
    report_md = output_dir / "android_lsl_runtime_artifact_validation.md"
    report_json.write_text(json.dumps(result.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Android LSL Runtime Artifact Validation",
        "",
        f"- Source: `{result.source_path}`",
        f"- Result: `{'PASS' if result.ok else 'FAIL'}`",
        f"- Native transport available: `{bool(result.status.get('native_transport_available'))}`",
        f"- Command receiver available: `{bool(result.status.get('command_receiver_available'))}`",
        f"- Current Android source behavior: `{result.status.get('current_android_source_behavior', '')}`",
        "",
    ]
    if result.failures:
        lines.extend(["## Failures", *[f"- {item}" for item in result.failures], ""])
    if result.warnings:
        lines.extend(["## Warnings", *[f"- {item}" for item in result.warnings], ""])
    report_md.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path, help="Phone run folder, ZIP, completion JSON, or lsl_runtime_status.json.")
    parser.add_argument("--expect-native-transport", action="store_true", help="Fail unless native Android LSL transport is active.")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for JSON/Markdown validation reports.")
    args = parser.parse_args(argv)

    result = validate_run_artifact(args.artifact, expect_native_transport=args.expect_native_transport)
    if args.output_dir:
        _write_report(result, args.output_dir)
    print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
