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


def _group_file(directory: Path, name: Any, suffix: str) -> Path:
    _require(isinstance(name, str) and bool(name) and not re.search(r"[\\:\x00-\x1f]", name)
             and not name.startswith("/") and all(part not in ("", ".", "..") for part in name.split("/"))
             and name.endswith(suffix) and ".partial." not in name, "invalid group result filename")
    path = (directory / name).resolve(strict=True)
    _require(path.is_relative_to(directory) and path.is_file(), "group result leaves its native directory")
    return path


def validate_group(manifest_path: Path, *, expected_group_sha256: str | None = None) -> dict[str, Any]:
    """Join both exact native attempts; never infer completion from two loose CSVs."""
    manifest_path = manifest_path.resolve(strict=True)
    group = json.loads(_bounded_bytes(manifest_path, 256 * 1024))
    attempt = group.get("groupAttemptId")
    _require(isinstance(attempt, str) and re.fullmatch(r"[A-Za-z0-9_-]{32}", attempt) is not None
             and manifest_path.name == f"native_group_{attempt}.results.json", "invalid group attempt identity")
    _require(group.get("schema") == "pps.native-group-results.v1" and group.get("completion") == "complete"
             and group.get("timingQualification") == "unqualified", "group has no complete native commit manifest")
    root = manifest_path.parent
    source_path = _group_file(root, group["selectedGroupManifestFile"], ".json")
    _require(source_path.parent == root, "selected group manifest must be beside its result")
    source_bytes = _bounded_bytes(source_path, 8 * 1024 * 1024)
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    _require(source_hash == group["selectedGroupManifestSha256"], "selected group manifest changed")
    if expected_group_sha256 is not None:
        _require(source_hash == expected_group_sha256, "result belongs to another group")
    source = json.loads(source_bytes)
    _require(source.get("schema") == "pps-run-session-group.v1"
             and source.get("part_split_schema") == "pps-runner-part-split.v1"
             and source.get("experiment_structure") == "pre_post" and source.get("parts_per_participant") == 2,
             "unsupported selected group")
    parts, selected_parts = group["parts"], source["parts"]
    _require(isinstance(parts, list) and isinstance(selected_parts, list)
             and len(parts) == len(selected_parts) == 2, "both ordered parts are required")
    identities, packages, result_files, reports = set(), set(), set(), []
    for number, (part, selected) in enumerate(zip(parts, selected_parts), 1):
        _require(type(part.get("partNumber")) is int and part["partNumber"] == number
                 and type(selected.get("part_number")) is int and selected["part_number"] == number,
                 "group part order changed")
        identity = part["partSessionId"]
        _require(isinstance(identity, str) and bool(identity) and identity not in identities
                 and identity == selected["part_session_id"], "group part identity changed")
        identities.add(identity)
        package_path = _group_file(root, part["packageManifestFile"], ".json")
        declared = Path(selected["session_manifest_path"])
        if not declared.is_absolute():
            declared = root / declared
        # Windows may serialize the same native file with a verbatim/short path.
        # Compare filesystem identity after the receipt path's containment check.
        _require(declared.samefile(package_path) and package_path not in packages,
                 "group package selection changed")
        packages.add(package_path)
        package_bytes = _bounded_bytes(package_path, 8 * 1024 * 1024)
        package_hash = hashlib.sha256(package_bytes).hexdigest()
        package = json.loads(package_bytes)
        _require(type(package.get("part_number")) is int and package["part_number"] == number
                 and package.get("part_session_id") == identity
                 and package.get("participant_id") == source["participant_id"], "group package identity changed")
        result_path = _group_file(root, part["resultManifestFile"], ".results.json")
        _require(result_path.parent == package_path.parent and result_path not in result_files,
                 "group result belongs to another part directory")
        result_files.add(result_path)
        result_bytes = _bounded_bytes(result_path, 256 * 1024)
        _require(hashlib.sha256(result_bytes).hexdigest() == part["resultManifestSha256"], "part result manifest changed")
        result = json.loads(result_bytes)
        _require(result["receipt"] == part["receipt"] and part["receipt"]["packageManifestSha256"] == package_hash,
                 "group part receipt changed")
        _require(result["identity"].get("groupAttemptId") == attempt
                 and result["identity"].get("selectedGroupManifestSha256") == source_hash
                 and result["identity"].get("partNumber") == number
                 and result["identity"].get("partSessionId") == identity
                 and result["identity"].get("participantId") == source["participant_id"], "part belongs to another group attempt")
        events_path = _group_file(root, part["eventsFile"], ".jsonl")
        dataset_path = _group_file(root, part["datasetFile"], ".csv")
        _require(events_path == _result_file(result_path.parent, result["eventsFile"], ".jsonl")
                 and dataset_path == _result_file(result_path.parent, result["datasetFile"], ".csv"),
                 "group event/dataset selection changed")
        with events_path.open("rb") as handle:
            header_bytes = handle.readline(256 * 1024 + 1)
        _require(len(header_bytes) <= 256 * 1024 and header_bytes.endswith(b"\n"), "invalid group event header")
        header = json.loads(header_bytes)
        _require(header.get("groupAttemptId") == attempt
                 and header.get("selectedGroupManifestSha256") == source_hash, "event belongs to another group attempt")
        blocks = package["blocks"]
        _require(isinstance(blocks, list) and bool(blocks)
                 and all(type(block.get("trial_count")) is int and block["trial_count"] > 0 for block in blocks),
                 "invalid selected part trial inventory")
        _require(sum(block["trial_count"] for block in blocks) == part["receipt"]["scoredTrialCount"],
                 "part result omits selected trials")
        reports.append(validate(result_path, expected_package_sha256=package_hash))
    return {"schema": "pps.native-group-result-file-audit.v1", "passed": True,
            "evidence": "file-contract-only", "timingQualification": "unqualified", "partCount": 2,
            **{key: sum(report[key] for report in reports)
               for key in ("eventRecordCount", "scoredTrialCount", "datasetRowCount")}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--package-sha256", help="Expected verified package manifest digest")
    parser.add_argument("--group", action="store_true", help="Audit a published native group result and both exact part attempts")
    parser.add_argument("--group-sha256", help="Expected verified session group manifest digest")
    args = parser.parse_args()
    if args.group and args.package_sha256:
        parser.error("--group requires --group-sha256, not --package-sha256")
    if not args.group and args.group_sha256:
        parser.error("--group-sha256 requires --group")
    try:
        if args.group:
            result = validate_group(args.manifest, expected_group_sha256=args.group_sha256)
        else:
            result = validate(args.manifest, expected_package_sha256=args.package_sha256)
    except (ValueError, OSError, KeyError, TypeError) as error:
        # Keep private identities, file contents and absolute paths out of logs.
        print(json.dumps({"passed": False, "evidence": "file-contract-only", "errorType": type(error).__name__,
                          "reason": str(error) if isinstance(error, ValueError) else "Result is unreadable or malformed"}))
        raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
