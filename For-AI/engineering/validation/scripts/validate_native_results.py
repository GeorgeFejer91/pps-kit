"""Independently audit native result files against the V1 Data_min contract.

This is file evidence only: it supplies no installed, participant, device,
physical timing, or replication qualification. It never modifies a result.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT / "packages" / "pps-runtime" / "src"))
from peripersonal_space_toolkit import session_runner as oracle  # noqa: E402

MAX_BYTES = 32 * 1024 * 1024


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _bounded_bytes(path: Path, maximum: int) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    _require(len(data) <= maximum, "result exceeds the file budget")
    return data


def _result_file(directory: Path, name: Any, suffix: str) -> Path:
    _require(isinstance(name, str) and bool(name) and not re.search(r"[\\/:\x00]", name)
             and name.endswith(suffix) and ".partial." not in name, "invalid published filename")
    path = (directory / name).resolve(strict=True)
    _require(path.parent == directory and path.is_file(), "result leaves its native directory")
    return path


def validate(manifest_path: Path, *, expected_package_sha256: str | None = None) -> dict[str, Any]:
    _require(manifest_path.name.endswith(".results.json"), "a published result manifest is required")
    manifest_path = manifest_path.resolve(strict=True)
    manifest = json.loads(_bounded_bytes(manifest_path, 256 * 1024))
    _require(manifest.get("schema") == "pps.native-results.v1" and manifest.get("completion") == "complete",
             "result has no complete native commit manifest")
    _require(manifest.get("timingQualification") == "unqualified"
             and manifest.get("audioEvidence") == "software-frame-submission", "unsupported timing evidence claim")
    receipt = manifest["receipt"]
    for key in ["packageGeneration", "runGeneration", "firstEventSequence", "lastEventSequence",
                "eventRecordCount", "scoredTrialCount", "datasetRowCount"]:
        _require(type(receipt.get(key)) is int and receipt[key] >= 0, "invalid receipt counter")
    for key in ["packageManifestSha256", "eventsSha256", "datasetSha256"]:
        _require(isinstance(receipt.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", receipt[key]) is not None,
                 "invalid receipt digest")
    if expected_package_sha256 is not None:
        _require(receipt["packageManifestSha256"] == expected_package_sha256, "result belongs to another package")
    events_path = _result_file(manifest_path.parent, manifest["eventsFile"], ".jsonl")
    dataset_path = _result_file(manifest_path.parent, manifest["datasetFile"], ".csv")
    event_bytes = _bounded_bytes(events_path, MAX_BYTES)
    csv_bytes = _bounded_bytes(dataset_path, MAX_BYTES - len(event_bytes))
    _require(hashlib.sha256(event_bytes).hexdigest() == receipt["eventsSha256"], "event bytes changed")
    _require(hashlib.sha256(csv_bytes).hexdigest() == receipt["datasetSha256"], "dataset bytes changed")
    _require(event_bytes.endswith(b"\n"), "incomplete event record")
    lines = event_bytes.decode("utf-8").split("\n")[:-1]
    _require(bool(lines), "missing event header")
    header = json.loads(lines[0])
    _require(header.get("schema") == "pps.native-event-journal.v1"
             and header.get("packageManifestSha256") == receipt["packageManifestSha256"], "event package mismatch")
    identity = manifest["identity"]
    _require(all(identity.get(key) == header.get(key) for key in
                 ["participantId", "sessionId", "partSessionId", "partNumber", "executionMode"]), "result identity mismatch")
    events = [json.loads(line) for line in lines[1:]]
    first, last = receipt["firstEventSequence"], receipt["lastEventSequence"]
    _require(first > 0 and last >= first and len(events) == receipt["eventRecordCount"] == last - first + 1,
             "event prefix count mismatch")
    _require(all(type(event.get("sequence")) is int for event in events)
             and [event["sequence"] for event in events] == list(range(first, last + 1)), "event sequence gap")
    _require(not any(event["eventType"] == "trial.interrupted" for event in events), "result contains an interrupted trial")
    _require(any(event["eventType"] == "audio.final-frame-submitted" for event in events), "missing native frame submission evidence")
    tail = events[-1]
    _require(tail["eventType"] == "native.results.finalization-requested"
             and all(tail["payload"].get(key) == receipt[key] for key in ["packageGeneration", "runGeneration"])
             and tail["payload"].get("expectedScoredTrials") == receipt["scoredTrialCount"], "result has no matching finalization intent")
    scored = [event["payload"] for event in events if event["eventType"] == "trial.scored"]
    _require(bool(scored) and len(scored) == receipt["scoredTrialCount"], "scored trial count mismatch")
    rows = []
    for row in scored:
        if not oracle._is_data_min_filler_or_debug(row):
            rows.append(oracle._data_min_row_from_rich(row, trial_number_global=len(rows) + 1))
    projected = io.StringIO(newline="")
    writer = csv.DictWriter(projected, fieldnames=oracle.DATA_MIN_FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)
    _require(projected.getvalue().encode("utf-8") == csv_bytes, "CSV differs from the V1 event projection")
    _require(len(rows) == receipt["datasetRowCount"], "dataset row count mismatch")
    return {"schema": "pps.native-result-file-audit.v1", "passed": True, "evidence": "file-contract-only",
            "timingQualification": "unqualified", "eventRecordCount": len(events),
            "scoredTrialCount": len(scored), "datasetRowCount": len(rows)}


def validate_group(group_manifest_path: Path) -> dict[str, Any]:
    """Derive split-session completion from both native commit manifests."""
    _require(group_manifest_path.name == "session_group_manifest.json", "a session group manifest is required")
    group_manifest_path = group_manifest_path.resolve(strict=True)
    group = json.loads(_bounded_bytes(group_manifest_path, 256 * 1024))
    _require(isinstance(group, dict), "invalid split session group")
    parts = group.get("parts")
    _require(group.get("schema") == "pps-run-session-group.v1"
             and group.get("part_split_schema") == "pps-runner-part-split.v1"
             and group.get("parts_per_participant") == 2
             and isinstance(parts, list) and len(parts) == 2
             and isinstance(group.get("session_group_id"), str) and bool(group["session_group_id"])
             and isinstance(group.get("participant_id"), str) and bool(group["participant_id"])
             and isinstance(group.get("source_run_setup_sha256"), str)
             and re.fullmatch(r"[0-9a-f]{64}", group["source_run_setup_sha256"]) is not None,
             "invalid split session group")
    totals = {"eventRecordCount": 0, "scoredTrialCount": 0, "datasetRowCount": 0}
    for number, part in enumerate(parts, 1):
        folder = f"part_{number:02}"
        _require(isinstance(part, dict) and type(part.get("part_number")) is int
                 and part["part_number"] == number
                 and part.get("part_folder_name") == folder
                 and isinstance(part.get("part_session_id"), str) and bool(part["part_session_id"]),
                 "invalid split part identity")
        part_dir = (group_manifest_path.parent / folder).resolve(strict=True)
        _require(part_dir.parent == group_manifest_path.parent and part_dir.is_dir(),
                 "split part leaves its session group")
        package_path = (part_dir / "session_manifest.json").resolve(strict=True)
        _require(package_path.parent == part_dir and package_path.is_file(),
                 "split package leaves its part directory")
        package_bytes = _bounded_bytes(package_path, 256 * 1024)
        package = json.loads(package_bytes)
        _require(isinstance(package, dict)
                 and package.get("schema") == "pps-run-session.v1"
                 and package.get("part_split_schema") == "pps-runner-part-split.v1"
                 and package.get("participant_id") == group["participant_id"]
                 and package.get("session_group_id") == group["session_group_id"]
                 and type(package.get("part_number")) is int and package["part_number"] == number
                 and package.get("part_folder_name") == folder
                 and package.get("part_session_id") == part["part_session_id"]
                 and package.get("source_run_setup_sha256") == group["source_run_setup_sha256"]
                 and isinstance(package.get("session_id"), str) and bool(package["session_id"])
                 and isinstance(package.get("execution_mode"), str) and bool(package["execution_mode"]),
                 "split package differs from its group")
        blocks = package.get("blocks")
        _require(isinstance(blocks, list) and bool(blocks)
                 and all(isinstance(block, dict) and type(block.get("trial_count")) is int
                         and block["trial_count"] > 0 for block in blocks),
                 "split package has no valid trial count")
        package_sha256 = hashlib.sha256(package_bytes).hexdigest()
        results = sorted(part_dir.glob("native_events_*.results.json"))
        _require(len(results) == 1 and re.fullmatch(r"native_events_[A-Za-z0-9_-]{32}\.results\.json", results[0].name)
                 is not None, "split part needs one unambiguous published native result")
        result_manifest = json.loads(_bounded_bytes(results[0], 256 * 1024))
        _require(isinstance(result_manifest, dict), "invalid native result")
        identity = result_manifest.get("identity", {})
        _require(isinstance(identity, dict)
                 and identity.get("participantId") == group["participant_id"]
                 and identity.get("sessionId") == package.get("session_id")
                 and identity.get("partSessionId") == part["part_session_id"]
                 and identity.get("partNumber") == number
                 and identity.get("executionMode") == package.get("execution_mode"),
                 "native result differs from its split package")
        audit = validate(results[0], expected_package_sha256=package_sha256)
        _require(audit["scoredTrialCount"] == sum(block["trial_count"] for block in blocks),
                 "native result trial count differs from its split package")
        for key in totals:
            totals[key] += audit[key]
    return {"schema": "pps.native-group-result-file-audit.v1", "passed": True,
            "evidence": "file-contract-only", "timingQualification": "unqualified",
            "sessionGroupComplete": True, "partCount": 2, **totals}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument("--group-manifest", type=Path, help="Audit a completed two-part native session")
    parser.add_argument("--package-sha256", help="Expected verified package manifest digest")
    args = parser.parse_args()
    if bool(args.manifest) == bool(args.group_manifest) or (args.group_manifest and args.package_sha256):
        parser.error("provide one result manifest or --group-manifest; --package-sha256 applies to one result")
    try:
        result = (validate_group(args.group_manifest) if args.group_manifest else
                  validate(args.manifest, expected_package_sha256=args.package_sha256))
    except (ValueError, OSError, KeyError, TypeError) as error:
        # Keep private identities, file contents and absolute paths out of logs.
        print(json.dumps({"passed": False, "evidence": "file-contract-only", "errorType": type(error).__name__,
                          "reason": str(error) if isinstance(error, ValueError) else "Result is unreadable or malformed"}))
        raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
