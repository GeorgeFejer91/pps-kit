"""Run a local LSL command/ack round-trip validation.

This script creates a command outlet and an acknowledgement outlet in the same
process, resolves both through liblsl, sends commands, applies them in a receiver
thread, and verifies that an applied ack returns for every command id.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import sys
import threading
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.lsl_command_ack import (  # noqa: E402
    LSLCommandAckInlet,
    LSLCommandAckOutlet,
    LSLCommandAckServer,
    LSLCommandInlet,
    LSLCommandOutlet,
)


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "artifacts" / "validation_runs" / f"lsl_command_ack_roundtrip_{stamp}"


def _stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean_ms": None, "median_ms": None, "max_ms": None}
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values),
        "median_ms": statistics.median(values),
        "max_ms": max(values),
    }


def run_roundtrip(*, output_dir: Path, count: int, timeout_s: float) -> dict[str, Any]:
    session_id = f"lsl_ack_{time.strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    command_outlet = LSLCommandOutlet(session_id=session_id, sender_id="sender")
    ack_outlet = LSLCommandAckOutlet(session_id=session_id, receiver_id="runner")

    # Give liblsl discovery a brief head start before resolving the matching
    # inlets.  The streams are long-lived after this point; no per-command
    # resolve happens in the latency path.
    time.sleep(0.25)
    command_inlet = LSLCommandInlet.resolve(source_id=command_outlet.source_id, timeout_s=timeout_s)
    ack_inlet = LSLCommandAckInlet.resolve(source_id=ack_outlet.source_id, timeout_s=timeout_s)
    command_outlet.wait_for_consumers(timeout_s=timeout_s)
    ack_outlet.wait_for_consumers(timeout_s=timeout_s)

    stop_event = threading.Event()
    applied: list[str] = []

    def _handler(signal):
        applied.append(signal.command_id)
        return {
            "status": "applied",
            "payload": {
                "applied_order": len(applied),
                "command": signal.command,
                "part_number": signal.payload.get("part_number", ""),
            },
        }

    server = LSLCommandAckServer(command_inlet=command_inlet, ack_outlet=ack_outlet, handler=_handler)

    def _serve() -> None:
        while not stop_event.is_set():
            server.poll_once(timeout_s=0.01)

    thread = threading.Thread(target=_serve, name="pps-lsl-command-ack-validation", daemon=True)
    thread.start()

    records: list[dict[str, Any]] = []
    try:
        for index in range(1, count + 1):
            before_send = command_outlet.local_clock()
            signal = command_outlet.send("start_part", payload={"part_number": 1, "index": index})
            ack = ack_inlet.wait_for(signal.command_id, timeout_s=timeout_s)
            observed_ack = command_outlet.local_clock()
            records.append(
                {
                    "index": index,
                    "command_id": signal.command_id,
                    "command": signal.command,
                    "ack_status": "" if ack is None else ack.status,
                    "issued_lsl_time": signal.issued_lsl_time,
                    "sender_before_send_lsl_time": before_send,
                    "sender_observed_ack_lsl_time": observed_ack,
                    "received_lsl_time": "" if ack is None else ack.received_lsl_time,
                    "applied_lsl_time": "" if ack is None else ack.applied_lsl_time,
                    "ack_lsl_time": "" if ack is None else ack.ack_lsl_time,
                    "sender_roundtrip_ms": (observed_ack - signal.issued_lsl_time) * 1000.0,
                    "receiver_receive_delay_ms": "" if ack is None else (ack.received_lsl_time - signal.issued_lsl_time) * 1000.0,
                    "receiver_apply_duration_ms": "" if ack is None else (ack.applied_lsl_time - ack.received_lsl_time) * 1000.0,
                    "ack_emit_after_apply_ms": "" if ack is None else (ack.ack_lsl_time - ack.applied_lsl_time) * 1000.0,
                }
            )
    finally:
        stop_event.set()
        thread.join(timeout=1.0)
        command_inlet.close()
        ack_inlet.close()

    missing = [row["command_id"] for row in records if row["ack_status"] != "applied"]
    roundtrip = [float(row["sender_roundtrip_ms"]) for row in records if row["ack_status"] == "applied"]
    receive_delay = [float(row["receiver_receive_delay_ms"]) for row in records if row["ack_status"] == "applied"]
    apply_duration = [float(row["receiver_apply_duration_ms"]) for row in records if row["ack_status"] == "applied"]
    ack_after_apply = [float(row["ack_emit_after_apply_ms"]) for row in records if row["ack_status"] == "applied"]
    report = {
        "schema": "pps-lsl-command-ack-roundtrip-report.v1",
        "passed": not missing and len(records) == count,
        "session_id": session_id,
        "command_source_id": command_outlet.source_id,
        "ack_source_id": ack_outlet.source_id,
        "expected_count": count,
        "applied_ack_count": len(records) - len(missing),
        "missing_ack_command_ids": missing,
        "latency": {
            "sender_roundtrip": _stats(roundtrip),
            "receiver_receive_delay": _stats(receive_delay),
            "receiver_apply_duration": _stats(apply_duration),
            "ack_emit_after_apply": _stats(ack_after_apply),
        },
        "records": records,
        "notes": [
            "Streams are resolved before sending; the per-command path only pushes one command sample and one ack sample.",
            "The ack is emitted after the receiver handler returns, so it confirms the local state transition rather than mere packet receipt.",
            "This validates LSL sender/receiver handshake mechanics, not physical hardware output timing.",
        ],
    }
    report_path = output_dir / "lsl_command_ack_roundtrip_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path = output_dir / "lsl_command_ack_roundtrip_report.md"
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return report


def _markdown(report: dict[str, Any]) -> str:
    latency = report.get("latency") or {}
    return "\n".join(
        [
            "# LSL Command/Ack Round Trip",
            "",
            f"- Passed: `{report.get('passed')}`",
            f"- Applied acks: `{report.get('applied_ack_count')}/{report.get('expected_count')}`",
            f"- Command source: `{report.get('command_source_id')}`",
            f"- Ack source: `{report.get('ack_source_id')}`",
            f"- Sender roundtrip: `{json.dumps(latency.get('sender_roundtrip') or {}, sort_keys=True)}`",
            f"- Receiver receive delay: `{json.dumps(latency.get('receiver_receive_delay') or {}, sort_keys=True)}`",
            f"- Receiver apply duration: `{json.dumps(latency.get('receiver_apply_duration') or {}, sort_keys=True)}`",
            f"- Ack emit after apply: `{json.dumps(latency.get('ack_emit_after_apply') or {}, sort_keys=True)}`",
            "",
            "The ack is an application-level confirmation sent over LSL after the receiver handler returns.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate local LSL command/ack round-trip behavior.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--timeout-s", type=float, default=5.0)
    args = parser.parse_args()
    output_dir = args.output_dir or _default_output_dir()
    report = run_roundtrip(output_dir=output_dir, count=max(1, int(args.count)), timeout_s=max(0.1, float(args.timeout_s)))
    print(json.dumps({"passed": report["passed"], "output_dir": str(output_dir), "latency": report["latency"]}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
